# Voice Interruption Replay

> `agent_framework_oci` feature — English guide.

**Main implementation:** `channels/interruption.py`

---

### 1. What it is

Decides whether audio received while the agent is speaking represents a new intent, a backchannel/noise event, or something that should simply replay/continue the previous speech.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
audio during speech
  ↓
InterruptionPolicy
  ├─ process → new message
  ├─ classify → lightweight classifier
  └─ replay → previous speech
```

### 4. How it works internally

The policy lives in the framework rather than domain code. It distinguishes terminal sessions, `idle_nudge`, non-interruptible speech, and potentially interruptible speech. When needed, it may use a lightweight classifier backed by `LLMProvider`; on classification failure, it can fail safely to replay.

The goal is to prevent “uh-huh”, noise, echo, or residual audio fragments from being interpreted as a full new intent.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
Agent: "Your invoice contains..."
User: "uh-huh"
→ replay/continue

Agent: "Your invoice contains..."
User: "wait, I want to ask something else"
→ process new intent
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

- Sending every noise fragment to an LLM increases latency and cost.
- Allowing interruption during non-interruptible transactional speech may corrupt UX/state.
- Replay should use a real previous utterance, not a technical envelope.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/channels/interruption.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
