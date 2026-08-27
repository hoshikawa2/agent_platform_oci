### Agent Framework OCI Architecture and Concepts

### Purpose of this document

This document **does not replace the root `README_en.md`** and does not repeat the agent-creation tutorial.

Use:

- [`README_en.md`](../../../README_en.md) to develop, configure, run, and test an agent end to end;
- this document to understand the architecture, responsibility boundaries, components, and where each type of implementation belongs;
- the other manuals in this folder to deepen a specific capability or solve a problem.

The separation is intentional: there is **one main tutorial** and several **specialized reference manuals**.

### Source of truth

When documentation diverges, use this order:

1. code for the version in use;
2. `README.md` / `README_en.md` from the same version;
3. normative SPECs/SDDs;
4. specialized manuals in this folder;
5. release notes and `README_old*` only as history.

### Platform mental model

Agent Framework OCI should be understood as a layered platform.

The **framework core** provides reusable, domain-neutral mechanisms: runtime, state, memory, routing, tool integration, guardrails, judges, persistence, observability, and common contracts.

The **agent** contains what is specific to the use case: intents, prompts, domain rules, specific policies, business workflow, mappings, integrations, and external components that belong to that agent.

**Gateways** handle cross-cutting ingress, governance, and integration responsibilities. They should not absorb the agent's business logic.

**MCP Servers** encapsulate tools and integrations with domain or legacy services. The **MCP Gateway** provides centralized catalog and governance for these tools.

### Main components

| Component | Main responsibility | Must not contain |
|---|---|---|
| `libs/agent_framework/` | Generic runtime, contracts, state, memory, routing, guardrails, judges, common integrations | Rule specific to a company or agent |
| `templates/agent_template_backend/` | Executable reference for creating agents | Permanent fork of the core |
| `apps/agent_gateway/` | Governed ingress, cross-cutting policies, rate limit, authentication, metadata | Business workflow |
| `apps/channel_gateway/` | Channel adaptation to the canonical contract | Agent business rule |
| `apps/mcp_gateway/` | Catalog, authorization, and centralized tool execution | Conversational logic |
| `mcp/servers/` | Integrations and tools by domain | Global agent orchestration |
| `evals/` | Certification and regression | Production logic |
| `deploy/` | Containers and Kubernetes | Functional rules |

### Conceptual request flow

A typical request goes through the following responsibilities:

```text
Canal
  |
  v
Channel Gateway
  |
  v
Agent Gateway
  |  governança / autenticação / rate limit / metadata
  v
Backend do agente
  |
  +--> Routing / stickiness / intent
  |
  +--> Estado / memória / checkpoint
  |
  +--> Guardrails / judges
  |
  +--> Workflow / políticas transacionais
  |
  +--> MCP Gateway
          |
          +--> MCP Server A --> sistema legado
          +--> MCP Server B --> serviço externo
          +--> MCP Server C --> API de domínio
```

Not every deployment needs to use all components. Composition should follow the agent's needs and the platform contracts.

### Agent runtime

The current runtime is based on `AgentRuntimeMixin` and `RuntimeContext`.

The template imports the runtime through `app.agents.runtime`, which re-exports the framework's official implementation. The goal is to prevent each agent from maintaining its own divergent copy of the runtime.

Current APIs confirmed in the code include:

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

These APIs represent runtime capabilities. Developers should prefer them over manually rebuilding the same logic inside each agent.

### Configuration versus code

A central framework guideline is that configurable behavior should remain in configuration.

Examples:

- agents and metadata: `config/agents.yaml`;
- routing: `config/routing.yaml`;
- tools: `config/tools.yaml`;
- MCP Servers and mappings: corresponding MCP configuration;
- LLM profiles: `llm_profiles.yaml`;
- policies and extensions: capability-specific configuration files.

Code should implement mechanisms. YAML/config should select behavior whenever that can be done without compromising security or contracts.

### Separation between framework and agent

A change belongs to the **framework** when it introduces a mechanism reusable by different agents.

Examples:

- new guardrail SPI;
- new rich LLM response contract;
- new generic checkpoint capability;
- new configurable tool-policy mechanism;
- new generic routing strategy.

A change belongs to the **agent** when it expresses a rule from a domain or company.

Examples:

- which charges can be disputed;
- a telecom-specific prompt;
- VAS rules;
- internal company codes;
- legacy-service mapping;
- specific phraseology.

If the core needs to import a concrete agent module in order to work, this separation has probably been broken.

### State, memory, and checkpoint are different concepts

**Execution state** represents what is happening in the turn and workflow.

**Conversation memory** preserves conversational context.

**Long-Term Memory** stores durable facts associated with a business identity.

**Checkpoint** persists LangGraph state snapshots for resume.

An old checkpoint must not, by itself, determine which transaction is active. The functional decision must use canonical transaction state.

### Routing and execution are different responsibilities

Routing answers: **which agent/intent should handle this message?**

Execution answers: **what should that agent do now?**

Route stickiness preserves continuity, but it must not prevent an explicit intent change. During a transaction, expected parameters and valid confirmation take precedence to avoid false intent shifts.

Full details: [Routing, Stickiness, and Intent Shift](./02_routing_stickiness_and_intent_shift.md).

### Tools and MCP

A tool represents an invokable capability.

The MCP Server implements or exposes that capability.

The MCP Gateway organizes catalog, authorization, mapping, and centralized execution.

The agent decides **when** a tool should be used in its flow; the tool/MCP decides **how** to access the corresponding service.

Full details: [MCP, Tools, Policies, and Parameter Extraction](./04_mcp_integration_tools_and_policies.md).

### Transactions

Operations with side effects require different handling from queries.

The framework provides state, confirmation, policy, and deterministic-workflow mechanisms. Concrete rules remain in the agent.

The LLM may participate in interpretation and composition, but it must not be the only source of truth for claiming that a critical operation was executed.

Full details: [Transactional Workflows and State](./03_transaction_workflows_and_state.md).

### Guardrails and Judges

Guardrails control or validate behavior during processing.

Judges evaluate quality, grounding, and other criteria.

The core provides native mechanisms and extension points. Domain-specific guardrails/judges should be loaded by the agent through configuration, avoiding specific imports inside the framework.

Full details: [Guardrails, Judges, and Transaction Evaluation](./06_guardrails_judges_and_transaction_evaluation.md).

### RAG, memory, and tools are not equivalent

- **RAG** retrieves knowledge.
- **Memory** preserves context/facts.
- **Tool** executes or queries an external capability.

Choosing the wrong mechanism creates bugs that are difficult to diagnose. Information that needs to be updated in a system should not be solved only through RAG; a durable customer fact should not depend only on prompt history.

### Observability as a cross-cutting contract

Routing, agent, transaction, tool, guardrail, judge, and failure must be correlatable.

Observability should record what happened, but it must not control business state. Sequence, trace IDs, and labels are diagnostic and audit infrastructure.

Full details: [Observability, Persistence, and Operational Readiness](./11_observability_persistence_and_operational_readiness.md).

### Where to place a new feature

Before implementing, ask these questions:

1. Is the capability reusable by different agents?
2. Is there a domain-specific rule?
3. Does it need state across turns?
4. Does it produce side effects?
5. Does it depend on an external system?
6. Should it be configurable?
7. Does it need to appear in observability?
8. Does it need to be evaluated by a guardrail/judge?

A reusable feature normally starts in the core and is enabled/configured by the agent. A business rule normally starts in the agent and uses core interfaces.

### Anti-patterns

Avoid:

- importing a concrete agent package inside the core;
- duplicating `AgentRuntimeMixin` in every agent;
- hardcoding agent, intent, tool, or company names in the runtime;
- using an LLM response as proof that an operation was executed;
- confusing an old checkpoint with the active transaction;
- executing a transactional operation without policy/confirmation when it is required;
- coupling an agent directly to dozens of services when MCP Gateway is the intended layer;
- creating a new functional document for every bug fix instead of updating the feature manual.

### Recommended path for a new developer

1. Read the architectural overview in this document.
2. Follow [`README_en.md`](../../../README_en.md) from beginning to end to create and run an agent.
3. When you reach a specific capability, use the corresponding specialized manual.
4. For failures, start with the [Developer Index](./INDEX_DEVELOPER_GUIDE.md), in the **Search by problem** section.
5. Before copying old code, confirm the API/import in the current template and core.

### Related documents

- [Main tutorial — README.md](../../../README.md)
- [Routing, Stickiness, and Intent Shift](./02_routing_stickiness_and_intent_shift.md)
- [Transactional Workflows and State](./03_transaction_workflows_and_state.md)
- [MCP, Tools, Policies, and Parameters](./04_mcp_integration_tools_and_policies.md)
- [Gateways and Authentication](./05_agent_gateway_mcp_gateway_and_auth.md)
- [Guardrails and Judges](./06_guardrails_judges_and_transaction_evaluation.md)
- [RAG and BusinessContext](./07_rag_business_context_and_grounding.md)
- [Long-Term Memory and Checkpoint](./08_long_term_memory_and_checkpoint.md)
- [LLM Rich Response](./09_llm_rich_response_reasoning.md)
- [Performance, Cache, and Async Runtime](./10_performance_cache_and_async_runtime.md)
- [Observability and Operational Readiness](./11_observability_persistence_and_operational_readiness.md)
