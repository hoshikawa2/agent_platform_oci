
### Agent Gateway, MCP Gateway e Autenticação

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **governança de entrada, gateways, catálogo MCP e autenticação entre componentes**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

Governança de entrada, gateways, catálogo mcp e autenticação entre componentes.

### Conteúdo técnico consolidado

### Agent Gateway, MCP Gateway, Execução Local e Basic Auth

Manual operacional e de integração dos gateways, incluindo responsabilidades, catálogo de tools, discovery, ordem de inicialização, portas, variáveis, Basic Auth ponta-a-ponta e troubleshooting.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### Arquitetura oficial dos gateways

> Conteúdo consolidado a partir de `Documentacao/MANUAL_AGENT_PLATFORM_GATEWAYS.md`.

### Objetivo

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

### Arquitetura Oficial

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

### Portas Oficiais

| Componente | Porta |
|------------|--------|
| Frontend | 5173 |
| Agent Gateway | 9000 |
| Backend Runtime | 8000 |
| MCP Gateway | 8300 |
| Telecom MCP Server | 8100 |
| Retail MCP Server | 8200 |

---

### Variáveis Oficiais

### Agent Template Backend

ENABLE_MCP_TOOLS=true

MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
MCP_GATEWAY_AGENT_ID=telecom_contas
MCP_GATEWAY_TENANT_ID=default

### Agent Gateway

DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml

### MCP Gateway

MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml

---

### Ordem de Inicialização

1. Telecom MCP Server
2. Retail MCP Server
3. MCP Gateway
4. Agent Template Backend
5. Agent Gateway
6. Frontend

---

### Terminal 1 — Telecom MCP Server

cd mcp/servers/telecom_mcp_server

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn main:app --host 0.0.0.0 --port 8100 --reload

Validação:

curl http://localhost:8100/health

---

### Terminal 2 — Retail MCP Server

cd mcp/servers/retail_mcp_server

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn main:app --host 0.0.0.0 --port 8200 --reload

Validação:

curl http://localhost:8200/health

---

### Terminal 3 — MCP Gateway

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

### Terminal 4 — Agent Template Backend

cd templates/agent_template_backend

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Validações:

curl http://localhost:8000/health
curl http://localhost:8000/agents

---

### Terminal 5 — Agent Gateway

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

### Terminal 6 — Frontend

cd agent_frontend

npm install

npm run dev -- --host 0.0.0.0 --port 5173

Abrir:

http://localhost:5173

Backend URL:

http://localhost:9000

---

### Fluxo de Tools

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

### Teste Integrado E2E

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

### Troubleshooting

### Backend chamando MCP Server direto

Confirmar:

MCP_GATEWAY_ENABLED=true

MCP_GATEWAY_URL=http://localhost:8300

### Porta incorreta

A porta oficial do MCP Gateway é:

8300

### Agent Gateway não encontra Backend

Validar:

curl http://localhost:8000/health

### MCP Gateway não encontra MCP Server

Validar:

curl http://localhost:8100/health
curl http://localhost:8200/health

---

### Decisões Arquiteturais Oficiais

- Agent Gateway centraliza governança
- Runtime executa LangGraph
- Runtime executa LLM
- MCP Gateway centraliza tools
- MCP Servers executam tools
- Backend usa MCP Gateway
- gateway_runtime.env.example foi removido
- MCP_GATEWAY_* fica no .env do backend
- Porta oficial MCP Gateway = 8300

### Execução local integrada

> Conteúdo consolidado a partir de `Documentacao/MANUAL_EXECUCAO_AGENT_GATEWAY_MCP_GATEWAY_FRONTEND.md`.

### Agent Gateway + MCP Gateway + Agent Template Backend + Frontend

### 1. Arquitetura de execução

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

### 2. Portas

| Componente | Porta | URL |
|---|---:|---|
| Frontend | 5173 | `http://localhost:5173` |
| Agent Gateway | 9000 | `http://localhost:9000` |
| Agent Template Backend | 8000 | `http://localhost:8000` |
| MCP Gateway | 8300 | `http://localhost:8300` |
| MCP Server / Mock Telecom MCP | 8001 | `http://localhost:8001` |

---

### 3. Ordem recomendada para subir

Subir nesta ordem:

1. MCP Server / Mock Telecom MCP
2. MCP Gateway
3. Agent Template Backend
4. Agent Gateway
5. Frontend

---

### 4. Terminal 1 — MCP Server / Mock Telecom MCP

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

### 5. Terminal 2 — MCP Gateway

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

### 6. Terminal 3 — Agent Template Backend / Agent Runtime

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

### 7. Terminal 4 — Agent Gateway

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

### 8. Terminal 5 — Frontend

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

### 9. Fluxo final esperado

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

### 10. Docker Compose para MCP Gateway + Mock MCP

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

### 11. Checklist de validação

### MCP Server

```bash
curl http://localhost:8001/health
```

### MCP Gateway

```bash
curl http://localhost:8300/health
curl http://localhost:8300/v1/tools
```

### Backend Runtime

```bash
curl http://localhost:8000/health
curl http://localhost:8000/agents
```

### Agent Gateway

```bash
curl http://localhost:9000/health
```

### Frontend

```text
http://localhost:5173
```

---

### 12. Erros comuns

### 12.1. Frontend chamando porta errada

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

### 12.2. MCP Gateway sem MCP Server

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

### 12.3. Tool sem BusinessContext

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

### 12.4. Agent Gateway não encontra backend

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

### 12.5. Rota governada não registrada

Se `/gateway/message/governed` retornar 404, significa que o arquivo de exemplo ainda não foi incluído no `app.main`.

Nesse caso, use a rota real `/gateway/message` ou registre no `main.py`:

```python
from app.routes.governed_proxy_example import router as governed_router

app.include_router(governed_router)
```

---

### 13. Variáveis consolidadas

### Agent Gateway

```env
DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml
```

### Agent Template Backend

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
LLM_PROVIDER=mock
```

### MCP Gateway

```env
MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml
```

---

### 14. Resumo rápido

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

### Basic Auth ponta-a-ponta

> Conteúdo consolidado a partir de `Documentacao/Implementando_Basic_Auth.md`.

Para validar **todo o circuito com Basic Auth**, você precisa configurar três relações distintas:

```text
Cliente de teste
   └─ Basic Auth A ─► Agent Gateway :8010
                         └─ Basic Auth B ─► Agent Backend :8000
                                                └─ Basic Auth C ─► MCP Gateway :8300
```

Há um detalhe importante: no pacote atual, a autenticação Basic já funciona para chamadas **de entrada**, mas os clientes internos ainda não enviam Basic Auth:

* `Agent Gateway → Agent Backend` não envia credencial;
* `Agent Backend → MCP Gateway` envia apenas Bearer Token.

Portanto, para testar o circuito inteiro com Basic Auth, faça os dois pequenos ajustes de código descritos abaixo.

---

### 1. Preparar o ambiente

Considere que o ZIP foi extraído em:

```bash
cd agent_framework_oci_authentication_v2_1
```

Crie um único ambiente virtual para facilitar o teste:

```bash
python -m venv .venv
source .venv/bin/activate
```

No Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale o framework e as dependências dos três componentes:

```bash
pip install -U pip

pip install -e ./libs/agent_framework

pip install \
  -r ./Tuning-Performance/Authentication/agent_template_backend_authentication/requirements.txt \
  -r ./apps/agent_gateway/requirements.txt \
  -r ./apps/mcp_gateway/requirements.txt
```

Confirme a importação:

```bash
python -c "from agent_framework.security import install_authentication; print('framework ok')"
```

---

### 2. Criar três pares de Client ID e Secret

Use credenciais diferentes para cada trecho. Para teste local:

| Fluxo                   | Client ID            | Secret de teste             |
| ----------------------- | -------------------- | --------------------------- |
| Cliente → Agent Gateway | `tia-test`           | `TiaGateway-Test-2026!`     |
| Agent Gateway → Backend | `agent-gateway-test` | `GatewayBackend-Test-2026!` |
| Backend → MCP Gateway   | `agent-backend-test` | `BackendMcp-Test-2026!`     |

Esses valores são apenas para ambiente local. Não os reutilize em produção.

### Gerar os hashes

O script está em:

```text
Tuning-Performance/Authentication/
  agent_template_backend_authentication/
    scripts/generate_secret_hash.py
```

Execute:

```bash
python Tuning-Performance/Authentication/agent_template_backend_authentication/scripts/generate_secret_hash.py \
  --secret 'TiaGateway-Test-2026!'
```

Depois:

```bash
python Tuning-Performance/Authentication/agent_template_backend_authentication/scripts/generate_secret_hash.py \
  --secret 'GatewayBackend-Test-2026!'
```

E:

```bash
python Tuning-Performance/Authentication/agent_template_backend_authentication/scripts/generate_secret_hash.py \
  --secret 'BackendMcp-Test-2026!'
```

Você receberá três valores semelhantes a:

```text
pbkdf2_sha256:310000:<salt>:<digest>
```

Guarde-os temporariamente:

```bash
HASH_CLIENT_GATEWAY='pbkdf2_sha256:310000:...'
HASH_GATEWAY_BACKEND='pbkdf2_sha256:310000:...'
HASH_BACKEND_MCP='pbkdf2_sha256:310000:...'
```

O hash muda a cada execução porque o salt é aleatório. Isso é esperado.

---

### 3. Configurar o Agent Gateway

Entre no diretório:

```bash
cd apps/agent_gateway
```

Copie o exemplo:

```bash
cp .env.example .env
```

Adicione ao final do `.env`:

```env
# Entrada: cliente/TIA -> Agent Gateway
AGENT_GATEWAY_AUTH_ENABLED=true
AGENT_GATEWAY_AUTH_MODE=basic
AGENT_GATEWAY_AUTH_BASIC_CLIENT_ID=tia-test
AGENT_GATEWAY_AUTH_BASIC_SECRET_HASH=COLE_AQUI_HASH_CLIENT_GATEWAY
AGENT_GATEWAY_AUTH_BASIC_REALM=agent-gateway

AGENT_GATEWAY_AUTH_PUBLIC_PATHS=/health,/docs,/openapi.json,/redoc
AGENT_GATEWAY_AUTH_PUBLIC_PREFIXES=

# Saída: Agent Gateway -> Agent Backend
BACKEND_AUTH_MODE=basic
BACKEND_AUTH_CLIENT_ID=agent-gateway-test
BACKEND_AUTH_SECRET=GatewayBackend-Test-2026!
```

Não coloque aspas no `.env`:

```env
BACKEND_AUTH_SECRET=GatewayBackend-Test-2026!
```

O arquivo de backends já aponta o backend Contas para:

```yaml
contas:
  url: http://localhost:8000
```

Arquivo:

```text
apps/agent_gateway/config/backends.yaml
```

Para este teste, mantenha apenas o backend `contas` ou force o backend no payload. Caso contrário, pedidos sobre ofertas e suporte podem ser roteados para portas em que nenhum backend está rodando.

---

### 4. Fazer o Agent Gateway enviar Basic Auth ao backend

Abra:

```text
libs/agent_framework/src/agent_framework/global_supervisor/client.py
```

Substitua a classe `BackendClient` por uma versão que aceite autenticação Basic.

No início do arquivo, adicione:

```python
import os
```

Altere o construtor:

```python
class BackendClient:
    def __init__(
        self,
        timeout_seconds: float = 120.0,
        basic_client_id: str | None = None,
        basic_secret: str | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.basic_client_id = basic_client_id
        self.basic_secret = basic_secret

    def _auth(self) -> httpx.BasicAuth | None:
        if self.basic_client_id and self.basic_secret:
            return httpx.BasicAuth(
                username=self.basic_client_id,
                password=self.basic_secret,
            )
        return None
```

No método `call_message`, troque:

```python
resp = await client.post(url, json=payload)
```

por:

```python
resp = await client.post(
    url,
    json=payload,
    auth=self._auth(),
)
```

No método `health`, você pode manter `/health` público. Caso queira enviar autenticação também, use:

```python
resp = await client.get(url, auth=self._auth())
```

Agora abra:

```text
apps/agent_gateway/app/main.py
```

Adicione:

```python
import os
```

Troque:

```python
backend_client = BackendClient(
    timeout_seconds=settings.BACKEND_TIMEOUT_SECONDS
)
```

por:

```python
backend_client = BackendClient(
    timeout_seconds=settings.BACKEND_TIMEOUT_SECONDS,
    basic_client_id=os.getenv("BACKEND_AUTH_CLIENT_ID"),
    basic_secret=os.getenv("BACKEND_AUTH_SECRET"),
)
```

Isso implementa:

```text
Agent Gateway → Agent Backend
Authorization: Basic base64(agent-gateway-test:GatewayBackend-Test-2026!)
```

---

### 5. Configurar o Agent Backend autenticado

Entre no diretório:

```bash
cd Tuning-Performance/Authentication/agent_template_backend_authentication
```

Copie o exemplo:

```bash
cp .env.example .env
```

Ajuste a seção de autenticação:

```env
# Entrada: Agent Gateway -> Agent Backend
AGENT_AUTH_ENABLED=true
AGENT_AUTH_MODE=basic
AGENT_AUTH_BASIC_CLIENT_ID=agent-gateway-test
AGENT_AUTH_BASIC_SECRET_HASH=COLE_AQUI_HASH_GATEWAY_BACKEND
AGENT_AUTH_BASIC_REALM=agent-contas

AGENT_AUTH_PUBLIC_PATHS=/health,/docs,/openapi.json,/redoc
AGENT_AUTH_PUBLIC_PREFIXES=
```

Para usar o MCP Gateway:

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60

# Saída: Agent Backend -> MCP Gateway
MCP_GATEWAY_AUTH_MODE=basic
MCP_GATEWAY_BASIC_CLIENT_ID=agent-backend-test
MCP_GATEWAY_BASIC_SECRET=BackendMcp-Test-2026!
```

Para evitar dependências externas durante o primeiro teste, configure também:

```env
LLM_PROVIDER=mock
ENABLE_LANGFUSE=false
ENABLE_ANALYTICS=false

SESSION_REPOSITORY_PROVIDER=memory
MEMORY_REPOSITORY_PROVIDER=memory
CHECKPOINT_REPOSITORY_PROVIDER=memory
CACHE_PROVIDER=memory
USAGE_REPOSITORY_PROVIDER=memory
```

Os nomes exatos de alguns providers podem depender do arquivo de configuração atual do framework. Caso o `.env.example` já contenha valores locais ou mock, preserve-os.

---

### 6. Fazer o Backend enviar Basic Auth ao MCP Gateway

Abra:

```text
libs/agent_framework/src/agent_framework/gateways/mcp_gateway_client.py
```

Substitua a implementação por:

```python
from __future__ import annotations

import base64
from typing import Any

import httpx


class MCPGatewayClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout_seconds: int = 60,
        auth_mode: str | None = None,
        basic_client_id: str | None = None,
        basic_secret: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.auth_mode = (auth_mode or "").strip().lower()
        self.basic_client_id = basic_client_id
        self.basic_secret = basic_secret

    def _headers(self) -> dict[str, str]:
        if (
            self.auth_mode == "basic"
            and self.basic_client_id
            and self.basic_secret
        ):
            raw = f"{self.basic_client_id}:{self.basic_secret}".encode("utf-8")
            encoded = base64.b64encode(raw).decode("ascii")
            return {"Authorization": f"Basic {encoded}"}

        if self.token:
            return {"Authorization": f"Bearer {self.token}"}

        return {}

    async def list_tools(self) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:
            response = await client.get(
                f"{self.base_url}/v1/tools",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def invoke_tool(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        channel: str | None,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        business_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "channel": channel,
            "tool_name": tool_name,
            "arguments": arguments or {},
            "business_context": business_context or {},
            "metadata": metadata or {},
        }

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:
            response = await client.post(
                f"{self.base_url}/v1/tools/{tool_name}/invoke",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()
```

Agora abra:

```text
libs/agent_framework/src/agent_framework/mcp/tool_router.py
```

Localize:

```python
MCPGatewayClient(
    base_url=getattr(
        settings,
        "MCP_GATEWAY_URL",
        "http://localhost:8300",
    ),
    token=getattr(settings, "MCP_GATEWAY_TOKEN", None),
    timeout_seconds=getattr(
        settings,
        "MCP_GATEWAY_TIMEOUT_SECONDS",
        settings.MCP_TOOL_TIMEOUT_SECONDS,
    ),
)
```

Altere para:

```python
MCPGatewayClient(
    base_url=getattr(
        settings,
        "MCP_GATEWAY_URL",
        "http://localhost:8300",
    ),
    token=getattr(settings, "MCP_GATEWAY_TOKEN", None),
    timeout_seconds=getattr(
        settings,
        "MCP_GATEWAY_TIMEOUT_SECONDS",
        settings.MCP_TOOL_TIMEOUT_SECONDS,
    ),
    auth_mode=getattr(
        settings,
        "MCP_GATEWAY_AUTH_MODE",
        None,
    ),
    basic_client_id=getattr(
        settings,
        "MCP_GATEWAY_BASIC_CLIENT_ID",
        None,
    ),
    basic_secret=getattr(
        settings,
        "MCP_GATEWAY_BASIC_SECRET",
        None,
    ),
)
```

Adicione estes campos em:

```text
libs/agent_framework/src/agent_framework/config/settings.py
```

Próximo das configurações existentes de MCP Gateway:

```python
MCP_GATEWAY_AUTH_MODE: str | None = None
MCP_GATEWAY_BASIC_CLIENT_ID: str | None = None
MCP_GATEWAY_BASIC_SECRET: str | None = None
```

Há também uma factory local em:

```text
Tuning-Performance/Authentication/
  agent_template_backend_authentication/
    app/mcp_gateway_client_factory.py
```

Ajuste para:

```python
from __future__ import annotations

import os

from agent_framework.gateways import MCPGatewayClient


def build_mcp_gateway_client() -> MCPGatewayClient | None:
    if os.getenv("MCP_GATEWAY_ENABLED", "true").lower() != "true":
        return None

    return MCPGatewayClient(
        base_url=os.getenv(
            "MCP_GATEWAY_URL",
            "http://localhost:8300",
        ),
        token=os.getenv("MCP_GATEWAY_TOKEN") or None,
        timeout_seconds=int(
            os.getenv("MCP_GATEWAY_TIMEOUT_SECONDS", "60")
        ),
        auth_mode=os.getenv("MCP_GATEWAY_AUTH_MODE"),
        basic_client_id=os.getenv(
            "MCP_GATEWAY_BASIC_CLIENT_ID"
        ),
        basic_secret=os.getenv(
            "MCP_GATEWAY_BASIC_SECRET"
        ),
    )
```

---

### 7. Configurar o MCP Gateway

Entre no diretório:

```bash
cd apps/mcp_gateway
```

Crie `.env`:

```bash
cp .env.example .env
```

Adicione:

```env
# Entrada: Agent Backend -> MCP Gateway
MCP_GATEWAY_AUTH_ENABLED=true
MCP_GATEWAY_AUTH_MODE=basic
MCP_GATEWAY_AUTH_BASIC_CLIENT_ID=agent-backend-test
MCP_GATEWAY_AUTH_BASIC_SECRET_HASH=COLE_AQUI_HASH_BACKEND_MCP
MCP_GATEWAY_AUTH_BASIC_REALM=mcp-gateway

MCP_GATEWAY_AUTH_PUBLIC_PATHS=/health,/ready,/docs,/openapi.json,/redoc
MCP_GATEWAY_AUTH_PUBLIC_PREFIXES=

MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml
```

### Desabilitar o mecanismo Bearer legado

O MCP Gateway ainda possui um segundo mecanismo antigo, configurado dentro de:

```text
apps/mcp_gateway/config/mcp_gateway.yaml
```

Localize a seção:

```yaml
auth:
  enabled: true
```

Altere para:

```yaml
auth:
  enabled: false
```

Isso é necessário porque o novo middleware já faz a autenticação Basic. Caso o `auth_check()` legado continue habilitado, a requisição passará pelo Basic e depois será rejeitada por não possuir Bearer Token.

---

### 8. Subir os componentes

Use quatro terminais.

### Terminal 1 — MCP Servers

O MCP Gateway precisa ter pelo menos um servidor MCP disponível para demonstrar uma chamada real.

Na raiz do projeto:

```bash
source .venv/bin/activate
```

Suba o servidor telecom:

```bash
uvicorn mcp.servers.telecom_mcp_server.main:app \
  --host 0.0.0.0 \
  --port 8100 \
  --reload
```

Em outro terminal, caso queira também o retail:

```bash
uvicorn mcp.servers.retail_mcp_server.main:app \
  --host 0.0.0.0 \
  --port 8200 \
  --reload
```

Confira as URLs configuradas em:

```text
apps/mcp_gateway/config/mcp_gateway.yaml
```

Para execução local, devem apontar para:

```yaml
url: http://localhost:8100
```

e:

```yaml
url: http://localhost:8200
```

---

### Terminal 2 — MCP Gateway

```bash
cd apps/mcp_gateway
source ../../.venv/bin/activate
```

Suba usando `--env-file`. Isso é importante porque o middleware lê variáveis com `os.getenv()`:

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8300 \
  --reload \
  --env-file .env
```

Teste a saúde pública:

```bash
curl http://localhost:8300/health
```

Teste um endpoint protegido sem credencial:

```bash
curl -i http://localhost:8300/v1/tools
```

Esperado:

```text
HTTP/1.1 401 Unauthorized
```

Teste com Basic Auth:

```bash
curl -i \
  -u 'agent-backend-test:BackendMcp-Test-2026!' \
  http://localhost:8300/v1/tools
```

Esperado:

```text
HTTP/1.1 200 OK
```

---

### Terminal 3 — Agent Backend

```bash
cd Tuning-Performance/Authentication/agent_template_backend_authentication
source ../../../.venv/bin/activate
```

Suba:

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --env-file .env
```

Teste saúde:

```bash
curl http://localhost:8000/health
```

Teste endpoint protegido sem credencial:

```bash
curl -i http://localhost:8000/agents
```

Esperado:

```text
HTTP/1.1 401 Unauthorized
```

Teste com a credencial usada pelo Agent Gateway:

```bash
curl -i \
  -u 'agent-gateway-test:GatewayBackend-Test-2026!' \
  http://localhost:8000/agents
```

Esperado:

```text
HTTP/1.1 200 OK
```

Teste mensagem diretamente:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -u 'agent-gateway-test:GatewayBackend-Test-2026!' \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "web",
    "agent_id": "telecom_contas",
    "tenant_id": "default",
    "payload": {
      "text": "Quero consultar minha fatura",
      "session_id": "teste-backend-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "message_id": "msg-001"
    }
  }'
```

---

### Terminal 4 — Agent Gateway

```bash
cd apps/agent_gateway
source ../../.venv/bin/activate
```

Suba:

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8010 \
  --reload \
  --env-file .env
```

Teste saúde:

```bash
curl http://localhost:8010/health
```

Teste endpoint protegido sem credencial:

```bash
curl -i http://localhost:8010/backends
```

Esperado:

```text
HTTP/1.1 401 Unauthorized
```

Teste com a credencial externa:

```bash
curl -i \
  -u 'tia-test:TiaGateway-Test-2026!' \
  http://localhost:8010/backends
```

Esperado:

```text
HTTP/1.1 200 OK
```

---

### 9. Validar o circuito completo

Force o backend `contas` para evitar que o roteador selecione um backend não iniciado:

```bash
curl -X POST http://localhost:8010/gateway/message \
  -u 'tia-test:TiaGateway-Test-2026!' \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "web",
    "backend_id": "contas",
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "session_id": "circuito-basic-001",
    "payload": {
      "text": "Quero consultar minha fatura",
      "session_id": "circuito-basic-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "message_id": "msg-circuito-001"
    }
  }'
```

O circuito esperado é:

```text
curl
  │ Basic tia-test
  ▼
Agent Gateway :8010
  │ Basic agent-gateway-test
  ▼
Agent Backend :8000
  │ Basic agent-backend-test
  ▼
MCP Gateway :8300
  ▼
MCP Server :8100 ou :8200
```

---

### 10. Como comprovar cada autenticação

Faça testes negativos em cada trecho.

### Secret externo incorreto

```bash
curl -i \
  -u 'tia-test:senha-errada' \
  http://localhost:8010/backends
```

Resultado esperado:

```text
401 Unauthorized
```

### Secret do gateway para backend incorreto

Altere temporariamente no `apps/agent_gateway/.env`:

```env
BACKEND_AUTH_SECRET=senha-errada
```

Reinicie o Agent Gateway e envie uma mensagem.

O gateway deverá retornar erro de backend, normalmente:

```text
502 Bad Gateway
```

O erro interno será originado por um:

```text
401 Unauthorized
```

do Agent Backend.

### Secret do backend para MCP incorreto

Altere temporariamente:

```env
MCP_GATEWAY_BASIC_SECRET=senha-errada
```

Reinicie o backend e execute uma frase que acione uma ferramenta MCP.

O backend deverá registrar falha na chamada ao MCP Gateway com:

```text
401 Unauthorized
```

---

### 11. Verificação rápida de portas

No Linux ou WSL:

```bash
ss -lntp | grep -E ':8000|:8010|:8100|:8200|:8300'
```

No Windows PowerShell:

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -in 8000,8010,8100,8200,8300 |
  Sort-Object LocalPort
```

Você deverá ver:

```text
8000  Agent Backend
8010  Agent Gateway
8100  Telecom MCP Server
8200  Retail MCP Server
8300  MCP Gateway
```

### Observação importante

O segredo original precisa existir no componente cliente:

```text
TIA ou curl:
  TiaGateway-Test-2026!

Agent Gateway:
  GatewayBackend-Test-2026!

Agent Backend:
  BackendMcp-Test-2026!
```

Os componentes servidores armazenam apenas os hashes:

```text
Agent Gateway:
  hash de TiaGateway-Test-2026!

Agent Backend:
  hash de GatewayBackend-Test-2026!

MCP Gateway:
  hash de BackendMcp-Test-2026!
```

Em produção, os segredos originais e hashes devem vir de Vault ou Kubernetes Secret, não de arquivos `.env`.

### Discovery e sincronização do catálogo MCP

> Conteúdo consolidado a partir de `docs/MCP_GATEWAY_DISCOVERY.md`.

### Goal

This evolution allows the MCP Gateway to discover tools from registered MCP Servers by reading a manifest or catalog endpoint.

The framework still points to a single MCP Gateway:

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
```

The MCP Gateway can point to many MCP Servers:

```text
Agent Framework
  -> MCP Gateway
     -> telecom_mcp_server
     -> retail_mcp_server
     -> nf_items_mcp_server
     -> any other MCP Server
```

### What is automatic

After a server is registered in `apps/mcp_gateway/config/mcp_gateway.yaml` with `discover: true`, the gateway can:

- call its manifest/catalog endpoint;
- normalize the returned tool list;
- publish the tools in `GET /v1/tools`;
- execute the discovered tool through `POST /v1/tools/{tool_name}/invoke`.

### What is still explicit

The gateway does not scan the network or GitHub by itself. You still register the MCP Server endpoint in YAML.

Example:

```yaml
servers:
  nf_items:
    enabled: true
    discover: true
    protocol: legacy_http
    transport: http
    url: http://localhost:8400/mcp
    catalog_endpoint: /tools
    invoke_endpoint: /tools/call
    timeout_seconds: 30
```

If `catalog_endpoint` is omitted, the gateway tries:

```text
/.well-known/mcp-server.json
/manifest
/mcp/tools
/tools/list
/tools
/v1/tools
```

### Expected manifest/catalog formats

The gateway accepts common shapes:

```json
{
  "server_id": "nf_items",
  "tools": [
    {
      "name": "buscar_notas_por_criterios",
      "description": "Search invoice items by criteria.",
      "input_schema": {
        "cliente": "string",
        "estado": "string",
        "preco": "number",
        "ean": "string",
        "margem": "number"
      }
    }
  ]
}
```

It also accepts:

```json
{"tools": [...]}
```

```json
{"data": {"tools": [...]}}
```

```json
{"capabilities": {"tools": [...]}}
```

### New endpoints

### List discovery servers

```bash
curl http://localhost:8300/v1/discovery/servers | jq
```

### Force catalog sync

```bash
curl -X POST http://localhost:8300/v1/discovery/sync | jq
```

### List merged static + discovered tools

```bash
curl http://localhost:8300/v1/tools | jq
```

### Precedence rule

Static tools configured under `tools:` override discovered tools with the same name. This allows operations teams to override timeout, cache, allowed agents, required business keys, and endpoint behavior safely.

### Plugging a new MCP Server

1. Start the MCP Server.
2. Confirm that it exposes a catalog or manifest endpoint.
3. Add it under `servers:` in `mcp_gateway.yaml` with `discover: true`.
4. Restart the MCP Gateway or call `POST /v1/discovery/sync`.
5. Confirm the tool appears in `GET /v1/tools`.
6. Invoke the tool through the gateway.

### Example invocation

```bash
curl -s -X POST http://localhost:8300/v1/tools/buscar_notas_por_criterios/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "agent_id": "telecom_contas",
    "channel": "web",
    "tool_name": "buscar_notas_por_criterios",
    "arguments": {
      "cliente": "CLIENTE-001",
      "estado": "SP",
      "preco": 100.0,
      "ean": "7890000000000",
      "margem": 0.05
    },
    "business_context": {
      "session_key": "session-001"
    }
  }' | jq
```

### Runbook operacional do MCP Gateway

> Conteúdo consolidado a partir de `Documentacao/MCP_GATEWAY_RUNBOOK.md`.

### Arquitetura corrigida

O backend/agente não deve chamar diretamente os MCP servers finais. O fluxo correto é:

```text
agent_template_backend / agent_framework
  -> MCP Gateway Client
  -> apps/mcp_gateway
  -> mcp/servers/telecom_mcp_server ou mcp/servers/retail_mcp_server
```

### Subir localmente

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

### Testes rápidos

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

### O que foi corrigido

- `apps/mcp_gateway/config/mcp_gateway.yaml` agora aponta para os MCP servers reais nas portas `8100` e `8200`.
- O MCP Gateway agora suporta o contrato legado dos MCP servers: `POST /mcp/tools/call` com `{tool_name, arguments}`.
- O `agent_framework` ganhou flags `MCP_GATEWAY_ENABLED`, `MCP_GATEWAY_URL`, `MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_AGENT_ID` e `MCP_GATEWAY_TENANT_ID`.
- O `MCPToolRouter` passa a chamar o MCP Gateway quando `MCP_GATEWAY_ENABLED=true`.
- `libs/agent_framework/config/mcp_servers.yaml` foi mantido como registry lógico/fallback, não como caminho principal quando o gateway está ativo.

### Evolução arquitetural dos gateways

> Conteúdo consolidado a partir de `Documentacao/README_AGENT_GATEWAY_AND_MCP_GATEWAY_EVOLUTION.md`.

Este overlay remove o conceito de `AI Gateway` separado.

### Arquitetura

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

### O que entra no Agent Gateway

```text
apps/agent_gateway/app/governance/
apps/agent_gateway/app/governance_middleware.py
apps/agent_gateway/app/routes/governed_proxy_example.py
apps/agent_gateway/config/gateway_governance.yaml
```

### O que entra no MCP Gateway

```text
apps/mcp_gateway/
libs/agent_framework/src/agent_framework/gateways/mcp_gateway_client.py
libs/agent_framework/src/agent_framework/runtime_mcp_gateway_adapter.py
```

### Aplicar overlay

```bash
unzip agent_platform_agent_gateway_mcp_gateway_overlay.zip -d /tmp/overlay
rsync -av /tmp/overlay/ ./
```

### Subir MCP Gateway local

```bash
docker compose -f deploy/docker/docker-compose.mcp-gateway.yml up --build
```

Serviços:

```text
MCP Gateway      http://localhost:8300
Mock Telecom MCP http://localhost:8001
```

### Testar MCP Gateway

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

### Como plugar no Agent Gateway

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

### Variáveis do Runtime

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
```

### Importante

Não existe `apps/ai_gateway`.

A governança de modelo fica no Agent Gateway como policy/metadados.

O Runtime continua usando os LLM providers existentes, podendo ler a política enviada pelo Gateway em:

```python
state["metadata"]["model_policy"]
```

### Inventário de arquivos e responsabilidades

> Conteúdo consolidado a partir de `Documentacao/INVENTARIO_AGENT_GATEWAY_MCP_GATEWAY.md`.

Este inventário lista os arquivos incluídos no overlay `agent_platform_agent_gateway_mcp_gateway_overlay.zip`, indicando a área, o tipo de alteração e a finalidade de cada arquivo.

### Resumo

| Área | Quantidade |
|---|---:|
| Documentação | 1 |
| Agent Gateway | 10 |
| MCP Gateway | 5 |
| Agent Framework | 4 |
| Template Backend | 2 |
| MCP Server Mock | 2 |
| Deploy | 2 |

### Arquivos por área

### Documentação

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `README_AGENT_GATEWAY_AND_MCP_GATEWAY_EVOLUTION.md` | Novo / overlay | Documento principal do overlay. Explica a nova arquitetura sem AI Gateway separado, com Agent Gateway governando políticas/modelos e MCP Gateway separado para tools. |

### Agent Gateway

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `apps/agent_gateway/app/config/governance_loader.py` | Novo / overlay | Carrega o arquivo YAML de governança do Agent Gateway a partir de AGENT_GATEWAY_GOVERNANCE_CONFIG. |
| `apps/agent_gateway/app/governance/__init__.py` | Novo / overlay | Inicializa o pacote Python de governança do Agent Gateway. |
| `apps/agent_gateway/app/governance/audit.py` | Novo / overlay | Centraliza logging/auditoria das decisões de governança do Agent Gateway, com proteção simples para não logar mensagem completa. |
| `apps/agent_gateway/app/governance/evaluation_hooks.py` | Novo / overlay | Hooks antes e depois da chamada ao backend/runtime. Serve para amostragem, evaluator, scoring ou integração futura com Langfuse. |
| `apps/agent_gateway/app/governance/model_policies.py` | Novo / overlay | Resolve políticas de modelo/profile no Agent Gateway. Define qual provider/model/profile deve ser usado por operação, tenant e agente. |
| `apps/agent_gateway/app/governance/rate_limit.py` | Novo / overlay | Implementa rate limit em memória por tenant, agente e canal antes de encaminhar a requisição ao backend/runtime. |
| `apps/agent_gateway/app/governance/usage.py` | Novo / overlay | Hook para registrar uso de gateway, políticas aplicadas e respostas do backend. Pronto para plugar métricas, banco, Langfuse ou OTEL. |
| `apps/agent_gateway/app/governance_middleware.py` | Novo / overlay | Componente principal de governança do Agent Gateway. Aplica rate limit, resolve model_policy, gera headers/metadados e executa hooks antes/depois do backend. |
| `apps/agent_gateway/app/routes/governed_proxy_example.py` | Novo / overlay | Exemplo de rota governada para demonstrar como aplicar governança antes de encaminhar para o Agent Backend/Runtime. |
| `apps/agent_gateway/config/gateway_governance.yaml` | Novo / overlay | Configuração de governança do Agent Gateway: profiles, operation_profiles, providers permitidos, rate limits, headers propagados e evaluation hooks. |

### MCP Gateway

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `apps/mcp_gateway/Dockerfile` | Novo / overlay | Imagem Docker do MCP Gateway. |
| `apps/mcp_gateway/app/__init__.py` | Novo / overlay | Inicializa o pacote Python da aplicação MCP Gateway. |
| `apps/mcp_gateway/app/main.py` | Novo / overlay | Aplicação FastAPI do MCP Gateway. Expõe health, ready, catálogo de tools e endpoint de invoke com auth, autorização, mapping, cache, timeout e retry. |
| `apps/mcp_gateway/config/mcp_gateway.yaml` | Novo / overlay | Configuração central do MCP Gateway: MCP servers, tools, versões, cache, timeout, retry, autorização por agente/canal e mapping BusinessContext → parâmetros. |
| `apps/mcp_gateway/requirements.txt` | Novo / overlay | Dependências Python do MCP Gateway. |

### Agent Framework

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `libs/agent_framework/src/agent_framework/gateway_policy_context.py` | Novo / overlay | Helper no framework para o Runtime ler a política de modelo enviada pelo Agent Gateway em state['metadata']['model_policy']. |
| `libs/agent_framework/src/agent_framework/gateways/__init__.py` | Novo / overlay | Inicializa o pacote de clients de gateways no framework, exportando MCPGatewayClient. |
| `libs/agent_framework/src/agent_framework/gateways/mcp_gateway_client.py` | Novo / overlay | Client assíncrono do framework para chamar o MCP Gateway: listar tools e executar tools. |
| `libs/agent_framework/src/agent_framework/runtime_mcp_gateway_adapter.py` | Novo / overlay | Mixin opcional para agentes/runtime chamarem tools via MCP Gateway e anexarem resultados em state['mcp_results']. |

### Template Backend

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `templates/agent_template_backend/app/mcp_gateway_client_factory.py` | Novo / overlay | Factory no template backend para construir MCPGatewayClient a partir de variáveis de ambiente. |

### MCP Server Mock

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `mcp/servers/mock_telecom_mcp/app.py` | Novo / overlay | Mock MCP Server com tools consultar_fatura e consultar_pagamentos para validar o MCP Gateway localmente. |
| `mcp/servers/mock_telecom_mcp/requirements.txt` | Novo / overlay | Dependências do mock MCP Server de telecom usado para testes locais. |

### Deploy

| Arquivo | Tipo | Finalidade |
|---|---|---|
| `deploy/docker/docker-compose.mcp-gateway.yml` | Novo / overlay | Docker Compose para subir MCP Gateway e mock_telecom_mcp localmente. |
| `deploy/k8s/mcp-gateway.yaml` | Novo / overlay | Manifest Kubernetes de Deployment e Service do MCP Gateway. |

### Observações de integração

### Agent Gateway

Os arquivos em `apps/agent_gateway` não criam um novo serviço. Eles evoluem o Agent Gateway existente para atuar como gateway dedicado da plataforma, centralizando:

- políticas de modelo/profile;
- rate limit;
- auditoria;
- hooks de avaliação;
- propagação de metadados de governança para o Runtime.

A rota `governed_proxy_example.py` é um exemplo de integração. O handler real do `POST /gateway/message` deve aplicar:

```python
governed_body, headers = governance.prepare_backend_request(body)
```

antes de chamar o backend/runtime, e:

```python
return governance.process_backend_response(data)
```

após receber a resposta.

### MCP Gateway

O MCP Gateway é um serviço separado. Ele centraliza:

- catálogo de tools;
- autorização por agente/canal;
- versionamento de tools;
- mapping de BusinessContext para parâmetros;
- cache;
- timeout;
- retry;
- auditoria simples.

### Runtime / Backend

O Runtime continua responsável por:

- LangGraph;
- estado;
- memória;
- checkpoints;
- fluxo;
- providers LLM existentes.

O Runtime passa a chamar tools via MCP Gateway usando `MCPGatewayClient` e/ou `MCPGatewayRuntimeMixin`.

### AI Gateway

Este overlay não cria `apps/ai_gateway`. A governança de modelo fica no Agent Gateway, e a execução LLM continua no Runtime/backend usando os providers já existentes.

### Arquivos de origem

Os arquivos abaixo foram consolidados neste manual:

- `Documentacao/MANUAL_AGENT_PLATFORM_GATEWAYS.md`
- `Documentacao/MANUAL_EXECUCAO_AGENT_GATEWAY_MCP_GATEWAY_FRONTEND.md`
- `Documentacao/Implementando_Basic_Auth.md`
- `docs/MCP_GATEWAY_DISCOVERY.md`
- `Documentacao/MCP_GATEWAY_RUNBOOK.md`
- `Documentacao/README_AGENT_GATEWAY_AND_MCP_GATEWAY_EVOLUTION.md`
- `Documentacao/INVENTARIO_AGENT_GATEWAY_MCP_GATEWAY.md`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.
