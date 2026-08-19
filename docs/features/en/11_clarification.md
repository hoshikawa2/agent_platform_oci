# Clarification

> `agent_framework_oci` feature — English guide.

**Main implementation:** `runtime/agent_runtime.py`

---

### 1. What it is

When required information is missing or a tool finds multiple options, the framework asks the user instead of guessing.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
ambiguous request
  ↓
NEEDS_CLARIFICATION
  ↓
question + options
  ↓
user answers
  ↓
framework resolves
  ↓
resume same tool/workflow
```

### 4. How it works internally

The runtime supports clarification for both missing parameters and ambiguous tool results. For tool-result clarification, a result with `status: NEEDS_CLARIFICATION` may include options; the runtime persists `pending_tool_clarification`, moves to `TOOL_RESULT_CLARIFICATION`, and can resolve responses by ordinal or name.

After selection, the framework reuses the same tool and injects resolved arguments, preventing the router from treating a short reply as a brand-new intent.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```json
{
  "status": "NEEDS_CLARIFICATION",
  "question": "Which service?",
  "options": [
    {"id": "tim_music", "label": "TIM Music"},
    {"id": "hbo_max", "label": "HBO Max"}
  ]
}
```

User: `the second one` → `hbo_max`.

### 7. Telemetry and observability

When the feature participates in an agent execution, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id`, and other correlation keys in state/events. This makes the decision observable through Langfuse/Observer without embedding observability logic in the domain.

### 8. How to test

1. Add a unit test for the core behavior.
2. Add a runtime integration test when state spans multiple turns.
3. Test the happy path and at least one failure/rejection path.
4. Confirm retries/replays do not duplicate side effects for transactional features.
5. In production, also validate telemetry and ID correlation.

### 9. Common mistakes

- Do not discard `pending_tool_clarification` between turns.
- A short answer should be resolved against pending options before normal routing.
- Options without stable identifiers/labels reduce resolution quality.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
