from __future__ import annotations

import json
import logging
from typing import Any

from .config_loader import load_intents, load_router_defaults, load_state_policies
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
        self.enable_llm_router = bool(getattr(settings, "ENABLE_LLM_ROUTER", False))
        logger.info(
            "EnterpriseRouter carregado intents=%s state_policies=%s llm_router=%s fallback=%s",
            len(self.intents),
            len(self.state_policies),
            self.enable_llm_router,
            self.fallback_agent,
        )

    async def route(self, state: dict[str, Any]) -> RouteDecision:
        session = (state.get("context") or {}).get("session", {}) or {}
        current_state = state.get("next_state") or session.get("metadata", {}).get("workflow_state")
        text = state.get("sanitized_input") or state.get("user_text") or ""

        decision = self._route_by_state(current_state)
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

    def _route_by_keyword(self, text: str) -> RouteDecision | None:
        normalized = text.lower()
        matches: list[tuple[int, int, IntentDefinition, str]] = []
        for intent in self.intents:
            if not intent.enabled:
                continue
            for kw in intent.keywords:
                if kw.lower() in normalized:
                    # menor priority vence; maior tamanho da keyword desempata
                    matches.append((intent.priority, -len(kw), intent, kw))
        if not matches:
            return None
        matches.sort(key=lambda x: (x[0], x[1]))
        _, _, intent, kw = matches[0]
        return RouteDecision(
            route=intent.agent,
            agent=intent.agent,
            intent=intent.name,
            confidence=0.85,
            reason=f"Keyword '{kw}' correspondeu à intent '{intent.name}'.",
            method="keyword",
            metadata={"matched_keyword": kw},
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
