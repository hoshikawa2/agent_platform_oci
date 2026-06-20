# Tutorial — Implementação de um Agente usando `agent_template_backend`

Este tutorial ensina como implementar um novo agente a partir do `agent_template_backend`, usando o framework como motor corporativo de execução.

A ideia central é simples:

```text
Framework = motor reutilizável
Agente = regra de negócio específica
MCP Server = fronteira padronizada com sistemas externos
Config YAML = comportamento alterável sem recompilar código
IC/NOC/GRL = rastreabilidade de negócio, operação e governança
```

![img_1.png](img_1.png)

O objetivo é que cada novo agente implemente apenas sua lógica de domínio — prompts, regras de negócio, ferramentas, schemas e nós específicos — sem recriar motores que já pertencem ao framework.

---

## 1. Visão geral da arquitetura

O template separa o que é genérico do que é específico.

```text
agent_template_backend/
├── app/
│   ├── main.py                    # API FastAPI, gateway, sessão, SSE e entrada do workflow
│   ├── state.py                   # Contrato de estado compartilhado do LangGraph
│   ├── workflows/
│   │   └── agent_graph.py          # Workflow corporativo com router, guardrails, agentes, judges e persistência
│   ├── agents/
│   │   ├── runtime.py              # Recursos comuns para agentes: MCP, RAG, cache, IC, LLM
│   │   ├── billing_agent.py        # Exemplo de agente de faturas
│   │   ├── product_agent.py        # Exemplo de agente de produtos
│   │   ├── orders_agent.py         # Exemplo de agente de pedidos
│   │   └── support_agent.py        # Exemplo de agente de suporte
│   └── examples/                  # Exemplos de IC, NOC, GRL, MCP e observer
├── config/
│   ├── agents.yaml                # Registro dos agentes disponíveis
│   ├── routing.yaml               # Intents, keywords, fallback e decisão de rota
│   ├── tools.yaml                 # Catálogo das ferramentas disponíveis para o backend
│   ├── mcp_servers.yaml           # Endpoints MCP locais
│   ├── mcp_servers.docker.yaml    # Endpoints MCP em Docker Compose
│   ├── mcp_parameter_mapping.yaml # Mapeamento entre chaves canônicas e parâmetros das tools
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

### 1.1. O que pertence ao framework

O framework deve concentrar os motores reutilizáveis:

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

### 1.2. O que pertence ao agente

O agente deve concentrar apenas customizações de domínio:

- Prompts específicos.
- Regras de negócio.
- Schemas próprios.
- Tools específicas.
- Clients de sistemas externos, preferencialmente encapsulados atrás de MCP.
- Mapeamento de parâmetros.
- Nós especializados, se houver.
- ICs de negócio da jornada.

Quando uma regra só faz sentido para um domínio, ela pertence ao agente. Quando uma capacidade deve ser usada por vários agentes, ela pertence ao framework.

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

O `AgentWorkflow`, em `app/workflows/agent_graph.py`, normalmente já contém nós corporativos como:

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

Para criar um novo agente, normalmente você altera:

```text
app/agents/<novo_agente>.py
app/workflows/agent_graph.py
app/state.py, se precisar de campos novos
config/agents.yaml
config/routing.yaml
config/tools.yaml
config/mcp_servers.yaml
config/mcp_parameter_mapping.yaml
config/identity.yaml
config/agents/<agent_id>/prompt_policy.yaml
config/agents/<agent_id>/guardrails.yaml
config/agents/<agent_id>/judges.yaml
.env
```

---

## 3. Pré-requisitos

### 3.1. Requisitos locais

- Python 3.12 ou 3.13.
- `pip` ou `uv`.
- Projeto `agent_framework` disponível no mesmo workspace, caso o template use instalação local.
- Servidores MCP, se o agente usar tools.
- Redis, Oracle Autonomous Database, MongoDB e Langfuse são opcionais conforme configuração.

Estrutura recomendada:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

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

O `.env` define quais motores serão ativados. Ele não é apenas um arquivo de propriedades: ele muda o comportamento do agente em tempo de execução.

Exemplo seguro para desenvolvimento local:

```env
APP_NAME=ai-agent-template
APP_ENV=local
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

LLM_PROVIDER=mock
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2048
LLM_TIMEOUT_SECONDS=120

SESSION_REPOSITORY_PROVIDER=memory
MEMORY_REPOSITORY_PROVIDER=memory
CHECKPOINT_REPOSITORY_PROVIDER=memory
USAGE_REPOSITORY_PROVIDER=memory

ENABLE_REDIS_CACHE=false
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=300

VECTOR_STORE_PROVIDER=memory
GRAPH_STORE_PROVIDER=memory
RAG_TOP_K=5
EMBEDDING_PROVIDER=mock

ENABLE_LANGFUSE=false
LANGFUSE_HOST=http://localhost:3005
ENABLE_OTEL=false
OTEL_SERVICE_NAME=ai-agent-template

ENABLE_ANALYTICS=false
ANALYTICS_PROVIDERS=noop
ENABLE_OCI_STREAMING=false
OCI_STREAM_ENDPOINT=
OCI_STREAM_OCID=
OCI_STREAM_PARTITION_KEY=agent-events

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

ROUTING_CONFIG_PATH=./config/routing.yaml
ROUTING_MODE=router
ENABLE_LLM_ROUTER=false

ENABLE_MCP_TOOLS=true
MCP_SERVERS_CONFIG_PATH=./config/mcp_servers.yaml
TOOLS_CONFIG_PATH=./config/tools.yaml
MCP_PARAMETER_MAPPING_PATH=./config/mcp_parameter_mapping.yaml
MCP_TOOL_TIMEOUT_SECONDS=30

IDENTITY_CONFIG_PATH=./config/identity.yaml
```

### 4.1. Como raciocinar sobre o `.env`

Antes de testar um novo agente, responda:

```text
O LLM será mock ou real?
A memória será local ou banco?
O checkpoint precisa sobreviver a restart?
As tools MCP serão chamadas de verdade ou simuladas?
O roteamento será por regra/intent ou supervisor?
Guardrails, judges e supervisor devem bloquear, revisar ou só observar?
Langfuse/OTEL/Streaming serão usados neste ambiente?
```

Para um primeiro teste, use `LLM_PROVIDER=mock`, persistência em `memory` e MCP mock/local. Depois evolua para LLM real, banco, Langfuse e serviços reais.

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

### 5.1. Antes do código: o que é um agente neste framework?

Um agente é uma classe de domínio que recebe o `state` do LangGraph, interpreta a intenção escolhida pelo roteador ou supervisor, coleta evidências, chama tools/RAG/LLM quando necessário e retorna uma decisão para o workflow continuar.

Ele não deve decidir sozinho tudo que o framework já decide. Por exemplo:

```text
O agente não cria sessão.
O agente não abre SSE.
O agente não compila LangGraph.
O agente não cria checkpoint.
O agente não executa guardrails globais.
O agente não chama sistema externo diretamente quando existe MCP Tool Router.
```

O agente deve responder perguntas como:

```text
Qual problema de negócio estou resolvendo?
Quais dados preciso para responder com segurança?
Quais tools podem fornecer esses dados?
Quais regras de domínio impedem ou autorizam uma ação?
Qual resposta deve ser devolvida ao usuário?
Quais eventos IC preciso emitir para auditoria da jornada?
```

### 5.2. Responsabilidades do arquivo `app/agents/financeiro_agent.py`

Esse arquivo deve conter a lógica específica do agente financeiro. Ele deve:

1. Receber o `state`.
2. Separar `context`, `session`, `business_context` e `tool_arguments`.
3. Emitir IC de início usando `AgentRuntimeMixin`.
4. Coletar contexto de tools MCP, se houver, usando o MCP Tool Router do framework.
5. Coletar contexto RAG, se houver, usando o RAG genérico do framework.
6. Montar um prompt de domínio.
7. Chamar o LLM pelo runtime comum, com cache e telemetria.
8. Montar uma resposta padronizada.
9. Emitir IC de conclusão.
10. Retornar dados para o workflow.


### 5.2.1. Entendendo `state`, `context`, `session`, `business_context` e `tool_arguments`

Antes de copiar o código do agente, o desenvolvedor precisa entender **de onde vêm os dados**. Em um agente corporativo, o erro mais comum é pegar qualquer campo diretamente do `state` sem saber se aquele dado veio do canal, do gateway, do identity resolver, do roteador ou do usuário.

O `state` é o envelope completo da execução do LangGraph. Dentro dele normalmente existe um `context`, que é o contexto normalizado pelo framework.

Dentro de `context`, se o projeto usa **Agent Gateway / Global Supervisor**, é comum existir também um bloco `session`:

```python
ctx = state.get("context") or {}
session = ctx.get("session") or {}
```

O papel de cada bloco é diferente:

```text
state
  Estado completo do workflow atual. Carrega texto, intent, route, resposta parcial,
  resultados MCP, dados de guardrail, checkpoint e outros campos técnicos.

context
  Contexto normalizado da mensagem atual. Normalmente vem do Channel Gateway,
  Identity Resolver e Agent Gateway.

session
  Dados da sessão e do canal. Ajuda a saber quem está conversando, por qual canal,
  em qual tenant, qual sessão global está ativa e qual backend/agente está atendendo.

business_context
  Dados de negócio já normalizados. Exemplo: customer_key, contract_key,
  interaction_key, session_key, protocol_id, invoice_id, order_id.

tool_arguments
  Parâmetros explícitos já preparados para tools/MCP. Quando existe, deve ter
  prioridade sobre inferências feitas pelo agente.
```

A ordem de confiança recomendada é:

```text
1. tool_arguments explícitos
2. business_context resolvido pelo framework
3. context normalizado
4. session e session.metadata, quando vierem do Agent Gateway
5. state direto
6. texto original do usuário, apenas para extração complementar
```

Essa ordem evita dois problemas:

```text
Problema 1: ignorar dados já resolvidos pelo Gateway/Identity Resolver.
Problema 2: sobrescrever um parâmetro canônico com um valor bruto e menos confiável.
```

Exemplo prático: se o `business_context.customer_key` já foi resolvido pelo framework, o agente não deve preferir um `user_id` genérico da sessão apenas porque ele existe. O `user_id` identifica o usuário no canal; o `customer_key` identifica o cliente no negócio.

Mesmo que um agente simples não use `session` diretamente, existe uma diferença entre **sessão técnica** e **contexto de negócio**.

### 5.2.2. Entendendo a classe `AgentRuntimeMixin` de `runtime.py`

Antes de escrever um agente novo, o desenvolvedor precisa entender por que quase todos os exemplos herdam de:

```python
from app.agents.runtime import AgentRuntimeMixin
```

O `AgentRuntimeMixin` é uma camada de conveniência operacional para o agente. Ele não é o agente, não é o workflow e não contém regra de negócio. Ele existe para evitar que cada agente tenha que reimplementar, de forma diferente, as mesmas capacidades técnicas.

Em termos simples:

```text
AgentRuntimeMixin = caixa de ferramentas padronizada do agente
FinanceiroAgent  = regra de negócio que usa essa caixa de ferramentas
AgentWorkflow    = motor LangGraph que chama o agente
Framework        = infraestrutura corporativa completa
```

Sem o `AgentRuntimeMixin`, cada desenvolvedor tenderia a escrever código próprio para:

```text
emitir IC/NOC/GRL
chamar MCP Tool Router
chamar RAG
montar cache de LLM
chamar LLM
montar chave de cache
tratar ausência de observer, cache, RAG ou tools
```

Isso geraria agentes inconsistentes. Um agente emitiria IC de um jeito, outro chamaria MCP diretamente, outro ignoraria cache, outro quebraria quando o observer estivesse desabilitado. O mixin evita esse problema.

#### 5.2.2.1. O que o `AgentRuntimeMixin` oferece

No template, o `AgentRuntimeMixin` concentra métodos utilitários como:

| Método | Para que serve | Quando o agente usa |
|---|---|---|
| `_emit_ic()` | Emite evento de negócio/auditoria | início, fim, decisão de negócio, contexto coletado |
| `_emit_noc()` | Emite evento operacional | erro técnico, timeout, fallback, indisponibilidade |
| `_emit_grl()` | Emite evento de governança customizado | regra de domínio bloqueou ou sanitizou algo |
| `_retrieve_rag_context()` | Consulta o RAG genérico do framework | agente precisa de contexto documental |
| `_collect_mcp_context()` | Chama as tools MCP declaradas no `state.mcp_tools` | agente precisa consultar sistemas externos |
| `_cache_get()` | Lê cache genérico | uso avançado, normalmente indireto |
| `_cache_set()` | Grava cache genérico | uso avançado, normalmente indireto |
| `_llm_cache_key()` | Monta chave estável de cache do LLM | normalmente usado internamente |
| `_invoke_llm_cached()` | Chama o LLM com cache e telemetria | agente precisa gerar resposta com LLM |

O desenvolvedor deve pensar assim:

```text
Eu escrevo a regra de negócio no run().
Quando precisar de infraestrutura, chamo um helper do AgentRuntimeMixin.
```

#### 5.2.2.2. O que o `AgentRuntimeMixin` não deve fazer

O mixin não deve conter regra de negócio específica, por exemplo:

```text
calcular contestação de fatura
consultar protocolo ANATEL diretamente
abrir SR Siebel diretamente
classificar cancelamento TIM
calcular valor de boleto financeiro
validar produto de varejo específico
```

Essas regras pertencem ao agente ou ao MCP Server do domínio.

A fronteira correta é:

```text
AgentRuntimeMixin
  sabe chamar MCP, RAG, cache, LLM e observer

Agente específico
  sabe quais evidências precisa, quais regras aplicar e como responder

MCP Server
  sabe falar com sistema real, mock, banco, REST, SOAP ou serviço legado
```

#### 5.2.2.3. Como o mixin recebe seus recursos

O `AgentRuntimeMixin` não cria `llm`, `tool_router`, `rag_service`, `cache` ou `observer`. Ele espera que o workflow injete esses objetos no construtor do agente.

Por isso, no agente aparece este padrão:

```python
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
```

Isso significa:

```text
llm          = motor de geração configurado pelo framework
telemetry    = spans/eventos técnicos
tool_router  = roteador MCP padronizado
rag_service  = busca documental/grafo/vetor
cache        = cache Redis/memory/etc.
settings     = configurações carregadas do .env/YAML
observer     = emissor IC/NOC/GRL
```

O agente recebe esses objetos prontos. Ele não deve criar uma nova instância por conta própria dentro do `run()`.

#### 5.2.2.4. Como `_emit_ic()`, `_emit_noc()` e `_emit_grl()` ajudam

Um agente precisa ser auditável, mas não deveria quebrar se a observabilidade estiver desligada.

Por isso, os métodos de emissão do mixin são **fail-open**: se não houver `observer`, ou se ocorrer erro ao emitir evento, a jornada de negócio continua.

Exemplo de IC:

```python
await self._emit_ic(
    "IC.FINANCEIRO_AGENT_STARTED",
    state,
    {"business_component": "financeiro"},
    component="agent.financeiro.start",
)
```

O desenvolvedor não precisa montar manualmente todos os metadados básicos. O mixin já tenta incluir informações como:

```text
session_id
conversation_key
tenant_id
agent_id
route
intent
message_id
channel_id
```

A regra prática é:

```text
Use _emit_ic() para marco de negócio.
Use _emit_noc() para problema operacional.
Use _emit_grl() para governança específica do domínio.
```

#### 5.2.2.5. Como `_collect_mcp_context()` funciona

O método `_collect_mcp_context(state)` lê a lista de tools já escolhidas pelo roteador:

```python
 tools = state.get("mcp_tools") or []
```

Depois chama o `tool_router` do framework para cada tool. O agente não precisa saber se a tool usa HTTP, Docker, mock ou serviço real.

Fluxo conceitual:

```text
routing.yaml escolhe intent
  ↓
intent define mcp_tools
  ↓
state.mcp_tools recebe a lista de tools
  ↓
AgentRuntimeMixin._collect_mcp_context()
  ↓
MCP Tool Router
  ↓
MCP Server
  ↓
resultado normalizado volta ao agente
```

Exemplo no agente:

```python
tool_context = await self._collect_mcp_context(state)
```

O desenvolvedor deve usar esse método quando basta chamar as tools definidas pela intent.

Se o agente precisar escolher argumentos especiais por tool, pular tools perigosas, exigir confirmação ou montar parâmetros adicionais, ele pode implementar um método próprio no agente e chamar o router de forma mais controlada, como no exemplo do `BackofficeAgent`.

#### 5.2.2.6. Como `_retrieve_rag_context()` funciona

O método `_retrieve_rag_context(state)` consulta o RAG genérico configurado no framework.

Ele usa como texto base:

```text
state.sanitized_input ou state.user_text
```

E tenta definir um namespace de busca a partir de:

```text
agent_profile.rag_namespace
agent_id
route
default
```

Também pode usar informações do `business_context`, como `customer_key` ou `contract_key`, para enriquecer busca em grafo ou contexto relacionado.

Exemplo:

```python
rag_context, rag_metadata = await self._retrieve_rag_context(state)
```

O agente usa `rag_context` no prompt e pode retornar `rag_metadata` para auditoria/debug.

Regra prática:

```text
Use RAG quando a resposta depende de documento, política, base de conhecimento ou conteúdo não codificado.
Não use RAG para substituir uma consulta operacional que deve ser feita por tool MCP.
```

#### 5.2.2.7. Como `_invoke_llm_cached()` funciona

O método `_invoke_llm_cached()` chama o LLM passando mensagens no formato chat:

```python
answer = await self._invoke_llm_cached(state, "FinanceiroAgent", messages)
```

Antes de chamar o LLM, ele monta uma chave de cache considerando elementos como:

```text
nome do agente
tenant_id
agent_id
intent
customer_key
contract_key
interaction_key
texto do usuário
conteúdo do prompt
```

Se já existir resposta no cache, o método retorna o valor cacheado. Se não existir, chama o LLM, grava no cache e retorna a resposta.

Isso evita que cada agente implemente cache de forma diferente.

O desenvolvedor deve entender que o cache é útil para prompts determinísticos ou consultas repetidas, mas deve ser usado com cuidado em ações sensíveis. O agente não deve confirmar operação externa apenas porque uma resposta de LLM veio de cache. Confirmações operacionais devem depender de retorno real da tool.

#### 5.2.2.8. Quando usar `_collect_mcp_context()` e quando criar lógica própria

Use `_collect_mcp_context()` quando:

```text
a intent já definiu as tools corretas
os parâmetros canônicos já estão no business_context
a execução pode chamar todas as tools da lista
nenhuma tool representa ação sensível
```

Crie lógica própria no agente quando:

```text
uma tool só pode ser chamada após confirmação explícita
uma tool exige argumentos adicionais derivados da mensagem
uma tool deve ser pulada se faltar campo obrigatório
uma tool de registro/alteração não pode rodar automaticamente
uma sequência de tools depende do resultado anterior
```

Exemplo de regra segura:

```python
if tool.startswith("registrar_") and not action_text:
    return {"ok": False, "skipped": True, "reason": "ação sem confirmação explícita"}
```

Isso é regra de domínio e deve ficar no agente, não no mixin.

#### 5.2.2.9. Como o dev deve ler o `run()` de um agente que herda o mixin

Ao abrir um agente, o desenvolvedor deve procurar esta estrutura mental:

```text
1. O agente emite IC de início?
2. Ele lê context/session/business_context de forma organizada?
3. Ele valida dados obrigatórios do domínio?
4. Ele chama MCP usando o mixin ou lógica própria controlada?
5. Ele chama RAG quando precisa de conhecimento documental?
6. Ele monta prompt com evidências, e não com chute?
7. Ele chama LLM via _invoke_llm_cached()?
8. Ele emite IC/NOC/GRL relevantes?
9. Ele retorna answer, next_state, mcp_results e metadados úteis?
```

Se o agente faz isso, ele está usando o framework corretamente.

#### 5.2.2.10. Exemplo mínimo de uso correto do mixin

```python
async def run(self, state):
    await self._emit_ic("IC.FINANCEIRO_STARTED", state, component="agent.financeiro.start")

    ctx = state.get("context") or {}
    business_context = ctx.get("business_context") or state.get("business_context") or {}

    if not business_context.get("customer_key"):
        return {
            "answer": "Informe o identificador do cliente para continuar.",
            "next_state": "WAITING_CUSTOMER_KEY",
            "mcp_results": [],
        }

    mcp_results = await self._collect_mcp_context(state)
    rag_context, rag_metadata = await self._retrieve_rag_context(state)

    messages = [
        {"role": "system", "content": "Você é um agente financeiro corporativo."},
        {"role": "user", "content": f"Evidências MCP: {mcp_results}\nContexto RAG: {rag_context}"},
    ]

    answer = await self._invoke_llm_cached(state, "FinanceiroAgent", messages)

    await self._emit_ic("IC.FINANCEIRO_COMPLETED", state, {"mcp_count": len(mcp_results)}, component="agent.financeiro.completed")

    return {
        "answer": answer,
        "next_state": "FINANCEIRO_ACTIVE",
        "mcp_results": mcp_results,
        "rag_metadata": rag_metadata,
    }
```

Esse exemplo mostra a intenção do mixin: o desenvolvedor escreve o raciocínio do agente, mas delega infraestrutura para métodos padronizados.

#### 5.2.2.11. Erros comuns ao usar o `AgentRuntimeMixin`

```text
Herdar de AgentRuntimeMixin, mas chamar REST diretamente dentro do agente.
Criar outro cache manual em vez de usar _invoke_llm_cached().
Emitir eventos diretamente em formatos diferentes do observer.
Colocar regra de domínio dentro do runtime.py.
Usar _collect_mcp_context() para tool de ação sem confirmação.
Ignorar business_context e pegar parâmetros soltos do payload.
Tratar session_id global e backend_session_id como se fossem a mesma coisa.
Sobrescrever métodos internos do mixin sem necessidade.
```

A regra mais importante é:

```text
O mixin padroniza capacidades técnicas.
O agente decide como aplicar essas capacidades ao domínio.
```


### 5.2.3. Entendendo `messages`: arquitetura conversacional do agente

Depois de entender `state`, `context`, `session`, `business_context`, `tool_arguments` e `AgentRuntimeMixin`, falta entender uma peça central: `messages`.

Em um agente, `messages` não é apenas uma lista de textos. Ele é o **contrato conversacional** que será enviado ao LLM naquela chamada. É nesse contrato que o agente organiza instruções, pergunta do usuário, evidências, contexto RAG, resultados MCP, memória resumida e formato esperado da resposta.

Um exemplo mínimo é:

```python
messages = [
    {
        "role": "system",
        "content": "Você é um agente financeiro. Não invente dados.",
    },
    {
        "role": "user",
        "content": "Quero consultar meu pagamento.",
    },
]
```

Esse formato é comum em frameworks e provedores modernos de IA conversacional. Ele aparece, com pequenas variações, em OpenAI Chat Completions/Responses API, OCI Generative AI OpenAI-compatible, LangChain `ChatModel`, LangGraph, Semantic Kernel, LlamaIndex e em arquiteturas com tool calling e MCP.

A ideia é simples:

```text
O agente monta uma conversa canônica.
O AgentRuntimeMixin chama o provider LLM padronizado.
O provider adapta essa conversa para o backend real.
```

Isso permite que o agente continue escrevendo `messages` de forma previsível, mesmo que por baixo o projeto use OCI Generative AI, OpenAI-compatible endpoint, LangChain, Llama local, mock ou outro provider.

#### 5.2.3.1. Papéis principais de uma mensagem

Cada item de `messages` possui pelo menos um `role` e um `content`.

| Role | Para que serve |
|---|---|
| `system` | Define identidade, limites, políticas, regras e comportamento do agente. |
| `user` | Representa a solicitação atual do usuário ou uma instrução contextualizada pelo framework. |
| `assistant` | Representa respostas anteriores do modelo, quando o histórico é incluído explicitamente. |
| `tool` | Representa resultado de ferramenta em fluxos com tool calling estruturado. |
| `developer` | Em alguns provedores, representa instruções intermediárias do desenvolvedor ou da aplicação. |

No template, o padrão mais simples usa principalmente:

```text
system → quem é o agente, o que ele pode fazer e o que ele não pode fazer
user   → mensagem atual + evidências + contexto de negócio + MCP + RAG
```

Esse padrão é intencionalmente simples para manter compatibilidade com vários runtimes.

#### 5.2.3.2. O que deve ir no `system`

O `system` deve conter regras estáveis e de maior prioridade. Ele responde:

```text
Quem é este agente?
Qual domínio ele atende?
Quais limites ele deve respeitar?
O que ele nunca deve inventar?
Quando ele deve pedir mais dados?
Quando ele deve recusar uma ação?
Qual tom e formato de resposta deve usar?
```

Exemplo:

```python
system_content = apply_agent_profile_prompt(
    state,
    """
    Você é um agente financeiro corporativo.
    Use somente dados fornecidos por MCP, RAG ou business_context.
    Não confirme pagamento, baixa, acordo ou contestação sem evidência de tool.
    Se faltar identificador obrigatório, peça apenas esse dado.
    Responda de forma curta, operacional e auditável.
    """.strip(),
)
```

Regras críticas devem ficar no `system`, não escondidas no meio do `user`.

#### 5.2.3.3. O que deve ir no `user`

O `user` deve trazer o pedido atual e o contexto necessário para responder. No agente corporativo, ele normalmente contém:

```text
mensagem atual do usuário
intent escolhida pelo roteador
route/agente ativo
business_context normalizado
resultados MCP
contexto RAG
metadados relevantes de sessão
instrução de formato para a resposta
```

Exemplo:

```python
messages = [
    {
        "role": "system",
        "content": system_content,
    },
    {
        "role": "user",
        "content": (
            "Mensagem do usuário:\n"
            f"{user_text}\n\n"
            "Intent e rota escolhidas pelo framework:\n"
            f"intent={state.get('intent')} route={state.get('route')}\n\n"
            "Contexto de negócio normalizado:\n"
            f"customer_key={business_context.get('customer_key')}\n"
            f"contract_key={business_context.get('contract_key')}\n"
            f"interaction_key={business_context.get('interaction_key')}\n\n"
            "Resultados MCP:\n"
            f"{tool_context}\n\n"
            "Contexto RAG:\n"
            f"{rag_context or '[sem contexto RAG]'}\n\n"
            "Instrução de resposta:\n"
            "Responda somente com base nas evidências acima. "
            "Se uma evidência obrigatória estiver ausente, diga que não foi encontrada."
        ),
    },
]
```

Observe que o exemplo não joga o `state` inteiro no prompt. Ele seleciona os campos relevantes.

#### 5.2.3.4. Relação entre `messages`, memória e histórico

`messages` não é a memória persistente do agente.

```text
Memória persistente
  Fica no repositório/memória do framework.
  Pode sobreviver a várias interações.
  Pode ser resumida, compactada ou consultada.

messages
  É o payload enviado ao LLM em uma chamada específica.
  Pode incluir um resumo de memória.
  Pode incluir parte do histórico.
  Não deve virar um dump completo da conversa.
```

Se o framework já carregou histórico ou resumo de conversa, o agente deve usar apenas o trecho necessário. Duplicar histórico manualmente aumenta custo, latência e risco de inconsistência.

#### 5.2.3.5. Relação entre `messages`, MCP e RAG

MCP e RAG produzem evidências. O LLM usa essas evidências para redigir a resposta.

```text
MCP Tool Router
  consulta sistemas, mocks, serviços ou ações externas
  retorna dados estruturados

RAG
  busca contexto documental
  retorna trechos relevantes e metadados

messages
  organizam essas evidências em uma conversa para o LLM
```

Um bom agente deixa claro para o LLM o que é evidência e o que é instrução.

Evite misturar tudo em um texto sem estrutura. Prefira blocos:

```text
Instruções:
- Não invente dados.

Mensagem do usuário:
...

Evidências MCP:
...

Contexto RAG:
...

Formato esperado:
...
```

Essa organização melhora a rastreabilidade e reduz alucinação.

#### 5.2.3.6. Compatibilidade com frameworks de mercado

O padrão de `messages` é compatível com a maior parte do ecossistema de IA conversacional, mas existem diferenças entre provedores.

| Framework/provedor | Compatibilidade conceitual | Atenção |
|---|---|---|
| OpenAI Chat/Responses | Alta | Roles, tool calls e formatos multimodais podem variar por API. |
| OCI Generative AI OpenAI-compatible | Alta | Normalmente aceita formato semelhante ao OpenAI-compatible. |
| LangChain `ChatModel` | Alta | Pode converter dicts para `SystemMessage`, `HumanMessage`, `AIMessage`. |
| LangGraph | Alta | O state pode carregar `messages` ou o agente pode montar messages por chamada. |
| Semantic Kernel | Alta | Usa conceitos equivalentes de chat history e roles. |
| LlamaIndex | Alta | Pode adaptar para chat engine ou completion engine. |
| Anthropic Messages API | Média/Alta | Pode exigir adaptações de system prompt e roles. |
| Modelos locais | Variável | Alguns esperam chat template específico. |

Por isso, o agente não deve chamar diretamente SDKs específicos. Ele monta `messages` e delega a chamada para:

```python
answer = await self._invoke_llm_cached(state, "FinanceiroAgent", messages)
```

Assim, a adaptação para o provider fica centralizada no runtime/framework.

#### 5.2.3.7. Pitfalls comuns ao montar `messages`

**Pitfall 1 — Enviar o `state` inteiro ao LLM**

Ruim:

```python
{"role": "user", "content": f"State completo: {state}"}
```

Melhor:

```python
{"role": "user", "content": f"customer_key={business_context.get('customer_key')}"}
```

O `state` pode conter dados técnicos, campos sensíveis, histórico, checkpoint e informações desnecessárias.

**Pitfall 2 — Mandar objetos enormes sem curadoria**

Ruim:

```python
f"Resultados completos: {mcp_results}"
```

Melhor:

```python
resumo_tools = [
    {
        "tool": r.get("tool_name") or r.get("tool"),
        "ok": r.get("ok"),
        "status": r.get("status"),
        "evidence": r.get("evidence") or r.get("summary"),
    }
    for r in mcp_results
]
```

Depois envie apenas o resumo necessário.

**Pitfall 3 — Passar dados sensíveis sem necessidade**

Ruim:

```python
f"CPF completo: {cpf}"
```

Melhor:

```python
f"Cliente identificado: {'sim' if customer_key else 'não'}"
```

Quando precisar enviar identificador, prefira chave canônica, hash ou valor mascarado, conforme política do projeto.

**Pitfall 4 — Deixar o LLM inventar quando a tool falhou**

Ruim:

```text
Responda sobre o pagamento do cliente.
```

Melhor:

```text
A tool consultar_pagamentos_financeiro retornou erro ou ausência de dados.
Não confirme pagamento. Informe que a evidência não foi encontrada.
```

**Pitfall 5 — Confundir instrução com evidência**

Ruim:

```text
O cliente pagou e você deve responder que está tudo certo.
```

Melhor:

```text
Evidência MCP:
- consultar_pagamentos_financeiro: status=COMPENSADO

Instrução:
- Explique o status de forma objetiva.
```

**Pitfall 6 — Colocar regra crítica só no `user`**

Regra de comportamento permanente deve ir no `system`. O `user` deve carregar o pedido e o contexto daquela interação.

**Pitfall 7 — Duplicar histórico**

Se o framework já incluiu resumo de memória, não reenvie toda a conversa manualmente.

**Pitfall 8 — Não pedir formato de resposta**

Em contexto corporativo, peça resposta curta, operacional, rastreável e baseada em evidência.

#### 5.2.3.8. Modelo recomendado de `messages` para agentes corporativos

Use este padrão como referência:

```python
system_content = apply_agent_profile_prompt(
    state,
    """
    Você é um agente corporativo especializado no domínio financeiro.
    Use somente evidências vindas de business_context, MCP e RAG.
    Não invente protocolo, cliente, contrato, status, pagamento ou ação operacional.
    Se faltar dado obrigatório, peça apenas esse dado.
    Responda de forma curta, operacional e auditável.
    """.strip(),
)

messages = [
    {
        "role": "system",
        "content": system_content,
    },
    {
        "role": "user",
        "content": (
            "Mensagem do usuário:\n"
            f"{user_text}\n\n"
            "Contexto de sessão resumido:\n"
            f"channel={session.get('channel')} tenant_id={session.get('tenant_id')}\n"
            f"global_session_id={session.get('global_session_id')}\n\n"
            "Contexto de negócio:\n"
            f"customer_key={business_context.get('customer_key')}\n"
            f"contract_key={business_context.get('contract_key')}\n"
            f"interaction_key={business_context.get('interaction_key')}\n\n"
            "Intent e rota:\n"
            f"intent={state.get('intent')} route={state.get('route')}\n\n"
            "Evidências MCP:\n"
            f"{mcp_evidence}\n\n"
            "Contexto RAG:\n"
            f"{rag_context or '[sem contexto RAG]'}\n\n"
            "Formato esperado:\n"
            "1. Resposta direta ao usuário.\n"
            "2. Não cite detalhes internos de arquitetura.\n"
            "3. Se faltou evidência, diga claramente o que faltou."
        ),
    },
]
```

Esse padrão ajuda o desenvolvedor a separar:

```text
Regras permanentes        → system
Pedido e contexto atual   → user
Evidências de tools       → bloco MCP
Conhecimento documental   → bloco RAG
Sessão/canal              → contexto resumido
Formato de saída          → instrução final
```

#### 5.2.3.9. Como revisar `messages` durante desenvolvimento

Durante o desenvolvimento, antes de culpar o LLM, revise o payload enviado para ele.

Perguntas úteis:

```text
O system prompt contém as regras mais importantes?
O user prompt contém a pergunta real do usuário?
O business_context certo foi incluído?
Os resultados MCP aparecem como evidência, e não como instrução inventada?
O RAG trouxe contexto útil ou só ruído?
Há dados sensíveis desnecessários?
O prompt está grande demais?
O formato de resposta esperado está claro?
```

Uma boa prática é emitir um IC de debug em ambiente não produtivo ou logar uma versão sanitizada do prompt, nunca o prompt bruto com dados sensíveis.


### 5.2.4. Recursos avançados agora padronizados pelo framework

Nos primeiros exemplos deste tutorial, o agente usa diretamente métodos simples como `_collect_mcp_context()` e `_invoke_llm_cached()`. Isso é suficiente para agentes simples. Porém, em agentes reais migrados para o framework, como um Backoffice/ANATEL, aparecem necessidades adicionais:

```text
normalizar tools por intent;
ler context/session/business_context/tool_arguments sempre da mesma forma;
montar argumentos MCP com aliases;
bloquear tools de ação quando falta payload obrigatório;
executar tools uma a uma com eventos de observabilidade;
montar messages sem despejar o state inteiro no prompt;
gerar fallback controlado quando o LLM falha.
```

Essas necessidades não são exclusivas do Backoffice. Por isso, a partir desta versão, elas passam a ser tratadas como **capacidades reutilizáveis do framework**, e não como código que cada agente deve copiar.

#### 5.2.4.1. `RuntimeContext`: leitura canônica do state

O framework passa a oferecer um objeto conceitual chamado `RuntimeContext`, obtido pelo agente com:

```python
runtime = self.get_runtime_context(state)
```

Esse objeto organiza:

```text
runtime.state              → state completo do LangGraph
runtime.context            → context normalizado
runtime.session            → dados de sessão/canal vindos do Gateway
runtime.session_metadata   → metadata da sessão
runtime.business_context   → identidade de negócio canônica
runtime.tool_arguments     → parâmetros explícitos para tools
runtime.sanitized_input    → texto sanitizado pelos guardrails
runtime.original_text      → texto original, quando necessário para extração controlada
```

O desenvolvedor não precisa ficar repetindo:

```python
ctx = state.get("context") or {}
session = ctx.get("session") or {}
business_context = ctx.get("business_context") or state.get("business_context") or {}
```

Ele pode usar:

```python
runtime = self.get_runtime_context(state)
customer_key = runtime.pick("customer_key", "cpf", "cnpj", "msisdn")
```

A ordem de confiança continua padronizada:

```text
1. tool_arguments
2. business_context
3. context
4. session
5. session.metadata
6. state
```

#### 5.2.4.2. `normalize_tools_by_intent()`: fallback de tools sem tirar poder do router

Em um agente ideal, o `EnterpriseRouter` escolhe a intent e injeta `mcp_tools` no `state`. Mas, em testes, chamadas diretas ou migrações, o agente pode ser executado sem essa injeção.

Para isso, o framework oferece:

```python
normalized_state = self.normalize_tools_by_intent(
    state,
    default_tools_by_intent=DEFAULT_TOOLS_BY_INTENT,
    default_intent="financeiro_pagamentos",
    route=self.name,
)
```

A regra é:

```text
Se state['mcp_tools'] veio do router, use essas tools.
Se não veio, use o fallback declarado pelo agente.
Remova duplicidades.
Preserve ordem estável.
Defina intent, route e active_agent quando estiverem ausentes.
```

Isso evita que cada agente implemente seu próprio `_normalize_state_tools()`.

#### 5.2.4.3. `build_tool_arguments()`: argumentos MCP canônicos

O agente pode montar argumentos MCP sem conhecer todos os detalhes do mapper:

```python
args = self.build_tool_arguments(
    state,
    tool_name="consultar_titulo_financeiro",
    intent=state.get("intent"),
    aliases={
        "customer_key": ["customer_id", "cpf", "cnpj"],
        "contract_key": ["contract_id", "invoice_id"],
    },
)
```

Esse método monta argumentos como:

```text
query
operator_instructions
customer_key
contract_key
interaction_key
session_key
parâmetros explícitos de tool_arguments
aliases configurados pelo domínio
```

Depois disso, o `MCPToolRouter` ainda aplica o `mcp_parameter_mapping.yaml`. Ou seja:

```text
build_tool_arguments() monta o contrato canônico.
mcp_parameter_mapping.yaml traduz para o nome esperado por cada MCP Server.
```

#### 5.2.4.4. Política de execução de tools sensíveis

Nem toda tool é apenas consulta. Algumas tools executam ações, como registrar parecer, abrir solicitação, cancelar serviço ou criar protocolo.

Essas tools devem ser declaradas com política em `config/tools.yaml`:

```yaml
tools:
  registrar_acao_backoffice:
    description: Registra ação operacional no backoffice.
    mcp_server: backoffice
    enabled: true
    tool_type: action
    requires: [protocol_id, action_text, operator_session]
    confirmation_required: false
    args_schema:
      protocol_id: string
      action_text: string
      operator_session: string
```

Com isso, o framework consegue bloquear a chamada antes de chegar ao MCP quando falta campo obrigatório:

```text
Tool registrar_acao_backoffice escolhida.
Framework monta argumentos.
Framework verifica requires.
Se action_text estiver ausente, retorna skipped=true.
Agente emite IC/NOC de domínio, se necessário.
```

Isso evita que cada agente escreva manualmente:

```python
if tool.startswith("registrar_") and not arguments.get("action_text"):
    ...
```

#### 5.2.4.5. `execute_tools_for_intent()`: execução padronizada das tools

O agente pode executar tools selecionadas pela intent com:

```python
mcp_results = await self.execute_tools_for_intent(
    state,
    tools=state.get("mcp_tools") or [],
    aliases=TOOL_ALIASES,
)
```

Esse método cuida de:

```text
montar argumentos;
aplicar política de execução;
chamar _call_mcp_tool();
normalizar resultado;
emitir IC.MCP_TOOL_CALLED;
emitir IC.TOOL_CALLED;
emitir NOC.MCP_TOOL_FAILED quando houver falha;
retornar skipped=true quando uma política bloquear a execução.
```

O agente ainda pode emitir ICs específicos de negócio depois disso. Exemplo: `AGA.010` para Speech Analytics, `AGA.011` para Cliente/IMDB, `AGA.020` para TAIS/templates.

#### 5.2.4.6. `build_messages()`: messages padronizado

Para evitar que cada agente monte prompts de forma diferente, o framework oferece:

```python
messages = self.build_messages(
    state,
    system_prompt=system_prompt,
    mcp_results=mcp_results,
    rag_context=rag_context,
    rag_metadata=rag_metadata,
)
```

Esse builder separa:

```text
system prompt;
mensagem do usuário;
intent e route;
business_context;
resultados MCP;
contexto RAG;
metadados RAG;
seções extras.
```

O objetivo é reduzir estes erros:

```text
enviar state inteiro para o LLM;
misturar regra permanente com evidência;
incluir dados sensíveis sem necessidade;
esquecer de informar que uma tool falhou;
duplicar histórico que o framework já carrega.
```

#### 5.2.4.7. Quando customizar e quando usar o framework

Use o framework para:

```text
ler contexto;
normalizar tools;
montar argumentos MCP;
aplicar política de execução;
chamar MCP;
montar messages;
chamar LLM com cache;
emitir eventos técnicos genéricos.
```

Use o agente para:

```text
definir regras de negócio;
definir aliases específicos do domínio;
definir prompts do domínio;
definir ICs específicos da jornada;
definir estados conversacionais como WAITING_*;
tratar compatibilidade de migração;
decidir fallback textual específico do domínio.
```

Essa separação permite que um agente real tenha customizações fortes sem virar um motor paralelo ao framework.


### 5.3. Criar o arquivo do agente

Crie:

```text
app/agents/financeiro_agent.py
```

Código-base comentado:

```python
from app.agents.prompting import apply_agent_profile_prompt
from app.agents.runtime import AgentRuntimeMixin


class FinanceiroAgent(AgentRuntimeMixin):
    # Este nome precisa bater com o nome usado no workflow e nas configurações.
    name = "financeiro_agent"

    def __init__(self, llm, telemetry=None, tool_router=None, rag_service=None, cache=None, settings=None, observer=None):
        # Estes objetos são injetados pelo workflow/framework.
        # O agente usa, mas não cria esses motores.
        self.llm = llm
        self.telemetry = telemetry
        self.tool_router = tool_router
        self.rag_service = rag_service
        self.cache = cache
        self.settings = settings
        self.observer = observer

    async def run(self, state):
        # 1. Marca o início da jornada de negócio deste agente.
        await self._emit_ic(
            "IC.FINANCEIRO_AGENT_STARTED",
            state,
            {"business_component": "financeiro"},
            component="agent.financeiro.start",
        )

        # 2. Separa os blocos do contrato do framework.
        # O agente lê esses blocos, mas quem cria/normaliza é o framework.
        ctx = state.get("context") or {}
        session = ctx.get("session") or {}
        session_metadata = session.get("metadata") or {}
        business_context = ctx.get("business_context") or state.get("business_context") or {}
        tool_arguments = ctx.get("tool_arguments") or state.get("tool_arguments") or {}

        # 3. Interpreta a mensagem atual usando o texto já sanitizado pelos guardrails,
        # mas preserva o texto original apenas quando precisar extrair identificadores.
        user_text = state.get("sanitized_input") or state.get("user_text") or ""
        original_text = (
            ctx.get("message")
            or ctx.get("text")
            or ctx.get("query")
            or session.get("last_user_message")
            or state.get("user_text")
            or user_text
        )

        # 4. Chama tools MCP selecionadas pelo roteamento, quando configuradas.
        # O agente não precisa saber se a tool usa REST, SOAP, DB ou mock.
        tool_context = await self._collect_tool_context(state)

        if tool_context:
            await self._emit_ic(
                "IC.FINANCEIRO_MCP_CONTEXT_COLLECTED",
                state,
                {"tool_result_count": len(tool_context)},
                component="agent.financeiro.mcp",
            )

        # 5. Recupera contexto documental, se o RAG estiver habilitado.
        rag_context, rag_metadata = await self._retrieve_rag_context(state)

        # 6. Monta a mensagem para o LLM.
        # O system prompt define comportamento e limites do agente.
        # O user prompt leva dados, evidências e contexto.
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

        # 7. Chama o LLM usando o runtime comum, com cache e telemetria.
        answer = await self._invoke_llm_cached(state, "FinanceiroAgent", messages)

        # 8. Retorna no contrato esperado pelo workflow.
        result = {
            "answer": f"[FinanceiroAgent] {answer}",
            "next_state": "FINANCEIRO_ACTIVE",
            "mcp_results": tool_context,
            "rag": rag_metadata,
        }

        # 9. Marca o fim da jornada de negócio.
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
        # Este método delega para o MCP Tool Router do framework.
        # As tools chamadas dependem da intent definida em routing.yaml.
        return await self._collect_mcp_context(state)
```

### 5.3.1. Como adaptar esse exemplo para um agente real

No exemplo acima, `session`, `business_context` e `tool_arguments` aparecem no prompt para fins didáticos. Em produção, o desenvolvedor deve evitar jogar objetos enormes diretamente no prompt. O ideal é selecionar apenas os campos necessários.

Exemplo de raciocínio para um agente financeiro:

```text
session.channel       → útil para ajustar linguagem ou entender origem da conversa.
session.tenant_id     → útil para isolamento multi-tenant.
business_context.customer_key → útil para consultar cliente/título/pagamento.
business_context.contract_key → útil para consultar contrato, fatura ou pedido.
business_context.interaction_key → útil para rastrear protocolo/chamado/interação.
tool_arguments        → útil quando o Gateway ou Identity Resolver já preparou parâmetros exatos.
```

Uma função utilitária comum dentro do agente é um `pick()` com ordem de precedência explícita:

```python
def pick(name: str, *, tool_arguments, business_context, ctx, session, session_metadata, state):
    if name in tool_arguments:
        return tool_arguments.get(name)
    if isinstance(business_context, dict) and name in business_context:
        return business_context.get(name)
    if name in ctx:
        return ctx.get(name)
    if name in session:
        return session.get(name)
    if name in session_metadata:
        return session_metadata.get(name)
    return state.get(name)
```

Essa função deixa claro que o agente não está “adivinhando” de onde vem o dado. Ele está seguindo uma política de confiança.

### 5.3.2. Onde entra o Agent Gateway nesse código?

Quando existe Agent Gateway / Global Supervisor, ele pode enriquecer a mensagem antes de enviá-la ao backend do agente. Exemplos de dados que podem chegar em `context.session`:

```json
{
  "session": {
    "global_session_id": "s1",
    "backend_session_id": "default:financeiro_agent:s1",
    "active_backend": "financeiro",
    "channel": "web",
    "tenant_id": "default",
    "metadata": {
      "selected_backend": "financeiro",
      "last_reason": "Backend escolhido por regras: matches=['pagamento']"
    }
  }
}
```

O agente não deve usar esse bloco para tomar decisão de negócio final. Ele deve usá-lo para contexto técnico, rastreabilidade e continuidade da conversa. A decisão de negócio deve continuar baseada em `business_context`, tools MCP, RAG e regras de domínio.

### 5.4. Como saber se o agente está bem implementado?

Um agente está bem implementado quando:

```text
Ele conhece regras de negócio, mas não conhece detalhes de infraestrutura.
Ele usa o runtime comum para LLM, RAG, cache, MCP e IC.
Ele retorna um contrato simples para o workflow.
Ele não duplica guardrail, checkpoint, sessão, memória ou telemetria.
Ele consegue ser testado isoladamente com state simulado.
```

---

## 6. Registrando o agente no workflow

### 6.1. Antes do código: o que é o workflow?

O workflow é o caminho controlado pelo LangGraph. Ele define a ordem de execução:

```text
entrada → guardrails → roteamento → agente → revisão → persistência → resposta
```

Criar a classe do agente não basta. O LangGraph só executa nós que foram registrados no grafo.

O registro no workflow responde três perguntas:

```text
Qual classe implementa o agente?
Qual nome de nó representa esse agente no grafo?
Para onde o fluxo segue depois que o agente responde?
```

### 6.2. Importar o agente

Edite:

```text
app/workflows/agent_graph.py
```

Adicione:

```python
from app.agents.financeiro_agent import FinanceiroAgent
```

### 6.3. Instanciar o agente

No `__init__` da classe `AgentWorkflow`, depois da criação de `agent_kwargs`:

```python
self.financeiro = FinanceiroAgent(llm, **agent_kwargs)
```

Essa linha injeta no agente os mesmos motores compartilhados pelos demais agentes: LLM, telemetry, MCP Tool Router, RAG, cache, settings e observer.

### 6.4. Criar o nó do LangGraph

Em `_build_graph()`:

```python
builder.add_node("financeiro_agent", self._node("financeiro_agent", self.financeiro_agent))
```

O primeiro `financeiro_agent` é o nome do nó no grafo. O segundo `self.financeiro_agent` é o método wrapper que será chamado quando o fluxo chegar nesse nó.

### 6.5. Adicionar rota condicional

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

Essa tabela conecta a decisão do roteador com o nó real do grafo.

### 6.6. Conectar o nó ao Output Supervisor

```python
builder.add_edge("financeiro_agent", "output_supervisor")
```

Essa linha é importante porque a resposta do agente não deve ir direto ao usuário. Ela passa antes por output supervisor, output guardrails, judges, supervisor review e persistência.

### 6.7. Criar o método wrapper

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

O wrapper adiciona telemetria ao redor do agente. A lógica de negócio continua dentro de `FinanceiroAgent.run()`.

### 6.8. Adicionar ao modo supervisor

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

Isso permite que o supervisor chame o novo agente quando `ROUTING_MODE=supervisor` ou quando houver handoff supervisionado.

### 6.9. Erros comuns neste capítulo

```text
Criar a classe do agente, mas esquecer add_node.
Adicionar add_node, mas esquecer add_conditional_edges.
Adicionar rota, mas esquecer add_edge para output_supervisor.
Usar nome diferente em routing.yaml, workflow e classe.
Chamar self.financeiro.run direto sem wrapper de telemetria.
```

---

## 7. Ajustando o estado do agente

### 7.1. Antes do código: o que é o state?

O `state` é o objeto que trafega entre os nós do LangGraph. Ele funciona como a memória de curto prazo da execução atual.

Ele não é o banco de dados, não é a memória conversacional completa e não deve virar um repositório gigante de informações.

Use o `state` para dados que precisam circular entre nós, por exemplo:

```text
texto do usuário
intent escolhida
rota escolhida
resposta parcial
resultado de uma tool
próximo estado da conversa
flags de decisão
```

Não use o `state` para:

```text
histórico longo de conversa
arquivos grandes
respostas completas de sistemas externos sem necessidade
conteúdo bruto de documentos
logs extensos
```

### 7.2. Quando alterar `app/state.py`

Edite:

```text
app/state.py
```

Somente adicione novos campos se o agente precisar compartilhar informações específicas com outros nós.

Exemplo:

```python
class AgentState(TypedDict, total=False):
    # campos existentes...
    financial_context: dict[str, Any]
    financial_decision: dict[str, Any]
```

### 7.3. Critério de decisão

Antes de criar um campo novo, pergunte:

```text
Outro nó precisa ler este dado?
Este dado precisa sobreviver ao próximo passo do workflow?
Este dado é pequeno e estruturado?
Este dado ajuda na auditoria ou na decisão?
```

Se a resposta for não, deixe o dado local ao agente ou grave em repositório apropriado.

---

## 8. Registrando o agente em `config/agents.yaml`

### 8.1. Antes do YAML: para que serve `agents.yaml`?

O `agents.yaml` é o cadastro oficial dos agentes disponíveis. Ele não executa o agente sozinho, mas informa ao framework quais agentes existem, quais configurações isoladas eles usam e quais metadados descrevem o domínio.

Ele responde:

```text
Qual é o agent_id?
Qual nome amigável aparece em listagens e debug?
Onde estão prompt, guardrails e judges específicos?
Qual domínio esse agente atende?
Quais metadados ajudam roteamento, auditoria e operação?
```

### 8.2. Exemplo de registro

Edite:

```text
config/agents.yaml
```

Adicione:

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

### 8.3. Cuidados

O `agent_id` precisa ser consistente com:

```text
nome do nó no workflow
nome usado em routing.yaml
session_id canônico
pasta config/agents/<agent_id>/
metadados de observabilidade
```

Evite renomear `agent_id` depois que o agente já estiver em produção, porque isso pode quebrar histórico, memória, checkpoint e métricas.

---

## 9. Criando configurações isoladas do agente

### 9.1. Antes do YAML: por que isolar configuração por agente?

Cada agente pode ter política de prompt, guardrails e judges próprios. Um agente financeiro pode exigir confirmação explícita antes de uma ação. Um agente de suporte pode permitir respostas mais abertas. Um agente jurídico pode exigir evidência documental.

Por isso, evite colocar tudo no arquivo global. Use configuração global para regras corporativas e configuração local para regras do domínio.

Crie:

```text
config/agents/financeiro_agent/
```

### 9.2. `prompt_policy.yaml`

Esse arquivo define a postura base do agente.

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

Use este arquivo para regras persistentes de comportamento, não para regras temporárias de teste.

### 9.3. `guardrails.yaml`

Esse arquivo complementa os guardrails globais.

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

Use guardrail quando a resposta precisa ser bloqueada, sanitizada ou revisada por regra.

### 9.4. `judges.yaml`

Judges avaliam qualidade, aderência, groundedness e outros critérios após a resposta ser produzida.

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.7
  - name: groundedness
    enabled: true
    threshold: 0.6
```

Use judge para avaliar resposta. Use guardrail para bloquear ou proteger. Use prompt para orientar comportamento.

---

## 10. Configurando roteamento em `config/routing.yaml`

### 10.1. Antes do YAML: o que é roteamento?

Roteamento é a decisão de qual agente deve tratar a mensagem.

Em um sistema multiagente, o usuário não deveria precisar saber qual agente chamar. Ele escreve uma mensagem, e o framework decide a rota.

O roteador normalmente considera:

```text
texto do usuário
estado atual da conversa
keywords
examples
prioridade
agent_id solicitado
políticas de estado
LLM router, se habilitado
```

### 10.2. Quando criar uma intent nova?

Crie uma intent quando existir uma categoria clara de solicitação que deve ir para um agente específico.

Exemplo de intent financeira:

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

### 10.3. O que significa `mcp_tools` na intent?

`mcp_tools` indica quais tools devem ser disponibilizadas/coletadas quando essa intent for escolhida. Assim, o agente não precisa decidir manualmente cada chamada em todos os casos simples.

O fluxo fica:

```text
routing.yaml escolhe intent
intent aponta agent
intent declara mcp_tools
AgentRuntimeMixin coleta contexto MCP
agente usa os dados na resposta
```

### 10.4. Políticas de estado

Se a conversa já estiver em um estado específico, a próxima mensagem pode precisar voltar ao mesmo agente, mesmo que o texto seja curto.

Exemplo:

```yaml
state_policies:
  - state: WAITING_FINANCEIRO_CONFIRMATION
    agent: financeiro_agent
    description: Mantém confirmações curtas no fluxo financeiro.
```

Isso evita que uma resposta como “sim” seja roteada para o agente errado.

### 10.5. Router versus supervisor

No modo router:

```env
ROUTING_MODE=router
```

O framework escolhe uma rota de forma mais direta, normalmente por regras, keywords, examples e score.

No modo supervisor:

```env
ROUTING_MODE=supervisor
```

Um supervisor pode decidir a sequência de agentes, handoff ou combinação de respostas.

Use router quando o domínio for bem mapeado. Use supervisor quando a conversa exigir decomposição, múltiplos agentes ou decisão mais flexível.

---

## 11. Configurando tools em `config/tools.yaml`

### 11.1. Antes do YAML: o que é uma tool?

Uma tool é uma capacidade externa que o agente pode usar para obter dados ou executar uma ação.

Exemplos:

```text
consultar fatura
consultar pagamento
abrir protocolo
buscar pedido
cancelar serviço
consultar base de conhecimento
```

A tool não é necessariamente o sistema real. Ela é o contrato que o backend conhece. O sistema real fica atrás do MCP Server.

### 11.2. Declarando tools

Edite:

```text
config/tools.yaml
```

Adicione:

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

### 11.3. Como pensar sobre uma tool

Antes de declarar uma tool, defina:

```text
Qual pergunta de negócio ela responde?
Ela só consulta ou executa uma ação?
Quais parâmetros são obrigatórios?
Quais parâmetros vêm da identidade canônica?
Qual MCP Server implementa a tool?
Qual timeout e fallback são aceitáveis?
O resultado tem dados sensíveis que precisam ser mascarados?
```

O backend não deve chamar diretamente HTTP/SOAP/DB de sistemas de negócio quando essa chamada puder ser padronizada via MCP Tool Router.

---

## 12. Configurando servidores MCP

### 12.1. Antes do YAML: o que é o MCP Server?

O MCP Server é o adaptador entre o mundo do agente e os sistemas reais. Ele permite que o backend converse com ferramentas de forma padronizada, sem conhecer detalhes de REST, SOAP, banco, filas ou mocks.

O desenho é:

```text
Agente
  ↓
MCP Tool Router do framework
  ↓
MCP Server do domínio
  ↓
Sistema real, mock, banco, REST, SOAP ou serviço interno
```

### 12.2. Configuração local

Edite:

```text
config/mcp_servers.yaml
```

Exemplo:

```yaml
servers:
  financeiro:
    transport: http
    endpoint: http://localhost:8300/mcp
    enabled: true
    description: MCP Server Financeiro local.
```

### 12.3. Configuração em Docker Compose

Edite:

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

### 12.4. Como evitar erro comum de endpoint

Localmente, `localhost` funciona porque backend e MCP rodam na mesma máquina.

Dentro do Docker Compose, `localhost` dentro do container do backend aponta para o próprio container do backend, não para o container do MCP. Por isso, em Docker, use o nome do serviço:

```text
http://financeiro-mcp:8300/mcp
```

---

## 13. Configurando mapeamento de parâmetros MCP

### 13.1. Antes do YAML: por que existe mapeamento?

O framework trabalha com chaves canônicas para não depender dos nomes específicos de cada sistema.

Exemplo:

```text
customer_key = cliente canônico no framework
contract_key = contrato/fatura/pedido/título canônico
interaction_key = interação externa
session_key = sessão técnica
```

Mas cada tool pode esperar nomes diferentes:

```text
customer_id
cpf
msisdn
clientCode
contract_id
invoice_id
order_id
```

O `mcp_parameter_mapping.yaml` faz essa tradução sem obrigar o agente a conhecer os nomes internos de cada MCP.

### 13.2. Exemplo

Edite:

```text
config/mcp_parameter_mapping.yaml
```

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

### 13.3. Como validar o mapeamento

Se a tool recebe parâmetro errado, investigue nesta ordem:

```text
payload enviado ao /gateway/message
config/identity.yaml
business_context resolvido
config/mcp_parameter_mapping.yaml
args_schema da tool
assinatura real no MCP Server
```

---

## 14. Configurando identidade de negócio

### 14.1. Antes do YAML: o que é identidade de negócio?

Identidade de negócio é a normalização das chaves que representam o cliente, contrato, pedido, protocolo, sessão ou interação.

Sem essa camada, cada canal envia um nome diferente e cada tool espera outro nome. O resultado é erro de parâmetro, tool sem dado obrigatório ou consulta ao cliente errado.

O `identity.yaml` responde:

```text
De onde posso extrair customer_key?
De onde posso extrair contract_key?
De onde posso extrair interaction_key?
De onde posso extrair session_key?
Quais chaves são obrigatórias?
```

### 14.2. Exemplo

Edite:

```text
config/identity.yaml
```

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
        - context.business_context.customer_key
        - context.session.metadata.customer_key
        - customer_key
        - customer_id
        - cpf
        - cnpj
        - user_id
    contract_key:
      description: Contrato, pedido, fatura ou título principal.
      sources:
        - business_context.contract_key
        - context.business_context.contract_key
        - context.session.metadata.contract_key
        - contract_key
        - contract_id
        - invoice_id
        - order_id
    interaction_key:
      description: Chave externa da interação.
      sources:
        - business_context.interaction_key
        - context.business_context.interaction_key
        - context.session.metadata.interaction_key
        - interaction_key
        - call_id
        - message_id
        - protocol_id
    session_key:
      description: Sessão técnica estável.
      sources:
        - business_context.session_key
        - context.business_context.session_key
        - context.session.backend_session_id
        - context.session.global_session_id
        - context.session.metadata.session_key
        - session_key
        - conversation_key
        - session_id
```

### 14.3. Como pensar sobre identidade

Use o mínimo necessário. Não torne tudo obrigatório. Para uma pergunta genérica, talvez só `session_key` seja suficiente. Para consultar um título financeiro, talvez `customer_key` e `contract_key` sejam obrigatórios.

A identidade resolvida aparece em `business_context` dentro do `state` e é usada pelo `MCP Tool Router`.

### 14.4. Relação entre SessionContext e BusinessContext

Quando o Agent Gateway está presente, ele pode criar ou transportar dados de sessão. Esses dados são importantes, mas não substituem a identidade de negócio.

```text
SessionContext responde:
  Quem está falando?
  Por qual canal?
  Qual sessão global está ativa?
  Qual backend está atendendo?
  Qual foi a razão da última decisão de rota?

BusinessContext responde:
  Qual cliente deve ser consultado?
  Qual contrato/fatura/pedido está em discussão?
  Qual protocolo/chamado/interação identifica o caso?
  Qual chave deve ser enviada para a tool MCP?
```

Regra prática:

```text
Use session para continuidade, rastreabilidade e canal.
Use business_context para consultar sistemas, chamar MCP e tomar decisão de negócio.
Use tool_arguments quando parâmetros já vierem explicitamente preparados.
```

Exemplo de erro comum:

```text
Usar session.user_id como customer_key sem validar identity.yaml.
```

O correto é deixar o `IdentityResolver` transformar `user_id`, `cpf`, `msisdn`, `customer_id` ou outro identificador em uma chave canônica como `customer_key`.

---

## 15. Implementando ou conectando um MCP Server

### 15.1. Antes do código: qual é o papel do MCP Server?

O MCP Server é onde fica a integração com sistemas externos ou mocks de domínio. Ele permite que o agente use uma tool sem conhecer implementação técnica.

O backend sabe chamar:

```text
consultar_titulo_financeiro(customer_id, contract_id)
```

Mas não sabe, nem deveria saber, se essa consulta usa:

```text
REST
SOAP
banco Oracle
arquivo mock
serviço legado
fila
sistema interno
```

### 15.2. Contrato conceitual das tools

Exemplo conceitual:

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

### 15.3. Critério para mock versus real

Use mock quando:

```text
o sistema real não está disponível
você está testando roteamento e contrato
você quer validar frontend/backend sem depender de VPN
você quer montar testes automatizados determinísticos
```

Use integração real quando:

```text
o contrato já foi validado
os parâmetros estão corretos
o timeout e fallback foram definidos
há observabilidade para sucesso e falha
há dados seguros para teste
```

Para desenvolvimento, você pode usar `use_mock: true` no `mcp_parameter_mapping.yaml` ou implementar um MCP Server local com respostas simuladas.

---

## 16. IC, NOC e GRL no novo agente

### 16.1. Antes dos eventos: por que eles existem?

IC, NOC e GRL não são logs comuns. Eles existem para rastrear a execução de forma corporativa.

```text
IC  = evento de negócio ou jornada do agente
NOC = evento operacional, erro, indisponibilidade, timeout ou degradação
GRL = evento de governança, guardrail, bloqueio, revisão ou sanitização
```

Use `logger.info()` para diagnóstico simples. Use IC/NOC/GRL quando o evento precisa aparecer em auditoria, observabilidade ou análise operacional.

### 16.2. IC — eventos de negócio

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

### 16.3. NOC — eventos operacionais

NOC deve ser usado para saúde técnica, indisponibilidade, erro, timeout, fallback e degradação.

Exemplo:

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

### 16.4. GRL — guardrails

A maior parte dos GRLs já é emitida pelo workflow em:

```text
input_guardrails
output_supervisor
output_guardrails
```

Só implemente GRL dentro do agente quando houver uma validação de domínio específica que não caiba nos guardrails globais.

### 16.5. Quando não criar evento novo

Não crie IC/NOC/GRL para cada linha de código. Crie eventos para decisões importantes:

```text
entrada validada
contexto MCP coletado
decisão de negócio tomada
ação externa solicitada
ação externa concluída
fallback técnico acionado
resposta bloqueada ou revisada
workflow concluído
```

---

## 17. Build e execução local

### 17.1. Antes dos comandos: o que significa subir o backend?

Subir o backend significa iniciar a API que recebe mensagens, normaliza canal, resolve identidade, abre sessão, executa o workflow e devolve resposta.

Ele pode subir mesmo sem MCP real, desde que a configuração esteja em mock ou que as tools não sejam obrigatórias para o teste.

### 17.2. Rodar backend local

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

### 17.3. Validações imediatas

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

### 17.4. Como interpretar o resultado

```text
/health ok         → API subiu.
/agents lista      → agents.yaml foi carregado.
/debug/mcp/tools   → tools.yaml e mcp_servers.yaml foram carregados.
```

Se `/health` funciona mas `/agents` não lista o agente, o problema provavelmente está em `config/agents.yaml`. Se `/debug/mcp/tools` não mostra a tool, o problema provavelmente está em `tools.yaml` ou `mcp_servers.yaml`.

---

## 18. Subindo MCP Servers

### 18.1. Antes dos comandos: quando preciso subir MCP?

Você precisa subir MCP quando a intent escolhida usa `mcp_tools` e o agente depende dessas tools para responder.

Não precisa subir MCP para testar apenas:

```text
health check
registro de agentes
roteamento básico
mock LLM sem tools
fluxo conversacional simples sem consulta externa
```

### 18.2. Subir MCP Server local

Se os MCP Servers forem processos Python separados, suba cada um em uma porta distinta.

Exemplo:

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

### 18.3. Testar tool pelo backend

Teste pelo backend, não diretamente pelo MCP. Assim você valida o caminho completo:

```text
backend → MCP Tool Router → MCP Server → resposta
```

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

### 18.4. Como interpretar erros MCP

```text
Tool não encontrada         → tools.yaml ou nome da tool errado.
Servidor não encontrado     → mcp_servers.yaml não tem o mcp_server indicado pela tool.
Connection refused          → MCP Server não está rodando ou porta errada.
Parâmetro obrigatório ausente → identity.yaml ou mcp_parameter_mapping.yaml incorreto.
Timeout                     → MCP lento, endpoint errado, VPN, DNS ou sistema real indisponível.
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
- [ ] Agente usa `get_runtime_context()` ou padrão equivalente para ler `state/context/session/business_context`.
- [ ] Agente usa `normalize_tools_by_intent()` quando precisa de fallback de tools por intent.
- [ ] Agente usa `build_tool_arguments()` ou `execute_tools_for_intent()` quando precisa de aliases/política de tools.
- [ ] Tools de ação em `tools.yaml` possuem `tool_type`, `requires` e, quando necessário, `confirmation_required`.
- [ ] Dev entende que `AgentRuntimeMixin` é infraestrutura compartilhada, não regra de negócio.
- [ ] Agente usa `_emit_ic()`, `_emit_noc()` ou `_emit_grl()` em vez de emitir observabilidade em formato próprio.
- [ ] Agente usa `_collect_mcp_context()` para consultas simples às tools declaradas em `routing.yaml`.
- [ ] Agente usa `_retrieve_rag_context()` quando precisa de contexto documental.
- [ ] Agente usa `_invoke_llm_cached()` para chamada LLM com cache e telemetria.
- [ ] Dev entende que `messages` é o contrato conversacional enviado ao LLM, não a memória persistente.
- [ ] `messages` separa regras permanentes no `system` e pedido/evidências no `user`.
- [ ] `messages` inclui apenas campos necessários de `session`, `business_context`, MCP e RAG.
- [ ] Agente não envia `state` completo, objetos enormes ou dados sensíveis desnecessários ao LLM.
- [ ] Agente deixa claro no prompt quando MCP/RAG falharam, para evitar resposta inventada.
- [ ] Agente não chama REST, banco, SOAP ou serviço externo diretamente quando isso deveria estar atrás de MCP.
- [ ] Agente separa `context`, `session`, `business_context` e `tool_arguments` antes de tomar decisões.
- [ ] Agente usa `business_context` para decisões de negócio e `session` para continuidade/rastreabilidade.
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
- Use `RuntimeContext`, `build_tool_arguments()` e `execute_tools_for_intent()` antes de criar helpers locais duplicados no agente.
- Use `identity.yaml` para normalizar chaves de negócio.
- Use `mcp_parameter_mapping.yaml` para adaptar nomes de parâmetros.
- Use IC para eventos de negócio.
- Use NOC para falhas técnicas.
- Use GRL para decisões de segurança/validação.
- Monte `messages` com separação clara entre instrução, pedido, evidência MCP, contexto RAG e formato de saída.
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
- Enviar o `state` inteiro ou dumps grandes de tools/RAG diretamente dentro de `messages`.
- Colocar regras críticas apenas no `user` prompt quando deveriam estar no `system`.

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

```text
config/routing.yaml
keywords
examples
priority
ROUTING_MODE
ENABLE_LLM_ROUTER
```

### 25.2. Tool MCP não é chamada

Verifique:

```text
A intent em routing.yaml possui mcp_tools.
A tool existe em tools.yaml.
O MCP Server está em mcp_servers.yaml.
ENABLE_MCP_TOOLS=true.
O mapeamento existe em mcp_parameter_mapping.yaml.
A identidade tem as chaves necessárias.
```

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

Depois volte para `autonomous` quando wallet, DSN e variáveis estiverem corretos.

---


### 25.7. LLM responde inventando ou ignorando evidências

Quando o LLM inventa dados, confirma uma ação inexistente ou ignora uma tool, nem sempre o problema está no modelo. Muitas vezes o problema está em como `messages` foi montado.

Verifique:

```text
O system prompt proíbe claramente inventar dados?
O user prompt separa evidências MCP de instruções?
A falha da tool foi informada explicitamente ao LLM?
O agente enviou um dump confuso de mcp_results em vez de um resumo útil?
O RAG trouxe documentos relevantes ou ruído?
O prompt pediu formato de resposta claro?
Há histórico duplicado confundindo a resposta?
```

Exemplo de correção:

```text
Ruim:
  Responda sobre o pagamento do cliente usando os dados abaixo: [...]

Melhor:
  A tool consultar_pagamentos_financeiro retornou ok=false.
  Não confirme pagamento.
  Informe que a evidência de pagamento não foi encontrada.
```

Em ambiente de desenvolvimento, registre uma versão sanitizada de `messages` para revisar o que realmente chegou ao LLM. Nunca registre prompts brutos com CPF, token, credencial, dados sensíveis ou payloads grandes de sistemas externos.

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

## 28. Agent Gateway / Global Supervisor

Este capítulo é uma tratativa à parte. Em uma arquitetura com vários agentes, não basta saber construir um backend de agente isolado. Em algum momento o frontend recebe uma mensagem do usuário e precisa decidir **qual backend de agente deve tratar aquela conversa**.

Essa decisão não deve ficar espalhada no frontend, nem duplicada dentro de cada agente. Para isso existe o **Agent Gateway**, também chamado aqui de **Global Supervisor**.

### 28.1. Antes do código: qual problema o Agent Gateway resolve?

Imagine que a empresa tenha três backends independentes:

```text
Backend Contas
  resolve fatura, pagamento, consumo, segunda via, contestação

Backend Ofertas
  resolve planos, contratação, upgrade, retenção, desconto

Backend Suporte
  resolve internet lenta, sinal, rede, modem, falha técnica
```

Sem um gateway global, o frontend teria que saber regras como:

```text
Se a mensagem tem "fatura", chamar Contas.
Se a mensagem tem "plano", chamar Ofertas.
Se a mensagem tem "internet lenta", chamar Suporte.
```

Isso parece simples no começo, mas vira problema quando:

- surgem muitos agentes;
- uma conversa começa em Contas e depois muda para Ofertas;
- uma mensagem é ambígua, como “quero cancelar”;
- cada canal, Web, WhatsApp e Voz, começa a implementar sua própria regra;
- o desenvolvedor precisa manter roteamento, sessão e handoff em vários lugares.

O **Agent Gateway** centraliza essa decisão.

Ele recebe a mensagem normalizada do canal, descobre o backend correto e encaminha a requisição para o backend escolhido.

```text
Usuário
  ↓
Frontend / Canal
  ↓
Agent Gateway / Global Supervisor
  ↓
Backend Contas | Backend Ofertas | Backend Suporte | Outros backends
```

O Gateway **não substitui o agente**. Ele não deve conter regra de negócio de fatura, oferta ou suporte. Ele apenas decide **quem deve receber a mensagem**.

### 28.2. Diferença entre Supervisor do agente e Global Supervisor

Dentro de um backend de agente, você pode ter um supervisor local. Esse supervisor decide entre caminhos internos do próprio agente.

Exemplo dentro do agente de Contas:

```text
Mensagem: "Minha fatura veio alta"

Supervisor local do Backend Contas decide:
  - explicar fatura
  - consultar pagamentos
  - abrir contestação
  - chamar humano
```

O **Global Supervisor** decide em um nível acima:

```text
Mensagem: "Minha internet está lenta"

Global Supervisor decide:
  - isso não é Contas
  - isso deve ir para Suporte
```

A separação correta é:

```text
Global Supervisor / Agent Gateway
  decide o backend

Supervisor local do backend
  decide o fluxo interno do agente

Agente especializado
  executa a lógica de negócio
```

Essa separação evita que o framework ou o gateway fiquem contaminados com detalhes específicos de um domínio.

### 28.3. O que pertence ao Agent Gateway

O Gateway deve cuidar de responsabilidades transversais entre backends:

```text
agent_gateway/
  app/main.py
    expõe /gateway/message, /gateway/events/{session_id}, /debug/route,
    /backends, /backends/health e /health

  app/settings.py
    lê variáveis de ambiente do gateway global

  config/backends.yaml
    declara quais backends existem, suas URLs, domínios, keywords e prioridade

  .env.example
    documenta o modo de roteamento, TTL de sessão, timeout e provider LLM
```

O Gateway pode usar motores do framework para:

- roteamento global;
- sessão global;
- client HTTP para backends;
- supervisor LLM;
- observabilidade;
- publicação de eventos;
- proxy SSE.

No arquivo `agent_gateway/app/main.py`, o gateway usa componentes do framework como:

```python
from agent_framework.global_supervisor import (
    BackendClient,
    BackendRegistry,
    GlobalRouteRequest,
    GlobalSupervisorRouter,
    InMemoryGlobalSessionStore,
)
```

Isso significa que o gateway não está criando um mecanismo paralelo de roteamento. Ele está usando uma camada própria do framework para governar múltiplos backends.

### 28.4. O que não pertence ao Agent Gateway

O Gateway não deve implementar regras específicas como:

```text
consultar_fatura
consultar_pagamentos
abrir_contestacao
consultar_imdb
buscar_speech_analytics
abrir_sr_siebel
calcular_pro_rata
resolver_ean
```

Essas funcionalidades pertencem aos backends especializados ou aos MCP servers.

Uma regra prática:

```text
Se a lógica depende do negócio de um agente específico, ela não deve ficar no Gateway.
Se a lógica decide qual backend deve tratar a conversa, ela pode ficar no Gateway.
```

### 28.5. Estrutura do projeto `agent_gateway`

A estrutura mínima observada no projeto é:

```text
agent_gateway/
  app/
    main.py
    settings.py
  config/
    backends.yaml
  docs/
    ARQUITETURA_GLOBAL_SUPERVISOR.md
  .env.example
  Dockerfile
  README.md
  requirements.txt
```

Cada arquivo tem uma responsabilidade clara:

| Arquivo | Responsabilidade |
|---|---|
| `app/main.py` | expõe endpoints HTTP, chama o router global, encaminha mensagens aos backends e faz proxy SSE |
| `app/settings.py` | centraliza variáveis do gateway global |
| `config/backends.yaml` | cadastra backends disponíveis e regras de roteamento por domínio/keyword |
| `.env.example` | documenta como ligar/desligar modos de roteamento e providers |
| `Dockerfile` | empacota o gateway como serviço separado |
| `docs/ARQUITETURA_GLOBAL_SUPERVISOR.md` | explica a arquitetura conceitual |

### 28.6. Como o desenvolvedor deve pensar antes de configurar o Gateway

Antes de editar `config/backends.yaml`, o desenvolvedor deve responder quatro perguntas:

```text
1. Quais backends de agente existem?
2. Qual é o domínio de responsabilidade de cada backend?
3. Quais palavras ou exemplos indicam cada domínio?
4. O que deve acontecer quando a mensagem for ambígua?
```

Exemplo:

```text
Mensagem: "Quero cancelar"
```

Essa mensagem pode significar:

```text
Cancelar serviço avulso    → talvez Contas ou Ofertas
Cancelar plano inteiro     → talvez Ofertas ou Retenção
Cancelar por problema rede → talvez Suporte
```

Nesse caso, o router por keyword pode não ser suficiente. O modo `hybrid` pode manter o backend ativo se a conversa já tiver contexto, ou chamar o supervisor LLM se houver conflito.

### 28.7. Configurando os backends em `config/backends.yaml`

O arquivo principal de configuração do Gateway é:

```text
agent_gateway/config/backends.yaml
```

Exemplo:

```yaml
default_backend: contas

backends:
  contas:
    url: http://localhost:8001
    description: Backend responsável por faturas, contas, pagamentos, consumo, segunda via e contestação.
    domains: [contas, fatura, pagamento, consumo, contestacao]
    keywords: [fatura, conta, boleto, pagamento, consumo, segunda via, contestar, contestação, valor, cobrança]
    examples:
      - Quero consultar minha fatura
      - Minha conta veio alta
      - Preciso da segunda via do boleto
    priority: 10
    default_agent_id: telecom_contas

  ofertas:
    url: http://localhost:8002
    description: Backend responsável por ofertas, planos, upgrades, retenção e contratação.
    domains: [ofertas, planos, retenção, contratação]
    keywords: [oferta, plano, contratar, upgrade, desconto, promoção, pacote, retenção, cancelar serviço]
    examples:
      - Quero trocar meu plano
      - Tem alguma oferta para mim?
      - Quero cancelar um serviço
    priority: 20
    default_agent_id: telecom_ofertas

  suporte:
    url: http://localhost:8003
    description: Backend responsável por suporte técnico, falhas, rede, internet e atendimento operacional.
    domains: [suporte, técnico, rede, internet]
    keywords: [internet, sinal, rede, suporte, técnico, problema, falha, sem conexão, modem]
    examples:
      - Minha internet está lenta
      - Estou sem sinal
      - Preciso de suporte técnico
    priority: 30
    default_agent_id: telecom_suporte
```

O desenvolvedor não deve preencher esse YAML como uma lista aleatória de palavras. Ele deve pensar em **famílias de intenção**.

Exemplo correto:

```text
Família: contas
  assuntos: fatura, pagamento, consumo, segunda via, contestação
```

Exemplo ruim:

```text
Família: qualquer coisa que tenha "valor"
```

A palavra “valor” pode aparecer em fatura, oferta, desconto, contestação ou cobrança. Palavras genéricas devem ser usadas com cuidado.

### 28.8. Escolhendo o modo de roteamento global

O `.env` do gateway possui a variável:

```env
GLOBAL_ROUTING_MODE=hybrid
```

Os modos possíveis são:

| Modo | Como decide | Quando usar |
|---|---|---|
| `router` | usa regras, keywords, domínios e prioridade | desenvolvimento local, testes determinísticos, ambientes com baixa ambiguidade |
| `supervisor` | usa LLM para escolher backend | domínios muito parecidos ou mensagens muito abertas |
| `hybrid` | mantém backend ativo, usa regra e chama LLM em conflito | recomendado para produção inicial |

A decisão prática é:

```text
Se você quer previsibilidade total, use router.
Se você quer interpretação semântica forte, use supervisor.
Se você quer equilíbrio entre contexto, regra e LLM, use hybrid.
```

Para a maioria dos projetos corporativos, comece com:

```env
GLOBAL_ROUTING_MODE=hybrid
GLOBAL_KEEP_ACTIVE_BACKEND=true
GLOBAL_USE_SUPERVISOR_ON_CONFLICT=true
GLOBAL_MIN_ROUTER_CONFIDENCE=0.55
```

### 28.9. Entendendo sessão global e sessão do backend

O Gateway mantém uma sessão global, por exemplo:

```text
global_session_id = s1
```

O backend pode manter outra sessão interna, por exemplo:

```text
backend_session_id = default:telecom_contas:s1
```

O código do Gateway ajusta a resposta para manter os dois identificadores no `metadata`:

```json
{
  "session_id": "s1",
  "metadata": {
    "global_session_id": "s1",
    "backend_session_id": "default:telecom_contas:s1",
    "selected_backend": "contas"
  }
}
```

Essa separação é importante porque o usuário conversa com uma sessão global, mas cada backend pode precisar de sua própria chave interna para memória, checkpoint e histórico.

### 28.9.1. Como o Gateway deve entregar sessão ao backend

Para que o agente consiga entender de onde veio a conversa, o Gateway deve encaminhar a sessão dentro de `context.session` ou em uma estrutura equivalente normalizada pelo framework.

Exemplo de payload conceitual que chega ao backend:

```json
{
  "channel": "web",
  "tenant_id": "default",
  "agent_id": "financeiro_agent",
  "payload": {
    "text": "Quero consultar meu pagamento",
    "session_id": "s1",
    "customer_id": "12345"
  },
  "context": {
    "session": {
      "global_session_id": "s1",
      "backend_session_id": "default:financeiro_agent:s1",
      "active_backend": "financeiro",
      "channel": "web",
      "tenant_id": "default",
      "metadata": {
        "selected_backend": "financeiro",
        "route_confidence": 0.82
      }
    },
    "business_context": {
      "customer_key": "12345",
      "session_key": "default:financeiro_agent:s1"
    }
  }
}
```

O desenvolvedor do agente deve entender que `context.session` não é “mais um lugar para buscar qualquer parâmetro”. Ele é o contrato de continuidade da conversa. Para chamadas MCP, prefira sempre `business_context` e `tool_arguments`.

### 28.10. Subindo o Agent Gateway localmente

Entre no diretório do gateway:

```bash
cd agent_gateway
```

Copie o arquivo de ambiente:

```bash
cp .env.example .env
```

Configure o `PYTHONPATH` para enxergar o framework:

```bash
export PYTHONPATH=../agent_framework/src:.
```

Suba o serviço:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

Valide o health:

```bash
curl http://localhost:8010/health
```

Resposta esperada:

```json
{
  "status": "ok",
  "app": "agent-gateway-global-supervisor",
  "routing_mode": "hybrid",
  "backends": ["contas", "ofertas", "suporte"],
  "llm_provider": "mock"
}
```

Se esse endpoint não responder, o problema ainda está no gateway, não nos backends.

### 28.11. Subindo os backends de agente

O Gateway só roteia corretamente se os backends configurados em `backends.yaml` estiverem de pé.

Exemplo local:

```text
Gateway        http://localhost:8010
Contas         http://localhost:8001
Ofertas        http://localhost:8002
Suporte        http://localhost:8003
Frontend       http://localhost:5173
```

Cada backend precisa expor, no mínimo:

```text
GET  /health
POST /gateway/message
GET  /gateway/events/{session_id}
```

O endpoint `/backends/health` do Gateway verifica a saúde dos backends:

```bash
curl http://localhost:8010/backends/health
```

Use esse teste antes de culpar o roteamento. Se o backend está fora do ar, o Gateway pode até escolher corretamente, mas falhará no encaminhamento.

### 28.12. Testando apenas a decisão de rota

Antes de enviar uma mensagem real para o backend, teste a decisão:

```bash
curl -X POST http://localhost:8010/debug/route \
  -H 'content-type: application/json' \
  -d '{
    "channel": "web",
    "payload": {
      "text": "Minha fatura veio alta",
      "session_id": "s1"
    }
  }'
```

Resultado esperado:

```json
{
  "backend_id": "contas",
  "confidence": 0.8,
  "reason": "Backend escolhido por regras: matches=['fatura']"
}
```

O desenvolvedor deve interpretar o resultado assim:

```text
backend_id   → para qual backend o gateway mandaria a mensagem
confidence   → quão forte foi a decisão
reason       → por que a decisão foi tomada
```

Se o backend escolhido estiver errado, ajuste `domains`, `keywords`, `examples`, `priority` ou o modo de roteamento.

### 28.13. Enviando mensagem real pelo Gateway

Depois que a decisão de rota estiver correta, envie a mensagem real:

```bash
curl -X POST http://localhost:8010/gateway/message \
  -H 'content-type: application/json' \
  -d '{
    "channel": "web",
    "payload": {
      "text": "Minha fatura veio alta",
      "session_id": "s1",
      "msisdn": "11999999999"
    }
  }'
```

O Gateway fará:

```text
1. Receber a mensagem.
2. Emitir IC.GLOBAL_GATEWAY_RECEIVED.
3. Criar uma GlobalRouteRequest.
4. Chamar GlobalSupervisorRouter.
5. Escolher o backend.
6. Emitir IC.GLOBAL_BACKEND_SELECTED.
7. Encaminhar para o /gateway/message do backend.
8. Guardar o active_backend da sessão.
9. Acrescentar metadados de rota na resposta.
10. Emitir IC.GLOBAL_GATEWAY_COMPLETED.
```

### 28.14. Handoff entre backends

O handoff acontece quando um backend percebe que a conversa deve mudar de domínio.

Exemplo:

```text
Usuário começou em Contas:
  "Minha fatura veio alta"

Depois perguntou:
  "Tem algum plano melhor para reduzir esse valor?"
```

O backend de Contas pode responder com metadata pedindo troca:

```json
{
  "metadata": {
    "handover_backend": "ofertas"
  }
}
```

O Gateway detecta esse campo e chama automaticamente o novo backend.

O desenvolvedor precisa entender que handoff não é erro. É uma transição controlada entre domínios.

### 28.15. Proxy SSE pelo Gateway

O Gateway também possui endpoint:

```text
GET /gateway/events/{session_id}
```

Esse endpoint faz proxy do SSE do backend ativo.

Fluxo:

```text
Frontend abre EventSource no Gateway
  ↓
Gateway espera existir sessão global
  ↓
Gateway descobre active_backend
  ↓
Gateway monta URL SSE do backend
  ↓
Gateway repassa os eventos text/event-stream para o frontend
```

Teste:

```bash
curl -N http://localhost:8010/gateway/events/s1
```

Eventos esperados no início:

```text
event: connected
data: {"session_id":"s1","component":"agent_gateway"}

```

Depois que uma mensagem for enviada para `/gateway/message`, o Gateway deve emitir algo como:

```text
event: backend.selected
data: {"session_id":"s1","backend_id":"contas","backend_session_id":"s1"}
```

Se aparecer erro de MIME type, o backend ativo provavelmente não está retornando `text/event-stream` em `/gateway/events/{session_id}`.

### 28.16. IC e NOC do Agent Gateway

O Gateway deve emitir eventos próprios, diferentes dos eventos internos dos agentes.

Eventos encontrados no projeto:

| Evento | Significado |
|---|---|
| `IC.GLOBAL_GATEWAY_RECEIVED` | Gateway recebeu mensagem do canal |
| `IC.GLOBAL_BACKEND_SELECTED` | Gateway escolheu um backend |
| `IC.GLOBAL_BACKEND_HANDOVER` | Houve troca de backend durante a conversa |
| `IC.GLOBAL_GATEWAY_COMPLETED` | Gateway concluiu o encaminhamento |
| `NOC.005` | falha operacional no Gateway ou na chamada ao backend |
| `NOC.006` | conclusão HTTP observada pelo middleware |

Esses eventos não substituem os IC/NOC/GRL do backend. Eles complementam a visão ponta a ponta.

Em uma rastreabilidade completa, você deve conseguir enxergar:

```text
IC.GLOBAL_GATEWAY_RECEIVED
IC.GLOBAL_BACKEND_SELECTED
IC.BACKEND_WORKFLOW_STARTED
IC.TOOL_CALLED
GRL.INPUT_STARTED
GRL.OUTPUT_COMPLETED
IC.BACKEND_WORKFLOW_COMPLETED
IC.GLOBAL_GATEWAY_COMPLETED
```

### 28.17. Como integrar o frontend ao Agent Gateway

O frontend não deve chamar diretamente cada backend de agente.

Em vez disso, ele deve apontar para:

```text
POST http://localhost:8010/gateway/message
GET  http://localhost:8010/gateway/events/{session_id}
```

O frontend continua enviando uma mensagem normalizada:

```json
{
  "channel": "web",
  "payload": {
    "text": "Minha fatura veio alta",
    "session_id": "s1"
  }
}
```

O frontend não precisa saber se a mensagem foi para Contas, Ofertas ou Suporte. Essa informação pode aparecer em `metadata.selected_backend`, mas não deve virar regra de negócio no frontend.

### 28.18. Build do Gateway com Docker

O Dockerfile do Gateway usa:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY agent_framework /agent_framework
COPY agent_gateway /app
RUN pip install --no-cache-dir -e /agent_framework -r requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

Isso pressupõe que, no contexto de build, existam os diretórios:

```text
agent_framework/
agent_gateway/
```

Build:

```bash
docker build -t agent-gateway:local -f agent_gateway/Dockerfile .
```

Run:

```bash
docker run --rm -p 8010:8010 \
  --env-file agent_gateway/.env \
  agent-gateway:local
```

### 28.19. Checklist de implementação do Agent Gateway

Antes de considerar o Gateway pronto, valide:

```text
[ ] /health responde.
[ ] /backends lista todos os backends esperados.
[ ] /backends/health consegue chamar cada backend.
[ ] /debug/route escolhe o backend correto para mensagens óbvias.
[ ] /debug/route explica o motivo da decisão.
[ ] /gateway/message encaminha para o backend escolhido.
[ ] response.metadata.selected_backend aparece na resposta.
[ ] response.metadata.global_route_decision aparece na resposta.
[ ] /debug/sessions mostra active_backend após primeira mensagem.
[ ] /gateway/events/{session_id} retorna text/event-stream.
[ ] handoff_backend funciona quando um backend solicita troca.
[ ] IC.GLOBAL_* aparece na observabilidade.
[ ] NOC.005 aparece em falhas reais de backend.
```

### 28.20. Erros comuns no Agent Gateway

#### Erro 1: Gateway escolhe backend errado

Causas comuns:

```text
keywords genéricas demais
priority mal definida
examples insuficientes
GLOBAL_MIN_ROUTER_CONFIDENCE muito baixo
modo router usado para domínio ambíguo
```

Correção:

```text
1. Teste /debug/route.
2. Leia o campo reason.
3. Ajuste domains, keywords e examples.
4. Se continuar ambíguo, use hybrid ou supervisor.
```

#### Erro 2: Gateway escolhe certo, mas retorna 502

Isso normalmente significa que o backend escolhido está fora do ar ou não expõe `/gateway/message`.

Teste:

```bash
curl http://localhost:8001/health
curl -X POST http://localhost:8001/gateway/message \
  -H 'content-type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste","session_id":"s1"}}'
```

#### Erro 3: SSE retorna `application/json` em vez de `text/event-stream`

O backend ativo precisa expor SSE corretamente.

Teste direto no backend:

```bash
curl -i -N http://localhost:8001/gateway/events/s1
```

O header esperado é:

```text
content-type: text/event-stream
```

#### Erro 4: Sessão global existe, mas o backend ativo não aparece

Verifique:

```bash
curl http://localhost:8010/debug/sessions
```

Depois envie uma mensagem por `/gateway/message`. O `active_backend` só é definido depois que o Gateway roteia uma mensagem com sucesso.

### 28.21. Como explicar essa arquitetura para um novo desenvolvedor

Uma forma simples de ensinar é:

```text
O backend de agente sabe resolver um tipo de problema.
O Gateway sabe escolher qual backend deve resolver o problema.
O framework fornece os motores reutilizáveis para ambos.
```

Portanto, ao implementar um novo agente, o desenvolvedor deve fazer duas integrações:

```text
1. Criar o backend especializado usando agent_template_backend.
2. Registrar esse backend no agent_gateway/config/backends.yaml.
```

Ele não deve alterar o frontend para cada novo agente. Também não deve colocar regra de negócio do novo agente dentro do Gateway.


---

## 29. Conclusão

O `agent_template_backend` fornece a espinha dorsal corporativa para novos agentes. A implementação de um agente novo deve se limitar ao domínio: prompts, regras, tools, clients, schemas e decisões específicas.

O padrão correto é:

```text
Framework = motor reutilizável
Agente = customização de negócio
MCP = fronteira padronizada com sistemas externos
Config YAML = comportamento alterável sem mexer no motor
IC/NOC/GRL = rastreabilidade corporativa
```

Um desenvolvedor não deve apenas copiar arquivos. Ele deve entender que cada alteração representa uma decisão arquitetural:

```text
Criar agente       → define a lógica de domínio.
Registrar workflow → torna o agente executável pelo LangGraph.
Ajustar state      → compartilha dados entre nós.
Configurar agents  → declara o agente para o framework.
Configurar routing → ensina o framework quando chamar o agente.
Configurar tools   → declara capacidades externas.
Configurar MCP     → conecta tools a sistemas ou mocks.
Configurar identity→ normaliza chaves de negócio.
Emitir IC/NOC/GRL  → torna a execução auditável.
Testar gateway     → valida o fluxo real fim a fim.
```

Seguindo esse modelo, novos agentes podem ser criados com padronização, escalabilidade, rastreabilidade e manutenção mais simples.


## 30. Entrega final com Agent Gateway

Ao final da implementação, a entrega recomendada deve conter quatro projetos ou diretórios claramente separados:

```text
agent_framework/
  biblioteca reutilizável com motores de workflow, routing, guardrails,
  judges, supervisor, memória, checkpoint, observabilidade e MCP tool router

agent_template_backend/
  backend especializado de um agente, com domínio, prompts, tools,
  state, workflow e configurações próprias

agent_gateway/
  global supervisor que roteia conversas entre vários backends de agentes

agent_frontend/
  interface Web, WhatsApp ou Voz que conversa com o Agent Gateway
```

A relação correta é:

```text
Frontend
  chama Agent Gateway

Agent Gateway
  escolhe o backend

Backend do agente
  executa o workflow especializado

MCP Server
  executa ou simula ferramentas de negócio

Framework
  fornece os motores reutilizáveis para gateway e backends
```

### 30.1. Sequência final de subida local

Uma sequência local completa pode ser:

```bash
# 1. Subir MCP do agente, se existir
cd mcp_servers/meu_agente_mcp
uvicorn app.main:app --host 0.0.0.0 --port 9001 --reload

# 2. Subir backend do agente Contas
cd agent_template_backend
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# 3. Subir Agent Gateway
cd agent_gateway
cp .env.example .env
export PYTHONPATH=../agent_framework/src:.
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

# 4. Subir frontend
cd agent_frontend
npm install
npm run dev
```

### 30.2. Sequência final de testes

```bash
# Gateway vivo
curl http://localhost:8010/health

# Backends registrados
curl http://localhost:8010/backends

# Saúde dos backends
curl http://localhost:8010/backends/health

# Decisão de rota
curl -X POST http://localhost:8010/debug/route \
  -H 'content-type: application/json' \
  -d '{"channel":"web","payload":{"text":"Minha fatura veio alta","session_id":"s1"}}'

# Mensagem real ponta a ponta
curl -X POST http://localhost:8010/gateway/message \
  -H 'content-type: application/json' \
  -d '{"channel":"web","payload":{"text":"Minha fatura veio alta","session_id":"s1","msisdn":"11999999999"}}'

# Sessões globais
curl http://localhost:8010/debug/sessions

# SSE pelo Gateway
curl -N http://localhost:8010/gateway/events/s1
```

### 30.3. Critério de aceite arquitetural

A implementação está arquiteturalmente correta quando:

```text
[ ] o frontend não conhece URLs individuais dos backends de agentes;
[ ] o Gateway não contém regra de negócio específica de fatura, oferta ou suporte;
[ ] cada backend continua independente;
[ ] cada backend usa os motores do framework;
[ ] o Gateway usa o GlobalSupervisorRouter do framework;
[ ] o roteamento global é observável;
[ ] cada troca de backend gera metadados e evento de handoff;
[ ] os MCP servers continuam plugáveis por backend/agente;
[ ] a sessão global e a sessão do backend são preservadas no metadata;
[ ] o desenvolvedor consegue testar rota antes de testar execução real.
```

Com esse desenho, adicionar um novo agente não exige reescrever o frontend nem copiar lógica entre backends. O desenvolvedor cria o backend especializado, registra no Agent Gateway e deixa o framework cuidar dos motores transversais.
