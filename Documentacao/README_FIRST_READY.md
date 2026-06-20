# Projeto Agent Framework FIRST-ready

Esta versão mantém a arquitetura do `meu_projeto_agent_framework` e adiciona os padrões operacionais encontrados no projeto FIRST.

## Recursos adicionados

1. **SSE no padrão FIRST**
   - `GET /gateway/events/{session_id}` para stream `text/event-stream`.
   - `POST /gateway/message/sse` para processar mensagem emitindo eventos SSE.
   - Eventos: `connected`, `flow.start`, `session.upserted`, `message.received`, `workflow.started`, `workflow.completed`, `message.responded`, `flow.end`.
   - Keepalive configurável por `SSE_KEEPALIVE_SECONDS`.
   - Lock por sessão para evitar concorrência dentro da mesma conversa.
   - Replay de eventos via `Last-Event-ID` ou query param `last_event_id`.

2. **Persistência de sessão e mensagens**
   - Implementado provider `sqlite`, executável localmente.
   - `SESSION_REPOSITORY_PROVIDER=sqlite`.
   - `MEMORY_REPOSITORY_PROVIDER=sqlite`.
   - Tabelas locais: `agent_sessions`, `agent_messages`.
   - Idempotência por `message_id`.

3. **Checkpoint persistente**
   - Implementado provider `sqlite` para checkpoint final do workflow.
   - `CHECKPOINT_REPOSITORY_PROVIDER=sqlite`.
   - Endpoint de leitura: `GET /sessions/{session_id}/checkpoint`.

4. **Histórico de mensagens**
   - Endpoint: `GET /sessions/{session_id}/messages`.
   - Histórico usado como memória conversacional antes de chamar o LangGraph.

5. **Cache**
   - Novo módulo `agent_framework.cache.cache`.
   - Suporta cache local em memória e Redis se `ENABLE_REDIS_CACHE=true`.

6. **RAG / Vector Store**
   - `agent_framework.rag.vector_store` agora possui `InMemoryVectorStore`, `SQLiteVectorStore` e contrato `AutonomousVectorStore`.
   - A versão SQLite usa busca lexical local para desenvolvimento.
   - O contrato permite trocar por Oracle Vector Search sem alterar a camada de aplicação.

7. **Observabilidade**
   - Mantém Langfuse existente.
   - Acrescenta eventos de gateway/SSE/workflow com `session_id`, `agent_id`, `tenant_id`, `message_id`, rota e intenção.

## Arquitetura resultante

```text
Browser
  |-- POST /gateway/message/sse
  |-- GET  /gateway/events/{session_id}
        |
FastAPI Template Backend
        |
ChannelGateway
        |
SessionRepository + MessageHistory + CheckpointRepository
        |
LangGraph AgentWorkflow
        |
Guardrails -> Router/Supervisor -> Agent -> Output Guardrails -> Judges
        |
Telemetry / Langfuse / OCI Streaming
```

## Como rodar localmente

```bash
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ../agent_framework
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd agent_frontend
python -m http.server 3000
```

Abra:

```text
http://localhost:3000
```

## Variáveis principais

```env
SESSION_REPOSITORY_PROVIDER=sqlite
MEMORY_REPOSITORY_PROVIDER=sqlite
CHECKPOINT_REPOSITORY_PROVIDER=sqlite
VECTOR_STORE_PROVIDER=sqlite
SQLITE_DB_PATH=./data/agent_framework.db
ENABLE_SSE=true
SSE_KEEPALIVE_SECONDS=15
ENABLE_MESSAGE_IDEMPOTENCY=true
```

## Teste via curl

Mensagem normal:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste","message":"teste","session_id":"s1","user_id":"u1","message_id":"m1"}}'
```

Mensagem com SSE:

```bash
curl -N http://localhost:8000/gateway/events/s1
```

Em outro terminal:

```bash
curl -X POST http://localhost:8000/gateway/message/sse \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste","message":"teste","session_id":"s1","user_id":"u1","message_id":"m2"}}'
```

Histórico:

```bash
curl http://localhost:8000/sessions/s1/messages
```

Checkpoint:

```bash
curl http://localhost:8000/sessions/s1/checkpoint
```

## Observação importante

A versão adicionada é executável localmente com SQLite. As classes `AutonomousSessionRepository`, `DatabaseMessageHistory`, `AutonomousCheckpointRepository` e `AutonomousVectorStore` mantêm o contrato para Oracle Autonomous Database, mas nesta entrega usam SQLite como backend local para permitir rodar e testar sem infraestrutura Oracle.

## Evolução de Observabilidade no padrão FIRST

Esta versão adiciona uma camada corporativa de observabilidade ao framework, mantendo os componentes reutilizáveis dentro de `agent_framework`.

### Componentes adicionados

```text
agent_framework/observability/
├── context.py             # ContextVar: request_id, session_id, user_id, tenant_id, agent_id, channel, ura_call_id, workflow_id, message_id
├── telemetry.py           # Facade central: span, event, generation, rag_event, cache_event, checkpoint_event
├── event_bus.py           # Event bus interno para plugar logs, SSE, OCI Streaming, Elastic, Phoenix etc.
├── otel.py                # OpenTelemetry opcional via OTLP
├── workflow_events.py     # workflow.started, node.started, node.completed, edge.selected, workflow.failed
├── guardrail_events.py    # guardrail.<CODE>.evaluated e guardrail.<CODE>.blocked
├── judge_events.py        # judge.<NAME>.evaluated
├── streaming_events.py    # sse.connected, sse.keepalive, sse.event.emitted
└── decorators.py          # decorator @traced para classes do framework
```

### Correlação ponta-a-ponta

Cada chamada HTTP cria ou propaga `x-request-id` e o fluxo de mensagem vincula:

```text
request_id → tenant_id → agent_id → session_id → user_id → channel → message_id → workflow_id
```

O contexto usa `ContextVar`, portanto funciona em chamadas assíncronas, FastAPI, LangGraph e providers LLM.

### Langfuse

Ative no `.env`:

```env
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

O framework registra:

```text
Trace de conversa
├── http.request
├── agent.gateway_message
├── workflow.langgraph.ainvoke
├── workflow.input_guardrails
│   └── guardrail.<CODE>.evaluated / blocked
├── workflow.routing_decision
├── workflow.agent.<agent>
│   └── generation.<model>
├── workflow.output_guardrails
├── workflow.judge
│   └── judge.<NAME>.evaluated
├── workflow.supervisor_review
├── workflow.persist
└── sse.event.emitted / sse.keepalive
```

### OpenTelemetry

Ative no `.env`:

```env
ENABLE_OTEL=true
OTEL_SERVICE_NAME=agent-framework-template
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

Com isso, os mesmos spans são exportados via OTLP para Elastic, Grafana Tempo, Jaeger, Collector ou outro backend compatível.

### SSE observável

O `SSEHub` agora registra eventos de:

- conexão aberta;
- replay de eventos;
- evento emitido;
- keepalive;
- lock por sessão no processamento de mensagem.

### Guardrails e Judges

Além dos eventos agregados (`guardrails.input.completed`, `judges.completed`), cada decisão individual gera telemetria própria:

```text
guardrail.MSK.evaluated
guardrail.OOS.blocked
judge.response_quality.evaluated
judge.groundedness.evaluated
```

### Extensão para outros backends

A classe `Telemetry.event_bus` permite plugar novos handlers sem alterar o workflow. Exemplo:

```python
async def enviar_para_elastic(event):
    ...

telemetry.event_bus.subscribe(enviar_para_elastic)
```


---

## Evolução FIRST Enterprise Completa

Esta versão recebeu os componentes que faltavam para aproximar o framework do padrão operacional do projeto FIRST:

### Persistência Oracle Autonomous Database

Foram adicionados providers reais Oracle:

- `OracleSessionRepository`
- `OracleMessageHistory`
- `OracleCheckpointRepository`
- `OracleCache`
- `OracleVectorStore`
- `OracleGraphStore`
- `OracleStore`

Tabelas criadas automaticamente com prefixo configurável `ADB_TABLE_PREFIX`:

- `<PREFIX>_AGENT_SESSION`
- `<PREFIX>_AGENT_MESSAGE`
- `<PREFIX>_WORKFLOW_CHECKPOINT`
- `<PREFIX>_WORKFLOW_CHECKPOINT_WRITE`
- `<PREFIX>_WORKFLOW_CHECKPOINT_BLOB`
- `<PREFIX>_SSE_EVENT`
- `<PREFIX>_CACHE_ENTRY`
- `<PREFIX>_RAG_DOCUMENT`
- `<PREFIX>_GRAPH_EDGE`

### Configuração Oracle

```env
SESSION_REPOSITORY_PROVIDER=oracle
MEMORY_REPOSITORY_PROVIDER=oracle
CHECKPOINT_REPOSITORY_PROVIDER=oracle
CACHE_BACKEND_PROVIDER=oracle
VECTOR_STORE_PROVIDER=oracle
GRAPH_STORE_PROVIDER=oracle
SSE_STORE_PROVIDER=oracle

ADB_USER=ADMIN
ADB_PASSWORD=***
ADB_DSN=meu_adb_high
ADB_WALLET_LOCATION=/path/wallet
ADB_WALLET_PASSWORD=***
ADB_TABLE_PREFIX=AGENTFW
```

### SSE Enterprise

O SSE agora possui:

- lock por sessão (`SessionLockManager`)
- keepalive configurável
- replay por `Last-Event-ID`
- persistência de eventos em SQLite ou Oracle
- telemetria de conexão, replay, keepalive e desconexão

Endpoint:

```text
GET /gateway/events/{session_id}?last_event_id=123
```

### LangGraph Deep Telemetry

Foi adicionado `LangGraphDeepTelemetry` com eventos:

- `langgraph.node.started`
- `langgraph.node.completed`
- `langgraph.node.failed`
- `langgraph.edge.selected`

Esses eventos são enviados para o Event Bus, Langfuse e OpenTelemetry quando habilitados.

### Token e Cost Accounting

Foi adicionado:

- `TokenUsageCollector`
- `CostTracker`
- cálculo de `prompt_tokens`, `completion_tokens`, `cached_tokens`, `total_tokens`
- cálculo de `cost_usd` e `cost_brl`

Configuração opcional:

```env
USD_BRL_RATE=5.0
MODEL_PRICES_JSON={"openai.gpt-4.1":{"input_per_1m":"2.00","output_per_1m":"8.00"}}
```

### Cache Enterprise

O cache agora é em cascata:

```text
L1: InMemory
L2: Redis, SQLite ou Oracle
```

Configuração:

```env
ENABLE_REDIS_CACHE=true
REDIS_URL=redis://localhost:6379/0
```

ou:

```env
CACHE_BACKEND_PROVIDER=oracle
```

### RAG Oracle 23ai

Foi adicionado `OracleVectorStore`, com suporte a coluna `VECTOR` e `VECTOR_DISTANCE()` quando um embedding provider for conectado.
Sem embedding provider, mantém fallback lexical para desenvolvimento local.

Também foi adicionado `OracleGraphStore` com tabela de arestas, pronto para evoluir para PGQL/Property Graph.

### Langfuse

Cada chamada LLM agora gera `generation` com:

- input
- output
- model
- provider
- token usage
- cost metadata

Além disso, spans de workflow, guardrails, judges, RAG, cache, checkpoint, SSE e LangGraph são publicados pelo mesmo Event Bus.

