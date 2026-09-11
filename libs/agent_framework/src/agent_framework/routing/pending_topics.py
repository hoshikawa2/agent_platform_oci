from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .multi_intent import MultiIntentPlanner

AgentHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class PendingTopicDrain:
    answer: str
    agent_responses: list[dict[str, Any]]
    pending_topics: list[dict[str, Any]]
    handled_topics: list[dict[str, Any]]
    mcp_results: list[dict[str, Any]]
    rag_results: list[dict[str, Any]]
    state_patch: dict[str, Any]


_LIVE_TRANSACTION_STATUSES = {
    "COLLECTING_PARAMETERS", "AWAITING_CONFIRMATION", "WAITING_CONFIRMATION",
    "PENDING", "RUNNING", "IN_PROGRESS",
}

_TRANSACTION_STATE_KEYS = {
    "active_transaction", "transaction_status", "transaction_pre_validation",
    "confirmation_required", "confirmation_received", "selected_tool_call",
    "pending_tool_call", "pending_tool_clarification", "pending_domain_workflow",
    "missing_parameters", "tool_policy_result", "next_state", "workflow_id",
}


def _has_live_transaction(state: dict[str, Any]) -> bool:
    active = state.get("active_transaction")
    active_status = active.get("status") if isinstance(active, dict) else None
    status = str(active_status or state.get("transaction_status") or "").upper()
    if status:
        return status in _LIVE_TRANSACTION_STATUSES
    return bool(state.get("confirmation_required") or state.get("pending_tool_call"))


async def drain_pending_topics(
    state: dict[str, Any],
    candidate: str,
    handlers: dict[str, AgentHandler],
) -> PendingTopicDrain:
    """Drain read-only topics and retain anything that cannot finish safely."""
    route = state.get("route_decision") if isinstance(state.get("route_decision"), dict) else {}
    plan = route.get("metadata", {}).get("multi_intent_plan")
    topics = list(state.get("pending_topics") or (
        plan.get("operations", [])[1:] if isinstance(plan, dict) else []
    ))
    remaining: list[dict[str, Any]] = []
    handled = list(state.get("handled_topics") or [])
    combined_mcp_results = list(state.get("mcp_results") or [])
    combined_rag_results = list(state.get("rag_results") or [])
    secondary_answers: list[str] = []
    state_patch: dict[str, Any] = {}
    may_promote_deferred = not _has_live_transaction(state)
    agent_responses = list(state.get("agent_responses") or [])
    if not agent_responses and str(candidate or "").strip():
        primary_agent = str(
            state.get("active_agent")
            or state.get("route")
            or route.get("agent")
            or route.get("route")
            or state.get("agent_id")
            or "agent"
        )
        agent_responses.append({
            "agent": primary_agent,
            "intent": state.get("intent") or route.get("intent"),
            "answer": str(candidate).strip(),
            "primary": True,
            "status": "completed",
        })
    for topic in topics:
        disposition = topic.get("disposition")
        promoted = False
        if disposition == "defer":
            if not may_promote_deferred:
                remaining.append(topic)
                continue
            topic = {**topic, "disposition": "execute", "status": "pending"}
            disposition = "execute"
            promoted = True
            may_promote_deferred = False
        if disposition != "execute":
            handled.append({**topic, "status": "completed"})
            continue
        handler = handlers.get(str(topic.get("agent") or ""))
        if handler is None:
            remaining.append(topic)
            continue
        source_text = str(topic.get("source_text") or "").strip()
        child = {
            **state,
            "user_text": source_text,
            "message_text": source_text,
            "sanitized_input": source_text,
            "route": topic.get("agent"),
            "active_agent": topic.get("agent"),
            "intent": topic.get("intent"),
            "domain": topic.get("domain"),
            "mcp_tools": topic.get("tools") or [],
            "route_decision": {
                "route": topic.get("agent"), "agent": topic.get("agent"),
                "intent": topic.get("intent"), "mcp_tools": topic.get("tools") or [],
                "metadata": {"multi_intent_secondary": True},
            },
            "active_transaction": None,
            "transaction_status": None,
            "transaction_pre_validation": None,
            "confirmation_required": False,
            "confirmation_received": False,
            "selected_tool_call": {},
            "pending_tool_call": {},
            "pending_tool_clarification": None,
            "pending_domain_workflow": None,
            "missing_parameters": [],
            "tool_policy_result": None,
            "mcp_results": [],
            "available_mcp_tools": topic.get("tools") or [],
            "next_state": None,
            "workflow_id": None,
            "route_bypassed": False,
        }
        try:
            result = await handler(child)
        except Exception:
            remaining.append(topic)
            continue
        answer = str((result or {}).get("answer") or "").strip()
        if not answer:
            remaining.append(topic)
            continue
        for evidence in (result or {}).get("mcp_results") or []:
            if isinstance(evidence, dict) and evidence not in combined_mcp_results:
                combined_mcp_results.append(evidence)
        rag_metadata = (result or {}).get("rag")
        rag_context = str((result or {}).get("rag_context") or "").strip()
        if isinstance(rag_metadata, dict):
            rag_evidence = {
                "operation_id": topic.get("operation_id"),
                "intent": topic.get("intent"),
                "agent": topic.get("agent"),
                "source_text": source_text,
                "metadata": rag_metadata,
            }
            if rag_context:
                rag_evidence["context"] = rag_context
            if rag_evidence not in combined_rag_results:
                combined_rag_results.append(rag_evidence)
        secondary_answers.append(answer)
        if promoted:
            agent_responses = [{**item, "primary": False} for item in agent_responses]
        agent_responses.append({
            "operation_id": topic.get("operation_id"),
            "agent": topic.get("agent"),
            "intent": topic.get("intent"),
            "answer": answer,
            "primary": promoted,
            "status": "completed",
        })
        if promoted:
            for key in _TRANSACTION_STATE_KEYS:
                if key in (result or {}):
                    state_patch[key] = result[key]
            state_patch.update({
                "route": topic.get("agent"),
                "active_agent": topic.get("agent"),
                "intent": topic.get("intent"),
                "domain": topic.get("domain"),
                "mcp_tools": topic.get("tools") or [],
                # Replace the completed transaction's continuity snapshot so
                # the next reply cannot be routed back to the previous agent.
                "route_decision": {
                    "route": topic.get("agent"),
                    "agent": topic.get("agent"),
                    "intent": topic.get("intent"),
                    "domain": topic.get("domain"),
                    "mcp_tools": topic.get("tools") or [],
                    "next_state": (result or {}).get("next_state"),
                    "metadata": {
                        "multi_intent_secondary": True,
                        "promoted_from_pending_topics": True,
                        "operation_id": topic.get("operation_id"),
                    },
                },
            })
        handled.append({**topic, "status": "completed"})

    secondary_answers.extend(MultiIntentPlanner.public_messages(plan))
    unique = []
    for answer in secondary_answers:
        if answer and answer.casefold() not in candidate.casefold() and answer not in unique:
            unique.append(answer)
    if unique:
        secondary = "\n\n".join(unique)
        candidate = f"{candidate.rstrip()}\n\n{secondary}".strip()
    return PendingTopicDrain(
        answer=candidate,
        agent_responses=agent_responses,
        pending_topics=remaining,
        handled_topics=handled,
        mcp_results=combined_mcp_results,
        rag_results=combined_rag_results,
        state_patch=state_patch,
    )
