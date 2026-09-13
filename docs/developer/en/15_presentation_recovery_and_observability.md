### Presentation, recovery, and observability

### Deterministic renderers

Use `response.mode: renderer` for trusted structured tool results whose values must not be changed by an LLM. Register each renderer once at startup. Its keyword-only contract accepts `tool_name`, `result`, `state`, and `agent_label`; return `None` when required fields are absent so the configured fallback can run. Select, format, and mask allowed fields—never interpolate the complete payload. The executable YAML and implementation are in the matching [Portuguese chapter](../pt/15_apresentacao_recuperacao_e_observabilidade.md).

### Organization of `app/presentation/`

In `agent_template_backend`, domain-specific renderers live in:

```text
app/presentation/
├── __init__.py
└── tool_renderers.py
```

The folder separates **how a trusted domain result should be presented** from the generic infrastructure that selects and executes renderers. Therefore:

- `app/presentation/` implements functions such as `financial.balance`, `billing.invoice`, or another agent-specific renderer;
- `agent_framework.presentation` owns the registry, call contract, and generic runtime integration;
- `config/tools.yaml` selects `response.mode: renderer` and the renderer name;
- agent startup imports/registers renderers once.

Renderers must not fetch data, decide authorization, execute tools, mutate transactional state, or reinterpret a result with an LLM. Their input should already be an authorized/trusted result; the renderer only selects, masks, and formats fields.

**Anti-pattern:** building a copy of the framework presentation registry or pipeline inside `app/presentation/`. If several agents need the same formatting/selection mechanism, evolve it in the core; only domain-specific presentation remains in the agent.

### Output supervision and recovery

The Output Supervisor may allow, sanitize, retry, block, hand over, or observe candidate output. Keep retries bounded, provide objective retry guidance, and revalidate rewritten output. Permanent authorization or dependency failure is not a content retry.

Distinguish validation, transient dependency, permanent dependency, persistence, and programming failures. Before an external send, bounded retry may be safe. After an ambiguous send, query status/idempotency before resending. After external confirmation, persist the outcome before replying. A new user message must not erase evidence of uncertain execution. Checkpoint retry, integrity checks, compaction, and recovery do not make an external action idempotent.

### Voice interruption and replay

On barge-in, preserve confirmed transcript, mark interrupted output, and discard stale audio. An interrupted utterance is not transaction confirmation. Replay uses interaction/message identity and the same scoped session; resume only after revalidating pending state, confirmation, and idempotency.

### Events, mappings, and Pub/Sub

Emit functional behavior as IC, operational dependency/latency as NOC, and guardrail/supervisor decisions as GRL through the observer abstraction. Include tenant, agent, session, transaction/execution, component, and duration where available. Never record credentials, complete prompts, PII, or raw financial payloads.

Map legacy consumer labels through a default registry plus agent overlay. Keep internal events semantic; do not hardcode historical external labels in runtime code.

Pub/Sub publication occurs after the functional decision and must not change its outcome. Ordering requires explicit `sequence`, correlation, and a stable partition key; multiple pods do not provide global ordering. Define retention/TTL, duplicate handling, filters, and failure policy. A Pub/Sub filter does not remove the event from other telemetry destinations.

Validate payload masking, supervisor revalidation, bounded retry, uncertain effects, correlation, mapping, multi-consumer ordering, and voice behavior. Run `pytest -q tests/test_advanced_developer_documentation.py`.
