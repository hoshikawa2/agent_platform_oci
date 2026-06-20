# AI Agent Platform com MCP Tools

Esta versão adiciona uma camada MCP ao framework:

- `agent_framework.mcp.MCPToolRouter`
- `agent_template_backend/config/mcp_servers.yaml`
- `agent_template_backend/config/tools.yaml`
- `mcp_servers/telecom_mcp_server`
- `mcp_servers/retail_mcp_server`

## Subir localmente

Terminal 1:

```bash
bash ./scripts/run_mcp_servers.sh
```

Terminal 2:

```bash
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -e ../agent_framework
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --reload-dir config --port 8000
```

Terminal 3:

```bash
cd agent_frontend
python -m http.server 5173
```

## Testes rápidos

Listar tools MCP carregadas pelo backend:

```bash
curl http://localhost:8000/debug/mcp/tools
```

Chamar tool diretamente via backend:

```bash
curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura \
  -H 'Content-Type: application/json' \
  -d '{"msisdn":"11999999999","invoice_id":"INV-001"}'
```

Roteamento Telecom + MCP:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"session_id":"sess-tel-1","message":"Minha fatura veio alta","context":{"msisdn":"11999999999","invoice_id":"INV-001"}}}'
```

Roteamento Retail + MCP:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"session_id":"sess-ret-1","message":"Meu pedido não chegou","context":{"order_id":"PED-1001","customer_id":"C-001"}}}'
```

## Docker Compose

```bash
docker compose up --build
```

No compose, o backend usa `config/mcp_servers.docker.yaml` para apontar para `telecom-mcp` e `retail-mcp`.
