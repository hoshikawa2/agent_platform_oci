# Semantic Route Stickiness and Global Session Control in Agent Framework OCI

## Purpose

This optional capability uses a lightweight LLM profile and no regex, phrase lists, or domain-specific language rules. It classifies each turn as:

- `CONTINUE`: keep the active agent;
- `ROUTE`: run the regular Enterprise Router;
- `HUMAN_HANDOFF`: request human assistance;
- `END_SESSION`: finish the automated session.

The classifier does not answer the user, execute tools, or implement domain rules. Human handoff and session ending are handled by global graph nodes.

## Flow

```text
Incoming turn
  -> lightweight semantic classifier
       CONTINUE + active agent -> active agent
       ROUTE / low confidence / error -> Enterprise Router
       HUMAN_HANDOFF -> human_handoff node
       END_SESSION -> end_session node
```

`CONTINUE` is converted to `ROUTE` when there is no active agent. Global session actions can be detected on the first turn.

## Configuration

```dotenv
ENABLE_ROUTE_STICKINESS=true
ROUTE_STICKINESS_LLM_PROFILE=route_continuity
ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.90
ROUTE_STICKINESS_HISTORY_TURNS=2
ROUTE_STICKINESS_MAX_TOKENS=80
HUMAN_HANDOFF_MESSAGE=I will transfer your request to a person.
END_SESSION_MESSAGE=The session has ended. Thank you for contacting us.
```

```yaml
profiles:
  route_continuity:
    provider: oci_openai
    model: openai.gpt-4.1-mini
    temperature: 0
    max_tokens: 80
    timeout_seconds: 5
```

Use the smallest approved model available in the target OCI environment.

## Human handoff contract

The router returns route `human_handoff`, intent `human_handoff`, `handoff=true`, and metadata `session_control=HUMAN_HANDOFF`. The graph node sets:

- `human_handoff_requested=true`;
- `session_ended=false`;
- `next_state=HUMAN_HANDOFF_REQUESTED`.

It emits `session.human_handoff.requested`. The customer integration remains responsible for choosing the human queue and protocol.

## End-session contract

The router returns route `end_session`, intent `end_session`, and metadata `session_control=END_SESSION`. The graph node sets:

- `session_ended=true`;
- `human_handoff_requested=false`;
- `next_state=SESSION_ENDED`.

It emits `session.end.requested`. Channel-specific session expiration or connection closing remains an integration responsibility.

## Safety behavior

- Only decisions above the configured confidence threshold are accepted.
- Invalid JSON, timeout, low confidence, or errors fall back to the Enterprise Router.
- Human handoff and session ending do not execute domain agents or MCP tools.
- The classifier never selects a human queue and never physically closes a channel connection.

## Tests

Run:

```bash
PYTHONPATH=libs/agent_framework/src pytest -q tests/unit/test_semantic_route_stickiness.py
```

The suite covers CONTINUE, ROUTE, low confidence, invalid output, HUMAN_HANDOFF, END_SESSION, first-turn global actions, and CONTINUE without an active agent.
