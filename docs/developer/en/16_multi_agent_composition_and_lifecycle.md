### Multi-agent composition and lifecycle

### Effective isolation

An `agent_id` is not merely a label. Real isolation includes prompt, routing, tools, MCP servers, guardrails, judges, memory, checkpoints, cache, telemetry, and identity, normally scoped as `tenant_id:agent_id:session_id`. The complete registry and runtime-bundle code are in the matching [Portuguese chapter](../pt/16_multiagente_composicao_e_ciclo_de_vida.md).

Every configured path must exist and be validated at startup. A system prefix guides the model but is not a security boundary; code must enforce tool authorization, persistence namespaces, and pipeline selection.

### Current template limitation

Although `agents.yaml` accepts per-agent paths, the template currently builds one router, one tool/RAG composition, and one global guardrail/judge pair. YAML alone does not provide per-request isolation. Use one global profile per deployment or implement an explicit cached runtime bundle per `agent_id`. Cache immutable/expensive objects rather than constructing LLM clients, routers, or pipelines for every message. Never silently fall back to another agent's bundle.

### Subagents and LLM composition

A subagent is a bounded capability with declared purpose, input/output, authorized tools, timeout/budget, and return conditions. A supervisor consolidates structured results and passes minimum relevant context with correlation and maximum delegation depth. Use routing for one-specialty turns; use supervision only for genuine decomposition. Handoff transfers conversation ownership; subagent delegation leaves final-response ownership with the supervisor.

Reuse framework LLM profiles and clients rather than creating provider SDKs inside domain components. Explicit, observable profile fallback preserves authentication, rate limits, retries, cache, and telemetry; configuration failure must not become an apparently valid answer.

### RAG, memory, and security

`RAG_PROVIDER=kbdb` works only when the execution's `RagService` uses the intended settings. A simple intent should still retrieve knowledge when agent policy requires it. Scope RAG collections, long-term memory, and checkpoints by tenant and agent. Long-term memory stores permitted summarized facts; checkpoints store execution state; neither may mix another agent's identity.

Authentication establishes a principal; authorization controls tenant, agent, route, and tool. Production secrets require hashing/rotation and TLS. Trusted-proxy headers are safe only behind an authenticated edge that removes client-supplied values.

### Startup and delivery lifecycle

At startup validate registry/paths, create providers, register actions/renderers, load workflows, construct bundles, and check mandatory dependencies. `/health` reports process liveness; `/ready` must reject traffic when a required dependency is unusable. Invalid configuration should fail before the first conversation.

Development order: copy the canonical template; create domain agent/configuration; register node and route; implement tools, mappings, policies, actions, and renderers; configure controls/RAG/memory/telemetry; run unit, loader, graph, conversational, and failure tests; run offline evaluation, load, and readiness checks; publish with version, compatibility, and rollback.

The definition of done includes isolation, confirmation, idempotency, recovery, grounding, controls, correlated telemetry, no data leakage, dependency-failure behavior, and PT/EN documentation parity. Run `pytest -q tests/test_advanced_developer_documentation.py`.
