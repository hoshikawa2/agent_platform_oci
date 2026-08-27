
### Agent Gateway, MCP Gateway, and Authentication

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **ingress governance, gateways, MCP catalog, and authentication between components**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

Ingress governance, gateways, MCP catalog, and authentication between components.

### Consolidated technical content

### Agent Gateway, MCP Gateway, Local Execution, and Basic Auth

Operational and integration manual for the gateways, including responsibilities, tool catalog, discovery, startup order, ports, variables, end-to-end Basic Auth, and troubleshooting.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### Official gateway architecture

> Content consolidated from `Documentacao/MANUAL_AGENT_PLATFORM_GATEWAYS.md`.

### Goal

This document consolidates:
- Official architecture
- Component inventory
- Complete local-execution procedure
- MCP Gateway
- Agent Gateway
- Backend Runtime
- Frontend
- E2E tests
- Troubleshooting
- Architectural decisions

---

### Official Architecture

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

### Official Ports

| Component | Port |
|------------|--------|
| Frontend | 5173 |
| Agent Gateway | 9000 |
| Backend Runtime | 8000 |
| MCP Gateway | 8300 |
| Telecom MCP Server | 8100 |
| Retail MCP Server | 8200 |

---

### Official Variables

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

### Startup Order

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

Validation:

curl http://localhost:8100/health

---

### Terminal 2 — Retail MCP Server

cd mcp/servers/retail_mcp_server

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn main:app --host 0.0.0.0 --port 8200 --reload

Validation:

curl http://localhost:8200/health

---

### Terminal 3 — MCP Gateway

cd apps/mcp_gateway

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export MCP_GATEWAY_CONFIG_PATH=config/mcp_gateway.yaml

python -m uvicorn app.main:app --host 0.0.0.0 --port 8300 --reload

Validations:

curl http://localhost:8300/health
curl http://localhost:8300/ready
curl http://localhost:8300/v1/tools

Test:

curl -X POST http://localhost:8300/v1/tools/consultar_fatura/invoke

---

### Terminal 4 — Agent Template Backend

cd templates/agent_template_backend

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Validations:

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

Validations:

curl http://localhost:9000/health

Test:

curl -X POST http://localhost:9000/gateway/message

---

### Terminal 6 — Frontend

cd agent_frontend

npm install

npm run dev -- --host 0.0.0.0 --port 5173

Open:

http://localhost:5173

Backend URL:

http://localhost:9000

---

### Tool Flow

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

### Integrated E2E Test

Frontend
↓
Agent Gateway
↓
Backend Runtime
↓
MCP Gateway
↓
Telecom MCP Server

Expected result:

- Agent Gateway receives the request
- Runtime executes LangGraph
- MCP Gateway resolves the tool
- MCP Server responds
- User receives the response

---

### Troubleshooting

### Backend calling MCP Server directly

Confirm:

MCP_GATEWAY_ENABLED=true

MCP_GATEWAY_URL=http://localhost:8300

### Incorrect port

The official MCP Gateway port is:

8300

### Agent Gateway cannot find Backend

Validate:

curl http://localhost:8000/health

### MCP Gateway cannot find MCP Server

Validate:

curl http://localhost:8100/health
curl http://localhost:8200/health

---

### Official Architectural Decisions

- Agent Gateway centralizes governance
- Runtime executes LangGraph
- Runtime executes LLM
- MCP Gateway centralizes tools
- MCP Servers execute tools
- Backend uses MCP Gateway
- `gateway_runtime.env.example` was removed
- `MCP_GATEWAY_*` stays in the backend `.env`
- Official MCP Gateway port = 8300

### Integrated local execution

> Content consolidated from `Documentacao/MANUAL_EXECUCAO_AGENT_GATEWAY_MCP_GATEWAY_FRONTEND.md`.

### Agent Gateway + MCP Gateway + Agent Template Backend + Frontend

### 1. Execution architecture

The local architecture is:

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

Model governance, rate limiting, audit, and policies live in the **Agent Gateway**.

The **Agent Runtime / Agent Template Backend** remains responsible for:

- LangGraph;
- state;
- memory;
- checkpoints;
- supervisor/router;
- guardrails;
- judges;
- LLM calls through existing providers;
- tool calls through MCP Gateway.

---

### 2. Ports

| Component | Port | URL |
|---|---:|---|
| Frontend | 5173 | `http://localhost:5173` |
| Agent Gateway | 9000 | `http://localhost:9000` |
| Agent Template Backend | 8000 | `http://localhost:8000` |
| MCP Gateway | 8300 | `http://localhost:8300` |
| MCP Server / Mock Telecom MCP | 8001 | `http://localhost:8001` |

---

### 3. Recommended startup order

Start in this order:

1. MCP Server / Mock Telecom MCP
2. MCP Gateway
3. Agent Template Backend
4. Agent Gateway
5. Frontend

---

### 4. Terminal 1 — MCP Server / Mock Telecom MCP

If you are using the mock included in the overlay:

```bash
cd agent_platform_oci/mcp/servers/mock_telecom_mcp

python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

Validate:

```bash
curl http://localhost:8001/health
```

Expected result:

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

Validate health:

```bash
curl http://localhost:8300/health
```

Validate readiness:

```bash
curl http://localhost:8300/ready
```

List tools:

```bash
curl -s http://localhost:8300/v1/tools | jq
```

Execute tool:

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

Expected result:

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

or, if your backend is in another folder:

```bash
cd agent_platform_oci/templates/agent_template_backend
```

Activate environment:

```bash
source .venv/bin/activate
```

If `.venv` does not exist yet:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure variables:

```bash
export MCP_GATEWAY_ENABLED=true
export MCP_GATEWAY_URL=http://localhost:8300
export MCP_GATEWAY_TIMEOUT_SECONDS=60

export AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml
```

If you are using OCI/OpenAI-compatible, also keep the backend's existing variables:

```bash
export LLM_PROVIDER=oci_openai
export OCI_GENAI_API_KEY=<sua-chave>
```

or, for mock:

```bash
export LLM_PROVIDER=mock
```

Start backend:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Validate:

```bash
curl http://localhost:8000/health
```

Validate agents:

```bash
curl http://localhost:8000/agents | jq
```

Test backend directly:

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

Activate environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure variables:

```bash
export DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
export AGENT_GATEWAY_GOVERNANCE_CONFIG=config/gateway_governance.yaml
```

Start Agent Gateway:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload
```

Validate:

```bash
curl http://localhost:9000/health
```

If the example governed route is registered in `app.main`, test:

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

If the actual route is `/gateway/message`, test:

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

or the folder where the frontend is located.

Install dependencies:

```bash
npm install
```

Start:

```bash
npm run dev -- --host 0.0.0.0 --port 5173
```

Open:

```text
http://localhost:5173
```

Configure in the frontend:

```text
Backend URL: http://localhost:9000
Agent: telecom_contas
Session ID: session-001
Customer Key: 11999999999
Contract Key: INV-001
```

The frontend must call the **Agent Gateway** on port 9000, not the MCP Gateway.

---

### 9. Expected final flow

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

### 10. Docker Compose for MCP Gateway + Mock MCP

It is also possible to start MCP Gateway + Mock MCP with Docker Compose:

```bash
cd agent_platform_oci

docker compose -f deploy/docker/docker-compose.mcp-gateway.yml up --build
```

This starts:

```text
MCP Gateway      http://localhost:8300
Mock Telecom MCP http://localhost:8001
```

Then start manually:

- Agent Template Backend on port 8000;
- Agent Gateway on port 9000;
- Frontend on port 5173.

---

### 11. Validation checklist

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

### 12. Common errors

### 12.1. Frontend calling the wrong port

Wrong:

```text
Frontend → http://localhost:8000
```

Correct:

```text
Frontend → http://localhost:9000
```

If you want to test without Agent Gateway, you can temporarily point to port 8000. But in the final model, the frontend must use the Agent Gateway.

---

### 12.2. MCP Gateway without an MCP Server

Symptom:

```text
MCP server unavailable
```

Fix:

```bash
curl http://localhost:8001/health
```

If it fails, start the mock MCP server.

---

### 12.3. Tool without BusinessContext

Symptom:

```json
{
  "missing_business_keys": ["customer_key", "contract_key"]
}
```

Fix:

send:

```json
"business_context": {
  "customer_key": "11999999999",
  "contract_key": "INV-001",
  "session_key": "session-001"
}
```

---

### 12.4. Agent Gateway cannot find backend

Symptom:

```text
Connection refused http://localhost:8000
```

Fix:

validate:

```bash
curl http://localhost:8000/health
```

and configure:

```bash
export DEFAULT_AGENT_BACKEND_URL=http://localhost:8000
```

---

### 12.5. Governed route not registered

If `/gateway/message/governed` returns 404, the example file has not yet been included in `app.main`.

In that case, use the actual `/gateway/message` route or register it in `main.py`:

```python
from app.routes.governed_proxy_example import router as governed_router

app.include_router(governed_router)
```

---

### 13. Consolidated variables

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

### 14. Quick summary

In five terminals:

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

### End-to-end Basic Auth

> Content consolidated from `Documentacao/Implementando_Basic_Auth.md`.

To validate **the entire circuit with Basic Auth**, you need to configure three distinct trust relationships:

```text
Cliente de teste
   └─ Basic Auth A ─► Agent Gateway :8010
                         └─ Basic Auth B ─► Agent Backend :8000
                                                └─ Basic Auth C ─► MCP Gateway :8300
```

There is one important detail: in the current package, Basic authentication already works for **incoming** calls, but internal clients still do not send Basic Auth:

* `Agent Gateway → Agent Backend` does not send credentials;
* `Agent Backend → MCP Gateway` sends only a Bearer Token.

Therefore, to test the entire circuit with Basic Auth, make the two small code changes described below.

---

### 1. Prepare the environment

Assume the ZIP was extracted to:

```bash
cd agent_framework_oci_authentication_v2_1
```

Create a single virtual environment to make testing easier:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the framework and dependencies for the three components:

```bash
pip install -U pip

pip install -e ./libs/agent_framework

pip install \
  -r ./Tuning-Performance/Authentication/agent_template_backend_authentication/requirements.txt \
  -r ./apps/agent_gateway/requirements.txt \
  -r ./apps/mcp_gateway/requirements.txt
```

Confirm the import:

```bash
python -c "from agent_framework.security import install_authentication; print('framework ok')"
```

---

### 2. Create three Client ID and Secret pairs

Use different credentials for each hop. For local testing:

| Flow | Client ID | Test Secret |
| ----------------------- | -------------------- | --------------------------- |
| Cliente → Agent Gateway | `tia-test`           | `TiaGateway-Test-2026!`     |
| Agent Gateway → Backend | `agent-gateway-test` | `GatewayBackend-Test-2026!` |
| Backend → MCP Gateway   | `agent-backend-test` | `BackendMcp-Test-2026!`     |

These values are for local environments only. Do not reuse them in production.

### Generate the hashes

The script is located at:

```text
Tuning-Performance/Authentication/
  agent_template_backend_authentication/
    scripts/generate_secret_hash.py
```

Run:

```bash
python Tuning-Performance/Authentication/agent_template_backend_authentication/scripts/generate_secret_hash.py \
  --secret 'TiaGateway-Test-2026!'
```

Then:

```bash
python Tuning-Performance/Authentication/agent_template_backend_authentication/scripts/generate_secret_hash.py \
  --secret 'GatewayBackend-Test-2026!'
```

And:

```bash
python Tuning-Performance/Authentication/agent_template_backend_authentication/scripts/generate_secret_hash.py \
  --secret 'BackendMcp-Test-2026!'
```

You will receive three values similar to:

```text
pbkdf2_sha256:310000:<salt>:<digest>
```

Store them temporarily:

```bash
HASH_CLIENT_GATEWAY='pbkdf2_sha256:310000:...'
HASH_GATEWAY_BACKEND='pbkdf2_sha256:310000:...'
HASH_BACKEND_MCP='pbkdf2_sha256:310000:...'
```

The hash changes on every run because the salt is random. This is expected.

---

### 3. Configure the Agent Gateway

Enter the directory:

```bash
cd apps/agent_gateway
```

Copy the example:

```bash
cp .env.example .env
```

Add to the end of `.env`:

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

Do not put quotes in `.env`:

```env
BACKEND_AUTH_SECRET=GatewayBackend-Test-2026!
```

The backend configuration file already points the `contas` backend to:

```yaml
contas:
  url: http://localhost:8000
```

File:

```text
apps/agent_gateway/config/backends.yaml
```

For this test, keep only the `contas` backend or force the backend in the payload. Otherwise, requests about offers and support may be routed to ports where no backend is running.

---

### 4. Make Agent Gateway send Basic Auth to the backend

Open:

```text
libs/agent_framework/src/agent_framework/global_supervisor/client.py
```

Replace the `BackendClient` class with a version that supports Basic authentication.

At the beginning of the file, add:

```python
import os
```

Change the constructor:

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

In the `call_message` method, replace:

```python
resp = await client.post(url, json=payload)
```

with:

```python
resp = await client.post(
    url,
    json=payload,
    auth=self._auth(),
)
```

In the `health` method, you can keep `/health` public. If you also want to send authentication, use:

```python
resp = await client.get(url, auth=self._auth())
```

Now open:

```text
apps/agent_gateway/app/main.py
```

Add:

```python
import os
```

Replace:

```python
backend_client = BackendClient(
    timeout_seconds=settings.BACKEND_TIMEOUT_SECONDS
)
```

with:

```python
backend_client = BackendClient(
    timeout_seconds=settings.BACKEND_TIMEOUT_SECONDS,
    basic_client_id=os.getenv("BACKEND_AUTH_CLIENT_ID"),
    basic_secret=os.getenv("BACKEND_AUTH_SECRET"),
)
```

This implements:

```text
Agent Gateway → Agent Backend
Authorization: Basic base64(agent-gateway-test:GatewayBackend-Test-2026!)
```

---

### 5. Configure the authenticated Agent Backend

Enter the directory:

```bash
cd Tuning-Performance/Authentication/agent_template_backend_authentication
```

Copy the example:

```bash
cp .env.example .env
```

Adjust the authentication section:

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

To use MCP Gateway:

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60

# Saída: Agent Backend -> MCP Gateway
MCP_GATEWAY_AUTH_MODE=basic
MCP_GATEWAY_BASIC_CLIENT_ID=agent-backend-test
MCP_GATEWAY_BASIC_SECRET=BackendMcp-Test-2026!
```

To avoid external dependencies during the first test, also configure:

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

The exact names of some providers may depend on the framework's current configuration file. If `.env.example` already contains local or mock values, preserve them.

---

### 6. Make the Backend send Basic Auth to MCP Gateway

Open:

```text
libs/agent_framework/src/agent_framework/gateways/mcp_gateway_client.py
```

Replace the implementation with:

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

Now open:

```text
libs/agent_framework/src/agent_framework/mcp/tool_router.py
```

Locate:

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

Change to:

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

Add these fields in:

```text
libs/agent_framework/src/agent_framework/config/settings.py
```

Near the existing MCP Gateway settings:

```python
MCP_GATEWAY_AUTH_MODE: str | None = None
MCP_GATEWAY_BASIC_CLIENT_ID: str | None = None
MCP_GATEWAY_BASIC_SECRET: str | None = None
```

There is also a local factory in:

```text
Tuning-Performance/Authentication/
  agent_template_backend_authentication/
    app/mcp_gateway_client_factory.py
```

Adjust it to:

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

### 7. Configure the MCP Gateway

Enter the directory:

```bash
cd apps/mcp_gateway
```

Create `.env`:

```bash
cp .env.example .env
```

Add:

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

### Disable the legacy Bearer mechanism

The MCP Gateway still has a second legacy mechanism, configured in:

```text
apps/mcp_gateway/config/mcp_gateway.yaml
```

Locate the section:

```yaml
auth:
  enabled: true
```

Change to:

```yaml
auth:
  enabled: false
```

This is necessary because the new middleware already performs Basic authentication. If the legacy `auth_check()` remains enabled, the request will pass Basic authentication and then be rejected because it does not have a Bearer Token.

---

### 8. Start the components

Use four terminals.

### Terminal 1 — MCP Servers

The MCP Gateway needs at least one available MCP server to demonstrate a real call.

From the project root:

```bash
source .venv/bin/activate
```

Start the telecom server:

```bash
uvicorn mcp.servers.telecom_mcp_server.main:app \
  --host 0.0.0.0 \
  --port 8100 \
  --reload
```

In another terminal, if you also want retail:

```bash
uvicorn mcp.servers.retail_mcp_server.main:app \
  --host 0.0.0.0 \
  --port 8200 \
  --reload
```

Check the URLs configured in:

```text
apps/mcp_gateway/config/mcp_gateway.yaml
```

For local execution, they should point to:

```yaml
url: http://localhost:8100
```

and:

```yaml
url: http://localhost:8200
```

---

### Terminal 2 — MCP Gateway

```bash
cd apps/mcp_gateway
source ../../.venv/bin/activate
```

Start it using `--env-file`. This is important because the middleware reads variables with `os.getenv()`:

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8300 \
  --reload \
  --env-file .env
```

Test public health:

```bash
curl http://localhost:8300/health
```

Test a protected endpoint without credentials:

```bash
curl -i http://localhost:8300/v1/tools
```

Expected:

```text
HTTP/1.1 401 Unauthorized
```

Test with Basic Auth:

```bash
curl -i \
  -u 'agent-backend-test:BackendMcp-Test-2026!' \
  http://localhost:8300/v1/tools
```

Expected:

```text
HTTP/1.1 200 OK
```

---

### Terminal 3 — Agent Backend

```bash
cd Tuning-Performance/Authentication/agent_template_backend_authentication
source ../../../.venv/bin/activate
```

Start:

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --env-file .env
```

Test health:

```bash
curl http://localhost:8000/health
```

Test a protected endpoint without credentials:

```bash
curl -i http://localhost:8000/agents
```

Expected:

```text
HTTP/1.1 401 Unauthorized
```

Test with the credential used by Agent Gateway:

```bash
curl -i \
  -u 'agent-gateway-test:GatewayBackend-Test-2026!' \
  http://localhost:8000/agents
```

Expected:

```text
HTTP/1.1 200 OK
```

Test a message directly:

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

Start:

```bash
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8010 \
  --reload \
  --env-file .env
```

Test health:

```bash
curl http://localhost:8010/health
```

Test a protected endpoint without credentials:

```bash
curl -i http://localhost:8010/backends
```

Expected:

```text
HTTP/1.1 401 Unauthorized
```

Test with the external credential:

```bash
curl -i \
  -u 'tia-test:TiaGateway-Test-2026!' \
  http://localhost:8010/backends
```

Expected:

```text
HTTP/1.1 200 OK
```

---

### 9. Validate the complete circuit

Force the `contas` backend to prevent the router from selecting a backend that has not been started:

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

The expected circuit is:

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

### 10. How to prove each authentication hop

Run negative tests on each hop.

### Incorrect external secret

```bash
curl -i \
  -u 'tia-test:senha-errada' \
  http://localhost:8010/backends
```

Expected result:

```text
401 Unauthorized
```

### Incorrect gateway-to-backend secret

Temporarily change this in `apps/agent_gateway/.env`:

```env
BACKEND_AUTH_SECRET=senha-errada
```

Restart the Agent Gateway and send a message.

The gateway should return a backend error, normally:

```text
502 Bad Gateway
```

The internal error will originate from a:

```text
401 Unauthorized
```

from the Agent Backend.

### Incorrect backend-to-MCP secret

Temporarily change:

```env
MCP_GATEWAY_BASIC_SECRET=senha-errada
```

Restart the backend and execute a phrase that triggers an MCP tool.

The backend should record a failure in the MCP Gateway call with:

```text
401 Unauthorized
```

---

### 11. Quick port verification

On Linux or WSL:

```bash
ss -lntp | grep -E ':8000|:8010|:8100|:8200|:8300'
```

On Windows PowerShell:

```powershell
Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -in 8000,8010,8100,8200,8300 |
  Sort-Object LocalPort
```

You should see:

```text
8000  Agent Backend
8010  Agent Gateway
8100  Telecom MCP Server
8200  Retail MCP Server
8300  MCP Gateway
```

### Important note

The original secret must exist in the client component:

```text
TIA ou curl:
  TiaGateway-Test-2026!

Agent Gateway:
  GatewayBackend-Test-2026!

Agent Backend:
  BackendMcp-Test-2026!
```

Server components store only the hashes:

```text
Agent Gateway:
  hash de TiaGateway-Test-2026!

Agent Backend:
  hash de GatewayBackend-Test-2026!

MCP Gateway:
  hash de BackendMcp-Test-2026!
```

In production, original secrets and hashes should come from Vault or Kubernetes Secret, not `.env` files.

### MCP catalog discovery and synchronization

> Content consolidated from `docs/MCP_GATEWAY_DISCOVERY.md`.

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

### MCP Gateway operational runbook

> Content consolidated from `Documentacao/MCP_GATEWAY_RUNBOOK.md`.

### Corrected architecture

The backend/agent must not call the final MCP servers directly. The correct flow is:

```text
agent_template_backend / agent_framework
  -> MCP Gateway Client
  -> apps/mcp_gateway
  -> mcp/servers/telecom_mcp_server ou mcp/servers/retail_mcp_server
```

### Start locally

From the project root:

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

### Terminal 4 - Backend/agent

In the `.env` of the backend/agent or runtime that uses `agent_framework`, enable:

```env
ENABLE_MCP_TOOLS=true
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_AGENT_ID=telecom_contas
MCP_GATEWAY_TENANT_ID=default
```

### Quick tests

### Gateway health

```bash
curl http://localhost:8300/health
```

### List of tools exposed by the gateway

```bash
curl http://localhost:8300/v1/tools
```

### Tool call through the gateway

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

Expected response: `ok: true`, `data.invoice_id`, `data.msisdn`, `metadata.server: telecom`.

### What was fixed

- `apps/mcp_gateway/config/mcp_gateway.yaml` now points to the real MCP servers on ports `8100` and `8200`.
- MCP Gateway now supports the legacy MCP-server contract: `POST /mcp/tools/call` with `{tool_name, arguments}`.
- `agent_framework` gained the flags `MCP_GATEWAY_ENABLED`, `MCP_GATEWAY_URL`, `MCP_GATEWAY_TOKEN`, `MCP_GATEWAY_AGENT_ID`, and `MCP_GATEWAY_TENANT_ID`.
- `MCPToolRouter` now calls the MCP Gateway when `MCP_GATEWAY_ENABLED=true`.
- `libs/agent_framework/config/mcp_servers.yaml` was retained as a logical registry/fallback, not as the primary path when the gateway is active.

### Architectural evolution of the gateways

> Content consolidated from `Documentacao/README_AGENT_GATEWAY_AND_MCP_GATEWAY_EVOLUTION.md`.

This overlay removes the concept of a separate `AI Gateway`.

### Architecture

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

### What belongs in the Agent Gateway

```text
apps/agent_gateway/app/governance/
apps/agent_gateway/app/governance_middleware.py
apps/agent_gateway/app/routes/governed_proxy_example.py
apps/agent_gateway/config/gateway_governance.yaml
```

### What belongs in the MCP Gateway

```text
apps/mcp_gateway/
libs/agent_framework/src/agent_framework/gateways/mcp_gateway_client.py
libs/agent_framework/src/agent_framework/runtime_mcp_gateway_adapter.py
```

### Apply overlay

```bash
unzip agent_platform_agent_gateway_mcp_gateway_overlay.zip -d /tmp/overlay
rsync -av /tmp/overlay/ ./
```

### Start MCP Gateway locally

```bash
docker compose -f deploy/docker/docker-compose.mcp-gateway.yml up --build
```

Services:

```text
MCP Gateway      http://localhost:8300
Mock Telecom MCP http://localhost:8001
```

### Test MCP Gateway

```bash
curl http://localhost:8300/health
curl http://localhost:8300/v1/tools
```

Execute tool:

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

### How to plug it into Agent Gateway

In the actual `POST /gateway/message` handler, before forwarding to backend/runtime:

```python
governed_body, headers = governance.prepare_backend_request(body)
```

After receiving the backend response:

```python
return governance.process_backend_response(data)
```

The file below shows a complete example:

```text
apps/agent_gateway/app/routes/governed_proxy_example.py
```

### Runtime Variables

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
MCP_GATEWAY_TIMEOUT_SECONDS=60
```

### Important

There is no `apps/ai_gateway`.

Model governance lives in Agent Gateway as policy/metadata.

Runtime continues using the existing LLM providers and may read the policy sent by the Gateway from:

```python
state["metadata"]["model_policy"]
```

### File and responsibility inventory

> Content consolidated from `Documentacao/INVENTARIO_AGENT_GATEWAY_MCP_GATEWAY.md`.

This inventory lists the files included in the `agent_platform_agent_gateway_mcp_gateway_overlay.zip` overlay, indicating the area, type of change, and purpose of each file.

### Summary

| Area | Quantity |
|---|---:|
| Documentation | 1 |
| Agent Gateway | 10 |
| MCP Gateway | 5 |
| Agent Framework | 4 |
| Template Backend | 2 |
| MCP Server Mock | 2 |
| Deploy | 2 |

### Files by area

### Documentation

| File | Type | Purpose |
|---|---|---|
| `README_AGENT_GATEWAY_AND_MCP_GATEWAY_EVOLUTION.md` | New / overlay | Main overlay document. Explains the new architecture without a separate AI Gateway, with Agent Gateway governing policies/models and a separate MCP Gateway for tools. |

### Agent Gateway

| File | Type | Purpose |
|---|---|---|
| `apps/agent_gateway/app/config/governance_loader.py` | New / overlay | Loads the Agent Gateway governance YAML file from `AGENT_GATEWAY_GOVERNANCE_CONFIG`. |
| `apps/agent_gateway/app/governance/__init__.py` | New / overlay | Initializes the Agent Gateway governance Python package. |
| `apps/agent_gateway/app/governance/audit.py` | New / overlay | Centralizes logging/auditing of Agent Gateway governance decisions, with simple protection to avoid logging the full message. |
| `apps/agent_gateway/app/governance/evaluation_hooks.py` | New / overlay | Hooks before and after the backend/runtime call. Used for sampling, evaluator, scoring, or future Langfuse integration. |
| `apps/agent_gateway/app/governance/model_policies.py` | New / overlay | Resolves model/profile policies in Agent Gateway. Defines which provider/model/profile should be used by operation, tenant, and agent. |
| `apps/agent_gateway/app/governance/rate_limit.py` | New / overlay | Implements in-memory rate limiting by tenant, agent, and channel before forwarding the request to backend/runtime. |
| `apps/agent_gateway/app/governance/usage.py` | New / overlay | Hook to record gateway usage, applied policies, and backend responses. Ready to plug into metrics, database, Langfuse, or OTEL. |
| `apps/agent_gateway/app/governance_middleware.py` | New / overlay | Main Agent Gateway governance component. Applies rate limiting, resolves `model_policy`, generates headers/metadata, and executes hooks before/after the backend. |
| `apps/agent_gateway/app/routes/governed_proxy_example.py` | New / overlay | Example governed route demonstrating how to apply governance before forwarding to the Agent Backend/Runtime. |
| `apps/agent_gateway/config/gateway_governance.yaml` | New / overlay | Agent Gateway governance configuration: profiles, operation profiles, allowed providers, rate limits, propagated headers, and evaluation hooks. |

### MCP Gateway

| File | Type | Purpose |
|---|---|---|
| `apps/mcp_gateway/Dockerfile` | New / overlay | MCP Gateway Docker image. |
| `apps/mcp_gateway/app/__init__.py` | New / overlay | Initializes the MCP Gateway application Python package. |
| `apps/mcp_gateway/app/main.py` | New / overlay | MCP Gateway FastAPI application. Exposes health, ready, tool catalog, and invoke endpoint with auth, authorization, mapping, cache, timeout, and retry. |
| `apps/mcp_gateway/config/mcp_gateway.yaml` | New / overlay | Central MCP Gateway configuration: MCP servers, tools, versions, cache, timeout, retry, authorization by agent/channel, and BusinessContext → parameter mapping. |
| `apps/mcp_gateway/requirements.txt` | New / overlay | MCP Gateway Python dependencies. |

### Agent Framework

| File | Type | Purpose |
|---|---|---|
| `libs/agent_framework/src/agent_framework/gateway_policy_context.py` | New / overlay | Framework helper for Runtime to read the model policy sent by Agent Gateway in `state['metadata']['model_policy']`. |
| `libs/agent_framework/src/agent_framework/gateways/__init__.py` | New / overlay | Initializes the framework gateway-client package, exporting `MCPGatewayClient`. |
| `libs/agent_framework/src/agent_framework/gateways/mcp_gateway_client.py` | New / overlay | Async framework client for MCP Gateway: list tools and execute tools. |
| `libs/agent_framework/src/agent_framework/runtime_mcp_gateway_adapter.py` | New / overlay | Optional mixin for agents/runtime to call tools through MCP Gateway and append results to `state['mcp_results']`. |

### Template Backend

| File | Type | Purpose |
|---|---|---|
| `templates/agent_template_backend/app/mcp_gateway_client_factory.py` | New / overlay | Factory in the template backend to build `MCPGatewayClient` from environment variables. |

### MCP Server Mock

| File | Type | Purpose |
|---|---|---|
| `mcp/servers/mock_telecom_mcp/app.py` | New / overlay | Mock MCP Server with `consultar_fatura` and `consultar_pagamentos` tools for local MCP Gateway validation. |
| `mcp/servers/mock_telecom_mcp/requirements.txt` | New / overlay | Dependencies for the telecom mock MCP Server used in local tests. |

### Deploy

| File | Type | Purpose |
|---|---|---|
| `deploy/docker/docker-compose.mcp-gateway.yml` | New / overlay | Docker Compose file to start MCP Gateway and `mock_telecom_mcp` locally. |
| `deploy/k8s/mcp-gateway.yaml` | New / overlay | Kubernetes Deployment and Service manifest for MCP Gateway. |

### Integration notes

### Agent Gateway

The files under `apps/agent_gateway` do not create a new service. They evolve the existing Agent Gateway to act as the platform's dedicated gateway, centralizing:

- model/profile policies;
- rate limiting;
- auditing;
- evaluation hooks;
- propagation of governance metadata to Runtime.

The `governed_proxy_example.py` route is an integration example. The actual `POST /gateway/message` handler should apply:

```python
governed_body, headers = governance.prepare_backend_request(body)
```

before calling backend/runtime, and:

```python
return governance.process_backend_response(data)
```

after receiving the response.

### MCP Gateway

MCP Gateway is a separate service. It centralizes:

- tool catalog;
- authorization by agent/channel;
- tool versioning;
- BusinessContext-to-parameter mapping;
- cache;
- timeout;
- retry;
- simple audit.

### Runtime / Backend

Runtime remains responsible for:

- LangGraph;
- state;
- memory;
- checkpoints;
- flow;
- existing LLM providers.

Runtime now calls tools through MCP Gateway using `MCPGatewayClient` and/or `MCPGatewayRuntimeMixin`.

### AI Gateway

This overlay does not create `apps/ai_gateway`. Model governance stays in Agent Gateway, and LLM execution remains in Runtime/backend using the existing providers.

### Source files

The files below were consolidated into this manual:

- `Documentacao/MANUAL_AGENT_PLATFORM_GATEWAYS.md`
- `Documentacao/MANUAL_EXECUCAO_AGENT_GATEWAY_MCP_GATEWAY_FRONTEND.md`
- `Documentacao/Implementando_Basic_Auth.md`
- `docs/MCP_GATEWAY_DISCOVERY.md`
- `Documentacao/MCP_GATEWAY_RUNBOOK.md`
- `Documentacao/README_AGENT_GATEWAY_AND_MCP_GATEWAY_EVOLUTION.md`
- `Documentacao/INVENTARIO_AGENT_GATEWAY_MCP_GATEWAY.md`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
