from __future__ import annotations

from agent_framework.llm.structured_output import parse_json_object

import json
import logging
from dataclasses import dataclass
from typing import Any

from .models import IntentDefinition, RouteDecision

logger = logging.getLogger("agent_framework.routing.continuity")


@dataclass(slots=True)
class ContinuityEvaluation:
    decision: str
    confidence: float
    reason: str
    raw: str


class SemanticRouteContinuity:
    """LLM-only semantic turn control and route stickiness.

    This component deliberately contains no linguistic regexes, keyword lists or
    domain-specific rules. It classifies the turn as CONTINUE, ROUTE,
    HUMAN_HANDOFF or END_SESSION. Low confidence, timeout and parsing errors fall
    back to the normal EnterpriseRouter.
    """

    def __init__(self, settings: Any, llm: Any, telemetry: Any = None):
        self.settings = settings
        self.llm = llm
        self.telemetry = telemetry
        self.enabled = bool(getattr(settings, "ENABLE_ROUTE_STICKINESS", False))
        self.profile_name = str(
            getattr(settings, "ROUTE_STICKINESS_LLM_PROFILE", "route_continuity")
        )
        self.confidence_threshold = float(
            getattr(settings, "ROUTE_STICKINESS_CONFIDENCE_THRESHOLD", 0.90)
        )
        self.history_turns = max(
            1, int(getattr(settings, "ROUTE_STICKINESS_HISTORY_TURNS", 2))
        )

    async def evaluate(
        self,
        state: dict[str, Any],
        *,
        intents: list[IntentDefinition],
    ) -> RouteDecision | None:
        active_agent = str(state.get("active_agent") or "").strip()
        if not self.enabled or self.llm is None:
            return None

        enabled_intents = [intent for intent in intents if intent.enabled]
        known_agents = {intent.agent for intent in enabled_intents}
        if active_agent and active_agent not in known_agents:
            active_agent = ""

        text = str(state.get("sanitized_input") or state.get("user_text") or "").strip()
        if not text:
            return None

        try:
            evaluation = await self._classify(
                state,
                text=text,
                active_agent=active_agent,
                intents=enabled_intents,
            )
        except Exception as exc:
            logger.warning("Route stickiness LLM failed; using EnterpriseRouter: %s", exc)
            await self._emit(
                state,
                {
                    "decision": "ROUTE",
                    "confidence": 0.0,
                    "reason": f"continuity_error:{type(exc).__name__}",
                    "active_agent": active_agent,
                    "route_bypassed": False,
                },
            )
            return None

        accepted = evaluation.confidence >= self.confidence_threshold
        bypass = evaluation.decision == "CONTINUE" and accepted and bool(active_agent)
        await self._emit(
            state,
            {
                "decision": evaluation.decision,
                "confidence": evaluation.confidence,
                "reason": evaluation.reason,
                "active_agent": active_agent,
                "route_bypassed": bypass,
                "profile_name": self.profile_name,
            },
        )
        if not accepted:
            return None

        if evaluation.decision == "HUMAN_HANDOFF":
            return RouteDecision(
                route="human_handoff",
                agent="human_handoff",
                intent="human_handoff",
                confidence=evaluation.confidence,
                reason=evaluation.reason or "O usuário solicitou atendimento humano.",
                method="continuity",
                handoff=True,
                metadata={
                    "route_bypassed": True,
                    "continuity_decision": evaluation.decision,
                    "continuity_profile": self.profile_name,
                    "session_control": "HUMAN_HANDOFF",
                    "raw_llm_answer": evaluation.raw[:1000],
                },
            )

        if evaluation.decision == "END_SESSION":
            return RouteDecision(
                route="end_session",
                agent="end_session",
                intent="end_session",
                confidence=evaluation.confidence,
                reason=evaluation.reason or "O usuário solicitou o encerramento do atendimento.",
                method="continuity",
                metadata={
                    "route_bypassed": True,
                    "continuity_decision": evaluation.decision,
                    "continuity_profile": self.profile_name,
                    "session_control": "END_SESSION",
                    "raw_llm_answer": evaluation.raw[:1000],
                },
            )

        if not bypass:
            return None

        previous = state.get("route_decision") or {}
        intent_name = str(previous.get("intent") or state.get("intent") or "continuity")
        domain = previous.get("domain") or state.get("domain")
        tools = previous.get("mcp_tools") or state.get("mcp_tools") or []
        return RouteDecision(
            route=active_agent,
            agent=active_agent,
            intent=intent_name,
            confidence=evaluation.confidence,
            reason=evaluation.reason or "Mensagem continua sob responsabilidade do agente ativo.",
            method="continuity",
            metadata={
                "route_bypassed": True,
                "continuity_decision": evaluation.decision,
                "continuity_profile": self.profile_name,
                "raw_llm_answer": evaluation.raw[:1000],
            },
            domain=domain,
            mcp_tools=list(tools),
        )

    async def _classify(
        self,
        state: dict[str, Any],
        *,
        text: str,
        active_agent: str,
        intents: list[IntentDefinition],
    ) -> ContinuityEvaluation:
        agent_capabilities = self._agent_capabilities(intents)
        history = self._compact_history(state.get("history") or [])
        previous = state.get("route_decision") or {}

        system = (
            "Você é um classificador semântico de continuidade de rota. "
            "Sua única tarefa é classificar o tratamento global da mensagem atual. "
            "Use CONTINUE somente quando existir agente ativo e ele continuar claramente adequado para "
            "uma continuação, aprofundamento, resposta, correção ou referência ao contexto anterior. "
            "Use HUMAN_HANDOFF quando o usuário solicitar explicitamente atendimento por uma pessoa. "
            "Use END_SESSION quando o usuário indicar claramente que deseja finalizar o atendimento e "
            "não precisa continuar. Use ROUTE para novo assunto, possível responsabilidade de outro "
            "agente, ausência de agente ativo, contexto insuficiente ou qualquer dúvida. "
            "Não responda ao usuário e não selecione um novo agente. Retorne somente JSON válido com "
            "decision, confidence e reason. decision deve ser CONTINUE, ROUTE, HUMAN_HANDOFF ou END_SESSION."
        )
        payload = {
            "active_agent": active_agent,
            "active_agent_capabilities": agent_capabilities.get(active_agent, []),
            "other_agents": {
                agent: capabilities
                for agent, capabilities in agent_capabilities.items()
                if agent != active_agent
            },
            "previous_intent": previous.get("intent") or state.get("intent"),
            "previous_domain": previous.get("domain") or state.get("domain"),
            "recent_history": history,
            "current_message": text,
        }
        answer = await self.llm.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            profile_name=self.profile_name,
            component_name="route_continuity",
            generation_name="llm.route_continuity",
        )
        data = self._parse_json(answer)
        decision = str(data.get("decision") or "ROUTE").strip().upper()
        if decision not in {"CONTINUE", "ROUTE", "HUMAN_HANDOFF", "END_SESSION"}:
            decision = "ROUTE"
        if decision == "CONTINUE" and not active_agent:
            decision = "ROUTE"
        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = min(1.0, max(0.0, confidence))
        return ContinuityEvaluation(
            decision=decision,
            confidence=confidence,
            reason=str(data.get("reason") or ""),
            raw=str(answer),
        )

    def _agent_capabilities(self, intents: list[IntentDefinition]) -> dict[str, list[str]]:
        capabilities: dict[str, list[str]] = {}
        for intent in intents:
            description = intent.description or intent.name
            capabilities.setdefault(intent.agent, []).append(description)
        return capabilities

    def _compact_history(self, history: list[dict[str, Any]]) -> list[dict[str, str]]:
        limit = self.history_turns * 2
        compact: list[dict[str, str]] = []
        for message in history[-limit:]:
            role = str(message.get("role") or message.get("type") or "unknown")
            content = str(message.get("content") or "").strip()
            if content:
                compact.append({"role": role, "content": content[:1200]})
        return compact

    def _parse_json(self, answer: Any) -> dict[str, Any]:
        return parse_json_object(answer)

    async def _emit(self, state: dict[str, Any], payload: dict[str, Any]) -> None:
        if self.telemetry:
            await self.telemetry.event(
                "router.continuity",
                {
                    "session_id": state.get("conversation_key") or state.get("session_id"),
                    **payload,
                },
            )
