
### Developer Index — Agent Framework OCI

### How to use this documentation

The documentation has three clear levels:

1. **Main tutorial:** [`README_en.md`](../../../README_en.md) — build, configure, run and test an agent end to end.
2. **Architecture:** [01 — Architecture and Concepts](./01_architecture_and_concepts.md) — components, boundaries and implementation placement.
3. **Specialized references:** manuals `02` through `11` — deep implementation and troubleshooting by capability.

If you are creating a new agent, start with the main README.

If something is not working, use **Search by problem** below.

### Search by problem

| Problem / question | Usually involves | Go to |
|---|---|---|
| Framework selects the wrong agent/intent | routing, intents, thresholds, deterministic/LLM mode | [Routing and Stickiness](./02_routing_stickiness_and_intent_shift.md) |
| Agent stays stuck on the same subject | route stickiness, intent shift, handoff | [Routing and Stickiness](./02_routing_stickiness_and_intent_shift.md) |
| A parameter answer is mistaken for a new intent | transaction precedence, parameter extraction | [Transactional Workflows](./03_transaction_workflows_and_state.md) |
| Transaction keeps asking for the same parameter | transaction state, extractor, schema | [Transactional Workflows](./03_transaction_workflows_and_state.md) and [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| “yes/no” confirmation does not continue the flow | confirmation state | [Transactional Workflows](./03_transaction_workflows_and_state.md) |
| A closed transaction reappears | old checkpoint vs active transaction | [Transactional Workflows](./03_transaction_workflows_and_state.md) and [LTM/Checkpoint](./08_long_term_memory_and_checkpoint.md) |
| System claims an operation ran but there is no evidence | MCP results, `COMPLETED`, transaction judges | [Transactional Workflows](./03_transaction_workflows_and_state.md) and [Guardrails/Judges](./06_guardrails_judges_and_transaction_evaluation.md) |
| A tool is missing | tools config, MCP catalog/discovery | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| MCP Server is missing from catalog | registration, manifest/discovery, MCP Gateway | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) and [Gateways](./05_agent_gateway_mcp_gateway_and_auth.md) |
| Tool parameters are wrong | schema, mapping, BusinessContext, extraction | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| Transactional tool executes without confirmation | policy, `require_confirmation` | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| 401 between gateway/backend/MCP | Basic Auth, hop credentials | [Gateways and Auth](./05_agent_gateway_mcp_gateway_and_auth.md) |
| Need to decide framework vs agent ownership | core/agent boundary | [Architecture and Concepts](./01_architecture_and_concepts.md) |
| Agent-specific guardrail breaks another agent | extension model, domain imports | [Guardrails and Judges](./06_guardrails_judges_and_transaction_evaluation.md) |
| Judge does not run for a transaction | sampling, transaction signals | [Guardrails and Judges](./06_guardrails_judges_and_transaction_evaluation.md) |
| Groundedness gets the wrong context | RAG context, MCP evidence, judge inputs | [RAG/Grounding](./07_rag_business_context_and_grounding.md) |
| RAG returns no useful content | provider, ingestion, embeddings | [RAG/Grounding](./07_rag_business_context_and_grounding.md) |
| Unsure whether to use RAG, memory or a tool | responsibility separation | [Architecture and Concepts](./01_architecture_and_concepts.md) |
| Memory disappears across sessions | LTM vs conversation memory | [LTM and Checkpoint](./08_long_term_memory_and_checkpoint.md) |
| Memory leaks across customer/agent | identity isolation | [LTM and Checkpoint](./08_long_term_memory_and_checkpoint.md) |
| Need `reasoning_content` | `ainvoke_response()` | [LLM Rich Response](./09_llm_rich_response_reasoning.md) |
| `reasoning_content` is `None` | provider/model does not expose it | [LLM Rich Response](./09_llm_rich_response_reasoning.md) |
| Too many LLM calls | deterministic routing, concurrency, cache | [Performance](./10_performance_cache_and_async_runtime.md) |
| Deadlock across event loops | cross-loop runtime/sequence | [Performance](./10_performance_cache_and_async_runtime.md) |
| Logs/traces do not correlate the same agent | labels, IDs, observability mapping | [Observability](./11_observability_persistence_and_operational_readiness.md) |
| Historical example no longer compiles | stale docs vs current API | [README Alignment Validation](./VALIDATION_README_ALIGNMENT.md) |
| Need to create a new agent from scratch | complete flow | [`README_en.md`](../../../README_en.md) |

### Search by feature

### [01 — Architecture and Concepts](./01_architecture_and_concepts.md)

**What it is:** component, contract and responsibility-boundary reference.

**Use it when:** understanding the platform or deciding where a feature belongs.

### [02 — Routing, Route Stickiness and Intent Shift](./02_routing_stickiness_and_intent_shift.md)

**What it is:** agent/intent discovery, stickiness, handoff and intent-shift reference.

**Use it when:** routing is wrong or session continuity behaves incorrectly.

### [03 — Transactional Workflows and State](./03_transaction_workflows_and_state.md)

**What it is:** multi-turn transaction lifecycle, states, confirmation, resume and execution evidence.

**Use it when:** transactions loop, resume incorrectly or perform critical operations.

### [04 — MCP, Tools, Policies and Parameter Extraction](./04_mcp_integration_tools_and_policies.md)

**What it is:** tools, MCP Servers, mappings, policies and extraction reference.

**Use it when:** building or troubleshooting tool integration.

### [05 — Agent Gateway, MCP Gateway and Authentication](./05_agent_gateway_mcp_gateway_and_auth.md)

**What it is:** gateway responsibilities, governance and component authentication.

**Use it when:** troubleshooting ingress, catalog, authorization or gateway deployment.

### [06 — Guardrails, Judges and Transaction Evaluation](./06_guardrails_judges_and_transaction_evaluation.md)

**What it is:** native/external validation, judges, grounding and transaction evaluation.

**Use it when:** validation blocks, skips or evaluates incorrectly.

### [07 — RAG, BusinessContext and Grounding](./07_rag_business_context_and_grounding.md)

**What it is:** RAG providers, retrieved context, BusinessContext and grounding.

**Use it when:** retrieved knowledge does not reach the runtime/judge correctly.

### [08 — Long-Term Memory and Checkpoint](./08_long_term_memory_and_checkpoint.md)

**What it is:** durable memory, conversational memory, identity and state snapshots.

**Use it when:** context disappears, leaks or resumes incorrectly.

### [09 — LLM Rich Response and reasoning_content](./09_llm_rich_response_reasoning.md)

**What it is:** structured inference output beyond the `str` returned by `ainvoke()`.

**Use it when:** consumers require provider metadata, usage or reasoning exposed by the provider.

### [10 — Performance, Cache and Async Runtime](./10_performance_cache_and_async_runtime.md)

**What it is:** concurrency, caching, LLM and event-loop optimization reference.

**Use it when:** reducing avoidable latency or diagnosing deadlocks.

### [11 — Observability, Persistence and Operational Readiness](./11_observability_persistence_and_operational_readiness.md)

**What it is:** correlation, events, labels, sequencing, persistence and production diagnostics.

**Use it when:** proving execution paths or diagnosing production behavior.

### Main tutorial

[`README_en.md`](../../../README_en.md) remains the complete step-by-step guide.

### Maintenance

Do not create another tutorial parallel to the root README.

When a feature evolves:

- update the README only when the normal developer flow changes;
- update the specialized manual with behavior, configuration, examples and troubleshooting;
- update SPECs when contracts change;
- keep release notes as history, not as the only current documentation.
