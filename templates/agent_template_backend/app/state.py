from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    tenant_id: str
    agent_id: str
    session_id: str
    conversation_key: str
    agent_profile: dict[str, Any]
    user_text: str
    sanitized_input: str
    route: str
    intent: str
    route_decision: dict[str, Any]
    answer: str
    final_answer: str
    history: list[dict[str, Any]]
    context: dict[str, Any]
    guardrail_decisions: list[dict[str, Any]]
    judge_results: list[dict[str, Any]]
    next_state: str
    domain: str
    mcp_tools: list[str]
    mcp_results: list[dict[str, Any]]
    supervisor_plan: dict[str, Any]
    supervisor_results: list[dict[str, Any]]
    active_agent: str
    blocked: bool
    supervisor_action: str
    supervisor_guidance: str
    supervisor_attempt: int
    supervisor_handover_reason: str
    output_supervisor_results: list[dict[str, Any]]
    output_guardrails_already_applied: bool
