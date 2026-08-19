# Route Stickiness

> `agent_framework_oci` feature — English guide.

**Main implementation:** `routing/enterprise_router.py + runtime/agent_runtime.py`

---

### 1. What it is

Prevents short follow-up messages from unnecessarily switching the conversation to another agent.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
current message
 + short history
 + previous route
   ↓
semantic continuity
   ↓
keep route or handoff
```

### 4. How it works internally

Route Stickiness evaluates whether a new message is semantically continuous with the current subject/agent. It reduces agent ping-pong for messages such as “what about that amount?”, “yes”, “the second one”, or “and last month?”.

Existing settings include `ENABLE_ROUTE_STICKINESS`, `ROUTE_STICKINESS_LLM_PROFILE`, `ROUTE_STICKINESS_CONFIDENCE_THRESHOLD`, `ROUTE_STICKINESS_HISTORY_TURNS`, and `ROUTE_STICKINESS_MAX_TOKENS`. The decision may still allow handoff when there is enough evidence of a topic change.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```env
ENABLE_ROUTE_STICKINESS=true
ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.90
ROUTE_STICKINESS_HISTORY_TURNS=2
ROUTE_STICKINESS_MAX_TOKENS=80
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

- A threshold that is too low may trap the user on the wrong agent.
- A threshold that is too high may lose continuity on short follow-ups.
- Stickiness should not block explicit handoff when the user clearly changes intent.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/routing/enterprise_router.py`
- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
