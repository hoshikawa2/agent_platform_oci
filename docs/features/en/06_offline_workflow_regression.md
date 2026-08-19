# Offline Workflow Regression

> `agent_framework_oci` feature — English guide.

**Main implementation:** `workflows/runtime.py + Tuning-Performance/Offline_Workflow_Regression`

---

### 1. What it is

Allows workflow logic to be regression-tested without requiring the full production infrastructure.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Test
  ↓
explicit deterministic test backend
  ↓
run → PAUSED
  ↓
resume → COMPLETED
  ↓
state/side-effect assertions
```

### 4. How it works internally

`WorkflowRuntime` includes an **explicitly opt-in deterministic/offline test backend**. When `allow_deterministic_fallback=True`, this backend is explicitly selected even if LangGraph is installed, keeping regression results reproducible across developer machines and CI. It can validate DSL rules, conditions, pause/resume behavior, and duplicate-execution protection without depending on LangGraph internals, a database, OCI, or external APIs.

Production behavior still uses LangGraph. Offline mode must never become a silent fallback when LangGraph fails or is unavailable in production.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
run(workflow)
  action_a = executed once
  status = PAUSED

resume(workflow)
  action_a remains executed once
  action_b = executed once
  status = COMPLETED
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

- Using the offline backend in production hides real issues.
- Over-mocking can stop the test from validating real DSL behavior.
- Failing to assert pre-pause side effects may hide duplicate execution.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/Tuning-Performance/Offline_Workflow_Regression`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
