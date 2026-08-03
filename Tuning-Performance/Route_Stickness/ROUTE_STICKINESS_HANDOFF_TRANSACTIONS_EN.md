# Route Stickiness, Handoff, Session End, and MCP Policies

## 1. Purpose

This document consolidates semantic route continuity, human handoff, session ending, and minimal protection for read-only and transactional MCP tools in the OCI Agent Framework.

The capabilities are complementary:

- **Route stickiness** decides whether a turn stays with the active agent or returns to the Enterprise Router.
- **Handoff and session end** handle global session actions outside domain agents.
- **MCP policies** decide whether an already selected tool may execute, distinguishing `read_only` from `transactional` operations.

All capabilities are optional and preserve previous behavior when disabled or not configured.

## 2. Architecture overview

```text
Incoming message
   |
   +-- session already ended? -- yes --> reject session reuse
   |
   +-- route stickiness enabled --> lightweight semantic classifier
   |       |
   |       +-- CONTINUE + active agent --> active agent
   |       +-- ROUTE/low confidence/error --> Enterprise Router
   |       +-- HUMAN_HANDOFF --> global human_handoff node
   |       +-- END_SESSION --> global end_session node
   |
   +-- route stickiness disabled --> Enterprise Router
                                           |
                                           v
                                      domain agent
                                           |
                                           v
                                  selected MCP tool
                                           |
                                           v
                              read-only/transactional policy
                                  |                    |
                               allowed              blocked
                                  |                    |
                                  v                    v
                           MCP Gateway/Server     safe response
```

The continuity classifier does not answer users, choose another agent, execute tools, or interpret business rules. The MCP Server remains the final authority for authentication, authorization, idempotency, validation, and atomicity.

## 3. Continuity and session decisions

| Decision | Condition | Destination | Runs agent/MCP? |
|---|---|---|---|
| `CONTINUE` | The message remains in the active agent's domain and exceeds the threshold | active agent | yes, according to the agent flow |
| `ROUTE` | Topic change, uncertainty, low confidence, or failure | Enterprise Router | only after routing |
| `HUMAN_HANDOFF` | Human assistance requested | global `human_handoff` node | no |
| `END_SESSION` | Session ending requested or confirmed | global `end_session` node | no |

On the first turn, `CONTINUE` is normalized to `ROUTE` because no active agent exists. `HUMAN_HANDOFF` and `END_SESSION` may be detected on the first turn.

### 3.1 Why the decision is semantic

The implementation uses no regexes, phrase lists, pronoun lists, or language-specific keywords. Code retains only technical decisions:

- feature flag;
- presence of an active agent;
- confidence threshold;
- output-contract validation;
- fallback on timeout, error, or invalid JSON.

This avoids domain-specific language-pattern maintenance and keeps multilingual behavior in the LLM profile.

## 4. Global session contracts

### 4.1 Human handoff

The router returns:

```json
{
  "route": "human_handoff",
  "intent": "human_handoff",
  "method": "continuity",
  "handoff": true,
  "metadata": {
    "session_control": "HUMAN_HANDOFF",
    "route_bypassed": true
  }
}
```

The global node sets:

- `session_control=HUMAN_HANDOFF`;
- `human_handoff_requested=true`;
- `session_ended=false`;
- `next_state=HUMAN_HANDOFF_REQUESTED`.

The `session.human_handoff.requested` event lets the integration select the queue, provider, and protocol. The framework assumes no specific human-service platform.

### 4.2 Session end

The router returns:

```json
{
  "route": "end_session",
  "intent": "end_session",
  "method": "continuity",
  "metadata": {
    "session_control": "END_SESSION",
    "route_bypassed": true
  }
}
```

The global node sets:

- `session_control=END_SESSION`;
- `session_ended=true`;
- `human_handoff_requested=false`;
- `next_state=SESSION_ENDED`.

The `session.end.requested` event should be emitted before persistence. For definitive closure, `session_ended=true` must be persisted, and new messages using the same `session_id` must be blocked before guardrails, routing, agents, RAG, judges, or MCP.

## 5. Read-only and transactional MCP policies

### 5.1 Responsibility

After routing and agent selection identify a tool, `MCPToolRouter` applies policy immediately before the external call:

- `read_only`: retrieves data without changing state and does not require confirmation by default.
- `transactional`: changes state and may require explicit confirmation and mandatory fields.

This classification adds no LLM router and does not replace the existing per-agent/per-intent tool allowlist.

### 5.2 Backend configuration

```text
templates/agent_template_backend/config/tool_policies.yaml
```

```dotenv
TOOL_POLICIES_PATH=./config/tool_policies.yaml
```

```yaml
version: 1

defaults:
  operation_type: read_only
  require_confirmation: false

tool_policies:
  consultar_plano:
    operation_type: read_only

  alterar_plano:
    operation_type: transactional
    require_confirmation: true
    requires: [new_plan_id]

  cancelar_servico:
    operation_type: transactional
    require_confirmation: true
```

A confirmed transaction must receive a literal boolean:

```json
{
  "new_plan_id": "CONTROLE_100",
  "confirmed": true
}
```

`"confirmation": true` is also accepted. Strings such as `"true"` do not confirm an operation.

### 5.3 Compatibility

- If `tool_policies.yaml` is absent, the framework preserves `tool_type`, `requires`, `confirmation_required`, and `execution_policy` from `tools.yaml`.
- Legacy tools without policy execute as before.
- An explicit entry in the new file takes precedence for that tool's type and confirmation behavior.
- `tools.yaml` remains the source for endpoint, schema, enablement, and cache.
- Policy belongs in the backend rather than `libs/agent_framework` because it varies by application and domain.

## 6. Interaction between continuity and transactions

Route stickiness does not authorize transactions. Even when `CONTINUE` retains the active agent, every tool passes through MCP policy again.

Example:

```text
User: I want to switch to the Control 100 plan.
Agent: Do you confirm the change to Control 100?
User: Yes.
  -> CONTINUE retains product_agent
  -> agent retrieves the pending action
  -> MCPToolRouter validates confirmation=true
  -> alterar_plano executes
```

For `HUMAN_HANDOFF` or `END_SESSION`, no domain agent or MCP tool should execute. A pending transaction must be invalidated or remain suspended according to an explicit application policy; it must never execute implicitly after handoff or session end.

## 7. Continuity configuration

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

Use the smallest approved model available in the OCI environment. The classifier receives only the active agent, capabilities derived from intents, previous intent/domain, limited recent history, and the current message. It receives no complete RAG context, full MCP results, agent prompt, or business rules.

## 8. Safety and fallback

- Only decisions above the configured threshold are accepted.
- `CONTINUE` without an active agent becomes `ROUTE`.
- Low confidence, timeout, error, or invalid JSON falls back to the Enterprise Router.
- Handoff and session ending execute no tools.
- Transaction confirmation requires a literal boolean.
- Conversational validation does not replace MCP Server controls.
- Ended sessions must be blocked at request entry.
- Transaction retries require idempotency in the destination service.

## 9. Telemetry

Continuity event:

```json
{
  "decision": "CONTINUE",
  "confidence": 0.97,
  "active_agent": "product_agent",
  "route_bypassed": true,
  "profile_name": "route_continuity"
}
```

Recommended fields:

- `route_decision.method`;
- `active_agent`;
- `route_bypassed`;
- `continuity_signal`;
- `session_control`;
- `human_handoff_requested`;
- `session_ended`;
- `tool_name`;
- `operation_type`;
- `policy_source`;
- `blocked_by_policy`.

## 10. Tests and benchmark

Minimum scenarios:

1. continuity with router bypass;
2. domain change with router fallback;
3. low confidence, timeout, and invalid JSON;
4. `CONTINUE` without an active agent;
5. handoff and session end on first and subsequent turns;
6. rejection of messages after session end;
7. read-only call without confirmation;
8. transaction without confirmation, with a string, and with a valid boolean;
9. missing mandatory field;
10. absent `tool_policies.yaml` using legacy behavior.

```bash
PYTHONPATH=libs/agent_framework/src:templates/agent_template_backend python -m pytest -q
```

For benchmarking, compare the same conversation with the feature enabled and disabled. Record `route_bypassed`, calls to `llm.router`, `llm.route_continuity` latency, tokens per profile, and total p50/p95/p99 latency. Attribute gains to stickiness only when `route_bypassed=true` and no Enterprise Router generation occurs in the same turn.

## 11. Adoption criteria

Adopt route stickiness for multi-turn conversations that frequently remain with the same agent. Register policies only for tools requiring additional behavior, starting with transactions that require confirmation. Keep authorization, idempotency, and business rules in the MCP Server to avoid competing sources of truth.
