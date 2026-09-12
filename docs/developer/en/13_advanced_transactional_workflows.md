### Advanced transactional workflows

### Goal

This chapter turns a sensitive tool into a deterministic transaction with parameter collection, pre-validation, confirmation, versioned workflow, pause/resume, idempotency, and recovery. Business rules and actions belong to the agent; the execution engine belongs to the framework.

### Actual flow

1. `routing.yaml` selects the agent and limits candidate tools.
2. `tools.yaml` describes arguments, prompts, and response behavior.
3. `mcp_parameter_mapping.yaml` resolves identity, defaults, and extraction.
4. `tool_policies.yaml` classifies the operation and requires confirmation.
5. Optional pre-validation checks whether execution may continue without producing an effect.
6. After unambiguous confirmation, execution is direct or delegated to `WorkflowToolExecutor`.
7. `WorkflowRuntime` loads the active version, runs actions, persists pauses, and returns `COMPLETED`, `PAUSED`, or `FAILED`.
8. An idempotency key prevents duplicate external effects.

### Catalog and policy are different contracts

```yaml
# config/tools.yaml
tools:
  request_return:
    description: Opens an order return.
    mcp_server: retail
    enabled: true
    tool_type: action
    confirmation_required: true
    requires: [order_id, reason]
    args_schema:
      order_id:
        type: string
        label: the order number
        user_prompt: Provide the order number.
      reason:
        type: string
        label: the return reason
        user_prompt: What is the return reason?
```

```yaml
# config/tool_policies.yaml
version: 1
defaults:
  operation_type: read_only
  require_confirmation: false
tool_policies:
  request_return:
    operation_type: transactional
    require_confirmation: true
    requires: [order_id, reason]
    pre_validation:
      enabled: true
      tool: validate_return
      fail_open: false
    execution:
      mode: workflow
      workflow: order_return
      version: active
```

`tools.yaml` is the public catalog; `tool_policies.yaml` governs effects. Do not rely only on catalog `confirmation_required`: effective policy must declare `operation_type` and `require_confirmation`. A pre-validation tool must be read-only and never perform the transaction early. Prefer `fail_open: false` for sensitive operations.

### Versioned workflow and actions

Store definitions under `workflows/<name>.vN.yaml` and maintain a valid active definition. Node IDs must be unique; `start`, destinations, and `resume_from` must exist; `retry` accepts 0 through 10. Paths under `$.input.*` read workflow input and `$.nodes.<id>.*` read earlier results.

Agent actions use `@workflow_action("name")`, matching `node.action`, and implement `(params: dict, state: dict) -> dict`. Import the action module during startup so decorators register. Return serializable data only—never an HTTP client, connection, exception, or coroutine. Complete executable YAML and Python are available in the matching [Portuguese chapter](../pt/13_workflows_transacionais_avancados.md).

### Idempotent external effects

Create one `create_idempotency_store(...)` instance at startup and inject it into actions. Build the key from stable business identity, operation, resource, and contract version—not merely a timestamp. `IDEMPOTENCY_PROVIDER` takes precedence over checkpoint, session, and cache providers. For production transactions, enable `IDEMPOTENCY_REQUIRE_DURABLE=true` and select an appropriate `oracle`, `redis`, or `sqlite` provider. Memory does not protect across pods or restarts. Persist the outcome only after the external system confirms the effect.

### Pause, expected input, and resume

A node may declare `pause.expected_input` with `key`, `allowed_values`, normalization, `reprompt`, and a semantic classifier. Explicit confirmation remains deterministic; the classifier handles only inconclusive replies and must return an allowed option. `contextual_reentry` releases the workflow and returns the utterance to normal routing without confirming user facts.

Resume with the same `execution_id`; a new execution creates a separate transaction. The checkpoint must contain serializable data sufficient to rebuild the pause. Duplicate replies must check idempotency before repeating an effect.

### Intent shift, recovery, and replay

When a user abandons a transaction, clear pending call, collected arguments, confirmation, and related transaction state. Do not reuse parameters from a closed transaction. A contextual question may be answered and return to the pause; a genuine intent change explicitly closes or suspends the flow according to agent policy.

- `PAUSED`: persist execution ID, prompt, and expected-input contract.
- `FAILED`: keep technical details in telemetry and return a safe message.
- timeout after sending: query idempotency or external status before resending.
- replay after `COMPLETED`: return the persisted result without execution.
- new version: in-flight runs retain their version; `active` applies to new runs.

Test invalid graphs, valid/invalid paths, retry, pause/resume, unmatched answers, intent shift, duplicates, idempotency-provider failure, and post-finalization replay. Run `pytest -q tests/test_advanced_developer_documentation.py`.
