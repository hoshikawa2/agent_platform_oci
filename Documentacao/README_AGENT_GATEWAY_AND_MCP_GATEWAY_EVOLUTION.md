# Agent Platform OCI — Agent Gateway + MCP Gateway Evolution

Este overlay remove o conceito de `AI Gateway` separado.

## Arquitetura

```text
Frontend
  ↓
Agent Gateway
  ├── governance
  ├── model policies
  ├── rate limit
  ├── audit
  └── evaluation hooks
  ↓
Agent Backend / Runtime
  ├── LangGraph
  ├── state
  ├── memory
  ├── checkpoints
  └── LLM providers via profiles existentes
       ↓
     MCP Gateway
       ↓
     MCP Servers
```

## O que entra no Agent Gateway

```text
apps/agent_gateway/app/governance/
apps/agent_gateway/app/governance_middleware.py
apps/agent_gateway/app/routes/governed_proxy_example.py
apps/agent_gateway/config/gateway_governance.yaml
```

## O que entra no MCP Gateway

```text
apps/mcp_gateway/
libs/agent_framework/src/agent_framework/gateways/mcp_gateway_client.py
libs/agent_framework/src/agent_framework/runtime_mcp_gateway_adapter.py
```

## Aplicar overlay

```bash
unzip agent_platform_agent_gateway_mcp_gateway_overlay.zip -d /tmp/overlay
rsync -av /tmp/overlay/ ./
```

## Subir MCP Gateway local

```bash
docker compose -f deploy/docker/docker-compose.mcp-gateway.yml up --build
```

Serviços:

```text
MCP Gateway      http://localhost:8300
Mock Telecom MCP http://localhost:8001
```

## Testar MCP Gateway

```bash
curl http://localhost:8300/health
curl http://localhost:8300/v1/tools
```

Executar tool:

```bash
curl -s -X POST http://localhost:8300/v1/tools/consultar_fatura/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "channel": "web",
    "tool_name": "consultar_fatura",
    "business_context": {
      "customer_key": "11999999999",
      "contract_key": "INV-001",
      "session_key": "session-001"
    }
  }' | jq
```

## Como plugar no Agent Gateway

No handler real do `POST /gateway/message`, antes de encaminhar ao backend/runtime:

```python
governed_body, headers = governance.prepare_backend_request(body)
```

Ao receber resposta do backend:

```python
return governance.process_backend_response(data)
```

O arquivo abaixo mostra um exemplo completo:

```text
apps/agent_gateway/app/routes/governed_proxy_example.py
```

## Variáveis do Runtime

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
```

## Importante

Não existe `apps/ai_gateway`.

A governança de modelo fica no Agent Gateway como policy/metadados.

O Runtime continua usando os LLM providers existentes, podendo ler a política enviada pelo Gateway em:

```python
state["metadata"]["model_policy"]
```
