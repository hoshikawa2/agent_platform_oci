from __future__ import annotations

from typing import Any, Callable

from .output_supervisor import OutputSupervisor
from .rail_action import RailAction


def inject_guidance(prompt: str, guidance: str | None) -> str:
    if not guidance:
        return prompt
    return f"{prompt}\n\nInstruções de correção do supervisor:\n{guidance.strip()}"


def to_langgraph_node(
    supervisor: OutputSupervisor,
    *,
    candidate_key: str = "candidate_response",
    context_key: str = "context",
) -> Callable[[dict[str, Any]], Any]:
    async def node(state: dict[str, Any]) -> dict[str, Any]:
        candidate = state.get(candidate_key) or state.get("response") or state.get("answer") or ""
        context = dict(state.get(context_key) or {})
        context.setdefault("supervisor_attempt", int(state.get("supervisor_attempt", 0)))
        decision = await supervisor.evaluate(candidate, context)
        update = dict(state)
        update["supervisor_action"] = decision.action.value
        update["supervisor_guidance"] = decision.guidance
        update["supervisor_handover_reason"] = decision.handover_reason
        update["supervisor_decision"] = decision
        if decision.action == RailAction.RETRY:
            update["supervisor_attempt"] = int(state.get("supervisor_attempt", 0)) + 1
        if decision.approved:
            update[candidate_key] = decision.candidate
            update["response"] = decision.candidate
        elif decision.action == RailAction.BLOCK:
            update["response"] = decision.fallback_message
        elif decision.action == RailAction.HANDOVER:
            update["response"] = "Vou encaminhar seu atendimento para continuidade com um especialista."
        return update
    return node


def to_langgraph_router(
    *,
    retry_target: str = "llm",
    handover_target: str = "handover",
    end_target: str = "__end__",
) -> Callable[[dict[str, Any]], str]:
    def route(state: dict[str, Any]) -> str:
        action = state.get("supervisor_action")
        if action == RailAction.RETRY.value:
            return retry_target
        if action == RailAction.HANDOVER.value:
            return handover_target
        return end_target
    return route
