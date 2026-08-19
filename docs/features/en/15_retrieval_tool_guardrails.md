# Retrieval / Tool Guardrails

> `agent_framework_oci` feature — English guide.

**Main implementation:** `guardrails/pipeline.py + guardrails/rails.py`

---

### 1. What it is

Applies safety and validation not only to user input and final output, but also to RAG-retrieved knowledge and tool arguments/results.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
User
 ↓
Input Guardrails
 ↓
RAG → Retrieval Guardrails
 ↓
LLM/Tool call → Tool Guardrails
 ↓
API
 ↓
Output Guardrails
```

### 4. How it works internally

The framework has distinct guardrail stages. For retrieval, rails such as `RAGSEC` and `RET_REL` can validate retrieved-content safety and relevance. For tools, `TOOL_VAL` validates usage/arguments before or around execution.

Global settings include `ENABLE_INPUT_GUARDRAILS`, `ENABLE_OUTPUT_GUARDRAILS`, `ENABLE_PARALLEL_GUARDRAILS`, `GUARDRAILS_FAIL_FAST`, and `GUARDRAILS_CONFIG_PATH`. The agent YAML is the source of truth for enabled rails.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```yaml
retrieval:
  rails:
    - RAGSEC
    - RET_REL

tool:
  rails:
    - TOOL_VAL
```

Example: the question concerns canceling a service, but RAG retrieves modem documentation. `RET_REL` can reject that context before it is used in the answer.

### 7. Telemetry and observability

When the feature participates in an agent execution, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id`, and other correlation keys in state/events. This makes the decision observable through Langfuse/Observer without embedding observability logic in the domain.

### 8. How to test

1. Add a unit test for the core behavior.
2. Add a runtime integration test when state spans multiple turns.
3. Test the happy path and at least one failure/rejection path.
4. Confirm retries/replays do not duplicate side effects for transactional features.
5. In production, also validate telemetry and ID correlation.

### 9. Common mistakes

- Having a rail implementation does not mean it is enabled: check `guardrails.yaml`.
- Fail-fast behavior should be chosen intentionally for each stage.
- Tool guardrails do not replace business validation inside the API/action itself.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/guardrails/pipeline.py`
- `libs/agent_framework/src/agent_framework/guardrails/rails.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
