# Agent Platform OCI — Manual Oficial de Agent Gateway e MCP Gateway

## Objetivo

Este documento consolida:
- Arquitetura oficial
- Inventário dos componentes
- Procedimento completo de execução local
- MCP Gateway
- Agent Gateway
- Backend Runtime
- Frontend
- Testes E2E
- Troubleshooting
- Decisões arquiteturais

---

# Arquitetura Oficial

Frontend (5173)
↓
Agent Gateway (9000)
↓
Agent Template Backend / Runtime (8000)
↓
MCP Gateway (8300)
↓
Telecom MCP Server (8100)
Retail MCP Server (8200)

---

# Portas Oficiais

| Componente | Porta |
|------------|--------|
| Frontend | 5173 |
| Agent Gateway | 9000 |
| Backend Runtime | 8000 |
| MCP Gateway | 8300 |
| Telecom MCP Server | 8100 |
| Retail MCP Server | 8200 |

---

# Variáveis Oficiais

## Agent Template Backend

ENABLE_MCP_TOOLS=true

MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
MCP_GATEWAY_AGENT_ID=telecom_contas
MCP_GATEWAY_TENANT_ID=default

## Agent Gateway

DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml

## MCP Gateway

MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml

---

# Ordem de Inicialização

1. Telecom MCP Server
2. Retail MCP Server
3. MCP Gateway
4. Agent Template Backend
5. Agent Gateway
6. Frontend

---

# Terminal 1 — Telecom MCP Server

cd mcp/servers/telecom_mcp_server

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn main:app --host 0.0.0.0 --port 8100 --reload

Validação:

curl http://localhost:8100/health

---

# Terminal 2 — Retail MCP Server

cd mcp/servers/retail_mcp_server

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn main:app --host 0.0.0.0 --port 8200 --reload

Validação:

curl http://localhost:8200/health

---

# Terminal 3 — MCP Gateway

cd apps/mcp_gateway

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml

python -m uvicorn app.main:app --host 0.0.0.0 --port 8300 --reload

Validações:

curl http://localhost:8300/health
curl http://localhost:8300/ready
curl http://localhost:8300/v1/tools

Teste:

curl -X POST http://localhost:8300/v1/tools/consultar_fatura/invoke

---

# Terminal 4 — Agent Template Backend

cd templates/agent_template_backend

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Validações:

curl http://localhost:8000/health
curl http://localhost:8000/agents

---

# Terminal 5 — Agent Gateway

cd apps/agent_gateway

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
export AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml

python -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload

Validações:

curl http://localhost:9000/health

Teste:

curl -X POST http://localhost:9000/gateway/message

---

# Terminal 6 — Frontend

cd agent_frontend

npm install

npm run dev -- --host 0.0.0.0 --port 5173

Abrir:

http://localhost:5173

Backend URL:

http://localhost:9000

---

# Fluxo de Tools

Agent
↓
MCPToolRouter
↓
MCPGatewayClient
↓
MCP Gateway
↓
MCP Server

---

# Teste Integrado E2E

Frontend
↓
Agent Gateway
↓
Backend Runtime
↓
MCP Gateway
↓
Telecom MCP Server

Resultado esperado:

- Agent Gateway recebe requisição
- Runtime executa LangGraph
- MCP Gateway resolve tool
- MCP Server responde
- Usuário recebe resposta

---

# Troubleshooting

## Backend chamando MCP Server direto

Confirmar:

MCP_GATEWAY_ENABLED=true

MCP_GATEWAY_URL=http://localhost:8300

## Porta incorreta

A porta oficial do MCP Gateway é:

8300

## Agent Gateway não encontra Backend

Validar:

curl http://localhost:8000/health

## MCP Gateway não encontra MCP Server

Validar:

curl http://localhost:8100/health
curl http://localhost:8200/health

---

# Decisões Arquiteturais Oficiais

- Agent Gateway centraliza governança
- Runtime executa LangGraph
- Runtime executa LLM
- MCP Gateway centraliza tools
- MCP Servers executam tools
- Backend usa MCP Gateway
- gateway_runtime.env.example foi removido
- MCP_GATEWAY_* fica no .env do backend
- Porta oficial MCP Gateway = 8300
