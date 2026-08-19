# Durable Idempotency

> `agent_framework_oci` feature — English guide.

**Main implementation:** `idempotency.py`

---

### 1. What it is

Prevents the same critical operation from executing twice, including when a retry lands on another replica/pod.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
request
  ↓
idempotency key
  ↓
durable store
  ├─ exists → return previous result
  └─ missing → execute → persist result
```

### 4. How it works internally

`create_idempotency_store(settings, ...)` chooses a backend according to configuration/platform. The framework provides `IdempotencyStore` and `InMemoryIdempotencyStore`, but distributed production should prefer shared storage. Settings include `IDEMPOTENCY_PROVIDER`, `IDEMPOTENCY_REQUIRE_DURABLE`, and `IDEMPOTENCY_TTL_SECONDS`.

Idempotency is different from retry: retry repeats an attempt; idempotency guarantees that repetition does not create another side effect.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
Pod A receives cancellation
→ key=customer:service:operation
→ executes
→ stores result

Pod A crashes

Pod B receives retry
→ same key
→ finds stored result
→ DOES NOT cancel again
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

- An in-memory store across multiple pods is not durable idempotency.
- A key that is too broad may block legitimate operations; too narrow may allow duplicates.
- TTL should match the real retry/replay window.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/idempotency.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
