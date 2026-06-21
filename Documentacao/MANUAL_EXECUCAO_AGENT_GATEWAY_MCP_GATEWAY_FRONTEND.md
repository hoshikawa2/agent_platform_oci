# Manual de Execução Local
## Agent Gateway + MCP Gateway + Agent Template Backend + Frontend

## 1. Arquitetura de execução

A arquitetura local fica assim:

```text
Frontend
  porta 5173
    │
    ▼
Agent Gateway
  porta 9000
    │
    ▼
Agent Template Backend / Agent Runtime
  porta 8000
    │
    ▼
MCP Gateway
  porta 8300
    │
    ▼
MCP Server / Mock Telecom MCP
  porta 8001
```

A governança de modelo, rate limit, auditoria e políticas ficam no **Agent Gateway**.

O **Agent Runtime / Agent Template Backend** continua responsável por:

- LangGraph;
- estado;
- memória;
- checkpoints;
- supervisor/router;
- guardrails;
- judges;
- chamada LLM via providers existentes;
- chamada de tools via MCP Gateway.

---

## 2. Portas

| Componente | Porta | URL |
|---|---:|---|
| Frontend | 5173 | `http://localhost:5173` |
| Agent Gateway | 9000 | `http://localhost:9000` |
| Agent Template Backend | 8000 | `http://localhost:8000` |
| MCP Gateway | 8300 | `http://localhost:8300` |
| MCP Server / Mock Telecom MCP | 8001 | `http://localhost:8001` |

---

## 3. Ordem recomendada para subir

Subir nesta ordem:

1. MCP Server / Mock Telecom MCP
2. MCP Gateway
3. Agent Template Backend
4. Agent Gateway
5. Frontend

---

# 4. Terminal 1 — MCP Server / Mock Telecom MCP

Se estiver usando o mock incluído no overlay:

```bash
cd agent_platform_oci/mcp/servers/mock_telecom_mcp

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

Validar:

```bash
curl http://localhost:8001/health
```

Resultado esperado:

```json
{
  "status": "ok",
  "service": "mock_telecom_mcp"
}
```

---

# 5. Terminal 2 — MCP Gateway

```bash
cd agent_platform_oci/apps/mcp_gateway

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

export MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml

uvicorn app.main:app --host 0.0.0.0 --port 8300 --reload
```

Validar health:

```bash
curl http://localhost:8300/health
```

Validar readiness:

```bash
curl http://localhost:8300/ready
```

Listar tools:

```bash
curl -s http://localhost:8300/v1/tools | jq
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

Resultado esperado:

```json
{
  "tool_name": "consultar_fatura",
  "version": "1.0.0",
  "ok": true,
  "data": {
    "invoice_id": "INV-001",
    "msisdn": "11999999999",
    "valor_total": 249.9,
    "vencimento": "2026-06-10",
    "status": "ABERTA"
  }
}
```

---

# 6. Terminal 3 — Agent Template Backend / Agent Runtime

```bash
cd agent_platform_oci/templates/agent_template_backend
```

ou, se o seu backend estiver em outra pasta:

```bash
cd agent_platform_oci/templates/agent_template_backend
```

Ativar ambiente:

```bash
source .venv/bin/activate
```

Se ainda não existir `.venv`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configurar variáveis:

```bash
export MCP_GATEWAY_ENABLED=true
export MCP_GATEWAY_URL=http://localhost:8300
export MCP_GATEWAY_TIMEOUT_SECONDS=60

export AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml
```

Se estiver usando OCI/OpenAI-compatible, manter também as variáveis já existentes do backend:

```bash
export LLM_PROVIDER=oci_openai
export OCI_GENAI_API_KEY=<sua-chave>
```

ou, para mock:

```bash
export LLM_PROVIDER=mock
```

Subir backend:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Validar:

```bash
curl http://localhost:8000/health
```

Validar agentes:

```bash
curl http://localhost:8000/agents | jq
```

Testar backend direto:

```bash
curl -s -X POST http://localhost:8000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "payload": {
      "message": "Quero consultar minha fatura",
      "session_id": "session-001",
      "user_id": "user-001",
      "message_id": "msg-001",
      "business_context": {
        "customer_key": "11999999999",
        "contract_key": "INV-001",
        "session_key": "session-001"
      }
    }
  }' | jq
```

---

# 7. Terminal 4 — Agent Gateway

```bash
cd agent_platform_oci/apps/agent_gateway
```

Ativar ambiente:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configurar variáveis:

```bash
export DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
export AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml
```

Subir Agent Gateway:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

Validar:

```bash
curl http://localhost:9000/health
```

Se a rota governada de exemplo estiver registrada no `app.main`, testar:

```bash
curl -s -X POST http://localhost:9000/gateway/message/governed \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "payload": {
      "message": "Quero consultar minha fatura",
      "session_id": "session-001",
      "user_id": "user-001",
      "message_id": "msg-001",
      "metadata": {
        "operation": "agent.final_answer"
      },
      "business_context": {
        "customer_key": "11999999999",
        "contract_key": "INV-001",
        "session_key": "session-001"
      }
    }
  }' | jq
```

Se a rota real for `/gateway/message`, testar:

```bash
curl -s -X POST http://localhost:9000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "payload": {
      "message": "Quero consultar minha fatura",
      "session_id": "session-001",
      "user_id": "user-001",
      "message_id": "msg-001",
      "metadata": {
        "operation": "agent.final_answer"
      },
      "business_context": {
        "customer_key": "11999999999",
        "contract_key": "INV-001",
        "session_key": "session-001"
      }
    }
  }' | jq
```

---

# 8. Terminal 5 — Frontend

```bash
cd agent_platform_oci/agent_frontend
```

ou a pasta onde estiver o frontend.

Instalar dependências:

```bash
npm install
```

Subir:

```bash
npm run dev -- --host 0.0.0.0 --port 5173
```

Abrir:

```text
http://localhost:5173
```

Configurar no frontend:

```text
Backend URL: http://localhost:9000
Agent: telecom_contas
Session ID: session-001
Customer Key: 11999999999
Contract Key: INV-001
```

O frontend deve chamar o **Agent Gateway** na porta 9000, não o MCP Gateway.

---

# 9. Fluxo final esperado

```text
Frontend 5173
  ↓
Agent Gateway 9000
  ↓
Agent Template Backend 8000
  ↓
MCP Gateway 8300
  ↓
Mock Telecom MCP 8001
```

---

# 10. Docker Compose para MCP Gateway + Mock MCP

Também é possível subir MCP Gateway + Mock MCP com Docker Compose:

```bash
cd agent_platform_oci

docker compose -f deploy/docker/docker-compose.mcp-gateway.yml up --build
```

Isso sobe:

```text
MCP Gateway      http://localhost:8300
Mock Telecom MCP http://localhost:8001
```

Depois subir manualmente:

- Agent Template Backend na porta 8000;
- Agent Gateway na porta 9000;
- Frontend na porta 5173.

---

# 11. Checklist de validação

## MCP Server

```bash
curl http://localhost:8001/health
```

## MCP Gateway

```bash
curl http://localhost:8300/health
curl http://localhost:8300/v1/tools
```

## Backend Runtime

```bash
curl http://localhost:8000/health
curl http://localhost:8000/agents
```

## Agent Gateway

```bash
curl http://localhost:9000/health
```

## Frontend

```text
http://localhost:5173
```

---

# 12. Erros comuns

## 12.1. Frontend chamando porta errada

Errado:

```text
Frontend → http://localhost:8000
```

Correto:

```text
Frontend → http://localhost:9000
```

Se você quiser testar sem Agent Gateway, pode apontar temporariamente para 8000. Mas no modelo final, o frontend deve usar o Agent Gateway.

---

## 12.2. MCP Gateway sem MCP Server

Sintoma:

```text
MCP server unavailable
```

Correção:

```bash
curl http://localhost:8001/health
```

Se falhar, subir o mock MCP server.

---

## 12.3. Tool sem BusinessContext

Sintoma:

```json
{
  "missing_business_keys": ["customer_key", "contract_key"]
}
```

Correção:

enviar:

```json
"business_context": {
  "customer_key": "11999999999",
  "contract_key": "INV-001",
  "session_key": "session-001"
}
```

---

## 12.4. Agent Gateway não encontra backend

Sintoma:

```text
Connection refused http://localhost:8000
```

Correção:

validar:

```bash
curl http://localhost:8000/health
```

e configurar:

```bash
export DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
```

---

## 12.5. Rota governada não registrada

Se `/gateway/message/governed` retornar 404, significa que o arquivo de exemplo ainda não foi incluído no `app.main`.

Nesse caso, use a rota real `/gateway/message` ou registre no `main.py`:

```python
from app.routes.governed_proxy_example import router as governed_router

app.include_router(governed_router)
```

---

# 13. Variáveis consolidadas

## Agent Gateway

```env
DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml
```

## Agent Template Backend

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
LLM_PROVIDER=mock
```

## MCP Gateway

```env
MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml
```

---

# 14. Resumo rápido

Em cinco terminais:

```bash
# Terminal 1
cd mcp/servers/mock_telecom_mcp
source .venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2
cd apps/mcp_gateway
source .venv/bin/activate
export MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml
uvicorn app.main:app --host 0.0.0.0 --port 8300 --reload

# Terminal 3
cd templates/agent_template_backend
source .venv/bin/activate
export MCP_GATEWAY_ENABLED=true
export MCP_GATEWAY_URL=http://localhost:8300
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 4
cd apps/agent_gateway
source .venv/bin/activate
export DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
export AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml
uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload

# Terminal 5
cd agent_frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```
