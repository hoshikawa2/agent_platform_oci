# Multi-Intent Planning

`MultiIntentPlanner` recognizes independent requests in one utterance and
builds a plan constrained to the intents, agents, and tools declared in
`config/routing.yaml`. It does not execute operations: the router selects the
primary operation and the domain workflow continues to own the transaction.

## Configuration and execution

No additional configuration is required. The planner uses the intents already
declared in `routing.yaml`, selects the single transactional operation from
`tool_policies.yaml`, and persists the remaining requests as `pending_topics`.

When `ENABLE_LLM_ROUTER=true`, a compound message whose deterministic plan is
missing or incomplete is sent to a structured multi-intent classifier. The LLM
may return only configured intent names and source fragments. Agent, domain,
and tool ownership are always hydrated from `routing.yaml`; unknown intents,
low confidence, and invalid JSON are rejected. The default confidence threshold
is `0.65` and can be overridden with
`multi_intent.llm_confidence_threshold`.

Known read-only topics execute through their own agent. A second mutation stays
pending for its own confirmation, while an unknown clause becomes off-context.

The router first resolves clauses from registered intent keywords, then uses the
semantic fallback only for an absent or incomplete compound plan, and routes
the transactional operation first. The graph drains read-only pending topics
before output supervision. During an open transaction,
`yes, and send me the invoice` confirms the transaction and records the
secondary request instead of causing an intent shift.

For multiple side-effecting actions, implement a transactional coordinator
that persists the plan, confirms it, executes idempotently, and records partial
failure or compensation. See `tests/unit/test_multi_intent_planner.py`. No
special Tuning-Performance template is needed because the behavior is native.
