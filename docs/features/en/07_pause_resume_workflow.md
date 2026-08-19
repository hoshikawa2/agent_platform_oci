# Resume de Workflow / Pause / Resume Workflow

> `agent_framework_oci` feature — English guide.

**Main implementation:** `workflows/runtime.py + workflows/graph.py`

---

### 1. What it is

Allows a workflow to stop at a safe point, persist state, and continue later using user input or another event.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Workflow
  ↓
pre-pause actions
  ↓
PAUSE
  ↓
checkpoint/state
  ↓
new message
  ↓
RESUME
  ↓
remaining actions
```

### 4. How it works internally

`WorkflowRuntime` exposes `arun(...)` and `aresume(...)`. The pause node is separated from the preceding action so previous side effects are not executed again on resume. The same `execution_id/thread_id` identifies the paused and resumed execution.

The runtime supports declarative conditions such as `all`, `any`, `not`, `eq`, `neq`, and `exists`, so pause/continue decisions do not need to live in the prompt.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
status = await runtime.arun(...)
# status == PAUSED

status = await runtime.aresume(execution_id, input={"confirmed": true})
# status == COMPLETED
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

- Losing the `execution_id` prevents resuming the right execution.
- Restarting the workflow from scratch after confirmation may duplicate side effects.
- Pause without shared checkpoint/state storage is fragile across multiple replicas.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/workflows/graph.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
