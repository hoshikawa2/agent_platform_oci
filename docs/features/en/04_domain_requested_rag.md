# Domain Requested RAG

> `agent_framework_oci` feature — English guide.

**Main implementation:** `runtime/agent_runtime.py`

---

### 1. What it is

Allows a tool or workflow to declare that external knowledge retrieval is required even when an MCP result already exists.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Tool/Workflow
   ↓
requires_rag=true
   ↓
rag_query / rag_queries
   ↓
framework RagService
   ↓
Retrieval Guardrails
   ↓
LLM/response
```

### 4. How it works internally

Normally the framework may skip RAG when MCP already provides sufficient data (`SKIP_RAG_WHEN_MCP_SUFFICIENT`). This feature lets the domain override that decision for a specific case. A result may declare `requires_rag`, `rag_query`, or `rag_queries`; the runtime uses those queries as overrides and invokes `RagService`.

The domain declares **what knowledge is needed**. It does not implement its own vector client, retriever, or parallel RAG prompt stack.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```json
{
  "requires_rag": true,
  "rag_queries": [
    "How to cancel YouTube Premium?",
    "How to cancel Aya Books?"
  ]
}
```

Related settings include `RAG_TOP_K` and `SKIP_RAG_WHEN_MCP_SUFFICIENT`.

### 7. Telemetry and observability

When the feature participates in an agent execution, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id`, and other correlation keys in state/events. This makes the decision observable through Langfuse/Observer without embedding observability logic in the domain.

### 8. How to test

1. Add a unit test for the core behavior.
2. Add a runtime integration test when state spans multiple turns.
3. Test the happy path and at least one failure/rejection path.
4. Confirm retries/replays do not duplicate side effects for transactional features.
5. In production, also validate telemetry and ID correlation.

### 9. Common mistakes

- Requesting RAG for transactional facts already resolved by an API adds unnecessary cost and latency.
- Queries that are too broad reduce relevance.
- Do not trust retrieved content for critical responses without Retrieval Guardrails.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
