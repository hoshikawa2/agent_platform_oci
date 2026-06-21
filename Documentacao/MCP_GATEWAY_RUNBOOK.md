# MCP Gateway Runbook

## Arquitetura corrigida

O backend/agente não deve chamar diretamente os MCP servers finais. O fluxo correto é:

```text
agent_template_backend / agent_framework
  -> MCP Gateway Client
  -> apps/mcp_gateway
  -> mcp/servers/telecom_mcp_server ou mcp/servers/retail_mcp_server
```

## Subir localmente

A partir da raiz do projeto:

### Terminal 1 - Telecom MCP Server

```bash
cd mcp/servers/telecom_mcp_server
python -m uvicorn main:app --host 0.0.0.0 --port 8100 --reload
```

### Terminal 2 - Retail MCP Server

```bash
cd mcp/servers/retail_mcp_server
python -m uvicorn main:app --host 0.0.0.0 --port 8200 --reload
```

### Terminal 3 - MCP Gateway

```bash
cd apps/mcp_gateway
export MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml
python -m uvicorn app.main:app --host 0.0.0.0 --port 8300 --reload
```

### Terminal 4 - Backend/agente

No `.env` do backend/agente ou do runtime que usa o `agent_framework`, habilite:

```env
ENABLE_MCP_TOOLS=true
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_AGENT_ID=telecom_contas
MCP_GATEWAY_TENANT_ID=default
```

## Testes rápidos

### Health do gateway

```bash
curl http://localhost:8300/health
```

### Lista de tools expostas pelo gateway

```bash
curl http://localhost:8300/v1/tools
```

### Chamada de tool via gateway

```bash
curl -X POST http://localhost:8300/v1/tools/consultar_fatura/invoke \
  -H 'Content-Type: application/json' \
  -d '{
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "channel": "web",
    "tool_name": "consultar_fatura",
    "arguments": {
      "msisdn": "11999999999",
      "invoice_id": "INV-123"
    },
    "business_context": {},
    "metadata": {"session_id": "local-test"}
  }'
```

Resposta esperada: `ok: true`, `data.invoice_id`, `data.msisdn`, `metadata.server: telecom`.

## O que foi corrigido

- `apps/mcp_gateway/config/mcp_gateway.yaml` agora aponta para os MCP servers reais nas portas `8100` e `8200`.
- O MCP Gateway agora suporta o contrato legado dos MCP servers: `POST /mcp/tools/call` com `{tool_name, arguments}`.
- O `agent_framework` ganhou flags `MCP_GATEWAY_ENABLED`, `MCP_GATEWAY_URL`, `MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_AGENT_ID` e `MCP_GATEWAY_TENANT_ID`.
- O `MCPToolRouter` passa a chamar o MCP Gateway quando `MCP_GATEWAY_ENABLED=true`.
- `libs/agent_framework/config/mcp_servers.yaml` foi mantido como registry lógico/fallback, não como caminho principal quando o gateway está ativo.
