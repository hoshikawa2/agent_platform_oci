# FRAMEWORK_CHANNEL_INPUT_MODE

This backend setting controls what kind of channel input the Agent Framework backend accepts.

It replaces the ambiguous use of `CHANNEL_GATEWAY_MODE` inside the backend.

## Values

```env
FRAMEWORK_CHANNEL_INPUT_MODE=embedded
```

The backend may use internal channel adapters to interpret simple/native channel payloads. This is useful for demos, labs, local frontend, curl tests, and simple environments.

```env
FRAMEWORK_CHANNEL_INPUT_MODE=external
```

The backend accepts only a normalized `GatewayRequest` produced by an external Channel Gateway. It does not parse native WhatsApp, Voice, Teams, or other channel payloads.

## Recommended enterprise setup

In the external channel gateway service:

```env
CHANNEL_GATEWAY_RUNTIME_MODE=adapter
```

In this backend:

```env
FRAMEWORK_CHANNEL_INPUT_MODE=external
```

Flow:

```text
External channel / browser / customer adapter
  ↓
channel_gateway:7000
  CHANNEL_GATEWAY_RUNTIME_MODE=adapter
  ↓ GatewayRequest
agent_template_backend:8000
  FRAMEWORK_CHANNEL_INPUT_MODE=external
  ↓
LangGraph / Agents / MCP / Guardrails
```

## Valid direct request to backend in external mode

```bash
curl -s -X POST "http://localhost:8000/gateway/message" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "payload": {
      "message": "Quero consultar minha fatura",
      "session_id": "backend-external-ok-001"
    }
  }' | jq
```

## Invalid direct request to backend in external mode

```bash
curl -i -s -X POST "http://localhost:8000/gateway/message" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quero consultar minha fatura",
    "session_id": "raw-payload-error-001"
  }'
```

Expected result: HTTP 422.

## Legacy compatibility

`CHANNEL_GATEWAY_MODE` is still present as a legacy alias for older environments, but new deployments should use:

```env
FRAMEWORK_CHANNEL_INPUT_MODE=embedded|external
```
