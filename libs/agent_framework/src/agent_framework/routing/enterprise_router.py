from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from .config_loader import load_intents, load_router_defaults, load_state_policies
from .continuity import SemanticRouteContinuity
from .models import IntentDefinition, RouteDecision, RouterStatePolicy
from agent_framework.llm.structured_output import parse_json_object
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

            # Confirmation is the only transaction input with absolute precedence:
            # an explicit yes/no answers the confirmation contract itself.
            if tx_status == "AWAITING_CONFIRMATION":
                consumed = await self._transaction_parameter_precedence(
                    state, text=str(text), state_decision=state_decision
                )
                if consumed is not None:
                    await self._emit(consumed, state)
                    return consumed

            # Transaction parameter precedence is absolute while collecting:
            # first let the active transaction try to consume the current turn.
            # Only when NO pending parameter can be extracted do we ask the
            # semantic classifier whether the user changed goals.  This prevents
            # value/name/reference answers (for example "a de 14,99") from being
            # stolen by a semantically plausible but incompatible intent.
            if tx_status == "COLLECTING_PARAMETERS":
                consumed = await self._transaction_parameter_precedence(
                    state, text=str(text), state_decision=state_decision
                )
                if consumed is not None:
                    await self._emit(consumed, state)
                    return consumed

            interruption = await self._transaction_state_interruption_candidate(
                state, text=str(text), state_decision=state_decision
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

            if tx_status == "COLLECTING_PARAMETERS":
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


    async def _transaction_parameter_precedence(
        self,
        state: dict[str, Any],
        *,
        text: str,
        state_decision: RouteDecision,
    ) -> RouteDecision | None:
        """Try to consume the turn under the active transaction contract first.

        AWAITING_CONFIRMATION consumes an explicit confirmation before any shift
        classification. COLLECTING_PARAMETERS also has precedence: if at least one
        pending parameter can be extracted, the active transaction keeps ownership
        of the turn. Semantic intent-shift is evaluated only when extraction returns
        no usable pending parameter.
        """
        tx_status = str(state.get("transaction_status") or "").strip().upper()
        if tx_status == "AWAITING_CONFIRMATION":
            confirmation = parse_transaction_confirmation(text)
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
    ) -> RouteDecision | None:
        """Detecta semanticamente mudança de intenção durante uma transação.

        Não existe lista de palavras para desistência ou mudança de assunto. Uma
        interrupção nasce de uma intent diferente resolvida por uma keyword
        configurada no ``routing.yaml`` ou, na ausência dela, por uma decisão
        semântica do LLM com o contexto da transação pendente.
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
            if not different:
                return None

            # During parameter collection, a configured keyword may be present in
            # a perfectly valid parameter answer (for example an order identifier
            # utterance containing the generic word "pedido").  When semantic
            # classification is available, use the configured route only as a
            # candidate hint and let the LLM decide CONTINUE vs SHIFT.  This avoids
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
        system = (
            "Você decide apenas se o turno atual continua a transação ativa ou muda de intenção. "
            "Use o significado da mensagem e o contexto transacional; não use palavras isoladas como regra. "
            "A extração dos parâmetros pendentes já foi tentada antes desta etapa e não consumiu o turno. "
            "Se ainda assim a mensagem for apenas uma resposta referencial/valor/nome ao dado pendente, retorne CONTINUE. "
            "Se o usuário passou claramente a perseguir outro objetivo, retorne SHIFT e a nova intent permitida. "
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
                max_tokens=512,
                profile_name="router",
                component_name="router",
                generation_name="llm.transaction_intent_shift",
            )
            data = self._parse_json(answer)
        except Exception as exc:
            logger.warning("Falha ao avaliar mudança semântica de intent transacional via LLM: %s", exc)
            return None

        if str(data.get("decision") or "").strip().upper() != "SHIFT":
            return None
        confidence = float(data.get("confidence") or 0.0)
        if confidence < self.intent_shift_threshold:
            return None

        intent_name = str(data.get("intent") or "").strip()
        if not intent_name or intent_name == (started_intent or previous_intent):
            return None
        agent = str(data.get("agent") or self._agent_for_intent(intent_name) or "").strip()
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
