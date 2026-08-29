# Fix: terminal workflow lifecycle in the same conversation session

## Problem
A conversational workflow could return `status=COMPLETED` and a final response (`workflow_response_final=true`), while a stale `pending_domain_workflow` / `expected_input` latch remained durable in LangGraph state. A later user message in the same `session_id` could therefore be interpreted as a resume of the already completed workflow.

Scenario 22 reproduces the issue: after invoice explanation is accepted and protocol is returned, `ah espera` must be treated as a new interaction in the same conversation session, not as SIM/NAO/CONTINUAR for the old workflow.

## Semantics after the fix
- Conversation identifiers are preserved (`session_id`, `session_key`, `conversation_key`, `user_id`, `msisdn`, customer/contract keys).
- The completed workflow is terminal only as an interaction/workflow, not as the user session.
- `pending_domain_workflow`, `pending_tool_clarification`, `workflow_input_reprompt`, active transaction latches and `next_state` are cleared.
- `transaction_status` is materialized as `COMPLETED` (or `FAILED`) so terminal state wins over stale checkpoints.
- The next message is routed as a new interaction in the same session.
- Router and input-guardrail layers defensively ignore stale paused-workflow contracts when transaction status is already terminal.

## Main files
- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `libs/agent_framework/src/agent_framework/routing/enterprise_router.py`
- `../app/workflows/agent_graph.py`
- `tests/test_paused_workflow_resume_precedence.py`

## Validation
- Framework transactional/routing suites: 119 passed.
- Focused migration suites: 12 passed.
- Full `tests/migration`: 789 passed.
