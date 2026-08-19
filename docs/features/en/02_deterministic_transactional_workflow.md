# Deterministic Transactional Workflow

> `agent_framework_oci` feature — English guide.

**Main implementation:** `workflows/runtime.py + mcp/tool_policy.py`

---

### 1. What it is

Ensures state-changing operations follow predictable steps with confirmation and execution control instead of depending on LLM creativity.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Customer message
   ↓
LLM understands intent
   ↓
Tool policy = transactional
   ↓
Deterministic workflow
   ↓
confirmation
   ↓
controlled execution
   ↓
result
```

### 4. How it works internally

The LLM may help interpret intent and extract parameters, but it should not decide the critical sequence of a transaction. `ToolPolicyRegistry` classifies tools, and `operation_type: transactional` activates transactional behavior. `WorkflowRuntime` executes the workflow, preserves state, and integrates pause/resume and error recovery.

`ENABLE_TRANSACTIONAL_WORKFLOWS` controls the capability globally, while `WORKFLOWS_PATH` points to workflow YAML files.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```yaml
tools:
  cancel_service:
    operation_type: transactional
    requires_confirmation: true
```

```text
1. locate service
2. validate eligibility
3. ask for confirmation
4. PAUSE
5. receive confirmation
6. RESUME
7. execute side effect
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

- Marking a write tool as `read_only` bypasses transactional protections.
- Re-running steps before a pause can duplicate side effects; use the official runtime.
- Do not use prompts as the only confirmation guarantee.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/mcp/tool_policy.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
