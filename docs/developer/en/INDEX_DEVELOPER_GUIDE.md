### Developer Index — Agent Framework OCI

### How to use this documentation

The documentation has three clear levels:

1. **Main tutorial:** [`README_en.md`](README_en.md) — creation, configuration, execution, and testing of an agent from start to finish.
2. **Architecture:** [01 — Architecture and Concepts](docs/developer/en/01_architecture_and_concepts.md) — components, responsibilities, and where to implement each concern.
3. **Specialized references:** manuals `02` through `11` — in-depth implementation and troubleshooting by capability.

If you are starting a new agent, begin with `README_en.md`.

If something is not working, use **Search by problem** below.

### Search by problem

| Problem / question | What is usually involved | Where to look |
|---|---|---|
| The framework does not find the correct agent/intent | routing, intents, threshold, deterministic/LLM mode | [Routing and Stickiness](docs/developer/en/02_routing_stickiness_and_intent_shift.md) |
| The agent gets stuck on the same subject and does not change intent | route stickiness, intent shift, handoff | [Routing and Stickiness](docs/developer/en/02_routing_stickiness_and_intent_shift.md) |
| An answer that should fill a parameter is interpreted as a new intent | transactional precedence, parameter extraction | [Transactional Workflows](docs/developer/en/03_transaction_workflows_and_state.md) |
| The transaction keeps asking for the same parameter | transaction state, extractor, schema | [Transactional Workflows](docs/developer/en/03_transaction_workflows_and_state.md) and [MCP/Tools](docs/developer/en/04_mcp_integration_tools_and_policies.md) |
| “yes/no” confirmation does not continue the flow | confirmation state, transaction state | [Transactional Workflows](docs/developer/en/03_transaction_workflows_and_state.md) |
| A completed transaction reappears | old checkpoint versus active transaction state | [Transactional Workflows](docs/developer/en/03_transaction_workflows_and_state.md) and [LTM/Checkpoint](docs/developer/en/08_long_term_memory_and_checkpoint.md) |
| The system says it executed something, but there is no evidence | MCP result, `COMPLETED` state, transactional judges | [Transactional Workflows](docs/developer/en/03_transaction_workflows_and_state.md) and [Guardrails/Judges](docs/developer/en/06_guardrails_judges_and_transaction_evaluation.md) |
| A tool does not appear or cannot be found | `tools.yaml`, MCP catalog, discovery | [MCP/Tools](docs/developer/en/04_mcp_integration_tools_and_policies.md) |
| MCP Server does not appear in the catalog | registration, manifest/discovery, MCP Gateway | [MCP/Tools](docs/developer/en/04_mcp_integration_tools_and_policies.md) and [Gateways](docs/developer/en/05_agent_gateway_mcp_gateway_and_auth.md) |
| Parameters sent to the tool are wrong | schema, mapping, BusinessContext, extractor | [MCP/Tools](docs/developer/en/04_mcp_integration_tools_and_policies.md) |
| A transactional operation executes without confirmation | tool policy, `require_confirmation` | [MCP/Tools](docs/developer/en/04_mcp_integration_tools_and_policies.md) |
| A name search requires an overly exact match | parameter extraction/mapping and agent logic | [MCP/Tools](docs/developer/en/04_mcp_integration_tools_and_policies.md) |
| I receive 401 between gateway/backend/MCP | Basic Auth, credentials per hop | [Gateways and Auth](docs/developer/en/05_agent_gateway_mcp_gateway_and_auth.md) |
| I need to decide whether something belongs to the framework or the agent | core/agent boundary | [Architecture and Concepts](docs/developer/en/01_architecture_and_concepts.md) |
| An agent-specific guardrail is breaking another agent | extensibility, domain imports in the core | [Guardrails and Judges](docs/developer/en/06_guardrails_judges_and_transaction_evaluation.md) |
| A judge does not run in a transaction | sampling, `always_run_for_transactional`, transaction signals | [Guardrails and Judges](docs/developer/en/06_guardrails_judges_and_transaction_evaluation.md) |
| Groundedness is evaluating without the correct context | RAG context, MCP evidence, judge inputs | [RAG/Grounding](docs/developer/en/07_rag_business_context_and_grounding.md) |
| RAG does not find content | provider, ingestion, embeddings, configuration | [RAG/Grounding](docs/developer/en/07_rag_business_context_and_grounding.md) |
| I do not know whether to use RAG, memory, or a tool | separation of responsibilities | [Architecture and Concepts](docs/developer/en/01_architecture_and_concepts.md) and [RAG/Grounding](docs/developer/en/07_rag_business_context_and_grounding.md) |
| Memory disappears when changing sessions | LTM versus conversation memory | [LTM and Checkpoint](docs/developer/en/08_long_term_memory_and_checkpoint.md) |
| Memory from one customer/agent appears in another | identity key, tenant/agent/customer isolation | [LTM and Checkpoint](docs/developer/en/08_long_term_memory_and_checkpoint.md) |
| I need to retrieve `reasoning_content` | `ainvoke_response()` | [LLM Rich Response](docs/developer/en/09_llm_rich_response_reasoning.md) |
| `reasoning_content` is `None` | provider/model does not expose the field | [LLM Rich Response](docs/developer/en/09_llm_rich_response_reasoning.md) |
| There are unnecessary LLM calls | deterministic routing, concurrency, cache | [Performance](docs/developer/en/10_performance_cache_and_async_runtime.md) |
| There is a deadlock or wait across event loops | cross-loop sequence/runtime | [Performance](docs/developer/en/10_performance_cache_and_async_runtime.md) |
| Logs/traces do not correlate the same agent | labels, IDs, and observability mapping | [Observability](docs/developer/en/11_observability_persistence_and_operational_readiness.md) |
| Sequence is interfering with processing | asynchronous sequence implementation | [Observability](docs/developer/en/11_observability_persistence_and_operational_readiness.md) and [Performance](docs/developer/en/10_performance_cache_and_async_runtime.md) |
| An old example does not compile | historical documentation versus current API | [README vs Code Validation](docs/developer/en/VALIDATION_README_ALIGNMENT.md) |
| I need to create a new agent from scratch | complete flow | [`README_en.md`](README_en.md) |
| I need to know where to place a new feature | architecture and boundaries | [Architecture and Concepts](docs/developer/en/01_architecture_and_concepts.md) |

### Search by feature

### [01 — Architecture and Concepts](docs/developer/en/01_architecture_and_concepts.md)

**What it is:** overview of components, contracts, and responsibility boundaries.

**Use when:** you need to understand the platform, decide where to implement something, or avoid coupling between core and agent.

### [02 — Routing, Route Stickiness, and Intent Shift](docs/developer/en/02_routing_stickiness_and_intent_shift.md)

**What it is:** complete reference for agent/intent discovery, stickiness, handoff, and intent changes.

**Use when:** the message goes to the wrong agent, does not change intent, or loses continuity.

### [03 — Transactional Workflows and State](docs/developer/en/03_transaction_workflows_and_state.md)

**What it is:** multi-turn transaction lifecycle, states, confirmation, pause/resume, and operational evidence.

**Use when:** there are loops, incorrect confirmations, incorrect resumes, or critical operations.

### [04 — MCP, Tools, Policies, and Parameter Extraction](docs/developer/en/04_mcp_integration_tools_and_policies.md)

**What it is:** reference for tools, MCP Servers, mappings, policies, and parameter extraction.

**Use when:** tool integration/execution is incorrect or needs to be created.

### [05 — Agent Gateway, MCP Gateway, and Authentication](docs/developer/en/05_agent_gateway_mcp_gateway_and_auth.md)

**What it is:** gateway responsibilities, governance, and authentication between components.

**Use when:** there is an ingress, catalog, authorization, 401, or gateway deployment problem.

### [06 — Guardrails, Judges, and Transaction Evaluation](docs/developer/en/06_guardrails_judges_and_transaction_evaluation.md)

**What it is:** native/external validations, judges, grounding, and rules for transactional turns.

**Use when:** a validation blocks, does not run, or produces an incorrect evaluation.

### [07 — RAG, BusinessContext, and Grounding](docs/developer/en/07_rag_business_context_and_grounding.md)

**What it is:** RAG providers, retrieved context, BusinessContext, and grounding.

**Use when:** retrieved knowledge does not correctly reach the agent/judge.

### [08 — Long-Term Memory and Checkpoint](docs/developer/en/08_long_term_memory_and_checkpoint.md)

**What it is:** durable memory, conversation memory, identity, and state snapshots.

**Use when:** context disappears, leaks, or the workflow resumes from the wrong place.

### [09 — LLM Rich Response and reasoning_content](docs/developer/en/09_llm_rich_response_reasoning.md)

**What it is:** structured inference response beyond the `str` returned by `ainvoke()`.

**Use when:** consumers need metadata, usage, or reasoning exposed by the provider.

### [10 — Performance, Cache, and Async Runtime](docs/developer/en/10_performance_cache_and_async_runtime.md)

**What it is:** concurrency, cache, LLM, and event-loop optimizations.

**Use when:** there is avoidable latency, serial processing, or deadlock.

### [11 — Observability, Persistence, and Operational Readiness](docs/developer/en/11_observability_persistence_and_operational_readiness.md)

**What it is:** correlation, events, labels, sequence, persistence, and diagnostics.

**Use when:** it is necessary to prove the executed path or diagnose production.

### Main tutorial

[`README_en.md`](README_en.md) remains the reference for the complete step-by-step flow:

`architecture → configuration → agent creation → registration → state → routing → tools → MCP → identity → execution → tests → gateways → memory → RAG`.

### Maintenance

Do not create another tutorial in parallel with `README_en.md`.

When evolving a feature:

- update the README only if the normal development flow changed;
- update the specialized manual with behavior, configuration, examples, and troubleshooting;
- update SPECs if the contract changed;
- keep release notes as history, not as the only current documentation.
