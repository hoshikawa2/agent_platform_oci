# Domain Requested LLM Composition

> `agent_framework_oci` feature — English guide.

**Main implementation:** `runtime/agent_runtime.py`

---

### 1. What it is

Lets domain logic compute the authoritative result and ask the LLM only to compose the final user-facing response.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Domain logic computes
   ↓
requires_llm_composition=true
   ↓
framework prevents direct MCP answer
   ↓
official LLMProvider
   ↓
natural-language response
```

### 4. How it works internally

The domain returns authoritative data plus a composition instruction. `AgentRuntimeMixin` recursively detects `requires_llm_composition` in tool/workflow results and avoids terminating through the direct MCP-answer path. Composition then uses the agent's official LLM provider, preserving profiles, tracing, usage accounting, and framework policies.

The LLM should compose language, not recalculate values or override already-resolved business rules.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```json
{
  "success": true,
  "refund_amount": "38.00",
  "requires_llm_composition": true,
  "response_instruction": "Explain the refund using only the computed values."
}
```

### 7. Telemetry and observability

When the feature participates in an agent execution, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id`, and other correlation keys in state/events. This makes the decision observable through Langfuse/Observer without embedding observability logic in the domain.

### 8. How to test

1. Add a unit test for the core behavior.
2. Add a runtime integration test when state spans multiple turns.
3. Test the happy path and at least one failure/rejection path.
4. Confirm retries/replays do not duplicate side effects for transactional features.
5. In production, also validate telemetry and ID correlation.

### 9. Common mistakes

- An overly broad instruction may let the LLM add unauthorized content.
- Do not delegate deterministic calculations back to the LLM.
- If free-form wording is unnecessary, prefer a deterministic direct response.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
