
### Agent Framework OCI Architecture and Concepts

### Purpose of this document

This document **does not replace the root `README_en.md`** and does not duplicate the end-to-end agent development tutorial.

Use:

- [`README_en.md`](../../../README_en.md) to develop, configure, run and test an agent end to end;
- this document to understand architecture, responsibility boundaries, components and where each implementation belongs;
- the other manuals in this folder to deepen a specific capability or troubleshoot a problem.

The separation is intentional: there is **one main tutorial** and multiple **specialized reference manuals**.

### Source of truth

When documentation differs, use this order:

1. code for the version in use;
2. `README.md` / `README_en.md` for the same version;
3. normative SPECs/SDDs;
4. specialized manuals in this folder;
5. release notes and `README_old*` only as historical material.

### Platform mental model

Agent Framework OCI is a layered platform.

The **framework core** provides reusable, domain-neutral mechanisms: runtime, state, memory, routing, tool integration, guardrails, judges, persistence, observability and common contracts.

The **agent** contains use-case-specific behavior: intents, prompts, domain rules, agent-specific policies, business workflows, mappings, integrations and external components owned by that agent.

**Gateways** handle cross-cutting ingress, governance and integration concerns. They should not absorb agent business logic.

**MCP Servers** encapsulate tools and integrations with domain or legacy services. The **MCP Gateway** provides centralized tool catalog and governance.

### Main components

| Component | Primary responsibility | Must not contain |
|---|---|---|
| `libs/agent_framework/` | Generic runtime, contracts, state, memory, routing, guardrails, judges and common integrations | Company- or agent-specific business rules |
| `templates/agent_template_backend/` | Executable reference for creating agents | A permanent fork of the core |
| `apps/agent_gateway/` | Governed ingress, cross-cutting policies, rate limits, auth and metadata | Business workflow |
| `apps/channel_gateway/` | Adapt channels to canonical contracts | Agent business logic |
| `apps/mcp_gateway/` | Central tool catalog, authorization and execution | Conversational orchestration |
| `mcp/servers/` | Domain tools and integrations | Global agent orchestration |
| `evals/` | Certification and regression | Production business logic |
| `deploy/` | Containers and Kubernetes artifacts | Functional rules |

### Conceptual request flow

```text
Channel
  |
  v
Channel Gateway
  |
  v
Agent Gateway
  |  governance / auth / rate limit / metadata
  v
Agent backend
  |
  +--> Routing / stickiness / intent
  |
  +--> State / memory / checkpoint
  |
  +--> Guardrails / judges
  |
  +--> Workflow / transaction policies
  |
  +--> MCP Gateway
          |
          +--> MCP Server A --> legacy system
          +--> MCP Server B --> external service
          +--> MCP Server C --> domain API
```

Not every deployment must use every component. Composition follows agent needs and platform contracts.

### Agent runtime

The current runtime is based on `AgentRuntimeMixin` and `RuntimeContext`.

The template imports runtime through `app.agents.runtime`, which re-exports the official framework implementation. This prevents each agent from maintaining a divergent copy.

Current APIs confirmed in this version include:

```python
AgentRuntimeMixin.get_runtime_context()
AgentRuntimeMixin.normalize_tools_by_intent()
AgentRuntimeMixin.build_tool_arguments()
AgentRuntimeMixin.execute_tools_for_intent()
AgentRuntimeMixin.prepare_memory_context()
AgentRuntimeMixin.build_messages()
AgentRuntimeMixin.transaction_state_patch()
AgentRuntimeMixin.transaction_clarification_message()
AgentRuntimeMixin.transaction_confirmation_message()
AgentRuntimeMixin.build_direct_mcp_answer()
```

Developers should prefer these runtime capabilities instead of rebuilding equivalent logic inside each agent.

### Configuration versus code

A core framework principle is to keep selectable behavior in configuration.

Examples:

- agents and metadata: `config/agents.yaml`;
- routing: `config/routing.yaml`;
- tools: `config/tools.yaml`;
- MCP Servers and mappings: corresponding MCP configuration;
- LLM profiles: `llm_profiles.yaml`;
- policies and extensions: capability-specific configuration.

Code implements mechanisms. YAML/config selects behavior whenever this can be done without weakening safety or contracts.

### Framework versus agent responsibility

A change belongs to the **framework** when it introduces a mechanism reusable by multiple agents.

A change belongs to the **agent** when it expresses company/domain behavior.

If the core must import a concrete agent module to work, that boundary is probably broken.

### State, memory and checkpoint are different concepts

**Execution state** represents what is happening in the turn/workflow.

**Conversation memory** preserves conversational context.

**Long-Term Memory** stores durable facts associated with business identity.

**Checkpointing** persists LangGraph state snapshots for resume.

An old checkpoint alone must not determine which transaction is active. Functional decisions should use canonical transaction state.

### Routing and execution are separate responsibilities

Routing answers: **which agent/intent should handle the message?**

Execution answers: **what should that agent do now?**

Route stickiness preserves continuity but must not block an explicit intent change. During a transaction, expected parameters and valid confirmation have precedence to avoid false intent shifts.

See [Routing, Stickiness and Intent Shift](./02_routing_stickiness_and_intent_shift.md).

### Tools and MCP

A tool is an invokable capability.

An MCP Server implements or exposes that capability.

The MCP Gateway organizes catalog, authorization, mapping and centralized execution.

The agent decides **when** a tool is needed; MCP determines **how** the corresponding service is accessed.

See [MCP, Tools, Policies and Parameter Extraction](./04_mcp_integration_tools_and_policies.md).

### Transactions

Side-effecting operations require different handling from read-only queries.

The framework provides state, confirmation, policy and deterministic workflow mechanisms. Concrete domain rules remain in the agent.

An LLM may participate in interpretation and composition, but it must not be the sole source of truth for claiming that a critical operation was executed.

See [Transactional Workflows and State](./03_transaction_workflows_and_state.md).

### Guardrails and judges

The core provides native mechanisms and extension points. Domain-specific guardrails/judges belong to the agent and should be loaded through configuration rather than hardcoded imports inside the core.

See [Guardrails, Judges and Transaction Evaluation](./06_guardrails_judges_and_transaction_evaluation.md).

### RAG, memory and tools are not interchangeable

- **RAG** retrieves knowledge.
- **Memory** preserves context/facts.
- **Tools** query or execute external capabilities.

Using the wrong mechanism creates difficult-to-diagnose behavior.

### Observability as a cross-cutting contract

Routing, agent, transaction, tool, guardrail, judge and failure events must be correlatable.

Observability records what happened; it must not become business-state control.

See [Observability, Persistence and Operational Readiness](./11_observability_persistence_and_operational_readiness.md).

### Where a new feature belongs

Before implementing a feature, ask:

1. Is it reusable by multiple agents?
2. Does it contain domain-specific rules?
3. Does it require state across turns?
4. Does it produce side effects?
5. Does it depend on an external system?
6. Should it be configurable?
7. Must it be observable?
8. Must a guardrail/judge evaluate it?

A reusable capability normally starts in the core and is enabled/configured by the agent. A business rule normally starts in the agent and uses core interfaces.

### Anti-patterns

Avoid:

- importing a concrete agent package inside the core;
- duplicating `AgentRuntimeMixin` per agent;
- hardcoding agent, intent, tool or company names in runtime;
- treating LLM output as proof of operation execution;
- treating an old checkpoint as the active transaction;
- executing transactional operations without required policy/confirmation;
- directly coupling agents to many services when MCP Gateway is the intended layer;
- creating a new functional document for every bug fix instead of updating the feature manual.

### Recommended path for a new developer

1. Read this architecture overview.
2. Follow [`README_en.md`](../../../README_en.md) end to end.
3. Use the specialized manual when reaching a specific capability.
4. For failures, start from the [Developer Index](./INDEX_DEVELOPER_GUIDE.md), under **Search by problem**.
5. Before copying historical code, confirm the API/import in the current template and core.

### Related documents

- [Main tutorial — README_en.md](../../../README_en.md)
- [Routing, Stickiness and Intent Shift](./02_routing_stickiness_and_intent_shift.md)
- [Transactional Workflows and State](./03_transaction_workflows_and_state.md)
- [MCP, Tools, Policies and Parameters](./04_mcp_integration_tools_and_policies.md)
- [Gateways and Authentication](./05_agent_gateway_mcp_gateway_and_auth.md)
- [Guardrails and Judges](./06_guardrails_judges_and_transaction_evaluation.md)
- [RAG and BusinessContext](./07_rag_business_context_and_grounding.md)
- [Long-Term Memory and Checkpoint](./08_long_term_memory_and_checkpoint.md)
- [LLM Rich Response](./09_llm_rich_response_reasoning.md)
- [Performance, Cache and Async Runtime](./10_performance_cache_and_async_runtime.md)
- [Observability and Operational Readiness](./11_observability_persistence_and_operational_readiness.md)
