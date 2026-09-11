from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .multi_intent import MultiIntentPlanner

AgentHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class PendingTopicDrain:
    answer: str
    pending_topics: list[dict[str, Any]]
    handled_topics: list[dict[str, Any]]
    mcp_results: list[dict[str, Any]]
    rag_results: list[dict[str, Any]]


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
    for topic in topics:
        disposition = topic.get("disposition")
        if disposition == "defer":
            remaining.append(topic)
            continue
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
        candidate, remaining, handled, combined_mcp_results, combined_rag_results
    )
