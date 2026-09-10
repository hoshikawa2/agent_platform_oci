# Multi-Intent Planning

`MultiIntentPlanner` recognizes independent requests in one utterance and
builds a plan constrained to the intents, agents, and tools declared in
`config/routing.yaml`. It does not execute operations or let the LLM invent a
sequence: the router selects the primary operation and the domain workflow
continues to own the transaction.

## Configuration and execution

No additional configuration is required. The planner uses the intents already
declared in `routing.yaml`, selects the single transactional operation from
`tool_policies.yaml`, and persists the remaining requests as `pending_topics`.

Known read-only topics execute through their own agent. A second mutation stays
pending for its own confirmation, while an unknown clause becomes off-context.

The router resolves clauses from registered intent keywords and routes the
transactional operation first. The graph drains read-only pending topics before
output supervision. During an open transaction,
`yes, and send me the invoice` confirms the transaction and records the
secondary request instead of causing an intent shift.

For multiple side-effecting actions, implement a transactional coordinator
that persists the plan, confirms it, executes idempotently, and records partial
failure or compensation. See `tests/unit/test_multi_intent_planner.py`. No
special Tuning-Performance template is needed because the behavior is native.
