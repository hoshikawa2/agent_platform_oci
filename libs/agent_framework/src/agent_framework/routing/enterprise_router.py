from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from .config_loader import load_intents, load_router_defaults, load_state_policies
from .continuity import SemanticRouteContinuity
from .models import IntentDefinition, RouteDecision, RouterStatePolicy

logger = logging.getLogger("agent_framework.routing")


class EnterpriseRouter:
    """Roteador enterprise para múltiplos agentes.

    Ordem de decisão:
    1. Política de estado da sessão/workflow.
    2. Classificação determinística por keywords e prioridade.
    3. Classificação via LLM, se habilitada.
    4. Fallback configurável.

    Isso evita o erro comum de rotear apenas por última mensagem. Em conversas
    longas, mensagens como "sim", "não", "pode fazer" dependem do estado.
    """

    def __init__(self, settings, llm=None, telemetry=None):
        self.settings = settings
        self.llm = llm
        self.telemetry = telemetry
        self.config_path = settings.ROUTING_CONFIG_PATH
        self.intents: list[IntentDefinition] = load_intents(self.config_path)
        self.state_policies: list[RouterStatePolicy] = load_state_policies(self.config_path)
        self.defaults = load_router_defaults(self.config_path)
        self.fallback_agent = self.defaults.get("fallback_agent", "billing_agent")
        self.intent_shift_threshold = float(self.defaults.get("confidence_threshold", 0.7))
        self.enable_llm_router = bool(getattr(settings, "ENABLE_LLM_ROUTER", False))
        self.continuity = SemanticRouteContinuity(settings, llm, telemetry)
        logger.info(
            "EnterpriseRouter carregado intents=%s state_policies=%s llm_router=%s fallback=%s",
            len(self.intents),
            len(self.state_policies),
            self.enable_llm_router,
            self.fallback_agent,
        )
        logger.info(
            "Semantic route stickiness enabled=%s profile=%s threshold=%s",
            self.continuity.enabled,
            self.continuity.profile_name,
            self.continuity.confidence_threshold,
        )

    async def route(self, state: dict[str, Any]) -> RouteDecision:
        session = (state.get("context") or {}).get("session", {}) or {}
        current_state = state.get("next_state") or session.get("metadata", {}).get("workflow_state")
        text = state.get("sanitized_input") or state.get("user_text") or ""

        # Estados transacionais preservam continuidade para respostas curtas
        # (parâmetros, "sim", "não"), mas NÃO podem aprisionar a sessão. Antes
        # de aplicar a política de estado, procuramos uma mudança explícita de
        # intenção. Se houver uma intent diferente com confiança suficiente, ela
        # vence o lock de estado e sinaliza ao runtime para encerrar a transação
        # pendente antes de executar a nova intent.
        state_decision = self._route_by_state(current_state)
        if state_decision:
            interruption = await self._transaction_state_interruption_candidate(
                state, text=str(text), state_decision=state_decision
            )
            if interruption is not None:
                await self._emit(interruption, state)
                return interruption
            await self._emit(state_decision, state)
            return state_decision

        # Mensagens que expressam de forma explícita uma intenção diferente da
        # intent/agente ativos devem prevalecer sobre a route stickiness. Isso
        # evita manter um fluxo read-only (por exemplo, tracking) quando o usuário
        # muda para uma ação transacional (por exemplo, devolução).
        keyword_candidate = self._route_by_keyword(text)
        active_agent = str(state.get("active_agent") or "").strip()
        previous = state.get("route_decision") or {}
        previous_intent = str(previous.get("intent") or state.get("intent") or "").strip()
        if (
            active_agent
            and keyword_candidate is not None
            and keyword_candidate.intent != previous_intent
            and self._is_explicit_intent_shift(keyword_candidate)
        ):
            keyword_candidate.metadata = {
                **(keyword_candidate.metadata or {}),
                "route_stickiness_preempted": True,
                "previous_agent": active_agent,
                "previous_intent": previous_intent,
            }
            await self._emit(keyword_candidate, state)
            return keyword_candidate

        decision = await self.continuity.evaluate(state, intents=self.intents)
        if decision:
            await self._emit(decision, state)
            return decision

        decision = self._route_by_keyword(text)
        if decision:
            await self._emit(decision, state)
            return decision

        if self.enable_llm_router and self.llm is not None:
            try:
                decision = await self._route_by_llm(text, state)
                await self._emit(decision, state)
                return decision
            except Exception as exc:
                logger.exception("Falha no roteamento por LLM; usando fallback: %s", exc)

        decision = RouteDecision(
            route=self.fallback_agent,
            agent=self.fallback_agent,
            intent="fallback",
            confidence=0.1,
            reason="Nenhuma intent determinística/LLM encontrada; usando fallback configurado.",
            method="fallback",
        )
        await self._emit(decision, state)
        return decision


    async def _transaction_state_interruption_candidate(
        self,
        state: dict[str, Any],
        *,
        text: str,
        state_decision: RouteDecision,
    ) -> RouteDecision | None:
        """Detecta uma nova intenção durante coleta/confirmação transacional.

        A política de estado continua protegendo respostas curtas/ambíguas. Uma
        interrupção só é aceita quando o roteador encontra uma intent diferente
        da transação ativa. Keywords explícitas são preferidas; na ausência delas,
        o LLM router pode decidir, desde que atinja o limiar configurado.

        O método não limpa o estado por conta própria. Ele marca a decisão com
        ``transaction_interruption=intent_shift`` para que o runtime feche o latch
        transacional de maneira centralizada e auditável.
        """
        active_tx = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
        started_intent = str(active_tx.get("started_from_intent") or "").strip()
        previous = state.get("route_decision") or {}
        previous_intent = str(previous.get("intent") or state.get("intent") or started_intent).strip()

        # Parameter answers have precedence over intent-shift detection.  A reply
        # such as ``R$ 71,99`` after the framework asked for ``valor`` is not a
        # new billing-explanation intent; it is the missing transaction argument.
        # Likewise, short entity-like replies (``TIM Music``) should remain in the
        # pending transaction.  Only clear question/action language is allowed to
        # escape to the router.
        missing = [str(x) for x in (state.get("missing_parameters") or []) if str(x).strip()]
        if missing and self._looks_like_pending_parameter_answer(text, missing):
            return None

        candidate = self._route_by_keyword(text)
        if candidate is not None:
            explicit = self._is_explicit_intent_shift(candidate)
            different = (
                candidate.agent != state_decision.agent
                or (started_intent and candidate.intent != started_intent)
                or (previous_intent and not previous_intent.startswith("state:") and candidate.intent != previous_intent)
            )
            if explicit and different:
                candidate.metadata = {
                    **(candidate.metadata or {}),
                    "transaction_interruption": "intent_shift",
                    "interrupted_state": state_decision.next_state,
                    "interrupted_agent": state_decision.agent,
                    "interrupted_intent": started_intent or previous_intent,
                }
                return candidate
            # Uma keyword reconhecida para a própria transação deve continuar
            # protegida pelo estado; não há necessidade de chamar o LLM.
            if not different:
                return None

        if not (self.enable_llm_router and self.llm is not None):
            return None
        try:
            candidate = await self._route_by_llm(text, state)
        except Exception as exc:
            logger.warning("Falha ao avaliar interrupção de estado transacional via LLM: %s", exc)
            return None

        different = (
            candidate.agent != state_decision.agent
            or (started_intent and candidate.intent != started_intent)
            or (previous_intent and not previous_intent.startswith("state:") and candidate.intent != previous_intent)
        )
        if not different or candidate.confidence < self.intent_shift_threshold:
            return None

        candidate.metadata = {
            **(candidate.metadata or {}),
            "transaction_interruption": "intent_shift",
            "interrupted_state": state_decision.next_state,
            "interrupted_agent": state_decision.agent,
            "interrupted_intent": started_intent or previous_intent,
        }
        return candidate

    @staticmethod
    def _looks_like_pending_parameter_answer(text: str, missing_parameters: list[str]) -> bool:
        """Return True when the current turn looks like an answer to a missing field.

        This is intentionally conservative: structured values are recognized by
        parameter semantics, while a short entity-like phrase is accepted only if
        it does not contain interrogative or explicit topic-shift language.
        """
        raw = str(text or "").strip()
        if not raw:
            return False
        normalized = unicodedata.normalize("NFKD", raw.lower())
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"\s+", " ", normalized).strip()
        names = {re.sub(r"[^a-z0-9_]+", "", str(x).lower()) for x in missing_parameters}

        # Explicit conversational shifts/questions must still escape the transaction.
        shift_tokens = (
            "quero ", "gostaria ", "preciso ", "me diga", "me informe", "mostre",
            "qual ", "quais ", "quando ", "onde ", "como ", "porque ", "por que ",
            "esquece", "esqueca", "mudei de assunto", "outra coisa", "voltar para",
            "cancelar ", "cancele ", "consultar ", "ver minha", "ver meu",
        )
        if "?" in raw or any(tok in normalized for tok in shift_tokens):
            return False

        # Common structured parameter families.
        if names & {"valor", "value", "amount", "price", "preco", "preço"}:
            if re.fullmatch(r"(?:r\$\s*)?[+-]?\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|(?:r\$\s*)?[+-]?\d+(?:[.,]\d{1,2})?", normalized, flags=re.I):
                return True
        if names & {"order_id", "pedido", "pedido_id", "invoice_id", "fatura_id", "protocol", "protocolo", "protocolo_id"}:
            if re.fullmatch(r"[a-z0-9._/-]{2,64}", normalized, flags=re.I):
                return True
        if names & {"data", "date", "due_date", "vencimento"}:
            if re.fullmatch(r"\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?", normalized):
                return True

        # A single short noun/entity phrase is usually the requested subject/reason.
        # Keep it in the transaction unless it contains clear routing language.
        words = re.findall(r"[a-z0-9$+.,/_-]+", normalized)
        if len(missing_parameters) == 1 and 1 <= len(words) <= 5:
            return True
        return False

    @staticmethod
    def _is_explicit_intent_shift(decision: RouteDecision) -> bool:
        """Retorna True para matches explícitos que devem vencer a stickiness.

        A regra é configurável porque usa a keyword já declarada no routing.yaml,
        sem listas linguísticas fixas no código. Keywords com quatro ou mais
        caracteres são tratadas como sinais explícitos de mudança de intenção.
        """
        matched = str((decision.metadata or {}).get("matched_keyword") or "").strip()
        return len(matched) >= 4

    def _route_by_state(self, current_state: str | None) -> RouteDecision | None:
        if not current_state:
            return None
        for policy in self.state_policies:
            if policy.state == current_state:
                return RouteDecision(
                    route=policy.agent,
                    agent=policy.agent,
                    intent=f"state:{policy.state}",
                    confidence=1.0,
                    reason=policy.description or f"Estado atual exige roteamento para {policy.agent}",
                    method="state",
                    next_state=policy.state,
                )
        return None

    @staticmethod
    def _keyword_tokens(value: str) -> list[str]:
        """Tokeniza texto para matching determinístico tolerante a palavras de ligação.

        A remoção de acentos evita duplicar regras apenas por variação ortográfica.
        Não há chamada de LLM neste caminho.
        """
        folded = unicodedata.normalize("NFKD", str(value or "").casefold())
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        return re.findall(r"[\w]+", folded, flags=re.UNICODE)

    @classmethod
    def _ordered_keyword_match(cls, keyword: str, text: str, *, max_gap: int = 3) -> bool:
        """Aceita uma keyword multi-token mesmo com poucos tokens inseridos.

        Ex.: ``cancelar pedido`` casa com ``quero cancelar meu pedido`` e
        ``cancelar o meu pedido``. O limite de gap mantém a regra conservadora e
        evita transformar o roteador determinístico em busca semântica ampla.
        Keywords de um único token continuam usando apenas o match exato legado.
        """
        wanted = cls._keyword_tokens(keyword)
        actual = cls._keyword_tokens(text)
        if len(wanted) < 2 or not actual:
            return False

        pos = -1
        for token in wanted:
            found = None
            upper = min(len(actual), pos + max_gap + 2)
            for idx in range(pos + 1, upper):
                if actual[idx] == token:
                    found = idx
                    break
            if found is None:
                return False
            pos = found
        return True

    @classmethod
    def _ordered_content_keyword_match(cls, keyword: str, text: str, *, max_gap: int = 4) -> bool:
        """Match determinístico tolerante à omissão de conectores curtos.

        Alguns ``routing.yaml`` usam frases naturais como ``qual é o meu plano``.
        A mesma intenção pode chegar como ``qual o meu plano``. O matcher legado
        falhava porque exigia também o token ``e`` (resultado da normalização de
        ``é``). Aqui tokens de até dois caracteres são tratados como conectores
        opcionais *apenas no lado da keyword*. Os tokens informativos continuam
        obrigatórios, em ordem e próximos entre si.

        A heurística é propositalmente linguística-neutra e não contém nomes de
        intents, agentes, domínios ou listas de verbos de negócio. Assim funciona
        com qualquer configuração carregada pelo ``routing.yaml`` sem LLM extra.
        """
        wanted_all = cls._keyword_tokens(keyword)
        actual = cls._keyword_tokens(text)
        if len(wanted_all) < 2 or not actual:
            return False

        wanted = [token for token in wanted_all if len(token) > 2]
        # Exigimos pelo menos dois tokens informativos para não transformar
        # keywords curtas em matches amplos demais.
        if len(wanted) < 2 or len(wanted) == len(wanted_all):
            return False

        pos = -1
        for token in wanted:
            found = None
            upper = min(len(actual), pos + max_gap + 2)
            for idx in range(pos + 1, upper):
                if actual[idx] == token:
                    found = idx
                    break
            if found is None:
                return False
            pos = found
        return True

    def _route_by_keyword(self, text: str) -> RouteDecision | None:
        normalized = text.casefold()
        matches: list[tuple[int, int, int, IntentDefinition, str, str]] = []
        for intent in self.intents:
            if not intent.enabled:
                continue
            for kw in intent.keywords:
                kw_normalized = kw.casefold()
                strategy = None
                # Exato primeiro para preservar o comportamento existente.
                if kw_normalized in normalized:
                    strategy = "exact"
                elif self._ordered_keyword_match(kw, text):
                    strategy = "ordered_tokens"
                elif self._ordered_content_keyword_match(kw, text):
                    strategy = "ordered_content_tokens"

                if strategy:
                    # menor priority vence; estratégias mais estritas vencem as relaxadas;
                    # keyword maior desempata dentro da mesma prioridade/estratégia.
                    strategy_rank = {
                        "exact": 0,
                        "ordered_tokens": 1,
                        "ordered_content_tokens": 2,
                    }[strategy]
                    matches.append((intent.priority, strategy_rank, -len(kw), intent, kw, strategy))
        if not matches:
            return None
        matches.sort(key=lambda x: (x[0], x[1], x[2]))
        _, _, _, intent, kw, strategy = matches[0]
        return RouteDecision(
            route=intent.agent,
            agent=intent.agent,
            intent=intent.name,
            confidence={
                "exact": 0.85,
                "ordered_tokens": 0.82,
                "ordered_content_tokens": 0.80,
            }[strategy],
            reason=(
                f"Keyword '{kw}' correspondeu à intent '{intent.name}'."
                if strategy == "exact"
                else (
                    f"Sequência de tokens da keyword '{kw}' correspondeu à intent '{intent.name}'."
                    if strategy == "ordered_tokens"
                    else f"Tokens informativos da keyword '{kw}' corresponderam à intent '{intent.name}'."
                )
            ),
            method="keyword",
            metadata={"matched_keyword": kw, "keyword_match_strategy": strategy},
            domain=intent.domain,
            mcp_tools=intent.mcp_tools,
        )

    async def _route_by_llm(self, text: str, state: dict[str, Any]) -> RouteDecision:
        allowed = [i for i in self.intents if i.enabled]
        allowed_payload = [
            {
                "intent": i.name,
                "agent": i.agent,
                "description": i.description,
                "examples": i.examples[:3],
                "mcp_tools": i.mcp_tools,
                "domain": i.domain,
            }
            for i in allowed
        ]
        system = (
            "Você é um roteador de intenções para uma plataforma de agentes. "
            "Classifique a mensagem do usuário em uma das intents permitidas. "
            "Retorne somente JSON válido com: intent, agent, confidence, reason. "
            "Não responda ao usuário final."
        )
        user = {
            "message": text,
            "allowed_intents": allowed_payload,
            "session_context": (state.get("context") or {}).get("session", {}),
        }
        answer = await self.llm.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=512,
            profile_name="router",
            component_name="router",
            generation_name="llm.router",
        )
        data = self._parse_json(answer)
        intent_name = str(data.get("intent") or "fallback")
        agent = str(data.get("agent") or self._agent_for_intent(intent_name) or self.fallback_agent)
        confidence = float(data.get("confidence") or 0.5)
        return RouteDecision(
            route=agent,
            agent=agent,
            intent=intent_name,
            confidence=confidence,
            reason=str(data.get("reason") or "Classificação via LLM."),
            method="llm",
            metadata={"raw_llm_answer": answer[:1000]},
            domain=self._domain_for_intent(intent_name),
            mcp_tools=self._tools_for_intent(intent_name),
        )

    def _agent_for_intent(self, intent_name: str) -> str | None:
        for intent in self.intents:
            if intent.name == intent_name:
                return intent.agent
        return None

    def _tools_for_intent(self, intent_name: str) -> list[str]:
        for intent in self.intents:
            if intent.name == intent_name:
                return intent.mcp_tools
        return []

    def _domain_for_intent(self, intent_name: str) -> str | None:
        for intent in self.intents:
            if intent.name == intent_name:
                return intent.domain
        return None

    def _parse_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            return json.loads(text)
        except Exception:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    async def _emit(self, decision: RouteDecision, state: dict[str, Any]) -> None:
        if self.telemetry:
            await self.telemetry.event(
                "router.decision",
                {
                    "session_id": state.get("session_id"),
                    "route": decision.route,
                    "intent": decision.intent,
                    "confidence": decision.confidence,
                    "method": decision.method,
                    "reason": decision.reason,
                    "domain": decision.domain,
                    "mcp_tools": decision.mcp_tools,
                },
            )
