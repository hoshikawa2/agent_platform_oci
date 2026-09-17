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
    operation_results: dict[str, dict[str, Any]]


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
    # Persisted plan has precedence because route_decision is intentionally
    # replaced on continuation/confirmation turns. Keeping the plan outside
    # route_decision lets a terminal primary operation be correlated back to
    # its original operation_id after WAITING_*/AWAITING_CONFIRMATION.
    plan = state.get("multi_intent_plan")
    if not isinstance(plan, dict):
        plan = route.get("metadata", {}).get("multi_intent_plan")
    # `pending_topics` is the authoritative execution queue.  Never rebuild it
    # from the persisted multi-intent plan on continuation turns: the plan is
    # durable read-only context, while pending_topics represents work that is
    # still allowed to execute.  Rehydrating from plan.operations would execute
    # already-completed secondary operations again after a confirmation/resume.
    topics = list(state.get("pending_topics") or [])
    remaining: list[dict[str, Any]] = []
    handled = list(state.get("handled_topics") or [])
    combined_mcp_results = list(state.get("mcp_results") or [])
    combined_rag_results = list(state.get("rag_results") or [])
    secondary_answers: list[str] = []
    state_patch: dict[str, Any] = {}
    may_promote_deferred = not _has_live_transaction(state)

    # agent_responses is only the visible projection for the current turn.
    # Durable operation data must not be kept there because checkpointed
    # responses from a previous plan would leak into later turns.
    operation_results = dict(state.get("operation_results") or {})

    # Promote the primary operation to durable operation_results only when it
    # is terminal.  On the first turn of a transactional operation the same
    # candidate may merely be a confirmation prompt, so _has_live_transaction
    # deliberately prevents an early/false COMPLETED record.
    primary_operation = None
    if isinstance(plan, dict):
        operations = plan.get("operations") or []
        if operations and isinstance(operations[0], dict):
            primary_operation = operations[0]

    def _primary_terminal_status() -> str | None:
        if not isinstance(primary_operation, dict) or _has_live_transaction(state):
            return None
        terminal_map = {
            "COMPLETED": "completed",
            "FAILED": "failed",
            "CANCELLED": "cancelled",
            "BLOCKED": "blocked",
            "OUT_OF_SCOPE": "out_of_scope",
        }
        active = state.get("active_transaction")
        active_status = active.get("status") if isinstance(active, dict) else None
        tx_status = str(active_status or state.get("transaction_status") or "").upper()
        if tx_status in terminal_map:
            return terminal_map[tx_status]

        # Workflow-backed MCP results commonly carry the terminal status under
        # result.status instead of transaction_status.  Prefer the most recent
        # current-turn result.
        for evidence in reversed(list(state.get("mcp_results") or [])):
            if not isinstance(evidence, dict):
                continue
            status = str(evidence.get("transaction_status") or "").upper()
            result = evidence.get("result")
            if not status and isinstance(result, dict):
                status = str(result.get("status") or "").upper()
            if status in terminal_map:
                return terminal_map[status]
            if evidence.get("ok") is False:
                return "failed"
            if evidence.get("ok") is True:
                return "completed"

        # Read-only/non-tool primaries are terminal when the agent has produced
        # a candidate and there is no live transaction latch.
        if not (primary_operation.get("tools") or []):
            return "completed"
        return None

    primary_status = _primary_terminal_status()
    if primary_status:
        operation_id = str(primary_operation.get("operation_id") or "").strip()
        if operation_id:
            operation_results[operation_id] = {
                "operation_id": operation_id,
                "plan_id": plan.get("plan_id") if isinstance(plan, dict) else None,
                "agent": primary_operation.get("agent"),
                "intent": primary_operation.get("intent"),
                "domain": primary_operation.get("domain"),
                "source_text": str(primary_operation.get("source_text") or "").strip(),
                "status": primary_status,
                "answer": str(candidate or "").strip(),
                "mcp_results": list(state.get("mcp_results") or []),
                "rag_results": list(state.get("rag_results") or []),
                "transaction_status": state.get("transaction_status"),
                "transaction_pre_validation": state.get("transaction_pre_validation"),
                "transaction_evidence": list(state.get("transaction_evidence") or []),
            }

    agent_responses: list[dict[str, Any]] = []
    if str(candidate or "").strip():
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
    current_plan_id = str(plan.get("plan_id") or "").strip() if isinstance(plan, dict) else ""

    for topic in topics:
        operation_id = str(topic.get("operation_id") or "").strip()
        existing_result = operation_results.get(operation_id) if operation_id else None
        if isinstance(existing_result, dict):
            existing_status = str(existing_result.get("status") or "").strip().lower()
            existing_plan_id = str(existing_result.get("plan_id") or "").strip()
            same_plan = bool(current_plan_id and existing_plan_id == current_plan_id)
            # Compatibility for results created before plan_id was persisted:
            # only treat them as the same operation when the durable identity
            # fields still match the currently queued topic.
            if not existing_plan_id and current_plan_id:
                same_plan = all(
                    str(existing_result.get(key) or "").strip() == str(topic.get(key) or "").strip()
                    for key in ("agent", "intent", "domain", "source_text")
                )
            if same_plan and existing_status in {"completed", "failed", "cancelled", "blocked", "out_of_scope"}:
                # Completed operations are durable read-only context.  They can
                # be consumed by later processing through operation_results, but
                # are never dispatched or re-projected by the execution queue.
                handled.append({**topic, "plan_id": current_plan_id or None, "status": existing_status})
                continue

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
            # Durable completed results are available to downstream agents as
            # read-only operational context for dependency/parameter reuse.
            "operation_results": operation_results,
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
        operation_id = str(topic.get("operation_id") or "").strip()
        if operation_id:
            operation_results[operation_id] = {
                "operation_id": operation_id,
                "plan_id": current_plan_id or None,
                "agent": topic.get("agent"),
                "intent": topic.get("intent"),
                "domain": topic.get("domain"),
                "source_text": source_text,
                "status": "completed",
                "answer": answer,
                "mcp_results": list((result or {}).get("mcp_results") or []),
                "rag": (result or {}).get("rag"),
                "rag_context": (result or {}).get("rag_context"),
            }
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
        handled.append({**topic, "plan_id": current_plan_id or None, "status": "completed"})

    # Public planner messages belong to the turn that created the plan.  A
    # persisted plan may be read on later confirmation/resume turns, but its
    # presentation messages must not be emitted again.
    route_plan = ((route.get("metadata") or {}).get("multi_intent_plan") if isinstance(route, dict) else None)
    if isinstance(route_plan, dict):
        secondary_answers.extend(MultiIntentPlanner.public_messages(route_plan))
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
        operation_results=operation_results,
    )
