# Tutorial — Implementação de um Agente usando `agent_template_backend`

Este tutorial mostra como criar um novo agente a partir do modelo `agent_template_backend`, mantendo o padrão corporativo do framework: LangGraph, roteamento enterprise, supervisor, guardrails, judges, memória, checkpoint, observabilidade, analytics IC/NOC/GRL e integração com MCP Tools.

![img_1.png](../img_1.png)

O objetivo é que cada novo agente implemente apenas sua lógica de domínio — prompts, regras de negócio, ferramentas, schemas e nós específicos — sem recriar motores que já pertencem ao framework.

---

## 1. Visão geral da arquitetura

O template segue esta divisão:

```text
agent_template_backend/
├── app/
│   ├── main.py                    # API FastAPI, gateway, SSE, sessão, memória e chamada do workflow
│   ├── state.py                   # Estado compartilhado do LangGraph
│   ├── workflows/
│   │   └── agent_graph.py          # Workflow LangGraph com guardrails, router, agentes, judges e persistência
│   ├── agents/
│   │   ├── runtime.py              # Mixin comum para MCP, RAG, cache e emissão de IC/GRL
│   │   ├── billing_agent.py        # Exemplo de agente de faturas
│   │   ├── product_agent.py        # Exemplo de agente de produtos
│   │   ├── orders_agent.py         # Exemplo de agente de pedidos
│   │   └── support_agent.py        # Exemplo de agente de suporte
│   └── examples/                  # Exemplos de IC, NOC, GRL, MCP e observer
├── config/
│   ├── agents.yaml                # Registro de agentes disponíveis
│   ├── routing.yaml               # Intents, keywords, fallback e roteamento
│   ├── tools.yaml                 # Catálogo de tools MCP
│   ├── mcp_servers.yaml           # Endpoints MCP locais
│   ├── mcp_servers.docker.yaml    # Endpoints MCP em Docker Compose
│   ├── mcp_parameter_mapping.yaml # Mapeamento de chaves canônicas para parâmetros das tools
│   ├── identity.yaml              # Resolução de identidade de negócio
│   ├── guardrails.yaml            # Guardrails globais
│   ├── judges.yaml                # Judges globais
│   ├── prompt_policy.yaml         # Política global de prompt
│   └── agents/<agent_id>/         # Configurações isoladas por agente
├── data/
│   └── agent_framework.db         # Banco local de exemplo, quando aplicável
├── Dockerfile
├── requirements.txt
└── .env                           # Configuração local
```

### Responsabilidade do framework

O framework deve concentrar os motores genéricos:

- LangGraph e montagem do workflow.
- Checkpoint.
- Memória.
- Session repository.
- Channel gateway.
- Enterprise Router.
- Supervisor.
- Guardrails.
- Output Supervisor.
- Judges.
- Telemetria Langfuse/OpenTelemetry.
- Analytics IC/NOC/GRL.
- MCP Tool Router.
- Cache.
- RAG genérico.

### Responsabilidade do agente

O agente deve concentrar apenas customizações de domínio:

- Prompts específicos.
- Regras de negócio.
- Schemas próprios.
- Tools específicas.
- Clients de sistemas externos.
- Mapeamento de parâmetros.
- Nós especializados, se houver.
- ICs de negócio da jornada.

Essa separação evita que cada agente recrie seu próprio motor de execução.

---

## 2. Fluxo de execução do template

O fluxo principal começa em `app/main.py`, no endpoint `/gateway/message`.

```text
Canal / Frontend / API
  ↓
POST /gateway/message
  ↓
ChannelGateway.normalize()
  ↓
IdentityResolver
  ↓
SessionRepository
  ↓
MemoryRepository
  ↓
AgentWorkflow.ainvoke()
  ↓
LangGraph
  ↓
Input Guardrails
  ↓
Enterprise Router ou Supervisor
  ↓
Agente especializado
  ↓
MCP Tool Router / RAG / Cache / LLM
  ↓
Output Supervisor
  ↓
Output Guardrails
  ↓
Judges
  ↓
Supervisor Review
  ↓
Persistência / Checkpoint / Memória
  ↓
Resposta
```

O `AgentWorkflow`, em `app/workflows/agent_graph.py`, já contém os nós corporativos:

```text
input_guardrails
routing_decision
billing_agent
product_agent
orders_agent
support_agent
handoff
supervisor_agent
output_supervisor
output_guardrails
judge
supervisor_review
persist
```

Para criar um agente novo, normalmente você altera:

1. `app/agents/<novo_agente>.py`
2. `app/workflows/agent_graph.py`
3. `app/state.py`, se precisar de campos novos
4. `config/agents.yaml`
5. `config/routing.yaml`
6. `config/tools.yaml`
7. `config/mcp_servers.yaml`
8. `config/mcp_parameter_mapping.yaml`
9. `config/identity.yaml`, se houver novas chaves de negócio
10. `config/agents/<agent_id>/prompt_policy.yaml`
11. `config/agents/<agent_id>/guardrails.yaml`
12. `config/agents/<agent_id>/judges.yaml`
13. `.env`

---

## 3. Pré-requisitos

### 3.1. Requisitos locais

- Python 3.12 ou 3.13.
- `pip` ou `uv`.
- Projeto `agent_framework` disponível no mesmo workspace, pois o Dockerfile espera algo como:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

- Servidores MCP, se o agente usar tools.
- Redis, Oracle Autonomous Database, MongoDB e Langfuse são opcionais conforme configuração.

### 3.2. Instalação local

Dentro do diretório `agent_template_backend`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Se o `agent_framework` estiver em desenvolvimento local:

```bash
pip install -e ../agent_framework
```

Em Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e ..\agent_framework
```

---

## 4. Configuração do `.env`

O arquivo `.env` controla o comportamento do backend. Não versionar credenciais reais.

Exemplo seguro para desenvolvimento local:

```env
APP_NAME=ai-agent-template
APP_ENV=local
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# LLM
# Opções comuns: mock, oci_openai, oci_sdk, openai_compatible
LLM_PROVIDER=mock
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2048
LLM_TIMEOUT_SECONDS=120

# OCI/OpenAI-compatible, se usar OCI GenAI
OCI_GENAI_BASE_URL=https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1
OCI_GENAI_MODEL=<modelo>
OCI_GENAI_API_KEY=<api-key-ou-token>
OCI_CONFIG_FILE=~/.oci/config
OCI_PROFILE=DEFAULT
OCI_COMPARTMENT_ID=<ocid-do-compartment>
OCI_REGION=<region>

# Persistência local simples
SESSION_REPOSITORY_PROVIDER=memory
MEMORY_REPOSITORY_PROVIDER=memory
CHECKPOINT_REPOSITORY_PROVIDER=memory
USAGE_REPOSITORY_PROVIDER=memory

# Redis/cache
ENABLE_REDIS_CACHE=false
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=300

# RAG
VECTOR_STORE_PROVIDER=memory
GRAPH_STORE_PROVIDER=memory
RAG_TOP_K=5
EMBEDDING_PROVIDER=mock

# Observabilidade
ENABLE_LANGFUSE=false
LANGFUSE_HOST=http://localhost:3005
ENABLE_OTEL=false
OTEL_SERVICE_NAME=ai-agent-template

# Analytics IC/NOC/GRL
ENABLE_ANALYTICS=false
ANALYTICS_PROVIDERS=noop
ENABLE_OCI_STREAMING=false
OCI_STREAM_ENDPOINT=
OCI_STREAM_OCID=
OCI_STREAM_PARTITION_KEY=agent-events

# Guardrails, judges e supervisor
ENABLE_INPUT_GUARDRAILS=true
ENABLE_OUTPUT_GUARDRAILS=true
ENABLE_OUTPUT_SUPERVISOR=true
ENABLE_JUDGES=true
ENABLE_SUPERVISOR=true
ENABLE_PARALLEL_GUARDRAILS=true
GUARDRAILS_FAIL_FAST=true
OUTPUT_SUPERVISOR_MAX_RETRIES=3
GUARDRAILS_CONFIG_PATH=./config/guardrails.yaml
JUDGES_CONFIG_PATH=./config/judges.yaml
PROMPT_POLICY_PATH=./config/prompt_policy.yaml

# Roteamento
ROUTING_CONFIG_PATH=./config/routing.yaml
ROUTING_MODE=router
ENABLE_LLM_ROUTER=false

# MCP
ENABLE_MCP_TOOLS=true
MCP_SERVERS_CONFIG_PATH=./config/mcp_servers.yaml
TOOLS_CONFIG_PATH=./config/tools.yaml
MCP_PARAMETER_MAPPING_PATH=./config/mcp_parameter_mapping.yaml
MCP_TOOL_TIMEOUT_SECONDS=30

# Identidade
IDENTITY_CONFIG_PATH=./config/identity.yaml
```

Para usar Oracle Autonomous Database, ajuste:

```env
SESSION_REPOSITORY_PROVIDER=autonomous
MEMORY_REPOSITORY_PROVIDER=autonomous
CHECKPOINT_REPOSITORY_PROVIDER=autonomous
USAGE_REPOSITORY_PROVIDER=autonomous

ADB_USER=<usuario>
ADB_PASSWORD=<senha>
ADB_DSN=<dsn>
ADB_WALLET_LOCATION=<caminho-wallet>
ADB_WALLET_PASSWORD=<senha-wallet>
ADB_TABLE_PREFIX=AGENTFW
```

Para usar Langfuse:

```env
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=<public-key>
LANGFUSE_SECRET_KEY=<secret-key>
LANGFUSE_HOST=http://localhost:3005
```

---

## 5. Criando um novo agente

Neste exemplo, vamos criar um agente chamado `financeiro_agent` para atendimento financeiro genérico.

### 5.1. Criar o arquivo do agente

Crie:

```text
app/agents/financeiro_agent.py
```

Código-base:

```python
from app.agents.prompting import apply_agent_profile_prompt
from app.agents.runtime import AgentRuntimeMixin


class FinanceiroAgent(AgentRuntimeMixin):
    name = "financeiro_agent"

    def __init__(self, llm, telemetry=None, tool_router=None, rag_service=None, cache=None, settings=None, observer=None):
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings
        self.observer = observer

    async def run(self, state):
        await self._emit_ic(
            "IC.FINANCEIRO_AGENT_STARTED",
            state,
            {"business_component": "financeiro"},
            component="agent.financeiro.start",
        )

        session = (state.get("context") or {}).get("session", {})
        tool_context = await self._collect_tool_context(state)

        if tool_context:
            await self._emit_ic(
                "IC.FINANCEIRO_MCP_CONTEXT_COLLECTED",
                state,
                {"tool_result_count": len(tool_context)},
                component="agent.financeiro.mcp",
            )

        rag_context, rag_metadata = await self._retrieve_rag_context(state)

        messages = [
            {
                "role": "system",
                "content": apply_agent_profile_prompt(
                    state,
                    "Você é um agente financeiro. Responda com clareza, usando dados das ferramentas quando disponíveis. Não confirme ações financeiras sem evidência e confirmação explícita."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Mensagem: {state.get('sanitized_input') or state['user_text']}\n"
                    f"Sessão: {session}\n"
                    f"Intent: {state.get('intent')}\n"
                    f"Dados MCP: {tool_context}\n"
                    f"Contexto RAG: {rag_context}"
                ),
            },
        ]

        answer = await self._invoke_llm_cached(state, "FinanceiroAgent", messages)

        result = {
            "answer": f"[FinanceiroAgent] {answer}",
            "next_state": "FINANCEIRO_ACTIVE",
            "mcp_results": tool_context,
            "rag": rag_metadata,
        }

        await self._emit_ic(
            "IC.FINANCEIRO_AGENT_COMPLETED",
            state,
            {
                "answer_chars": len(result.get("answer") or ""),
                "has_mcp_results": bool(tool_context),
                "rag_enabled": bool(rag_metadata.get("enabled")),
            },
            component="agent.financeiro.completed",
        )

        return result

    async def _collect_tool_context(self, state):
        return await self._collect_mcp_context(state)
```

Esse agente usa recursos já existentes no `AgentRuntimeMixin`:

- `_emit_ic()` para eventos de negócio.
- `_collect_mcp_context()` para chamar tools selecionadas pelo roteador.
- `_retrieve_rag_context()` para recuperar contexto RAG.
- `_invoke_llm_cached()` para chamada ao LLM com cache.

---

## 6. Registrando o agente no workflow

Edite:

```text
app/workflows/agent_graph.py
```

### 6.1. Importar o agente

Adicione:

```python
from app.agents.financeiro_agent import FinanceiroAgent
```

### 6.2. Instanciar o agente

No `__init__` da classe `AgentWorkflow`, depois de `agent_kwargs`:

```python
self.financeiro = FinanceiroAgent(llm, **agent_kwargs)
```

### 6.3. Criar o nó do LangGraph

Em `_build_graph()`:

```python
builder.add_node("financeiro_agent", self._node("financeiro_agent", self.financeiro_agent))
```

### 6.4. Adicionar rota condicional

No dicionário de `builder.add_conditional_edges("routing_decision", ...)`, inclua:

```python
"financeiro_agent": "financeiro_agent",
```

Exemplo:

```python
builder.add_conditional_edges(
    "routing_decision",
    lambda s: s.get("route", "billing_agent"),
    {
        "billing_agent": "billing_agent",
        "product_agent": "product_agent",
        "orders_agent": "orders_agent",
        "support_agent": "support_agent",
        "financeiro_agent": "financeiro_agent",
        "handoff": "handoff",
        "supervisor_agent": "supervisor_agent",
    },
)
```

### 6.5. Conectar o nó ao Output Supervisor

```python
builder.add_edge("financeiro_agent", "output_supervisor")
```

### 6.6. Criar o método wrapper

Na classe `AgentWorkflow`:

```python
async def financeiro_agent(self, state):
    async with self.langgraph_telemetry.node("financeiro_agent", state):
        async with self.telemetry.span(
            "workflow.agent.financeiro",
            session_id=state.get("conversation_key") or state.get("session_id"),
            input={"intent": state.get("intent")},
        ):
            return await self.financeiro.run(state)
```

### 6.7. Adicionar ao modo supervisor

No método `supervisor_agent()`, ajuste o mapa de handlers:

```python
handlers = {
    "billing_agent": self.billing.run,
    "product_agent": self.product.run,
    "orders_agent": self.orders.run,
    "support_agent": self.support.run,
    "financeiro_agent": self.financeiro.run,
}
```

---

## 7. Ajustando o estado do agente

Edite:

```text
app/state.py
```

Adicione novos campos apenas se o agente precisar guardar algo específico no estado do LangGraph.

Exemplo:

```python
class AgentState(TypedDict, total=False):
    # campos existentes...
    financial_context: dict[str, Any]
    financial_decision: dict[str, Any]
```

Evite colocar dados grandes no estado. Para histórico longo, use memória. Para evidências externas, use RAG, banco ou cache.

---

## 8. Registrando o agente em `config/agents.yaml`

Edite:

```text
config/agents.yaml
```

Adicione um novo item:

```yaml
agents:
  - agent_id: financeiro_agent
    name: Financeiro Agent
    description: Agente para dúvidas financeiras, pagamentos, saldos, acordos e segunda via.
    prompt_policy_path: ./config/agents/financeiro_agent/prompt_policy.yaml
    routing_config_path: ./config/routing.yaml
    guardrails_config_path: ./config/agents/financeiro_agent/guardrails.yaml
    judges_config_path: ./config/agents/financeiro_agent/judges.yaml
    mcp_servers_config_path: ./config/mcp_servers.yaml
    tools_config_path: ./config/tools.yaml
    metadata:
      domain: financeiro
      system_prefix: |
        Você está executando o financeiro_agent.
        Use somente políticas, memória, checkpoints, guardrails e judges deste agent_id.
        Não misture histórico ou decisões de outros agentes.
```

Se quiser que este seja o agente padrão, ajuste o campo de agente default conforme o formato atual do seu `agents.yaml`.

---

## 9. Criando configurações isoladas do agente

Crie a pasta:

```text
config/agents/financeiro_agent/
```

### 9.1. `prompt_policy.yaml`

```yaml
id: financeiro_agent_prompt_policy
version: 1
description: Prompt base isolado do agente financeiro.
system_prefix: |
  Você é um agente corporativo especializado em atendimento financeiro.
  Seja claro, objetivo, auditável e não invente dados.
  Quando precisar executar uma ação, use ferramentas configuradas.
  Quando faltar informação obrigatória, peça apenas o dado necessário.
```

### 9.2. `guardrails.yaml`

```yaml
input:
  - code: MSK
    enabled: true
  - code: VLOOP
    enabled: true
  - code: PINJ
    enabled: true
output:
  - code: REVPREC
    enabled: true
  - code: CMP
    enabled: true
```

### 9.3. `judges.yaml`

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.7
  - name: groundedness
    enabled: true
    threshold: 0.6
```

---

## 10. Configurando roteamento em `config/routing.yaml`

Adicione uma intent para o novo agente:

```yaml
intents:
  - name: financeiro_pagamentos
    domain: financeiro
    agent: financeiro_agent
    description: Dúvidas sobre pagamento, saldo, fatura, boleto, acordo, contestação e segunda via.
    priority: 15
    mcp_tools:
      - consultar_titulo_financeiro
      - consultar_pagamentos_financeiro
    keywords:
      - pagamento
      - boleto
      - saldo
      - acordo
      - financeiro
      - segunda via
      - vencimento
      - cobrança
      - contestação
    examples:
      - Quero consultar meu pagamento.
      - Preciso da segunda via do boleto.
      - Meu pagamento ainda não foi baixado.
```

Se estiver usando políticas de estado, adicione:

```yaml
state_policies:
  - state: WAITING_FINANCEIRO_CONFIRMATION
    agent: financeiro_agent
    description: Mantém confirmações curtas no fluxo financeiro.
```

O roteador suporta dois modos:

```env
ROUTING_MODE=router
```

ou:

```env
ROUTING_MODE=supervisor
```

No modo `router`, uma intent aponta para um agente. No modo `supervisor`, o supervisor pode acionar um ou mais agentes.

---

## 11. Configurando tools em `config/tools.yaml`

Adicione as tools necessárias:

```yaml
tools:
  consultar_titulo_financeiro:
    description: Consulta um título financeiro por cliente e contrato.
    mcp_server: financeiro
    enabled: true
    args_schema:
      customer_id: string
      contract_id: string

  consultar_pagamentos_financeiro:
    description: Consulta pagamentos financeiros por cliente.
    mcp_server: financeiro
    enabled: true
    args_schema:
      customer_id: string
```

As tools devem existir no servidor MCP configurado. O backend não deve chamar diretamente HTTP/SOAP/DB de sistemas de negócio quando essa chamada puder ser padronizada via MCP Tool Router.

---

## 12. Configurando servidores MCP

Edite:

```text
config/mcp_servers.yaml
```

Exemplo local:

```yaml
servers:
  financeiro:
    transport: http
    endpoint: http://localhost:8300/mcp
    enabled: true
    description: MCP Server Financeiro local.
```

Para Docker Compose, edite:

```text
config/mcp_servers.docker.yaml
```

Exemplo:

```yaml
servers:
  financeiro:
    transport: http
    endpoint: http://financeiro-mcp:8300/mcp
    enabled: true
    description: MCP Server Financeiro em Docker.
```

---

## 13. Configurando mapeamento de parâmetros MCP

Edite:

```text
config/mcp_parameter_mapping.yaml
```

Exemplo:

```yaml
mcp_parameter_mapping:
  defaults:
    use_mock: true
  tools:
    consultar_titulo_financeiro:
      map:
        customer_key: customer_id
        contract_key: contract_id
        interaction_key: interaction_id
        session_key: session_id
    consultar_pagamentos_financeiro:
      map:
        customer_key: customer_id
        session_key: session_id
```

Interpretação:

```text
customer_key  -> chave canônica no framework
customer_id   -> parâmetro esperado pela tool MCP
```

Assim, o agente trabalha com identidade canônica, e cada tool recebe os nomes que seu MCP Server espera.

---

## 14. Configurando identidade de negócio

Edite:

```text
config/identity.yaml
```

Esse arquivo define como extrair chaves canônicas do payload, contexto, canal ou sessão.

Exemplo:

```yaml
identity:
  version: "2"
  required:
    - session_key
  keys:
    customer_key:
      description: Cliente canônico.
      sources:
        - business_context.customer_key
        - customer_key
        - customer_id
        - cpf
        - cnpj
        - user_id
    contract_key:
      description: Contrato, pedido, fatura ou título principal.
      sources:
        - business_context.contract_key
        - contract_key
        - contract_id
        - invoice_id
        - order_id
    interaction_key:
      description: Chave externa da interação.
      sources:
        - business_context.interaction_key
        - interaction_key
        - call_id
        - message_id
        - protocol_id
    session_key:
      description: Sessão técnica estável.
      sources:
        - business_context.session_key
        - session_key
        - conversation_key
        - session_id
```

A identidade resolvida aparece em `business_context` dentro do state e é usada pelo `MCP Tool Router`.

---

## 15. Implementando ou conectando um MCP Server

O backend espera que a tool exista no MCP Server. A implementação exata depende do padrão do seu servidor MCP, mas o contrato conceitual é:

```text
Backend Agent
  ↓
MCP Tool Router
  ↓
MCP Server financeiro
  ↓
Sistema real, mock, banco, REST, SOAP ou serviço interno
```

Exemplo conceitual de tools:

```python
async def consultar_titulo_financeiro(customer_id: str, contract_id: str, session_id: str | None = None):
    return {
        "customer_id": customer_id,
        "contract_id": contract_id,
        "status": "ABERTO",
        "valor": 129.90,
        "vencimento": "2026-06-20",
    }


async def consultar_pagamentos_financeiro(customer_id: str, session_id: str | None = None):
    return {
        "customer_id": customer_id,
        "pagamentos": [
            {"data": "2026-06-01", "valor": 129.90, "status": "COMPENSADO"}
        ],
    }
```

Para desenvolvimento, você pode usar `use_mock: true` no `mcp_parameter_mapping.yaml` ou implementar um MCP Server local com respostas simuladas.

---

## 16. IC, NOC e GRL no novo agente

### 16.1. IC — eventos de negócio

Use ICs dentro do agente para registrar passos relevantes da jornada.

Exemplo:

```python
await self._emit_ic(
    "IC.FINANCEIRO_AGENT_STARTED",
    state,
    {"business_component": "financeiro"},
    component="agent.financeiro.start",
)
```

Sugestão mínima por agente:

```text
IC.<AGENTE>_AGENT_STARTED
IC.<AGENTE>_MCP_CONTEXT_COLLECTED
IC.<AGENTE>_RAG_CONTEXT_RETRIEVED
IC.<AGENTE>_AGENT_COMPLETED
IC.<AGENTE>_BUSINESS_DECISION
IC.<AGENTE>_ACTION_REQUESTED
IC.<AGENTE>_ACTION_COMPLETED
```

### 16.2. NOC — eventos operacionais

NOC deve ser usado para saúde técnica, indisponibilidade, erro, timeout, fallback e degradação.

Exemplo direto, se necessário:

```python
await self.observer.emit_noc(
    "NOC.FINANCEIRO_TOOL_TIMEOUT",
    {
        "session_id": state.get("conversation_key") or state.get("session_id"),
        "tenant_id": state.get("tenant_id"),
        "agent_id": state.get("agent_id"),
        "tool": "consultar_titulo_financeiro",
    },
    component="agent.financeiro.tool",
)
```

### 16.3. GRL — guardrails

A maior parte dos GRLs já é emitida pelo workflow em:

```text
input_guardrails
output_supervisor
output_guardrails
```

Só implemente GRL dentro do agente quando houver uma validação de domínio específica que não caiba nos guardrails globais.

---

## 17. Build e execução local

### 17.1. Rodar backend local

Dentro de `agent_template_backend`:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verifique saúde:

```bash
curl http://localhost:8000/health
```

Listar agentes:

```bash
curl http://localhost:8000/agents
```

Listar tools MCP conhecidas:

```bash
curl http://localhost:8000/debug/mcp/tools
```

---

## 18. Subindo MCP Servers

Se os MCP Servers forem processos Python separados, suba cada um em uma porta distinta.

Exemplo conceitual:

```bash
cd ../mcp_servers/financeiro_mcp_server
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8300 --reload
```

Depois confirme que o endpoint configurado em `config/mcp_servers.yaml` está correto:

```yaml
servers:
  financeiro:
    endpoint: http://localhost:8300/mcp
```

Teste pelo backend:

```bash
curl -X POST http://localhost:8000/debug/mcp/call/consultar_titulo_financeiro \
  -H "Content-Type: application/json" \
  -d '{
    "business_context": {
      "customer_key": "12345",
      "contract_key": "ABC-999",
      "session_key": "sessao-teste"
    },
    "original_context": {
      "session_id": "sessao-teste"
    }
  }'
```

---

## 19. Build com Docker

O Dockerfile do template espera copiar `agent_framework` e `agent_template_backend`. Portanto, rode o build a partir do diretório pai que contém ambos.

Estrutura esperada:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

Build:

```bash
cd workspace
docker build -t agent-template-backend:local -f agent_template_backend/Dockerfile .
```

Run:

```bash
docker run --rm -p 8000:8000 \
  --env-file agent_template_backend/.env \
  agent-template-backend:local
```

Health check:

```bash
curl http://localhost:8000/health
```

---

## 20. Docker Compose sugerido

Crie um `docker-compose.yaml` no diretório pai, se quiser subir backend, Redis, Langfuse e MCP Servers juntos.

Exemplo simplificado:

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: agent_template_backend/Dockerfile
    env_file:
      - agent_template_backend/.env
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - financeiro-mcp

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  financeiro-mcp:
    build:
      context: ./mcp_servers/financeiro_mcp_server
    ports:
      - "8300:8300"
```

Quando estiver em Docker, use `config/mcp_servers.docker.yaml` e ajuste o `.env`:

```env
MCP_SERVERS_CONFIG_PATH=./config/mcp_servers.docker.yaml
```

---

## 21. Testando o agente pelo Gateway

### 21.1. Teste simples

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "agent_id": "financeiro_agent",
    "tenant_id": "default",
    "payload": {
      "text": "Quero consultar meu pagamento",
      "session_id": "teste-financeiro-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "contract_id": "ABC-999",
      "message_id": "msg-001"
    }
  }'
```

A resposta deve conter metadados como:

```json
{
  "channel": "web",
  "session_id": "default:financeiro_agent:teste-financeiro-001",
  "text": "...",
  "metadata": {
    "route": "financeiro_agent",
    "intent": "financeiro_pagamentos",
    "mcp_results": [],
    "business_context": {
      "customer_key": "12345",
      "contract_key": "ABC-999"
    }
  }
}
```

### 21.2. Teste de roteamento sem fixar `agent_id`

Se quiser validar o `default_agent_id` e o roteamento por intenção:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "tenant_id": "default",
    "payload": {
      "text": "Meu pagamento ainda não foi baixado",
      "session_id": "teste-router-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "contract_id": "ABC-999"
    }
  }'
```

### 21.3. Teste de SSE

Enviar mensagem com SSE:

```bash
curl -X POST http://localhost:8000/gateway/message/sse \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "agent_id": "financeiro_agent",
    "tenant_id": "default",
    "payload": {
      "text": "Preciso da segunda via do boleto",
      "session_id": "teste-sse-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "contract_id": "ABC-999"
    }
  }'
```

Abrir stream:

```bash
curl -N http://localhost:8000/gateway/events/default:financeiro_agent:teste-sse-001
```

Eventos esperados:

```text
connected
flow.start
session.upserted
message.received
workflow.started
workflow.completed
message.responded
flow.end
```

---

## 22. Testando debug endpoints

### 22.1. Roteamento

```bash
curl -X POST http://localhost:8000/debug/route \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Quero consultar meu pagamento",
    "context": {
      "agent_id": "financeiro_agent",
      "tenant_id": "default"
    }
  }'
```

### 22.2. Identidade

```bash
curl -X POST http://localhost:8000/debug/identity \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "teste-id-001",
    "customer_id": "12345",
    "contract_id": "ABC-999",
    "message_id": "msg-001"
  }'
```

### 22.3. Mensagens da sessão

```bash
curl http://localhost:8000/sessions/default:financeiro_agent:teste-financeiro-001/messages
```

### 22.4. Checkpoint

```bash
curl http://localhost:8000/sessions/default:financeiro_agent:teste-financeiro-001/checkpoint
```

### 22.5. Uso/custo

```bash
curl http://localhost:8000/debug/usage
```

---

## 23. Checklist de validação funcional

Use este checklist antes de considerar o agente pronto.

### 23.1. Configuração

- [ ] `.env` sem credenciais reais versionadas.
- [ ] `LLM_PROVIDER` correto.
- [ ] `ROUTING_MODE` definido: `router` ou `supervisor`.
- [ ] `ENABLE_MCP_TOOLS` ajustado conforme necessidade.
- [ ] `MCP_SERVERS_CONFIG_PATH` aponta para o YAML correto.
- [ ] `IDENTITY_CONFIG_PATH` aponta para `config/identity.yaml`.
- [ ] Persistência local ou Autonomous configurada.

### 23.2. Agente

- [ ] Arquivo criado em `app/agents/<agent>.py`.
- [ ] Classe implementa `async def run(self, state)`.
- [ ] Agente herda `AgentRuntimeMixin`.
- [ ] Prompts específicos aplicam `apply_agent_profile_prompt()`.
- [ ] Tools são chamadas via `_collect_mcp_context()`.
- [ ] RAG é chamado via `_retrieve_rag_context()`, se aplicável.
- [ ] LLM é chamado via `_invoke_llm_cached()`.
- [ ] Retorno contém `answer`, `next_state`, `mcp_results` e, se aplicável, `rag`.

### 23.3. Workflow

- [ ] Agente importado em `agent_graph.py`.
- [ ] Agente instanciado no `__init__`.
- [ ] Nó adicionado no `StateGraph`.
- [ ] Rota adicionada em `add_conditional_edges`.
- [ ] Edge criada para `output_supervisor`.
- [ ] Handler adicionado no modo supervisor, se necessário.

### 23.4. Roteamento

- [ ] Intent adicionada em `config/routing.yaml`.
- [ ] Keywords suficientes.
- [ ] Examples coerentes.
- [ ] `agent` da intent bate com o nome do nó do workflow.
- [ ] `mcp_tools` da intent existem em `config/tools.yaml`.

### 23.5. MCP

- [ ] Tool declarada em `config/tools.yaml`.
- [ ] MCP Server declarado em `config/mcp_servers.yaml`.
- [ ] Mapeamento declarado em `config/mcp_parameter_mapping.yaml`.
- [ ] Tool testada via `/debug/mcp/call/{tool_name}`.
- [ ] Timeout e fallback definidos.

### 23.6. Observabilidade

- [ ] ICs de início e fim emitidos.
- [ ] ICs de coleta MCP/RAG emitidos quando aplicável.
- [ ] NOCs emitidos em erros técnicos relevantes.
- [ ] GRLs globais aparecem em input/output.
- [ ] Langfuse ou outro provider recebe traces, se habilitado.

### 23.7. Testes

- [ ] `/health` retorna `status=ok`.
- [ ] `/agents` lista o agente novo.
- [ ] `/debug/route` escolhe o agente correto.
- [ ] `/debug/identity` resolve as chaves esperadas.
- [ ] `/gateway/message` retorna resposta correta.
- [ ] `/gateway/message/sse` publica eventos.
- [ ] `/sessions/{session_id}/messages` mostra histórico.
- [ ] `/sessions/{session_id}/checkpoint` mostra checkpoint.

---

## 24. Boas práticas de customização

### Faça

- Coloque regra de negócio no agente, não no framework.
- Use MCP para acesso a sistemas externos.
- Use `identity.yaml` para normalizar chaves de negócio.
- Use `mcp_parameter_mapping.yaml` para adaptar nomes de parâmetros.
- Use IC para eventos de negócio.
- Use NOC para falhas técnicas.
- Use GRL para decisões de segurança/validação.
- Mantenha prompts por agente em `config/agents/<agent_id>/prompt_policy.yaml`.
- Mantenha guardrails e judges isolados quando o agente tiver regras próprias.

### Evite

- Criar outro workflow fora de `AgentWorkflow` sem necessidade.
- Chamar REST/DB direto dentro do agente quando a chamada deveria ser tool MCP.
- Criar checkpointer próprio.
- Criar memória paralela fora do framework.
- Emitir telemetria em formato incompatível com `AgentObserver`.
- Colocar regra específica de um agente dentro do framework.
- Misturar histórico de agentes diferentes na mesma sessão.

---

## 25. Troubleshooting

### 25.1. `/gateway/message` retorna rota errada

Verifique:

```bash
curl -X POST http://localhost:8000/debug/route \
  -H "Content-Type: application/json" \
  -d '{"text":"sua frase de teste","context":{"agent_id":"financeiro_agent"}}'
```

Depois revise:

- `config/routing.yaml`
- keywords
- examples
- priority
- `ROUTING_MODE`
- `ENABLE_LLM_ROUTER`

### 25.2. Tool MCP não é chamada

Verifique:

- A intent em `routing.yaml` possui `mcp_tools`.
- A tool existe em `tools.yaml`.
- O MCP Server está em `mcp_servers.yaml`.
- `ENABLE_MCP_TOOLS=true`.
- O mapeamento existe em `mcp_parameter_mapping.yaml`.
- A identidade tem as chaves necessárias.

### 25.3. Tool recebe parâmetro errado

Revise:

```text
config/identity.yaml
config/mcp_parameter_mapping.yaml
payload enviado ao /gateway/message
```

Use:

```bash
curl -X POST http://localhost:8000/debug/identity \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","customer_id":"123","contract_id":"C1"}'
```

### 25.4. SSE dá MIME type incorreto

O endpoint correto é:

```text
GET /gateway/events/{session_id}
```

O `session_id` precisa ser a chave canônica completa retornada pelo gateway:

```text
tenant_id:agent_id:session_id_original
```

Exemplo:

```text
default:financeiro_agent:teste-sse-001
```

### 25.5. Langfuse não mostra traces

Verifique:

```env
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=<public-key>
LANGFUSE_SECRET_KEY=<secret-key>
LANGFUSE_HOST=http://localhost:3005
```

E confira:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/debug/env
```

### 25.6. Banco Autonomous não conecta

Para desenvolvimento, simplifique primeiro:

```env
SESSION_REPOSITORY_PROVIDER=memory
MEMORY_REPOSITORY_PROVIDER=memory
CHECKPOINT_REPOSITORY_PROVIDER=memory
USAGE_REPOSITORY_PROVIDER=memory
```

Depois volte para `autonomous` quando o wallet, DSN e variáveis estiverem corretos.

---

## 26. Modelo mínimo de entrega de um novo agente

Ao finalizar uma implementação, a entrega mínima deve conter:

```text
app/agents/<agent_name>.py
config/agents.yaml
config/routing.yaml
config/tools.yaml
config/mcp_servers.yaml
config/mcp_parameter_mapping.yaml
config/identity.yaml
config/agents/<agent_id>/prompt_policy.yaml
config/agents/<agent_id>/guardrails.yaml
config/agents/<agent_id>/judges.yaml
app/workflows/agent_graph.py
app/state.py, se necessário
.env.example ou documentação de variáveis
README.md com testes curl
```

---

## 27. Exemplo de teste completo

```bash
# 1. Health
curl http://localhost:8000/health

# 2. Agentes
curl http://localhost:8000/agents

# 3. Tools MCP
curl http://localhost:8000/debug/mcp/tools

# 4. Roteamento
curl -X POST http://localhost:8000/debug/route \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Quero consultar meu pagamento",
    "context": {"agent_id": "financeiro_agent", "tenant_id": "default"}
  }'

# 5. Identidade
curl -X POST http://localhost:8000/debug/identity \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "teste-final-001",
    "customer_id": "12345",
    "contract_id": "ABC-999"
  }'

# 6. Mensagem real
curl -X POST http://localhost:8000/gateway/message \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "web",
    "agent_id": "financeiro_agent",
    "tenant_id": "default",
    "payload": {
      "text": "Quero consultar meu pagamento",
      "session_id": "teste-final-001",
      "user_id": "user-001",
      "customer_id": "12345",
      "contract_id": "ABC-999",
      "message_id": "msg-final-001"
    }
  }'

# 7. Histórico
curl http://localhost:8000/sessions/default:financeiro_agent:teste-final-001/messages

# 8. Checkpoint
curl http://localhost:8000/sessions/default:financeiro_agent:teste-final-001/checkpoint
```

---

## 28. Conclusão

O `agent_template_backend` já fornece a espinha dorsal corporativa para novos agentes. A implementação de um agente novo deve se limitar ao domínio: prompts, regras, tools, clients, schemas e decisões específicas.

O padrão correto é:

```text
Framework = motor reutilizável
Agente = customização de negócio
MCP = fronteira padronizada com sistemas externos
Config YAML = comportamento alterável sem mexer no motor
IC/NOC/GRL = rastreabilidade corporativa
```

Seguindo este tutorial, novos agentes podem ser criados com padronização, escalabilidade, rastreabilidade e manutenção mais simples.
