from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from .config_loader import load_intents, load_multi_intent_config, load_router_defaults, load_state_policies
from .multi_intent import MultiIntentPlanner
from .continuity import SemanticRouteContinuity
from .models import IntentDefinition, RouteDecision, RouterStatePolicy
from agent_framework.llm.structured_output import parse_json_object
from agent_framework.mcp.tool_policy import ToolPolicyRegistry
from agent_framework.runtime.transaction_parameters import extract_transaction_parameters, parse_transaction_confirmation
from agent_framework.workflows.input_contract import (
    expected_input_reprompt,
    has_semantic_classifier,
    match_expected_input,
    match_semantic_classifier_output,
    meaningful_unmatched_resume_value,
    semantic_coherence_from_guardrails,
)

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
        tool_policies = ToolPolicyRegistry(getattr(settings, "TOOL_POLICIES_PATH", None))
        transactional_tools = {
            name for name, policy in tool_policies.policies.items()
            if policy.operation_type == "transactional" or policy.require_confirmation
        }
        self.multi_intent_planner = MultiIntentPlanner(
            self.intents,
            load_multi_intent_config(self.config_path),
            transactional_tools=transactional_tools,
        )
        self.fallback_agent = self.defaults.get("fallback_agent", "billing_agent")
        self.intent_shift_threshold = float(self.defaults.get("confidence_threshold", 0.7))
        self.transaction_confirmation = dict(self.defaults.get("transaction_confirmation") or {})
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

    @staticmethod
    def _history_message_intent(item: dict[str, Any]) -> str:
        metadata = item.get("metadata") if isinstance(item, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        direct = str(metadata.get("intent") or "").strip()
        if direct:
            return direct
        decision = metadata.get("route_decision")
        if isinstance(decision, dict):
            return str(decision.get("intent") or "").strip()
        return ""

    @classmethod
    def _collect_relevant_conversation_context(
        cls,
        *,
        state: dict[str, Any],
        pending_workflow: dict[str, Any],
        current_text: str,
    ) -> str:
        """Return the contiguous conversational suffix relevant to the paused workflow.

        The preferred anchor is the user turn that produced the current PAUSED
        workflow state. From there we keep the contiguous conversation through the
        immediately preceding assistant prompt. For legacy checkpoints without an
        anchor id, we walk backwards and stop at the first assistant turn whose
        recorded intent differs from the workflow owner intent. Transaction state,
        snapshots and tool evidence are deliberately not injected here: this context
        is only for understanding unresolved conversational requests, never for
        treating user claims as business evidence.
        """
        history = [x for x in (state.get("history") or []) if isinstance(x, dict)]
        if history:
            last = history[-1]
            if (
                str(last.get("role") or "") == "user"
                and str(last.get("content") or "").strip() == str(current_text or "").strip()
            ):
                history = history[:-1]
        if not history:
            return ""

        # Preferred boundary: the exact user message that produced the current
        # pause. This is refreshed on every PAUSED result, so a new decision does
        # not inherit unrelated older requests, even when they share the same
        # route/intent.
        anchor_message_id = str(pending_workflow.get("context_anchor_message_id") or "").strip()
        if anchor_message_id:
            for index, item in enumerate(history):
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                if str(metadata.get("message_id") or "").strip() == anchor_message_id:
                    history = history[index:]
                    break

        target_intent = str(
            pending_workflow.get("owner_intent")
            or (state.get("route_decision") or {}).get("intent")
            or state.get("intent")
            or ""
        ).strip()

        selected: list[dict[str, Any]] = []
        anchor_seen = False
        for item in reversed(history):
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if not content:
                continue

            if role == "assistant":
                item_intent = cls._history_message_intent(item)
                if anchor_seen and target_intent and item_intent and item_intent != target_intent:
                    break
                anchor_seen = True

            # Ignore everything before the first assistant anchor. This keeps a
            # malformed/incomplete history from pulling unrelated old user turns.
            if anchor_seen:
                selected.append(item)

        selected.reverse()
        rendered = []
        for item in selected:
            role = str(item.get("role") or "unknown").strip().lower()
            content = str(item.get("content") or "").strip()
            rendered.append(f"{role}: {content}")
        return "\n".join(rendered)

    @staticmethod
    def _collect_transaction_parameter_context(
        *, state: dict[str, Any], current_text: str, max_messages: int = 6
    ) -> str:
        """Render a bounded recent history only to resolve parameter references.

        This context is deliberately non-authoritative. It may help the extractor
        resolve references such as "a de 14,99" to an entity named in the recent
        assistant/tool-grounded conversation, but business pre-validation remains
        responsible for proving the candidate before confirmation/execution.
        """
        history = [item for item in (state.get("history") or []) if isinstance(item, dict)]
        if history:
            last = history[-1]
            if (
                str(last.get("role") or "").strip().lower() == "user"
                and str(last.get("content") or "").strip() == str(current_text or "").strip()
            ):
                history = history[:-1]
        selected = history[-max(1, int(max_messages or 1)):]
        rendered: list[str] = []
        for item in selected:
            role = str(item.get("role") or "unknown").strip().lower()
            content = str(item.get("content") or "").strip()
            if content:
                rendered.append(f"{role}: {content}")
        return "\n".join(rendered)

    async def _classify_expected_input_semantically(
        self,
        *,
        text: str,
        expected_input: dict[str, Any],
        pause_prompt: str,
        relevant_conversation_context: str = "",
        profile_name: str = "router",
        component_name: str = "workflow.expected_input",
        generation_name: str = "workflow.expected_input.semantic_classifier",
    ) -> tuple[str | None, str | None]:
        """Run an agent-defined classifier and constrain its output to allowed_values.

        The framework does not know what any option means. It only renders the
        workflow prompt, invokes the configured LLM and rejects every value not
        declared in ``allowed_values``.
        """
        if not has_semantic_classifier(expected_input) or self.llm is None:
            return None, None
        classifier = expected_input.get("semantic_classifier") or {}
        allowed = [str(x) for x in (expected_input.get("allowed_values") or [])]
        prompt = str(classifier.get("prompt") or "")
        rendered = (
            prompt.replace("{{ allowed_values }}", json.dumps(allowed, ensure_ascii=False))
            .replace("{{ pending_prompt }}", str(pause_prompt or ""))
            .replace("{{ relevant_conversation_context }}", str(relevant_conversation_context or ""))
            .replace("{{ user_input }}", str(text or ""))
        )
        unmatched_value = str(classifier.get("unmatched_value") or "").strip()
        protocol_options = list(allowed)
        if unmatched_value:
            protocol_options.append(unmatched_value)
        protocol = (
            "\n\nPROTOCOLO OBRIGATÓRIO DO FRAMEWORK: responda somente com UMA das "
            f"opções permitidas, sem explicação adicional: {json.dumps(protocol_options, ensure_ascii=False)}."
        )
        try:
            answer = await self.llm.ainvoke(
                [
                    {"role": "system", "content": rendered + protocol},
                    {"role": "user", "content": str(text or "")},
                ],
                profile_name=profile_name,
                component_name=component_name,
                generation_name=generation_name,
            )
        except Exception as exc:
            logger.warning("Falha no semantic_classifier do expected_input: %s", exc)
            return None, None
        raw = str(answer or "").strip()
        matched = match_semantic_classifier_output(raw, expected_input)
        if matched is not None:
            return matched, raw
        # Tolerate a tiny structured wrapper while still validating its value.
        try:
            data = parse_json_object(raw)
        except Exception:
            data = {}
        for key in ("value", "option", "choice", "classification", "result"):
            if key in data:
                matched = match_semantic_classifier_output(str(data.get(key) or ""), expected_input)
                if matched is not None:
                    return matched, raw
        return None, raw

    async def _prefer_contextual_reentry_over_semantic_resume(
        self,
        *,
        text: str,
        classified: str,
        expected_input: dict[str, Any],
        pause_prompt: str,
        relevant_conversation_context: str,
    ) -> tuple[bool, str | None, str | None]:
        """Protect contextual reentry from a premature workflow resume.

        ``semantic_classifier`` is agent-declared and normally authoritative. A
        special ambiguity exists when the same contract declares an option whose
        action is ``contextual_reentry``: an LLM can correctly notice a leading
        answer to the pause (for example a negative acknowledgement) but miss the
        substantive remainder of the same utterance. Resuming the workflow in
        that situation can immediately reach a terminal branch such as handoff,
        before normal routing sees the new information.

        The framework therefore performs a generic *precedence validation* only
        for non-literal semantic matches and only when the contract explicitly
        declares contextual reentry. No domain vocabulary or SIM/NAO semantics
        are embedded here.
        """
        if self.llm is None or not isinstance(expected_input, dict):
            return False, None, None
        classifier = expected_input.get("semantic_classifier")
        if not isinstance(classifier, dict):
            return False, None, None
        option_actions = classifier.get("option_actions")
        if not isinstance(option_actions, dict):
            return False, None, None

        reentry_option = None
        for option, cfg in option_actions.items():
            if isinstance(cfg, dict) and str(cfg.get("action") or "").strip().lower() == "contextual_reentry":
                reentry_option = str(option)
                break
        if not reentry_option or str(classified).upper() == reentry_option.upper():
            return False, reentry_option, None
        if classifier.get("contextual_reentry_precedence") is False:
            return False, reentry_option, None

        prompt = (
            "Você valida precedência entre retomar um workflow pausado e fazer reentrada contextual. "
            "Não decida a intenção de negócio. Analise apenas se a mensagem atual é totalmente "
            "consumida pela opção já classificada ou se contém informação substantiva adicional que "
            "precisa ser interpretada pelo pipeline normal.\n\n"
            f"Pergunta pendente: {str(pause_prompt or '').strip()}\n"
            f"Opção inicialmente classificada: {str(classified)}\n"
            f"Contexto relevante: {str(relevant_conversation_context or '').strip()}\n"
            f"Mensagem atual: {str(text or '').strip()}\n\n"
            "Responda somente REENTER se houver pedido, objeção, correção, explicação, motivo, entidade, "
            "valor, referência ou outro fato novo que ainda precise de interpretação além da resposta "
            "à pergunta pendente. Responda somente RESUME se a mensagem inteira for apenas a resposta "
            "à pergunta pendente, admitindo somente cortesia sem nova demanda."
        )
        try:
            answer = await self.llm.ainvoke(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": str(text or "")},
                ],
                profile_name="router",
                component_name="workflow.expected_input.precedence",
                generation_name="workflow.expected_input.contextual_reentry_precedence",
            )
        except Exception as exc:
            logger.warning("Falha ao validar precedência de contextual_reentry: %s", exc)
            return False, reentry_option, None
        raw = str(answer or "").strip()
        return raw.upper() == "REENTER", reentry_option, raw

    @staticmethod
    def _last_assistant_prompt(state: dict[str, Any], current_text: str) -> str:
        history = [item for item in (state.get("history") or []) if isinstance(item, dict)]
        if history and str(history[-1].get("role") or "").lower() == "user" and str(history[-1].get("content") or "").strip() == str(current_text or "").strip():
            history = history[:-1]
        for item in reversed(history):
            if str(item.get("role") or "").strip().lower() == "assistant":
                content = str(item.get("content") or "").strip()
                if content:
                    return content
        return ""

    async def _classify_transaction_confirmation_semantically(
        self, *, state: dict[str, Any], text: str
    ) -> tuple[str | None, str | None, str]:
        """Classify a non-literal confirmation using the existing workflow semantic engine.

        The deterministic parser remains authoritative for explicit yes/no. This
        fallback is only reached when that parser returns ``None``. Configuration
        is declarative under ``router.transaction_confirmation`` in routing.yaml.
        """
        cfg = self.transaction_confirmation if isinstance(self.transaction_confirmation, dict) else {}
        semantic = cfg.get("semantic_fallback") if isinstance(cfg.get("semantic_fallback"), dict) else {}
        if not bool(semantic.get("enabled", False)) or self.llm is None:
            return None, None, ""

        allowed = [str(x) for x in (semantic.get("allowed_values") or ["SIM", "NAO", "CONTINUAR"])]
        prompt = str(semantic.get("prompt") or "").strip()
        if not prompt:
            return None, None, ""
        expected_input = {
            "allowed_values": allowed,
            "semantic_classifier": {
                "enabled": True,
                "include_relevant_context": bool(semantic.get("include_relevant_context", True)),
                "prompt": prompt,
            },
        }
        relevant_context = ""
        if bool(semantic.get("include_relevant_context", True)):
            previous = state.get("route_decision") if isinstance(state.get("route_decision"), dict) else {}
            synthetic_pending = {
                "owner_intent": str(previous.get("intent") or state.get("intent") or "").strip(),
                "context_anchor_message_id": str((state.get("active_transaction") or {}).get("context_anchor_message_id") or "").strip() if isinstance(state.get("active_transaction"), dict) else "",
            }
            relevant_context = self._collect_relevant_conversation_context(
                state=state, pending_workflow=synthetic_pending, current_text=str(text)
            )
        pending_prompt = self._last_assistant_prompt(state, str(text))
        classified, raw = await self._classify_expected_input_semantically(
            text=str(text),
            expected_input=expected_input,
            pause_prompt=pending_prompt,
            relevant_conversation_context=relevant_context,
            profile_name=str(semantic.get("profile_name") or "router"),
            component_name="transaction.confirmation",
            generation_name="transaction.confirmation.semantic_classifier",
        )
        return classified, raw, relevant_context

    async def _route_contextual_reentry(
        self,
        *,
        state: dict[str, Any],
        original_input: str,
        relevant_context: str,
        classifier_output: str,
        raw_classifier: str | None,
        allowed_values: list[Any],
    ) -> RouteDecision:
        """Re-enter normal routing using bounded conversational context.

        This is deliberately a routing aid, not business evidence. The original
        utterance remains available separately for audit, while the effective
        text is used only to understand the unresolved request and extract
        candidate transaction parameters that must still pass normal validation
        and confirmation policies.
        """
        contextual_input = (
            "CONTEXTO DA SOLICITAÇÃO IMEDIATAMENTE ANTERIOR:\n"
            f"{str(relevant_context or '').strip()}\n\n"
            "CONTINUAÇÃO ATUAL DO CLIENTE:\n"
            f"{str(original_input or '').strip()}"
        ).strip()

        reentry_state = dict(state)
        reentry_state["pending_domain_workflow"] = None
        reentry_state["transaction_status"] = None

        # Contextual reentry is semantically richer than substring matching.
        # Prefer the configured LLM router when available; deterministic routing
        # remains the fallback for deployments that disable semantic routing.
        if self.enable_llm_router and self.llm is not None:
            try:
                decision = await self._route_by_llm(contextual_input, reentry_state)
            except Exception as exc:
                logger.exception("Falha no roteamento LLM durante reentrada contextual; usando fallback: %s", exc)
                decision = self._route_by_keyword(contextual_input) or RouteDecision(
                    route=self.fallback_agent,
                    agent=self.fallback_agent,
                    intent="fallback",
                    confidence=0.1,
                    reason="Falha no classificador semântico durante reentrada contextual; usando fallback configurado.",
                    method="fallback",
                    metadata={"contextual_reentry_llm_failed": True},
                )
        else:
            decision = self._route_by_keyword(contextual_input) or RouteDecision(
                route=self.fallback_agent,
                agent=self.fallback_agent,
                intent="fallback",
                confidence=0.3,
                reason="Fallback após reentrada contextual.",
                method="fallback",
            )

        decision.metadata = {
            **dict(decision.metadata or {}),
            "contextual_reentry": True,
            "contextual_reentry_input": contextual_input,
            "original_input": str(original_input or ""),
            "classifier_output": classifier_output,
            "classifier_raw_output": raw_classifier,
            "allowed_values": list(allowed_values or []),
            "relevant_conversation_context": str(relevant_context or ""),
            "user_claims_are_evidence": False,
            "previous_workflow_cancel_reason": "contextual_reentry",
        }
        return decision

    async def route(self, state: dict[str, Any]) -> RouteDecision:
        session = (state.get("context") or {}).get("session", {}) or {}
        explicit_next_state = state.get("next_state")
        tx_status_at_route = str(state.get("transaction_status") or "").strip().upper()
        terminal_tx = tx_status_at_route in {"COMPLETED", "FAILED", "CANCELLED", "BLOCKED", "OUT_OF_SCOPE"}
        operational_context_reset = bool(state.get("operational_context_reset"))
        if terminal_tx:
            # Same conversation/session, new interaction: a terminal workflow may
            # remain in durable history, but it must not own the next turn. This is
            # also a compatibility guard for checkpoints created before terminal
            # workflow tombstones were persisted.
            state["pending_domain_workflow"] = None
            state["pending_tool_clarification"] = None
            state["workflow_input_reprompt"] = None

        # Um status transacional terminal é a fonte de verdade sobre o latch. Se
        # um checkpoint legado/parcial ainda trouxer ``next_state`` da transação
        # encerrada, esse valor não pode aprisionar a próxima mensagem na política
        # de estado. O workflow_state da sessão continua disponível porque pode
        # representar um workflow conversacional independente da transação já
        # encerrada.
        if operational_context_reset:
            current_state = None
        elif terminal_tx and explicit_next_state:
            current_state = session.get("metadata", {}).get("workflow_state")
        else:
            current_state = explicit_next_state or session.get("metadata", {}).get("workflow_state")
        text = state.get("sanitized_input") or state.get("user_text") or ""

        # A paused conversational workflow owns the next turn when the current
        # input satisfies its declarative ``expected_input`` contract. This check
        # must happen before route continuity; otherwise a generic reply such as
        # "sim" can be misread as END_SESSION instead of resuming the workflow.
        pending_workflow = state.get("pending_domain_workflow")
        if isinstance(pending_workflow, dict) and pending_workflow.get("execution_id"):
            pause = pending_workflow.get("pause") if isinstance(pending_workflow.get("pause"), dict) else {}
            expected_input = pause.get("expected_input") if isinstance(pause, dict) else None
            matched = match_expected_input(str(text), expected_input)
            if matched is not None:
                previous = state.get("route_decision") or {}
                owner_agent = str(
                    pending_workflow.get("owner_agent")
                    or state.get("active_agent")
                    or previous.get("agent")
                    or state.get("route")
                    or self.fallback_agent
                ).strip()
                owner_intent = str(
                    pending_workflow.get("owner_intent")
                    or previous.get("intent")
                    or state.get("intent")
                    or f"workflow_resume:{pending_workflow.get('workflow_name') or 'paused'}"
                ).strip()
                decision = RouteDecision(
                    route=owner_agent,
                    agent=owner_agent,
                    intent=owner_intent,
                    confidence=1.0,
                    reason="Entrada consumida pelo contrato expected_input do workflow pausado.",
                    method="state",
                    domain=previous.get("domain") or state.get("domain"),
                    mcp_tools=[str(pending_workflow.get("resume_tool") or "retomar_workflow")],
                    metadata={
                        "route_bypassed": True,
                        "workflow_resume": True,
                        "workflow_name": pending_workflow.get("workflow_name"),
                        "workflow_execution_id": pending_workflow.get("execution_id"),
                        "normalized_input": matched,
                    },
                )
                await self._emit(decision, state)
                return decision

            # An explicit human-handoff request is a global conversation control,
            # not an intent shift and not a value of the paused workflow contract.
            # It must therefore preempt the workflow semantic classifier *after*
            # deterministic expected_input matching (so "sim"/"não" keep their
            # absolute contract precedence) but *before* unmatched semantic resume.
            # CONTINUE/ROUTE/END_SESSION decisions from this probe are ignored here;
            # the workflow remains authoritative for every non-handoff message.
            global_control = await self.continuity.evaluate_global_control(
                state, intents=self.intents, allowed_controls={"HUMAN_HANDOFF"}
            )
            if global_control is not None:
                global_control.metadata = {
                    **dict(global_control.metadata or {}),
                    "interrupted_workflow_name": pending_workflow.get("workflow_name"),
                    "interrupted_workflow_execution_id": pending_workflow.get("execution_id"),
                    "workflow_interruption": "human_handoff",
                }
                await self._emit(global_control, state)
                return global_control

            # Enumerated contracts retain workflow ownership for unmatched
            # replies. A workflow may explicitly opt in to semantic handling:
            # coherent free text can be resumed as a workflow-declared value,
            # while incoherent input still receives the declarative reprompt.
            if isinstance(expected_input, dict) and expected_input.get("allowed_values"):
                previous = state.get("route_decision") or {}
                owner_agent = str(
                    pending_workflow.get("owner_agent")
                    or state.get("active_agent")
                    or previous.get("agent")
                    or state.get("route")
                    or self.fallback_agent
                ).strip()
                owner_intent = str(
                    pending_workflow.get("owner_intent")
                    or previous.get("intent")
                    or state.get("intent")
                    or f"workflow_resume:{pending_workflow.get('workflow_name') or 'paused'}"
                ).strip()
                raw_classifier = None
                relevant_context = ""

                # Preferred path: the agent provides a prompt whose output must
                # be one of the dynamic allowed_values. The framework adds no
                # SIM/NAO or other domain semantics.
                if has_semantic_classifier(expected_input):
                    classifier_cfg = expected_input.get("semantic_classifier") or {}
                    relevant_context = ""
                    if bool(classifier_cfg.get("include_relevant_context")):
                        relevant_context = self._collect_relevant_conversation_context(
                            state=state,
                            pending_workflow=pending_workflow,
                            current_text=str(text),
                        )
                    classified, raw_classifier = await self._classify_expected_input_semantically(
                        text=str(text),
                        expected_input=expected_input,
                        pause_prompt=str(pause.get("prompt") or ""),
                        relevant_conversation_context=relevant_context,
                    )
                    if classified is not None:
                        option_actions = classifier_cfg.get("option_actions") if isinstance(classifier_cfg, dict) else {}
                        option_actions = option_actions if isinstance(option_actions, dict) else {}
                        action_cfg = option_actions.get(str(classified)) or option_actions.get(str(classified).upper())
                        action_cfg = action_cfg if isinstance(action_cfg, dict) else {}

                        # A semantic match that would resume the paused workflow
                        # must not prematurely win over an explicitly declared
                        # contextual_reentry option when the same utterance also
                        # carries substantive new information. This validation is
                        # intentionally generic and runs only after literal
                        # expected_input matching has already failed.
                        if str(action_cfg.get("action") or "").strip().lower() != "contextual_reentry":
                            prefer_reentry, reentry_option, precedence_raw = await self._prefer_contextual_reentry_over_semantic_resume(
                                text=str(text),
                                classified=str(classified),
                                expected_input=expected_input,
                                pause_prompt=str(pause.get("prompt") or ""),
                                relevant_conversation_context=relevant_context,
                            )
                            if prefer_reentry and reentry_option:
                                decision = await self._route_contextual_reentry(
                                    state=state,
                                    original_input=str(text),
                                    relevant_context=relevant_context,
                                    classifier_output=str(reentry_option),
                                    raw_classifier=raw_classifier,
                                    allowed_values=list(expected_input.get("allowed_values") or []),
                                )
                                decision.metadata = {
                                    **dict(decision.metadata or {}),
                                    "contextual_reentry_preempted_resume": True,
                                    "initial_classifier_output": str(classified),
                                    "contextual_reentry_precedence_raw_output": precedence_raw,
                                }
                                await self._emit(decision, state)
                                return decision

                        if str(action_cfg.get("action") or "").strip().lower() == "contextual_reentry":
                            decision = await self._route_contextual_reentry(
                                state=state,
                                original_input=str(text),
                                relevant_context=relevant_context,
                                classifier_output=str(classified),
                                raw_classifier=raw_classifier,
                                allowed_values=list(expected_input.get("allowed_values") or []),
                            )
                            await self._emit(decision, state)
                            return decision

                        decision = RouteDecision(
                            route=owner_agent,
                            agent=owner_agent,
                            intent=owner_intent,
                            confidence=1.0,
                            reason="Entrada classificada pelo semantic_classifier do expected_input.",
                            method="state",
                            domain=previous.get("domain") or state.get("domain"),
                            mcp_tools=[str(pending_workflow.get("resume_tool") or "retomar_workflow")],
                            metadata={
                                "route_bypassed": True,
                                "workflow_resume": True,
                                "workflow_semantic_classifier": True,
                                "workflow_name": pending_workflow.get("workflow_name"),
                                "workflow_execution_id": pending_workflow.get("execution_id"),
                                "normalized_input": classified,
                                "classifier_output": classified,
                                "classifier_raw_output": raw_classifier,
                                "allowed_values": list(expected_input.get("allowed_values") or []),
                                "original_input": str(text),
                                "relevant_conversation_context": relevant_context,
                            },
                        )
                        await self._emit(decision, state)
                        return decision

                # Legacy compatibility for workflows that still use the older
                # coherent-unmatched -> resume_as contract.
                semantic_coherent = semantic_coherence_from_guardrails(state)
                resume_as = meaningful_unmatched_resume_value(
                    expected_input,
                    semantic_coherent=semantic_coherent,
                )
                if resume_as is not None:
                    decision = RouteDecision(
                        route=owner_agent,
                        agent=owner_agent,
                        intent=owner_intent,
                        confidence=1.0,
                        reason="Entrada coerente fora das opções; aplicando política unmatched legada do workflow pausado.",
                        method="state",
                        domain=previous.get("domain") or state.get("domain"),
                        mcp_tools=[str(pending_workflow.get("resume_tool") or "retomar_workflow")],
                        metadata={
                            "route_bypassed": True,
                            "workflow_resume": True,
                            "workflow_unmatched": True,
                            "workflow_unmatched_action": "resume_as",
                            "workflow_name": pending_workflow.get("workflow_name"),
                            "workflow_execution_id": pending_workflow.get("execution_id"),
                            "normalized_input": resume_as,
                            "original_input": str(text),
                        },
                    )
                    await self._emit(decision, state)
                    return decision

                decision = RouteDecision(
                    route=owner_agent,
                    agent=owner_agent,
                    intent=owner_intent,
                    confidence=1.0,
                    reason="Entrada inválida para o contrato expected_input do workflow pausado; mantendo posse do workflow.",
                    method="state",
                    domain=previous.get("domain") or state.get("domain"),
                    mcp_tools=[],
                    metadata={
                        "route_bypassed": True,
                        "workflow_input_invalid": True,
                        "workflow_name": pending_workflow.get("workflow_name"),
                        "workflow_execution_id": pending_workflow.get("execution_id"),
                        "workflow_reprompt": expected_input_reprompt(
                            expected_input, pause_prompt=str(pause.get("prompt") or "")
                        ),
                        "workflow_semantic_classifier": bool(has_semantic_classifier(expected_input)),
                        "classifier_raw_output": raw_classifier if has_semantic_classifier(expected_input) else None,
                        "allowed_values": list(expected_input.get("allowed_values") or []),
                        "original_input": str(text),
                        "relevant_conversation_context": relevant_context if has_semantic_classifier(expected_input) else "",
                    },
                )
                await self._emit(decision, state)
                return decision

        # Estados transacionais preservam continuidade para respostas curtas
        # (parâmetros, "sim", "não"), mas NÃO podem aprisionar a sessão. Antes
        # de aplicar a política de estado, procuramos uma mudança explícita de
        # intenção. Se houver uma intent diferente com confiança suficiente, ela
        # vence o lock de estado e sinaliza ao runtime para encerrar a transação
        # pendente antes de executar a nova intent.
        state_decision = self._route_by_state(current_state)
        if state_decision:
            tx_status = str(state.get("transaction_status") or "").strip().upper()

            active_tx = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
            legacy_tx = state.get("pending_tool_call") or state.get("selected_tool_call") or {}
            state_lock_name = str(
                state_decision.next_state
                or current_state
                or state_decision.intent.removeprefix("state:")
                or ""
            ).strip().upper()
            transactional_state_lock = state_lock_name.startswith(
                ("WAITING_", "COLLECTING_", "AWAITING_")
            )

            # Rich transactional latches remain the primary source of truth.
            # The domain state lock is only a recovery fallback for checkpoints
            # where those latches were not restored. This prevents a generic
            # COLLECTING_* state from stealing a legitimate parameter answer.
            rich_transaction_context = bool(
                active_tx.get("tool_name")
                or (isinstance(legacy_tx, dict) and legacy_tx.get("tool_name"))
                or tx_status in {"COLLECTING_PARAMETERS", "AWAITING_CONFIRMATION"}
            )
            fallback_state_lock_context = bool(
                transactional_state_lock and not rich_transaction_context
            )
            has_transaction_context = bool(
                rich_transaction_context or fallback_state_lock_context
            )

            # Some hosts restore the domain state but omit transaction_status.
            # Infer only the generic phase needed by the precedence logic; do not
            # replace richer transaction data when it exists.
            effective_tx_status = tx_status
            if not effective_tx_status:
                if state_lock_name.startswith("COLLECTING_"):
                    effective_tx_status = "COLLECTING_PARAMETERS"
                elif state_lock_name.startswith("AWAITING_") or "CONFIRMATION" in state_lock_name:
                    effective_tx_status = "AWAITING_CONFIRMATION"

            precedence_state = state
            if effective_tx_status and effective_tx_status != tx_status:
                precedence_state = dict(state)
                precedence_state["transaction_status"] = effective_tx_status

            # Transactional interruption precedence is semantic, not lexical.
            #
            # COLLECTING_PARAMETERS is special: the pending parameter gets the
            # first opportunity to consume the turn.  If the input is pertinent
            # to the parameter, extraction returns values and the transaction
            # continues.  Only when the input is not pertinent do we ask the
            # semantic interruption classifier whether the user abandoned the
            # active transaction.  This preserves inputs such as
            # ``motivo é que desisti`` as a legitimate ``reason`` value while
            # still allowing ``não quero mais devolver; quero ver meus serviços``
            # to abandon the current operation and start a new objective.
            if effective_tx_status == "COLLECTING_PARAMETERS":
                if rich_transaction_context:
                    relevance = await self._classify_transaction_parameter_relevance(
                        precedence_state, text=str(text)
                    )
                    if relevance is True:
                        consumed = await self._transaction_parameter_precedence(
                            precedence_state, text=str(text), state_decision=state_decision
                        )
                        if consumed is not None:
                            consumed.metadata = {
                                **(consumed.metadata or {}),
                                "transaction_parameter_relevant": True,
                            }
                            await self._emit(consumed, state)
                            return consumed

                        # Pertinent to the requested parameter, but extraction did
                        # not produce a structured value. Keep transaction
                        # ownership and let the agent reprompt/clarify; do not
                        # reinterpret the same input as ABANDON or SHIFT.
                        state_decision.metadata = {
                            **(state_decision.metadata or {}),
                            "transaction_parameter_relevant": True,
                            "transaction_parameter_extraction_empty": True,
                        }
                        await self._emit(state_decision, state)
                        return state_decision

                    if relevance is None:
                        # Compatibility/fail-safe when the relevance classifier is
                        # unavailable: retain the previous extractor-first behavior.
                        consumed = await self._transaction_parameter_precedence(
                            precedence_state, text=str(text), state_decision=state_decision
                        )
                        if consumed is not None:
                            consumed.metadata = {
                                **(consumed.metadata or {}),
                                "transaction_parameter_relevance": "unknown",
                            }
                            await self._emit(consumed, state)
                            return consumed

                if has_transaction_context:
                    abandonment = await self._transaction_state_interruption_candidate(
                        precedence_state,
                        text=str(text),
                        state_decision=state_decision,
                        abandon_only=True,
                    )
                    if abandonment is not None:
                        abandonment.metadata = {
                            **(abandonment.metadata or {}),
                            "transaction_parameter_relevant": False if rich_transaction_context else None,
                        }
                        await self._emit(abandonment, state)
                        return abandonment

            # In confirmation/waiting phases there is no pending free-form
            # parameter whose value can be confused with abandonment.  Evaluate
            # ABANDON semantically before confirmation/state-lock consumption.
            # Plain confirmations (e.g. yes/no) are classified as CONTINUE by
            # this probe and then follow the normal confirmation path below.
            elif has_transaction_context:
                abandonment = await self._transaction_state_interruption_candidate(
                    precedence_state,
                    text=str(text),
                    state_decision=state_decision,
                    abandon_only=True,
                )
                if abandonment is not None:
                    await self._emit(abandonment, state)
                    return abandonment

            if effective_tx_status == "AWAITING_CONFIRMATION":
                consumed = await self._transaction_parameter_precedence(
                    precedence_state, text=str(text), state_decision=state_decision
                )
                if consumed is not None:
                    await self._emit(consumed, state)
                    return consumed

            interruption = await self._transaction_state_interruption_candidate(
                precedence_state, text=str(text), state_decision=state_decision
            )
            if interruption is not None:
                await self._emit(interruption, state)
                return interruption

            await self._emit(state_decision, state)
            return state_decision

        # Defensive recovery for checkpoints where the transactional latch survived
        # but ``next_state`` was not restored.  This can happen in host templates
        # that persist transaction fields independently from the router state.
        # Without this branch, a clear new intent may preempt route stickiness but
        # the runtime still resumes the old pending tool, producing hybrid replies
        # such as ``[BillingAgent] informe o número do pedido``.
        tx_status = str(state.get("transaction_status") or "").strip().upper()
        active_tx = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
        legacy_tx = state.get("pending_tool_call") or state.get("selected_tool_call") or {}
        has_tx = bool(active_tx.get("tool_name") or (isinstance(legacy_tx, dict) and legacy_tx.get("tool_name")))
        if has_tx and tx_status in {"COLLECTING_PARAMETERS", "AWAITING_CONFIRMATION"}:
            previous = state.get("route_decision") or {}
            tx_agent = str(previous.get("agent") or state.get("active_agent") or state.get("route") or self.fallback_agent).strip()
            synthetic = RouteDecision(
                route=tx_agent,
                agent=tx_agent,
                intent=f"state:{tx_status}",
                confidence=1.0,
                reason="Transação ativa recuperada sem next_state; avaliando possível interrupção de intenção.",
                method="state",
                next_state=tx_status,
            )
            if tx_status == "COLLECTING_PARAMETERS":
                relevance = await self._classify_transaction_parameter_relevance(
                    state, text=str(text)
                )
                if relevance is True:
                    consumed = await self._transaction_parameter_precedence(
                        state, text=str(text), state_decision=synthetic
                    )
                    if consumed is not None:
                        consumed.metadata = {
                            **(consumed.metadata or {}),
                            "transaction_state_recovered": True,
                            "transaction_parameter_relevant": True,
                        }
                        await self._emit(consumed, state)
                        return consumed
                    synthetic.metadata = {
                        **(synthetic.metadata or {}),
                        "transaction_state_recovered": True,
                        "transaction_parameter_relevant": True,
                        "transaction_parameter_extraction_empty": True,
                    }
                    await self._emit(synthetic, state)
                    return synthetic

                if relevance is None:
                    consumed = await self._transaction_parameter_precedence(
                        state, text=str(text), state_decision=synthetic
                    )
                    if consumed is not None:
                        consumed.metadata = {
                            **(consumed.metadata or {}),
                            "transaction_state_recovered": True,
                            "transaction_parameter_relevance": "unknown",
                        }
                        await self._emit(consumed, state)
                        return consumed

            # No parameter was consumed (or this is confirmation): now decide
            # semantically whether the user abandoned the active transaction.
            abandonment = await self._transaction_state_interruption_candidate(
                state,
                text=str(text),
                state_decision=synthetic,
                abandon_only=True,
            )
            if abandonment is not None:
                abandonment.metadata = {
                    **(abandonment.metadata or {}),
                    "transaction_state_recovered": True,
                }
                await self._emit(abandonment, state)
                return abandonment

            if tx_status == "AWAITING_CONFIRMATION":
                consumed = await self._transaction_parameter_precedence(
                    state, text=str(text), state_decision=synthetic
                )
                if consumed is not None:
                    consumed.metadata = {
                        **(consumed.metadata or {}),
                        "transaction_state_recovered": True,
                    }
                    await self._emit(consumed, state)
                    return consumed

            interruption = await self._transaction_state_interruption_candidate(
                state, text=str(text), state_decision=synthetic
            )
            if interruption is not None:
                interruption.metadata = {
                    **(interruption.metadata or {}),
                    "transaction_state_recovered": True,
                }
                await self._emit(interruption, state)
                return interruption

            # A transação continua ativa e a mensagem NÃO representa mudança de
            # intenção. Neste caso a decisão sintética de estado precisa vencer
            # route stickiness/continuity. Antes, o código apenas verificava uma
            # possível interrupção e, na ausência dela, caía adiante no LLM de
            # continuidade. Isso fazia respostas de parâmetro (ex.: ``R$ 71,99``)
            # perderem o latch determinístico da transação e reiniciarem a seleção
            # da tool.
            synthetic.metadata = {
                **(synthetic.metadata or {}),
                "transaction_state_recovered": True,
            }
            await self._emit(synthetic, state)
            return synthetic

        # Mensagens que expressam de forma explícita uma intenção diferente da
        # intent/agente ativos devem prevalecer sobre a route stickiness. Isso
        # evita manter um fluxo read-only (por exemplo, tracking) quando o usuário
        # muda para uma ação transacional (por exemplo, devolução).
        planner = getattr(self, "multi_intent_planner", None)
        multi_intent_plan = planner.plan(str(text)) if planner is not None else None
        multi_intent_method = "keyword"
        if (
            planner is not None
            and planner.looks_compound(str(text))
            and planner.needs_semantic_fallback(multi_intent_plan)
            and self.enable_llm_router
            and self.llm is not None
        ):
            try:
                semantic_plan = await self._plan_multi_intent_by_llm(str(text), state)
                if semantic_plan is not None:
                    multi_intent_plan = semantic_plan
                    multi_intent_method = "llm"
            except Exception as exc:
                # O fallback semântico é fail-safe: um plano determinístico
                # parcial continua válido se o provedor estiver indisponível.
                logger.exception("Falha no classificador LLM multi-intent: %s", exc)
        if multi_intent_plan is not None:
            primary = multi_intent_plan.operations[0]
            decision = RouteDecision(
                route=primary.agent,
                agent=primary.agent,
                intent=primary.intent,
                confidence=1.0,
                reason=(
                    "Plano multi-intent classificado semanticamente e validado contra intents configuradas."
                    if multi_intent_method == "llm"
                    else "Plano multi-intent validado a partir de intents configuradas."
                ),
                method=multi_intent_method,
                metadata={
                    "multi_intent": True,
                    "multi_intent_classifier": multi_intent_method,
                    "multi_intent_plan": multi_intent_plan.model_dump(mode="json"),
                },
                domain=primary.domain,
                mcp_tools=primary.tools,
            )
            await self._emit(decision, state)
            return decision

        keyword_candidate = self._route_by_keyword(text)
        active_agent = str(state.get("active_agent") or "").strip()
        previous = state.get("route_decision") or {}
        previous_intent = str(previous.get("intent") or state.get("intent") or "").strip()
        if (
            active_agent
            and keyword_candidate is not None
            and keyword_candidate.intent != previous_intent
        ):
            keyword_candidate.metadata = {
                **(keyword_candidate.metadata or {}),
                "route_stickiness_preempted": True,
                "previous_agent": active_agent,
                "previous_intent": previous_intent,
            }
            await self._emit(keyword_candidate, state)
            return keyword_candidate

        # Uma transação terminal encerra também a elegibilidade de route
        # stickiness/continuity herdada daquele fluxo no próximo roteamento.
        # O histórico conversacional continua intacto, mas o agente/intenção
        # anterior não pode capturar uma nova mensagem depois de COMPLETED,
        # FAILED, CANCELLED, BLOCKED ou OUT_OF_SCOPE. Nesses casos a mensagem
        # volta ao roteamento normal (keyword/LLM/fallback).
        if not terminal_tx and not operational_context_reset:
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


    async def _classify_transaction_parameter_relevance(
        self, state: dict[str, Any], *, text: str
    ) -> bool | None:
        """Semantically decide whether the turn answers a pending parameter.

        This is intentionally separate from extraction.  A parameter extractor
        may be able to manufacture a syntactically valid value from unrelated
        text; relevance answers the higher-level question first: does the user
        appear to be responding to what the active transaction asked for?

        Returns True/False when classification succeeds and None when the
        classifier is unavailable or its output cannot be trusted.
        """
        if not (self.enable_llm_router and self.llm is not None):
            return None
        missing = [str(name) for name in (state.get("missing_parameters") or []) if str(name).strip()]
        if not missing:
            return None
        active = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
        tool_name = str(active.get("tool_name") or "").strip()
        if not tool_name:
            return None
        payload = {
            "message": str(text or ""),
            "transaction": {
                "intent": active.get("started_from_intent") or state.get("intent"),
                "tool_name": tool_name,
                "tool_description": active.get("tool_description"),
                "missing_parameters": missing,
                "parameter_schema": active.get("parameter_schema") or {},
                "known_arguments": active.get("arguments") or {},
                "relevant_conversation_context": (
                    active.get("parameter_conversational_context")
                    or self._collect_transaction_parameter_context(state=state, current_text=str(text))
                ),
            },
        }
        system = (
            "Você decide somente se a mensagem do usuário é uma resposta pertinente ao(s) "
            "parâmetro(s) que a transação ativa está pedindo. Avalie significado e contexto, "
            "não palavras isoladas. Considere RELEVANT quando a mensagem fornece, esclarece, "
            "corrige ou referencia plausivelmente o dado solicitado, mesmo em linguagem livre. "
            "Considere NOT_RELEVANT quando a mensagem abandona a ação, inicia outro objetivo, "
            "faz uma pergunta diferente ou não responde ao dado pedido. Não extraia valores e "
            "não decida abandono/intent; classifique apenas pertinência. Retorne somente JSON "
            "válido: {\"relevance\":\"RELEVANT|NOT_RELEVANT\",\"confidence\":0.0,\"reason\":\"...\"}."
        )
        try:
            answer = await self.llm.ainvoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                temperature=0.0,
                fallback_max_tokens=256,
                profile_name="router",
                component_name="router.transaction_parameter_relevance",
                generation_name="llm.transaction_parameter_relevance",
            )
            data = self._parse_json(answer)
        except Exception as exc:
            logger.warning("Falha ao classificar pertinência do parâmetro transacional: %s", exc)
            return None
        relevance = str(data.get("relevance") or "").strip().upper()
        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            return None
        if confidence < self.intent_shift_threshold:
            return None
        if relevance == "RELEVANT":
            return True
        if relevance == "NOT_RELEVANT":
            return False
        return None

    async def _transaction_parameter_precedence(
        self,
        state: dict[str, Any],
        *,
        text: str,
        state_decision: RouteDecision,
    ) -> RouteDecision | None:
        """Try to consume the turn under the active transaction contract first.

        In AWAITING_CONFIRMATION, an explicit ABANDON candidate is classified
        before confirmation consumption; plain yes/no responses still keep
        deterministic confirmation precedence because they do not pass the
        abandonment gate. In COLLECTING_PARAMETERS, ABANDON is likewise checked
        before extraction, while SHIFT remains after parameter extraction so valid
        referential/value answers are not stolen from the active transaction.
        """
        tx_status = str(state.get("transaction_status") or "").strip().upper()
        if tx_status == "AWAITING_CONFIRMATION":
            active = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
            previous = state.get("route_decision") if isinstance(state.get("route_decision"), dict) else {}
            owner_intent = str(active.get("started_from_intent") or previous.get("intent") or state.get("intent") or "")
            compound_plan = self.multi_intent_planner.plan_confirmation_secondary(
                text, primary_intent=owner_intent, primary_agent=state_decision.agent
            )
            remainder = self.multi_intent_planner.confirmation_remainder(text)
            if (
                remainder
                and self.multi_intent_planner.needs_semantic_fallback(compound_plan)
                and self.enable_llm_router
                and self.llm is not None
            ):
                try:
                    semantic_plan = await self._plan_multi_intent_by_llm(
                        remainder,
                        state,
                        confirmation_primary=(owner_intent, state_decision.agent),
                    )
                    if semantic_plan is not None:
                        compound_plan = semantic_plan
                except Exception as exc:
                    logger.exception(
                        "Falha no classificador LLM multi-intent após confirmação: %s",
                        exc,
                    )
            confirmation = "confirm" if compound_plan is not None else parse_transaction_confirmation(text)
            source = "deterministic"
            classifier_output = None
            raw_classifier = None
            relevant_context = ""
            if confirmation is None:
                classified, raw_classifier, relevant_context = await self._classify_transaction_confirmation_semantically(
                    state=state, text=str(text)
                )
                classifier_output = classified
                semantic_cfg = self.transaction_confirmation.get("semantic_fallback") if isinstance(self.transaction_confirmation, dict) else {}
                semantic_cfg = semantic_cfg if isinstance(semantic_cfg, dict) else {}
                confirm_values = {str(x).strip().upper() for x in (semantic_cfg.get("confirm_values") or ["SIM"])}
                reject_values = {str(x).strip().upper() for x in (semantic_cfg.get("reject_values") or ["NAO"])}
                normalized = str(classified or "").strip().upper()
                if normalized in confirm_values:
                    confirmation = "confirm"
                    source = "semantic"
                elif normalized in reject_values:
                    confirmation = "reject"
                    source = "semantic"
                else:
                    return None
            state_decision.metadata = {
                **(state_decision.metadata or {}),
                "transaction_turn_consumed": True,
                "transaction_confirmation_decision": confirmation,
                "transaction_confirmation_source": source,
            }
            if compound_plan is not None:
                state_decision.metadata.update({
                    "multi_intent": True,
                    "multi_intent_confirmation": True,
                    "multi_intent_plan": compound_plan.model_dump(mode="json"),
                })
            if source == "semantic":
                state_decision.metadata.update({
                    "transaction_confirmation_classifier_output": classifier_output,
                    "transaction_confirmation_classifier_raw_output": raw_classifier,
                    "relevant_conversation_context": relevant_context,
                })
            return state_decision
        if tx_status != "COLLECTING_PARAMETERS":
            return None
        missing = [str(name) for name in (state.get("missing_parameters") or []) if str(name).strip()]
        if not missing:
            return None
        active = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
        tool_name = str(active.get("tool_name") or ((state.get("selected_tool_call") or {}).get("tool_name") if isinstance(state.get("selected_tool_call"), dict) else "") or "").strip()
        if not tool_name:
            return None
        known = dict(active.get("arguments") or {})
        schema = active.get("parameter_schema") if isinstance(active.get("parameter_schema"), dict) else {}
        description = str(active.get("tool_description") or "")
        conversational_context = str(active.get("parameter_conversational_context") or "").strip()
        if not conversational_context:
            conversational_context = self._collect_transaction_parameter_context(
                state=state, current_text=text
            )
        values = await extract_transaction_parameters(
            self.llm,
            text=text,
            tool_name=tool_name,
            missing_parameters=missing,
            known_arguments=known,
            parameter_schema=schema,
            tool_description=description,
            conversational_context=conversational_context,
        )
        if not values:
            return None
        state_decision.metadata = {
            **(state_decision.metadata or {}),
            "transaction_turn_consumed": True,
            "transaction_parameter_values": values,
            "transaction_parameter_source": "llm",
            "transaction_parameter_missing_before": missing,
        }
        return state_decision

    async def _transaction_state_interruption_candidate(
        self,
        state: dict[str, Any],
        *,
        text: str,
        state_decision: RouteDecision,
        abandon_only: bool = False,
    ) -> RouteDecision | None:
        """Detecta semanticamente mudança de intenção durante uma transação.

        Não existe lista de palavras para desistência. ABANDON é sempre uma
        decisão semântica do LLM baseada no contexto transacional. Uma possível
        nova intenção pode aparecer como hint do ``routing.yaml``, mas esse hint
        não decide abandono e não substitui a classificação semântica.
        """
        active_tx = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
        started_intent = str(active_tx.get("started_from_intent") or "").strip()
        previous = state.get("route_decision") or {}
        previous_intent = str(previous.get("intent") or state.get("intent") or started_intent).strip()

        configured_candidate = self._route_by_keyword(text)
        if configured_candidate is not None:
            different = (
                configured_candidate.agent != state_decision.agent
                or (started_intent and configured_candidate.intent != started_intent)
                or (previous_intent and not previous_intent.startswith("state:") and configured_candidate.intent != previous_intent)
            )

            # A configured candidate that resolves to the same intent/agent is not
            # sufficient to conclude that the active transaction continues.  The
            # user may be starting a *new instance of the same intent* with a
            # different transactional target (for example cancelling TIM Fashion
            # while Tamboro is awaiting confirmation).  In LLM mode keep the
            # candidate only as a semantic hint and let the transaction classifier
            # decide CONTINUE/REPLACE/ABANDON.  Without semantic classification we
            # retain the legacy state lock because guessing replacement from a
            # keyword alone would be unsafe.
            if not different and not (self.enable_llm_router and self.llm is not None):
                return None

            # During parameter collection, a configured keyword may be present in
            # a perfectly valid parameter answer (for example an order identifier
            # utterance containing the generic word "pedido").  When semantic
            # classification is available, use the configured route only as a
            # candidate hint and let the LLM decide CONTINUE, SHIFT or ABANDON.
            # This avoids
            # both failure modes: parameter extraction cannot hide a real new goal,
            # and a broad keyword cannot steal a legitimate parameter turn.
            if not (self.enable_llm_router and self.llm is not None):
                configured_candidate.metadata = {
                    **(configured_candidate.metadata or {}),
                    "transaction_interruption": "intent_shift",
                    "interrupted_state": state_decision.next_state,
                    "interrupted_agent": state_decision.agent,
                    "interrupted_intent": started_intent or previous_intent,
                    "interruption_source": "configured_routing",
                }
                return configured_candidate

        if not (self.enable_llm_router and self.llm is not None):
            return None

        allowed = [i for i in self.intents if i.enabled]
        allowed_payload = [
            {
                "intent": i.name,
                "agent": i.agent,
                "description": i.description,
                "examples": i.examples[:3],
                "domain": i.domain,
            }
            for i in allowed
        ]
        transaction_context = {
            "current_agent": state_decision.agent,
            "current_intent": started_intent or previous_intent,
            "transaction_status": state.get("transaction_status"),
            "tool_name": active_tx.get("tool_name"),
            # Structured arguments are part of the identity of the active
            # transaction.  They let the semantic classifier distinguish a new
            # instance of the same intent from a continuation without relying on
            # domain keywords or hard-coded product names.
            "active_arguments": dict(active_tx.get("arguments") or {}),
            "missing_parameters": list(state.get("missing_parameters") or []),
            "configured_candidate": (
                {
                    "intent": configured_candidate.intent,
                    "agent": configured_candidate.agent,
                    "confidence": configured_candidate.confidence,
                }
                if configured_candidate is not None
                else None
            ),
        }
        if abandon_only:
            system = (
                "Você decide somente se o usuário desistiu explicitamente da ação/transação ativa. "
                "Quando a transação estava coletando parâmetros, a pertinência ao parâmetro já foi avaliada antes desta etapa; "
                "portanto não transforme uma resposta pertinente ao parâmetro em abandono. "
                "Use o significado completo da mensagem e o contexto transacional; não use palavras isoladas como regra. "
                "Se houver desistência explícita da ação atual, retorne ABANDON. "
                "Quando o abandono vier acompanhado de um novo objetivo, também informe intent e agent desse novo objetivo. "
                "Quando for apenas abandono sem novo objetivo, intent e agent podem ser nulos. "
                "Se a mensagem apenas fornece parâmetro, confirma contexto, ou somente muda/adiciona outro objetivo sem "
                "desistir explicitamente da ação atual, retorne CONTINUE. "
                "Retorne somente JSON válido com decision, intent, agent, confidence, reason."
            )
        else:
            system = (
                "Você decide apenas se o turno atual continua a transação ativa, substitui a instância transacional ativa, "
                "ou muda de intenção. Use o significado da mensagem e o contexto transacional; não use palavras isoladas como regra. "
                "A extração dos parâmetros pendentes já foi tentada antes desta etapa e não consumiu o turno. "
                "Se ainda assim a mensagem for apenas uma resposta referencial/valor/nome ao dado pendente, retorne CONTINUE. "
                "Se o usuário continua com a MESMA intent, mas claramente inicia outra instância da operação com alvo/argumentos diferentes, "
                "retorne REPLACE e informe a mesma intent e agent. REPLACE significa substituir a transação ativa; não significa estado novo. "
                "Não use REPLACE quando o usuário apenas complementa/adiciona itens à mesma operação (por exemplo 'também', 'além desses'), "
                "nem quando apenas reformula ou confirma o mesmo alvo: nesses casos retorne CONTINUE. "
                "Se o usuário passou claramente a perseguir outro objetivo/intent sem desistir explicitamente da ação atual, "
                "retorne SHIFT e a nova intent permitida. "
                "Se o usuário desistiu explicitamente da ação/transação atual, retorne ABANDON. "
                "Quando ABANDON vier acompanhado de um novo objetivo, também informe intent e agent desse novo objetivo. "
                "Quando for apenas abandono sem novo objetivo, intent e agent podem ser nulos. "
                "Retorne somente JSON válido com decision, intent, agent, confidence, reason."
            )
        user = {
            "message": text,
            "transaction": transaction_context,
            "allowed_intents": allowed_payload,
            "session_context": (state.get("context") or {}).get("session", {}),
        }
        try:
            answer = await self.llm.ainvoke(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                temperature=0.0,
                fallback_max_tokens=512,
                profile_name="router",
                component_name="router",
                generation_name="llm.transaction_intent_shift",
            )
            data = self._parse_json(answer)
        except Exception as exc:
            logger.warning("Falha ao avaliar mudança semântica de intent transacional via LLM: %s", exc)
            return None

        decision_kind = str(data.get("decision") or "").strip().upper()
        if abandon_only:
            if decision_kind != "ABANDON":
                return None
        elif decision_kind not in {"SHIFT", "REPLACE", "ABANDON"}:
            return None
        confidence = float(data.get("confidence") or 0.0)
        if confidence < self.intent_shift_threshold:
            return None

        intent_name = str(data.get("intent") or "").strip()
        agent = str(data.get("agent") or "").strip()

        if decision_kind == "ABANDON":
            # ABANDON encerra explicitamente apenas a interação/transação ativa.
            # Pending topics de outros objetivos não são apagados aqui. Quando a
            # desistência também traz um novo objetivo, roteamos diretamente para
            # ele; em abandono puro, usamos um intent de estado sem tools para que
            # o agente atual apenas confirme o encerramento, sem rearmar a ação.
            if intent_name:
                agent = agent or str(self._agent_for_intent(intent_name) or "").strip()
                if not agent:
                    return None
                domain = self._domain_for_intent(intent_name)
                mcp_tools = self._tools_for_intent(intent_name)
            else:
                agent = str(state_decision.agent or state_decision.route or "").strip()
                if not agent:
                    return None
                intent_name = "state:TRANSACTION_ABANDONED"
                domain = None
                mcp_tools = []

            return RouteDecision(
                route=agent,
                agent=agent,
                intent=intent_name,
                confidence=confidence,
                reason=str(data.get("reason") or "Abandono explícito da transação ativa."),
                method="llm",
                metadata={
                    "transaction_interruption": "explicit_abandonment",
                    "interrupted_state": state_decision.next_state,
                    "interrupted_agent": state_decision.agent,
                    "interrupted_intent": started_intent or previous_intent,
                    "interruption_source": "semantic_classifier",
                    "configured_routing_hint": (
                        configured_candidate.intent if configured_candidate is not None else None
                    ),
                    "raw_llm_answer": answer[:1000],
                },
                domain=domain,
                mcp_tools=mcp_tools,
            )

        current_intent = started_intent or previous_intent
        if not intent_name:
            return None

        # Same-intent replacement is a transaction lifecycle event, not a new
        # conversation state.  It cancels only the active transaction instance
        # and re-enters normal routing for the same configured intent.
        if decision_kind == "REPLACE":
            if not current_intent or intent_name != current_intent:
                return None
            agent = agent or str(self._agent_for_intent(intent_name) or "").strip()
            if not agent:
                return None
            return RouteDecision(
                route=agent,
                agent=agent,
                intent=intent_name,
                confidence=confidence,
                reason=str(data.get("reason") or "Nova instância transacional da mesma intenção."),
                method="llm",
                metadata={
                    "transaction_interruption": "same_intent_replacement",
                    "interrupted_state": state_decision.next_state,
                    "interrupted_agent": state_decision.agent,
                    "interrupted_intent": current_intent,
                    "interruption_source": "semantic_classifier",
                    "configured_routing_hint": (
                        configured_candidate.intent if configured_candidate is not None else None
                    ),
                    "raw_llm_answer": answer[:1000],
                },
                domain=self._domain_for_intent(intent_name),
                mcp_tools=self._tools_for_intent(intent_name),
            )

        if intent_name == current_intent:
            return None
        agent = agent or str(self._agent_for_intent(intent_name) or "").strip()
        if not agent:
            return None

        candidate = RouteDecision(
            route=agent,
            agent=agent,
            intent=intent_name,
            confidence=confidence,
            reason=str(data.get("reason") or "Mudança semântica de intenção durante transação."),
            method="llm",
            metadata={
                "transaction_interruption": "intent_shift",
                "interrupted_state": state_decision.next_state,
                "interrupted_agent": state_decision.agent,
                "interrupted_intent": started_intent or previous_intent,
                "interruption_source": "semantic_classifier",
                "configured_routing_hint": (
                    configured_candidate.intent if configured_candidate is not None else None
                ),
                "raw_llm_answer": answer[:1000],
            },
            domain=self._domain_for_intent(intent_name),
            mcp_tools=self._tools_for_intent(intent_name),
        )
        return candidate

    @staticmethod
    def _is_explicit_intent_shift(decision: RouteDecision) -> bool:
        """Compatibilidade: keyword configurada é um sinal explícito de routing.

        Não há regra por conteúdo ou tamanho da keyword; o framework confia na
        configuração do domínio.
        """
        return decision.method == "keyword" and bool(str((decision.metadata or {}).get("matched_keyword") or "").strip())

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
                keyword_tokens = self._keyword_tokens(kw)
                text_tokens = self._keyword_tokens(text)
                if (
                    (len(keyword_tokens) == 1 and keyword_tokens[0] in text_tokens)
                    or (len(keyword_tokens) > 1 and kw_normalized in normalized)
                ):
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

    async def _plan_multi_intent_by_llm(
        self,
        text: str,
        state: dict[str, Any],
        *,
        confirmation_primary: tuple[str, str] | None = None,
    ):
        """Classify compound requests and validate them through the planner.

        The model returns only intent names and source fragments. Agent, domain
        and tool ownership always come from the loaded routing catalog.
        """
        allowed = [intent for intent in self.intents if intent.enabled]
        allowed_payload = [
            {
                "intent": intent.name,
                "description": intent.description,
                "examples": intent.examples[:3],
            }
            for intent in allowed
        ]
        secondary_only = confirmation_primary is not None
        system = (
            "Você é um classificador multi-intent. Identifique objetivos independentes "
            "expressos explicitamente pelo usuário. Não execute ações e não responda ao "
            "usuário. Use somente nomes presentes em allowed_intents. Para um pedido "
            "explícito que não pertença a nenhuma intent permitida, use intent=null e "
            "unsupported=true. Não transforme detalhes, parâmetros ou objetos de uma "
            "mesma solicitação em novas intents. "
            + (
                "A confirmação da transação já foi consumida; classifique somente o pedido "
                "secundário fornecido e retorne exatamente uma operação. "
                if secondary_only else
                "Retorne pelo menos duas operações somente quando houver múltiplos objetivos. "
            )
            + "Retorne somente JSON válido no formato: "
            '{"confidence":0.0,"operations":[{"intent":"nome_ou_null",'
            '"source_text":"trecho literal","unsupported":false}]}.'
        )
        active_tx = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
        payload = {
            "message": text,
            "allowed_intents": allowed_payload,
            "secondary_only": secondary_only,
            "transaction_context": ({
                "status": state.get("transaction_status"),
                "started_from_intent": active_tx.get("started_from_intent"),
                "tool_name": active_tx.get("tool_name"),
            } if active_tx else None),
        }
        answer = await self.llm.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            fallback_max_tokens=768,
            profile_name="router",
            component_name="router.multi_intent",
            generation_name="llm.router.multi_intent",
        )
        data = self._parse_json(answer)
        if confirmation_primary is not None:
            return self.multi_intent_planner.plan_confirmation_from_semantic(
                data,
                primary_intent=confirmation_primary[0],
                primary_agent=confirmation_primary[1],
            )
        return self.multi_intent_planner.plan_from_semantic(data)

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
            "Classifique semanticamente a mensagem do usuário em uma das intents permitidas. "
            "Quando houver uma transação ativa, considere a intent que iniciou a transação, "
            "o estado transacional e os parâmetros ainda pendentes. Se a mensagem apenas "
            "responder ao que está pendente, mantenha a intent da transação. Se o usuário "
            "passar a perseguir outro objetivo, classifique a nova intent. "
            "Retorne somente JSON válido com: intent, agent, confidence, reason. "
            "Não responda ao usuário final."
        )
        active_tx = state.get("active_transaction") if isinstance(state.get("active_transaction"), dict) else {}
        transaction_context = {
            "status": state.get("transaction_status"),
            "started_from_intent": active_tx.get("started_from_intent"),
            "tool_name": active_tx.get("tool_name"),
            "missing_parameters": list(state.get("missing_parameters") or []),
        } if active_tx else None
        user = {
            "message": text,
            "allowed_intents": allowed_payload,
            "session_context": ({} if state.get("operational_context_reset") else (state.get("context") or {}).get("session", {})),
            "transaction_context": transaction_context,
        }
        answer = await self.llm.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
            fallback_max_tokens=512,
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
        return parse_json_object(text)

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
