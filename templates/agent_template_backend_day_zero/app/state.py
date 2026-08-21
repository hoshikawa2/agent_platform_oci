from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    tenant_id: str
    agent_id: str
    session_id: str
    conversation_key: str
    workflow_id: str
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
    available_mcp_tools: list[str]
    selected_tool_call: dict[str, Any]
    pending_tool_call: dict[str, Any]
    active_transaction: dict[str, Any]
    last_transaction: dict[str, Any]
    transaction_status: str
    transaction_pre_validation: dict[str, Any]
    confirmation_required: bool
    confirmation_received: bool
    tool_policy_result: dict[str, Any]
    missing_parameters: list[str]
    supervisor_plan: dict[str, Any]
    supervisor_results: list[dict[str, Any]]
    active_agent: str
    route_bypassed: bool
    continuity_signal: dict[str, Any]
    session_control: str
    session_ended: bool
    human_handoff_requested: bool
    blocked: bool
    supervisor_action: str
    supervisor_guidance: str
    supervisor_attempt: int
    supervisor_handover_reason: str
    output_supervisor_results: list[dict[str, Any]]
    output_guardrails_already_applied: bool
    long_term_memories: list[dict[str, Any]]
    long_term_memory_context: str
    long_term_memory_write_result: dict[str, Any]
