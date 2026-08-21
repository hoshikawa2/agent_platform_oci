# Developer Guide — Multi-turn Transaction State

This document defines the operational contract for multi-turn transactions in Agent Framework OCI. It is normative for hosts and templates that use `AgentRuntime`, LangGraph checkpoints, and transactional tools.

## 1. Goal

A transaction may span multiple turns:

```text
User: cancel my order
Framework: provide the order number
User: PED-1001
Framework: confirm cancellation?
User: yes
Framework: execute the tool
```

The framework must preserve the transaction across all turns without relying on LLM reclassification, keyword routing, or re-extraction of parameters already collected.

## 2. Canonical transaction state

The canonical in-flight transaction is `active_transaction`.

```python
active_transaction: dict[str, Any]
last_transaction: dict[str, Any]
```

Every `AgentState` used by a host that enables multi-turn transactions **MUST** declare both fields. LangGraph uses the state schema for checkpoint persistence, so a field created dynamically by the runtime alone is not a safe durable contract.

Minimal example:

```python
from typing import Any, TypedDict

class AgentState(TypedDict, total=False):
    # ...normal fields...
    selected_tool_call: dict[str, Any]
    pending_tool_call: dict[str, Any]
    active_transaction: dict[str, Any]
    last_transaction: dict[str, Any]
    transaction_status: str
    missing_parameters: list[str]
    confirmation_required: bool
    confirmation_received: bool
```

## 3. Field responsibilities

| Field | Responsibility | Rule |
|---|---|---|
| `active_transaction` | Canonical in-flight transaction | Must survive checkpoint/resume while active. |
| `last_transaction` | Snapshot of the latest terminal transaction | Used for audit/evidence; does not automatically reactivate a transaction. |
| `transaction_status` | Current logical status | E.g. `COLLECTING_PARAMETERS`, `AWAITING_CONFIRMATION`, `COMPLETED`, `CANCELLED`, `OUT_OF_SCOPE`. |
| `missing_parameters` | Parameters still required | Must reflect canonical transaction state, not only the current message. |
| `selected_tool_call` | Auxiliary/backward-compatible state | Must not replace `active_transaction` as canonical state. |
| `pending_tool_call` | Auxiliary/backward-compatible state | May support compatibility but is not the primary latch. |
| `next_state` | Workflow routing guidance | Keeps the correct node/agent during collection/confirmation. |
| `transaction_pre_validation` | Pre-validation evidence | Stores validation before confirmation/execution. |
| `transaction_evidence` | Execution evidence | Stores results and the transaction execution trail. |

## 4. Recommended lifecycle

```text
IDLE
  ↓ transactional intent
COLLECTING_PARAMETERS
  ↓ complete parameters
PRE_VALIDATION (when configured)
  ↓ eligible
AWAITING_CONFIRMATION
  ↓ positive confirmation
EXECUTING
  ↓
COMPLETED
```

Alternative terminal outcomes include `CANCELLED`, `OUT_OF_SCOPE`, and `FAILED`.

## 5. Incremental parameter merge

A later answer must complement the existing transaction instead of rebuilding it from the latest text only.

```python
existing = dict((state.get("active_transaction") or {}).get("arguments") or {})
new_values = {"amount": "71.99"}
arguments = {**existing, **new_values}
```

Previously collected arguments must remain available on subsequent turns.

## 6. Routing precedence during an active transaction

When `active_transaction` is in `COLLECTING_PARAMETERS`, the message must first be evaluated as a possible answer to pending parameters.

Normative precedence:

1. clearly fills a pending parameter → continue transaction;
2. explicit cancel/abandon → cancel transaction;
3. unambiguous new intent → interrupt and route;
4. generic keyword in the same domain/agent → **do not** interrupt;
5. ambiguous message → keep transaction and clarify.

| Current state | Message | Correct result |
|---|---|---|
| `retail_order_cancel`, missing `order_id` | `PED-1001` | Continue cancellation and fill `order_id`. |
| `retail_order_cancel`, missing `order_id` | `the order is PED-1001` | Continue cancellation; `order` must not switch to tracking. |
| contestation, missing `amount` | `R$ 71.99` | Continue contestation and fill amount. |
| pending cancellation | `forget it, show my bill` | Explicit interruption is allowed. |
| pending cancellation | `track my order` | Unambiguous shift to tracking is allowed. |

## 7. Checkpoint and resume

Before normal routing, restore the checkpoint with the same conversation identity (`tenant_id`, `agent_id`, `session_id`/`conversation_key` according to the host contract).

An active transaction must be resumed before generic keyword routing or LLM continuity. `COLLECTING_PARAMETERS` without `active_transaction` should be treated as inconsistent state and diagnosed rather than silently restarting the tool.

## 8. Framework vs. agent responsibility

Framework owns latch persistence, argument merge, collection/confirmation states, resume precedence, deterministic confirmation, idempotency/evidence, and checkpoint/resume.

The agent owns domain tools, required parameters, domain messages, domain eligibility/pre-validation, and customer-facing final responses. It must not create a parallel transaction engine.

## 9. New host/template checklist

- [ ] `AgentState` declares `active_transaction`.
- [ ] `AgentState` declares `last_transaction`.
- [ ] `transaction_status` and `missing_parameters` are declared when used.
- [ ] Checkpoint provider is compatible with the state schema.
- [ ] The same conversation identity is reused across turns.
- [ ] New parameters are merged with previously collected arguments.
- [ ] Pending parameter answers take precedence over generic keyword routing.
- [ ] Explicit intent shifts remain possible.
- [ ] Transactional agent responses propagate `transaction_state_patch(state)` where required by the template.
- [ ] Multi-turn tests cover collection, confirmation, interruption, and resume.

## 10. Minimum regression tests

Test order cancellation with a pending `order_id`, contestation with a subject collected on the first turn and amount on the second, explicit interruption to a different intent, and checkpoint/resume using the same conversation identity.

## 11. Anti-patterns

- rebuilding the transaction from only the latest message;
- using `selected_tool_call` as the only latch source;
- removing `active_transaction` because it appears redundant;
- allowing a generic keyword such as `order` to interrupt `order_id` collection;
- keeping parameters only in node-local variables;
- duplicating transaction confirmation in the agent prompt;
- clearing the latch before a terminal state.

## 12. Project references

- `specs/SPEC-002-Agent-Runtime.md`
- `specs/SPEC-010-Agent-Development.md`
- `templates/agent_template_backend/app/state.py`
- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `libs/agent_framework/src/agent_framework/routing/enterprise_router.py`
- `Tuning-Performance/Deterministic_Transactional_Workflow/`
- `Tuning-Performance/Transaction_Pre_Validation/`
- `Tuning-Performance/Transaction_Evidence/`
