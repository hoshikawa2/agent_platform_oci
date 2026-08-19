# Dynamic Transaction States

> `agent_framework_oci` feature — English guide.

**Main implementation:** `runtime/agent_runtime.py + mcp/tool_policy.py`

---

### 1. What it is

Allows confirmation states to be derived from the current agent/domain instead of hardcoding every business domain into the framework.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
transactional tool
  ↓
current agent/domain
  ↓
WAITING_<PREFIX>_CONFIRMATION
  ↓
confirm/reject
  ↓
next state
```

### 4. How it works internally

Instead of maintaining fixed states such as `WAITING_BILLING_CONFIRMATION`, `WAITING_PRODUCT_CONFIRMATION`, and so on for every known domain, the runtime derives a prefix from the current agent and builds the confirmation state dynamically. This keeps the framework generic.

`operation_type` accepts `read_only`, `transactional`, `conversational`, and `internal`; only `transactional` enters the transactional confirmation path.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
VasAgent + cancel_vas
→ WAITING_VAS_CONFIRMATION

AddressAgent + change_address
→ WAITING_ADDRESS_CONFIRMATION
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

- Hardcoding states in domain code reduces reuse.
- Classifying a tool as `conversational` should not trigger transactional confirmation.
- Changing agent identifiers may change state prefixes; keep IDs stable.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `libs/agent_framework/src/agent_framework/mcp/tool_policy.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
