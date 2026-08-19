# Long Term Memory

> `agent_framework_oci` feature — English guide.

**Main implementation:** `memory/long_term_memory.py + memory/long_term_store.py`

---

### 1. What it is

Allows useful information to persist across different sessions without depending on the full transcript of a previous conversation.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Session A
  ↓
extract relevant memory
  ↓
Long Term Memory Store
  ↓
... days later ...
  ↓
Session B
  ↓
retrieve relevant context
  ↓
agent
```

### 4. How it works internally

Long-term memory is different from message history and checkpoints. It persists useful facts/preferences and retrieves them as context for a future session. The framework supports `memory`, `sqlite`, `autonomous`, and `oracle` providers.

Important settings include `ENABLE_LONG_TERM_MEMORY`, `LONG_TERM_MEMORY_PROVIDER`, `LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS`, `LONG_TERM_MEMORY_MIN_CONFIDENCE`, `LONG_TERM_MEMORY_AUTO_EXTRACT`, and `LONG_TERM_MEMORY_INJECT_CONTEXT`.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```env
ENABLE_LONG_TERM_MEMORY=true
LONG_TERM_MEMORY_PROVIDER=oracle
LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS=20
LONG_TERM_MEMORY_MIN_CONFIDENCE=0.70
LONG_TERM_MEMORY_AUTO_EXTRACT=true
LONG_TERM_MEMORY_INJECT_CONTEXT=true
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

- Do not confuse LTM with replaying the entire transcript.
- Irrelevant or low-confidence memories should not be injected.
- For multiple replicas, prefer shared durable storage over local memory.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/memory/long_term_memory.py`
- `libs/agent_framework/src/agent_framework/memory/long_term_store.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
