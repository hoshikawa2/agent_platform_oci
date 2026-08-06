# Implementando Basic Auth

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

# 1. Preparar o ambiente

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

# 2. Criar três pares de Client ID e Secret

Use credenciais diferentes para cada trecho. Para teste local:

| Fluxo                   | Client ID            | Secret de teste             |
| ----------------------- | -------------------- | --------------------------- |
| Cliente → Agent Gateway | `tia-test`           | `TiaGateway-Test-2026!`     |
| Agent Gateway → Backend | `agent-gateway-test` | `GatewayBackend-Test-2026!` |
| Backend → MCP Gateway   | `agent-backend-test` | `BackendMcp-Test-2026!`     |

Esses valores são apenas para ambiente local. Não os reutilize em produção.

## Gerar os hashes

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

# 3. Configurar o Agent Gateway

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

# 4. Fazer o Agent Gateway enviar Basic Auth ao backend

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

# 5. Configurar o Agent Backend autenticado

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

# 6. Fazer o Backend enviar Basic Auth ao MCP Gateway

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

# 7. Configurar o MCP Gateway

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

## Desabilitar o mecanismo Bearer legado

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

# 8. Subir os componentes

Use quatro terminais.

## Terminal 1 — MCP Servers

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

## Terminal 2 — MCP Gateway

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

## Terminal 3 — Agent Backend

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

## Terminal 4 — Agent Gateway

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

# 9. Validar o circuito completo

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

# 10. Como comprovar cada autenticação

Faça testes negativos em cada trecho.

## Secret externo incorreto

```bash
curl -i \
  -u 'tia-test:senha-errada' \
  http://localhost:8010/backends
```

Resultado esperado:

```text
401 Unauthorized
```

## Secret do gateway para backend incorreto

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

## Secret do backend para MCP incorreto

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

# 11. Verificação rápida de portas

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

## Observação importante

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
