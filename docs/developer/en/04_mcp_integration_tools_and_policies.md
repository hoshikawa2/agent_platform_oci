### MCP, Tools, Policies, and Parameter Extraction

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **tools, MCP Servers, mappings, read-only/transactional policies, and parameter extraction**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

Tools, MCP servers, mappings, read-only/transactional policies, and parameter extraction.

### Consolidated technical content

### MCP Integration, Tools, Policies, and Parameter Extraction

Development manual for integrating MCP Servers, registering tools, isolating tools by agent, configuring read-only/transactional policies, confirmation, and contextual parameter extraction.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### Complete MCP Server integration manual

> Content consolidated from `Documentacao/Manual_Integracao_MCP_Servers_Agent_Framework.docx`.

MCP Server Integration Manual  
Multi-Agent Framework - Router, Supervisor, Tools, and External Servers  
This document explains MCP concepts, how the current project integrates MCP servers, how to start the example Telecom and Retail servers, how to configure tools per agent, and how to evolve the implementation toward a solution that more closely follows the official MCP standard. The goal is to serve as a development, local-operations, and container/OCI deployment guide.

### MCP concepts

MCP stands for Model Context Protocol. It defines a standardized way for AI applications to access external context, tools, and capabilities from systems outside the model. Instead of putting integrations directly into the prompt or agent, MCP separates responsibilities: the agent decides what it needs, and an MCP server exposes tools, resources, and prompts in a controlled way.  
In the official standard, MCP uses JSON-RPC messages and defines transports such as stdio and Streamable HTTP. The current project uses a simplified HTTP implementation to make understanding and local testing easier, with REST endpoints `/mcp/tools/list` and `/mcp/tools/call`. This is appropriate for tutorials and prototyping, but it can later evolve to an official MCP client.

### How the current project organizes MCP

The relevant project structure is:
```
projeto_multi_agent_isolado/
  agent_framework/
    src/agent_framework/mcp/
      client.py
      models.py
      registry.py
      tool_router.py

  agent_template_backend/
    config/
      mcp_servers.yaml
      mcp_servers.docker.yaml
      tools.yaml
      mcp_parameter_mapping.yaml
    app/
      main.py
      workflows/agent_graph.py

  mcp_servers/
    telecom_mcp_server/
      main.py
      requirements.txt
      Dockerfile
    retail_mcp_server/
      main.py
      requirements.txt
      Dockerfile

  scripts/
    run_mcp_servers.sh
  docker-compose.yml
```

### Main components


### Simplified HTTP contract used by the project

```
GET  /mcp/tools/list
POST /mcp/tools/call

Payload de chamada:
{
  "tool_name": "consultar_fatura",
  "arguments": {
    "msisdn": "11999999999",
    "invoice_id": "INV-001"
  }
}

Resposta esperada:
{
  "ok": true,
  "result": { ... },
  "metadata": {
    "server": "telecom",
    "tool": "consultar_fatura"
  }
}
```

### How to start the example MCP servers

The project includes two example MCP servers: Telecom and Retail. They are independent FastAPI apps. The Telecom server runs on port 8100 and exposes tools such as `consultar_fatura`, `consultar_pagamentos`, `consultar_plano`, and `listar_servicos`. The Retail server runs on port 8200 and exposes tools such as `consultar_pedido`, `consultar_entrega`, `solicitar_troca`, and `solicitar_devolucao`.

### Local startup through the script

```
cd projeto_multi_agent_isolado
bash ./scripts/run_mcp_servers.sh
```
The script creates a venv in the root directory, installs the MCP-server dependencies, and starts both uvicorn processes in the background:
```
Telecom MCP: http://localhost:8100
Retail MCP:  http://localhost:8200
```

### Manual startup of Telecom MCP

```
cd projeto_multi_agent_isolado
python -m venv .venv
source .venv/bin/activate
pip install -r mcp_servers/telecom_mcp_server/requirements.txt
uvicorn --app-dir mcp_servers/telecom_mcp_server main:app --host 0.0.0.0 --port 8100
```

### Manual startup of Retail MCP

```
cd projeto_multi_agent_isolado
source .venv/bin/activate
pip install -r mcp_servers/retail_mcp_server/requirements.txt
uvicorn --app-dir mcp_servers/retail_mcp_server main:app --host 0.0.0.0 --port 8200
```

### Startup with Docker Compose

```
cd projeto_multi_agent_isolado
docker compose up --build
```
In Docker Compose, the backend uses `mcp_servers.docker.yaml` because, inside the compose network, localhost would point to the backend container itself. Therefore the endpoints use service names: `telecom-mcp` and `retail-mcp`.
```
services:
  telecom-mcp:
    ports:
      - "8100:8100"

  retail-mcp:
    ports:
      - "8200:8200"

  backend:
    environment:
      MCP_SERVERS_CONFIG_PATH: /app/config/mcp_servers.docker.yaml
    depends_on:
      - telecom-mcp
      - retail-mcp
```

### How to test MCP tools


### Direct health checks on the servers

```
curl http://localhost:8100/health
curl http://localhost:8200/health
```

### List tools directly from Telecom MCP

```
curl http://localhost:8100/mcp/tools/list
```

### Call a tool directly on Telecom MCP

```
curl -X POST http://localhost:8100/mcp/tools/call   -H 'Content-Type: application/json'   -d '{
    "tool_name": "consultar_fatura",
    "arguments": {
      "msisdn": "11999999999",
      "invoice_id": "INV-001"
    }
  }'
```

### Call a tool directly on Retail MCP

```
curl -X POST http://localhost:8200/mcp/tools/call   -H 'Content-Type: application/json'   -d '{
    "tool_name": "consultar_pedido",
    "arguments": {
      "order_id": "PED-1001",
      "customer_id": "C-001"
    }
  }'
```

### Test through the agent backend

After starting the MCP servers and backend, the backend provides debug endpoints to list and call tools through `MCPToolRouter`.
```
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -e ../agent_framework
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --reload-dir config --port 8000
curl http://localhost:8000/debug/mcp/tools

curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura   -H 'Content-Type: application/json'   -d '{"msisdn":"11999999999","invoice_id":"INV-001"}'
```

### How the agent calls MCP in the flow

The agent does not need to know the server URL. It calls a logical tool through `MCPToolRouter`. The expected flow is:
```
Usuário
  -> FastAPI /gateway/message
  -> Guardrails de input
  -> Router ou Supervisor escolhe o agente
  -> LangGraph executa o agent graph
  -> Agent decide usar uma tool
  -> MCPToolRouter.call("consultar_fatura", {...})
  -> MCPRegistry resolve servidor telecom
  -> MCPHttpClient chama http://localhost:8100/mcp/tools/call
  -> Resultado volta ao agent graph
  -> Guardrails de output
  -> Judges
  -> Resposta final
```

### Conceptual Python example

```
result = await tool_router.call(
    "consultar_fatura",
    {
        "msisdn": context.get("msisdn"),
        "invoice_id": context.get("invoice_id"),
    },
)

if result.ok:
    dados_fatura = result.result
else:
    # fallback controlado, telemetria e resposta segura
    erro = result.error
```

### Example through a gateway message

```
curl -X POST http://localhost:8000/gateway/message   -H 'Content-Type: application/json'   -d '{
    "channel": "web",
    "payload": {
      "session_id": "sess-tel-1",
      "message": "Minha fatura veio alta",
      "context": {
        "msisdn": "11999999999",
        "invoice_id": "INV-001"
      }
    }
  }'
curl -X POST http://localhost:8000/gateway/message   -H 'Content-Type: application/json'   -d '{
    "channel": "web",
    "payload": {
      "session_id": "sess-ret-1",
      "message": "Meu pedido não chegou",
      "context": {
        "order_id": "PED-1001",
        "customer_id": "C-001"
      }
    }
  }'
```

### How to configure new servers and tools


### Add a new MCP Server

Edit `agent_template_backend/config/mcp_servers.yaml` for local execution:
```
servers:
  crm:
    transport: http
    endpoint: http://localhost:8300/mcp
    enabled: true
    description: MCP Server de CRM.
```
Edit `agent_template_backend/config/mcp_servers.docker.yaml` for Docker execution:
```
servers:
  crm:
    transport: http
    endpoint: http://crm-mcp:8300/mcp
    enabled: true
    description: MCP Server de CRM via docker-compose.
```

### Register a new tool

Edit `agent_template_backend/config/tools.yaml`:
```
tools:
  consultar_cliente:
    description: Consulta dados cadastrais resumidos do cliente.
    mcp_server: crm
    enabled: true
    args_schema:
      customer_id: string
      document_id: string
```

### Implement the endpoint in the MCP server

```
TOOLS = {
    "consultar_cliente": {
        "description": "Consulta dados cadastrais resumidos do cliente.",
        "input_schema": {
            "customer_id": "string",
            "document_id": "string"
        },
    },
}

@app.post("/mcp/tools/call")
async def call_tool(call: ToolCall):
    if call.tool_name == "consultar_cliente":
        return {
            "ok": True,
            "result": {
                "customer_id": call.arguments.get("customer_id"),
                "status": "ATIVO",
                "segmento": "PREMIUM"
            },
            "metadata": {"server": "crm", "tool": "consultar_cliente"}
        }
```

### How to isolate MCP by agent

In a multi-agent architecture, not every agent should see every tool. The orders agent may use `consultar_pedido` and `consultar_entrega`. The billing agent may use `consultar_fatura` and `consultar_pagamentos`. This isolation reduces operational risk, improves governance, and simplifies each agent's prompt.

### Simple option: allowlist per agent

```
agents:
  - agent_id: billing_agent
    allowed_tools:
      - consultar_fatura
      - consultar_pagamentos
      - consultar_plano
      - listar_servicos

  - agent_id: orders_agent
    allowed_tools:
      - consultar_pedido
      - consultar_entrega
      - solicitar_troca
      - solicitar_devolucao
```

### Recommended option: tools by configuration file

For large projects, each agent can have its own `tools.yaml`, `guardrails.yaml`, and `judges.yaml`. This maintains real isolation by agent and makes versioning easier.
```
config/agents/telecom_contas/
  prompt_policy.yaml
  guardrails.yaml
  judges.yaml
  tools.yaml

config/agents/retail_orders/
  prompt_policy.yaml
  guardrails.yaml
  judges.yaml
  tools.yaml
```

### How to deploy with Docker and OCI


### Local deployment with Docker Compose

The current `docker-compose.yml` already has separate services for `telecom-mcp`, `retail-mcp`, backend, and frontend. This separation is correct because MCP Servers should be independently scalable and versionable from the agent backend.
```
docker compose up --build

# URLs externas para teste local:
http://localhost:8100/health
http://localhost:8200/health
http://localhost:8000/debug/mcp/tools
http://localhost:5173
```

### Deployment on OCI/OKE

In Kubernetes/OKE, each MCP Server should be deployed as a Deployment + Service. The agent backend points to the Service's internal DNS. Conceptual example:
```
apiVersion: v1
kind: Service
metadata:
  name: telecom-mcp
spec:
  selector:
    app: telecom-mcp
  ports:
    - port: 8100
      targetPort: 8100
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: telecom-mcp
spec:
  replicas: 2
  selector:
    matchLabels:
      app: telecom-mcp
  template:
    metadata:
      labels:
        app: telecom-mcp
    spec:
      containers:
        - name: telecom-mcp
          image: <registry>/telecom-mcp:1.0.0
          ports:
            - containerPort: 8100
```

### Backend configuration in Kubernetes

```
servers:
  telecom:
    transport: http
    endpoint: http://telecom-mcp.default.svc.cluster.local:8100/mcp
    enabled: true

  retail:
    transport: http
    endpoint: http://retail-mcp.default.svc.cluster.local:8200/mcp
    enabled: true
```

### Security, guardrails, and observability

MCP greatly increases agent capability, but also increases the attack and operational-risk surface. A tool can query sensitive data, open protocols/cases, cancel services, generate credits, or execute business actions. Therefore, the integration must be protected before, during, and after the call.

### Minimum security checklist

- Every tool must have a clear description and argument schema.
- Every action tool must require explicit user confirmation before execution.
- Each agent must have a tool allowlist.
- Sensitive data returned by MCP must pass through masking/sanitization before the final response.
- Every MCP call must generate a trace/span/event in Langfuse or OpenTelemetry.
- Timeouts and retry limits must be configured per tool or per server.
- Do not expose MCP Servers directly to the internet without authentication, TLS, and network controls.
- Separate read-only tools from transactional tools.

### Recommended telemetry

```
span: mcp.tool_call
attributes:
  tenant_id
  agent_id
  session_id
  tool_name
  mcp_server
  latency_ms
  ok
  error
  input_argument_keys
  result_size

event: mcp.tool_call.completed
metadata:
  tool_name
  server
  ok
  error
```

### Evolution toward official MCP

The current project uses a simplified HTTP contract. For enterprise production there are two options. The first is to keep this internal contract for simplicity, provided it is well documented, secure, and versioned. The second is to evolve to an official MCP client/server with JSON-RPC, stdio, or Streamable HTTP.

### Complete developer step-by-step

```
# 1. Baixar e abrir o projeto
cd projeto_multi_agent_isolado

# 2. Subir servidores MCP de exemplo
bash ./scripts/run_mcp_servers.sh

# 3. Em outro terminal, subir backend
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -e ../agent_framework
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --reload-dir config --port 8000

# 4. Validar tools carregadas pelo backend
curl http://localhost:8000/debug/mcp/tools

# 5. Chamar tool Telecom
curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura   -H 'Content-Type: application/json'   -d '{"msisdn":"11999999999","invoice_id":"INV-001"}'

# 6. Chamar tool Retail
curl -X POST http://localhost:8000/debug/mcp/call/consultar_pedido   -H 'Content-Type: application/json'   -d '{"order_id":"PED-1001","customer_id":"C-001"}'

# 7. Testar pelo gateway conversacional
curl -X POST http://localhost:8000/gateway/message   -H 'Content-Type: application/json'   -d '{"channel":"web","payload":{"session_id":"sess-ret-1","message":"Meu pedido não chegou","context":{"order_id":"PED-1001","customer_id":"C-001"}}}'
```

### Troubleshooting


### References

- Model Context Protocol Specification: https://modelcontextprotocol.io/specification
- MCP Transports: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- MCP Resources: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- Reference MCP Servers: https://github.com/modelcontextprotocol/servers
- LangChain MCP Adapters: https://docs.langchain.com/oss/python/langchain/mcp
- Project files: `agent_framework/src/agent_framework/mcp/*`, `agent_template_backend/config/mcp_servers.yaml`, `agent_template_backend/config/tools.yaml`, `mcp_servers/*`

### Read-only and transactional policies

The framework applies a minimal conversational policy immediately before the MCP call. `read_only` classification identifies queries; `transactional` identifies operations that change state. Authorization, idempotency, validation, and atomicity remain the responsibility of the MCP Server.

### Backend configuration

The configuration is optional and lives in `config/tool_policies.yaml` in `agent_template_backend`. The path can be set through `TOOL_POLICIES_PATH`. Do not place domain policies inside the shared library.  
Example:
defaults:
  operation_type: read_only
  require_confirmation: false
tool_policies:
  alterar_plano:
    operation_type: transactional
    require_confirmation: true
    requires: [new_plan_id]

### Execution and compatibility

- Confirmation must arrive as `confirmed: true` or `confirmation: true`; text with value `true` is not sufficient.
- If `tool_policies.yaml` does not exist, `tool_type`, `requires`, `confirmation_required`, and `execution_policy` from `tools.yaml` remain valid.
- Old tools without policy continue to work without behavior changes.
- A blocked call does not reach MCP and returns metadata `blocked_by_policy`, `operation_type`, and `policy_source`.

### Read-only and transactional policies

> Content consolidated from `Documentacao/README_TOOL_POLICIES.md`.

### Goal

The framework distinguishes query operations (`read_only`) from operations that change state (`transactional`) immediately before the MCP call. This classification does not replace authorization, idempotency, or MCP-server business rules; it only adds minimal conversational protection, especially explicit confirmation.

### Where to configure

Configuration belongs to the application backend:

```text
templates/agent_template_backend/config/tool_policies.yaml
```

The shared library contains only the loader and validation. The path is optional:

```dotenv
TOOL_POLICIES_PATH=./config/tool_policies.yaml
```

### Example

```yaml
version: 1

defaults:
  operation_type: read_only
  require_confirmation: false

tool_policies:
  consultar_plano:
    operation_type: read_only

  alterar_plano:
    operation_type: transactional
    require_confirmation: true
    requires: [new_plan_id]
```

To execute `alterar_plano`, the arguments must contain `new_plan_id` and a literal boolean confirmation:

```json
{"new_plan_id": "CONTROLE_100", "confirmed": true}
```

`"confirmation": true` is also accepted. Strings such as `"true"` are not accepted as confirmation.

### Compatibility

- If `tool_policies.yaml` does not exist, the framework continues to use `tool_type`, `requires`, `confirmation_required`, and `execution_policy` from `tools.yaml`.
- Old tools without policy continue to execute as before.
- An explicit policy in the new file takes precedence for that tool's `operation_type` and confirmation.
- The `tools.yaml` catalog remains the source for endpoint, schema, enablement, and cache.
- The new file must not be placed in `libs/agent_framework`, because decisions vary by application and domain.

### Execution flow

```text
agente -> MCPToolRouter -> validação da política -> mapeamento de parâmetros -> MCP Gateway/Server
```

A blocked call returns `ok=false`, `metadata.blocked_by_policy=true`, the operation type, and the policy source. The MCP server remains the final authority for authentication, authorization, validation, idempotency, and business transaction.

### Recommended migration

1. Update the library without creating the file: legacy behavior remains.
2. Create `config/tool_policies.yaml` in the backend.
3. Initially register only transactional operations that require confirmation.
4. Test calls without confirmation, with boolean confirmation, and with missing required fields.
5. Gradually remove duplicate confirmation settings from `tools.yaml` when all consuming templates already use the new configuration.


### Minimum transactional runtime (binding fix)

The routing `mcp_tools` list is an **allowlist**, not an instruction to execute every tool. The runtime now:

1. automatically executes only `read_only` tools;
2. selects at most one transactional action compatible with the user's request;
3. when `require_confirmation: true`, persists `pending_tool_call` and `transaction_status: AWAITING_CONFIRMATION`;
4. on the confirmation turn, reuses the same call and executes it with `confirmed: true`;
5. publishes `available_mcp_tools`, `selected_tool_call`, `tool_policy_result`, `confirmation_required`, and `confirmation_received` in state.

For the example scenario, order `123` (or `PED-ENTREGUE`) returns `ENTREGUE` in Retail MCP. Use:

```text
Quero devolver o pedido 123 porque me arrependi da compra.
Sim, confirmo a devolução.
```

The MCP contract was standardized to use `reason` in both the catalog and FastMCP server. `tool_policies.yaml` takes precedence over legacy fields in `tools.yaml`; these remain aligned in the templates for compatibility.

### Tool-policy integration and compatibility

> Content consolidated from `Documentacao/RELEASE_NOTES_TOOL_POLICIES.md`.

### Changes

- New optional `ToolPolicyRegistry` in the shared library.
- Central validation in `MCPToolRouter`, including direct calls.
- Minimum types `read_only` and `transactional`.
- Strict confirmation through `confirmed: true` or `confirmation: true`.
- Optional support for required fields per policy.
- Automatic fallback to `tool_type`, `requires`, `confirmation_required`, and `execution_policy` from `tools.yaml`.
- `config/tool_policies.yaml` and the `TOOL_POLICIES_PATH` variable in the main templates, Day Zero, and `Tuning-Performance/Normal` and `Tuning-Performance/Route_Stickness` variants.
- Unit policy and compatibility tests added in `tests/unit/test_tool_policies.py`.

### Checks performed

- Compilation of `libs`, `templates`, `Tuning-Performance`, and `tests`: passed.
- Structural validation of the six YAML files: passed.
- Isolated loader cases (transactional policy, confirmation, missing file, and missing registration): passed.
- Rendering of both updated Word manuals: passed, with no clipping or overlap on the added pages.

### Validation-environment limitation

The `pytest` suite was prepared but could not be fully executed in this environment because `pytest` and project runtime dependencies were not installed and access to the package index timed out. To reproduce in a project environment:

```bash
PYTHONPATH=libs/agent_framework/src:templates/agent_template_backend python -m pytest -q
```

### Backend/MCP integration correction
- `mcp_tools` is now treated as an allowlist.
- Actions are no longer automatically executed together with queries.
- Transactional confirmation is persisted and resumed on the next turn.
- `reason`/`motivo` incompatibility in Retail MCP was corrected.
- A deterministic delivered order was added for tests (`123`).
- The generic keyword `produto` was removed from the Telecom intent to avoid collisions with Retail returns.
- `Normal` and `Route_Stickness` templates in `Tuning-Performance` were synchronized.

### Contextual MCP parameter extraction

> Content consolidated from `Documentacao/RELEASE_NOTES_MCP_PARAMETER_EXTRACTION_FIX.md`.

### Problem fixed

The `extract` block in `mcp_parameter_mapping.yaml` existed in configuration and documentation, but it was not executed by the runtime. In addition, Business Context values could overwrite explicit arguments, causing `contract_key` to replace the `order_id` provided by the user.

### Fixes

- implementation of generic `strategy: llm` extraction after tool selection;
- preserved support for `strategy: month_name_pt`;
- dedicated `mcp_parameter_extraction` profile;
- `llm.mcp_parameter_extraction` telemetry;
- `extract` is no longer interpreted as simple mapping;
- explicit/extracted arguments take precedence over Business Context;
- removal of `contract_key: order_id` from templates;
- `order_id` configured as `string`;
- update of `Tuning-Performance` variants.

### Expected result

For the message `consultar pedido 123`, the MCP call must receive `order_id=123`, even when Business Context contains a different `contract_key`.

### Local use of MCP tools

> Content consolidated from `Documentacao/README_MCP.md`.

This version adds an MCP layer to the framework:

- `agent_framework.mcp.MCPToolRouter`
- `agent_template_backend/config/mcp_servers.yaml`
- `agent_template_backend/config/tools.yaml`
- `mcp_servers/telecom_mcp_server`
- `mcp_servers/retail_mcp_server`

### Start locally

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

### Quick tests

List MCP tools loaded by the backend:

```bash
curl http://localhost:8000/debug/mcp/tools
```

Call a tool directly through the backend:

```bash
curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura \
  -H 'Content-Type: application/json' \
  -d '{"msisdn":"11999999999","invoice_id":"INV-001"}'
```

Telecom routing + MCP:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"session_id":"sess-tel-1","message":"Minha fatura veio alta","context":{"msisdn":"11999999999","invoice_id":"INV-001"}}}'
```

Retail routing + MCP:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"session_id":"sess-ret-1","message":"Meu pedido não chegou","context":{"order_id":"PED-1001","customer_id":"C-001"}}}'
```

### Docker Compose

```bash
docker compose up --build
```

In compose, the backend uses `config/mcp_servers.docker.yaml` to point to `telecom-mcp` and `retail-mcp`.

### Read-only and transactional operations

Use `config/tool_policies.yaml` in the backend to classify only operations that need additional handling. Validation is applied in the central router before the MCP Gateway/Server. The file is optional and older templates continue using the policies already present in `tools.yaml`. Full configuration and the migration procedure are in [README_TOOL_POLICIES.md](README_TOOL_POLICIES.md).

### Source files

The files below were consolidated into this manual:

- `Documentacao/Manual_Integracao_MCP_Servers_Agent_Framework.docx`
- `Documentacao/README_TOOL_POLICIES.md`
- `Documentacao/RELEASE_NOTES_TOOL_POLICIES.md`
- `Documentacao/RELEASE_NOTES_MCP_PARAMETER_EXTRACTION_FIX.md`
- `Documentacao/README_MCP.md`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
