# External Channel Gateway

This service is a separate Channel Gateway that sits in front of the Agent Framework backend.

It has its own runtime mode, independent from the backend input mode.

## Runtime modes

```env
CHANNEL_GATEWAY_RUNTIME_MODE=adapter
```

`adapter` means this service receives channel-specific payloads and translates them into `GatewayRequest` before calling the Agent Framework backend.

```env
CHANNEL_GATEWAY_RUNTIME_MODE=proxy
```

`proxy` means this service accepts only an already-built `GatewayRequest` at `/gateway/message` and forwards it after validation.

## Recommended enterprise setup

In `channel_gateway/.env`:

```env
CHANNEL_GATEWAY_RUNTIME_MODE=adapter
AGENT_FRAMEWORK_BASE_URL=http://localhost:8000
DEFAULT_TENANT_ID=default
DEFAULT_AGENT_ID=telecom_contas
```

In `agent_template_backend/.env`:

```env
FRAMEWORK_CHANNEL_INPUT_MODE=external
```

This means:

```text
channel_gateway:7000 = understands channel payloads and builds GatewayRequest
backend:8000         = accepts only GatewayRequest and does not parse native channel payloads
```

## Run

```bash
cd channel_gateway
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 7000
```

## Test web adapter endpoint

```bash
curl -s -X POST "http://localhost:7000/channels/web/message" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quero consultar minha fatura",
    "session_id": "external-gw-test-001",
    "user_id": "user-external-001",
    "message_id": "msg-external-001",
    "customer_key": "11999999999",
    "contract_key": "3000131180",
    "interaction_key": "301953872",
    "session_key": "external-gw-test-001"
  }' | jq
```

## Test proxy mode

Set:

```env
CHANNEL_GATEWAY_RUNTIME_MODE=proxy
```

Then call:

```bash
curl -s -X POST "http://localhost:7000/gateway/message" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "payload": {
      "message": "Quero consultar minha fatura",
      "session_id": "proxy-test-001"
    }
  }' | jq
```

## Important distinction

Do not use `CHANNEL_GATEWAY_MODE=external` to mean “this service is external”.

Use:

```env
CHANNEL_GATEWAY_RUNTIME_MODE=adapter
```

for the external gateway service that owns adapters.

Use:

```env
FRAMEWORK_CHANNEL_INPUT_MODE=external
```

in the Agent Framework backend when the backend must accept only normalized `GatewayRequest` payloads.
