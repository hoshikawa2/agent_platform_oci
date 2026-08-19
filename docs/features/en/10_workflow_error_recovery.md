# Workflow Error Recovery

> `agent_framework_oci` feature — English guide.

**Main implementation:** `workflows/runtime.py`

---

### 1. What it is

Preserves partial execution state when a later step fails, making it possible to know what already happened and avoid repeating side effects.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
step A ✅
step B ✅
step C ❌
   ↓
FAILED + partial snapshot
   ↓
recovery decides what may continue/retry
```

### 4. How it works internally

The runtime preserves the partial LangGraph snapshot when a later step fails and produces generic `error_details`. When an external exception provides structured information, HTTP status, body, attempt count, code, and metadata may be preserved.

This feature does not mean “retry everything”. Safe recovery depends on knowing what already executed, idempotency guarantees, and the nature of the failure.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```json
{
  "status": "FAILED",
  "error_details": {
    "status": 503,
    "attempts": 3,
    "code": "UPSTREAM_UNAVAILABLE"
  },
  "state": {
    "protocol_created": true,
    "operation_completed": true,
    "sms_sent": false
  }
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

- Blind retries may repeat transactions.
- If external exceptions discard metadata, recovery becomes less precise.
- Always combine with Durable Idempotency for critical side effects.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
