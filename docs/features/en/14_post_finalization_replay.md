# Post Finalization Replay

> `agent_framework_oci` feature — English guide.

**Main implementation:** `channels/interruption.py + config/settings.py`

---

### 1. What it is

Prevents residual audio or late messages from reopening a session that has already been finalized.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
terminal session
  ↓
residual input
  ↓
policy detects finalization
  ↓
replay last utterance/fallback
  ↓
DO NOT reopen LangGraph
```

### 4. How it works internally

The interruption policy checks terminal-session metadata before treating an input as a new intent. When terminal speech is available, it uses `last_assistant_text`/`terminal_replay_text`; otherwise it may use `POST_FINALIZE_REPLAY_MESSAGE`.

The purpose is to protect the logical end of a session, especially on voice channels where audio packets may arrive after the finalization event.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
Agent: "The interaction is complete."
→ session finalized

late fragment arrives: "uh..."
→ replay "The interaction is complete."
→ no new routing / tool / LLM call
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

- If terminal state is not persisted, another replica may reopen the journey.
- Do not replay technical/JSON envelopes as user-facing speech.
- This feature does not replace an intentional new-session policy.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/channels/interruption.py`
- `libs/agent_framework/src/agent_framework/config/settings.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
