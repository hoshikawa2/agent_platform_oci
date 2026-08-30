
### Observabilidade, Persistência e Prontidão Operacional

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **telemetria, IC/NOC/GRL, correlação, sequência, persistência e diagnóstico operacional**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

Telemetria, ic/noc/grl, correlação, sequência, persistência e diagnóstico operacional.

### Conteúdo técnico consolidado

### Observabilidade, Persistência e Prontidão Operacional

Guia consolidado das capacidades FIRST-ready: correlação ponta-a-ponta, Langfuse, OpenTelemetry, SSE observável, persistência Oracle, token/cost accounting, cache e telemetria LangGraph.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### Base FIRST-ready e observabilidade

> Conteúdo consolidado a partir de `Documentacao/README_FIRST_READY.md`.

Esta versão mantém a arquitetura do `meu_projeto_agent_framework` e adiciona os padrões operacionais encontrados no projeto FIRST.

### Recursos adicionados

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

### Arquitetura resultante

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

### Como rodar localmente

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

### Variáveis principais

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

### Teste via curl

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

### Observação importante

A versão adicionada é executável localmente com SQLite. As classes `AutonomousSessionRepository`, `DatabaseMessageHistory`, `AutonomousCheckpointRepository` e `AutonomousVectorStore` mantêm o contrato para Oracle Autonomous Database, mas nesta entrega usam SQLite como backend local para permitir rodar e testar sem infraestrutura Oracle.

### Evolução de Observabilidade no padrão FIRST

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

### Política de auto-instrumentação OpenAI no Langfuse

A configuração oficial dos templates do framework é:

```env
ENABLE_LANGFUSE=true
ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION=false
```

O `false` é intencional. O framework já registra as chamadas ao modelo usando `Telemetry.generation(...)` e mantém a generation dentro do trace da requisição. Habilitar simultaneamente `langfuse.openai` cria uma segunda camada de instrumentação e pode resultar em `OpenAI-generation` como trace raiz, observations duplicadas e dupla contabilização de tokens/custos.

Use `true` somente para capturar chamadas diretas ao SDK OpenAI/OpenAI-compatible que ocorram fora da telemetria do framework. Esse é um modo de compatibilidade/diagnóstico, não o padrão operacional. Todos os `.env.example` do repositório devem permanecer explicitamente com o valor `false`.

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

### Evolução FIRST Enterprise Completa

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

### Extensões Enterprise Plus

> Conteúdo consolidado a partir de `Documentacao/README_FIRST_ENTERPRISE_PLUS.md`.

Esta versão evolui o framework nos quatro blocos solicitados:

1. **Langfuse Enterprise completo**
   - `Telemetry.span()` com trace/session/user/metadata/tags.
   - `Telemetry.generation()` com `usage`, token/cost metadata e compatibilidade Langfuse v2/v3.
   - `Telemetry.score()` para judges/avaliações.
   - Eventos arbitrários são registrados como spans seguros para evitar `Unknown observation type` no Langfuse.

2. **Token/Cost Accounting completo**
   - `TokenUsageCollector` suporta `prompt_tokens`, `completion_tokens`, `cached_tokens`, `reasoning_tokens` e `total_tokens`.
   - Tabela de preços por modelo via `MODEL_PRICES_JSON`.
   - Conversão USD→BRL via `USD_BRL_RATE`.
   - Persistência em `UsageRepository` e endpoint `/debug/usage`.

3. **Redis distribuído**
   - `DistributedCache`: L1 memória + L2 Redis/SQLite/Oracle.
   - `RedisCache` com `redis.asyncio` quando disponível e fallback sync.
   - Namespace por `CACHE_KEY_PREFIX`.
   - Telemetria de cache hit/miss/set/delete.

4. **Oracle Vector + PGQL reais**
   - `OracleVectorStore` usa `VECTOR_DISTANCE(..., COSINE)` e `TO_VECTOR()` no Oracle 23ai.
   - Tentativa automática de criar vector index quando suportado.
   - `OracleGraphStore` usa tabelas `GRAPH_NODE` e `GRAPH_EDGE`.
   - Suporte a criação de Property Graph e consulta por `GRAPH_TABLE`/PGQL, com fallback SQL.

Também foi corrigido o problema de duplicação SSE por replay + fila live usando controle de `max_replayed_id` no `SSEHub.subscribe()`.

### Testes

```bash
PYTHONPATH=agent_framework/src pytest -q tests/unit
```

Resultado validado nesta geração:

```text
17 passed
```

### Segurança

Os arquivos `.env` foram higienizados para não conter chaves reais. Configure suas credenciais localmente antes de usar OCI/Langfuse.

### Delta para padrão FIRST

> Conteúdo consolidado a partir de `Documentacao/README_FIRST_ENTERPRISE_DELTA.md`.

Esta versão corrige as prioridades levantadas na comparação com o FIRST:

1. Oracle Session Repository real
2. Oracle Message History real
3. Oracle LangGraph Checkpoint Repository real
4. LangGraph Deep Telemetry
5. Token Accounting
6. Cost Accounting
7. Session Lock SSE
8. Replay Buffer SSE
9. KeepAlive SSE
10. Recovery por Last-Event-ID
11. Redis Provider e Distributed Cache
12. Oracle Vector Provider
13. Oracle Graph Provider
14. RAG Telemetry
15. Langfuse Generation Tracking
16. OpenTelemetry/Event Bus compatível
17. OCI Streaming Exporter preservado

A lógica de domínio continua genérica; o framework não copia regras específicas de cobrança do FIRST.

### Operação máxima e contabilização

> Conteúdo consolidado a partir de `Documentacao/README_MAX_OPERACIONAL.md`.

Esta versão adiciona os ajustes operacionais que faltavam para aproximar o framework do padrão FIRST em produção.

### Ajustes incluídos nesta versão

### 1. Langfuse Enterprise Adapter
Novo módulo:

```text
agent_framework/observability/langfuse_enterprise.py
```

Inclui adaptador compatível com SDKs Langfuse v2/v3 para:

- atualização de trace;
- score/avaliação de trace;
- prompt registry quando suportado pelo SDK;
- isolamento das diferenças de API do Langfuse.

### 2. Token e Cost Accounting persistente
Novo pacote:

```text
agent_framework/billing/
```

Inclui:

- `UsageRecord`
- `SQLiteUsageRepository`
- `OracleUsageRepository`
- `create_usage_repository(settings)`

O provider LLM agora registra automaticamente:

- `prompt_tokens`
- `completion_tokens`
- `cached_tokens`
- `total_tokens`
- `cost_usd`
- `cost_brl`
- `tenant_id`
- `agent_id`
- `session_id`
- `message_id`

Novo endpoint:

```http
GET /debug/usage
GET /debug/usage?tenant_id=default
GET /debug/usage?session_id=<id>
```

### 3. RAG Service operacional
Novo módulo:

```text
agent_framework/rag/rag_service.py
```

Inclui:

- `RagService.add_documents()`
- `RagService.retrieve()`
- `RagResult.as_prompt_context()`
- telemetria de latência, quantidade de documentos, top scores e grafo.

### 4. Configuração nova
Variável adicionada:

```env
USAGE_REPOSITORY_PROVIDER=sqlite
```

Valores:

```text
sqlite
oracle
autonomous
```

### 5. Compatibilidade operacional local
Por padrão, a contabilização de uso usa SQLite mesmo que o restante esteja em memória. Assim é possível testar localmente sem Oracle.

### Teste rápido

```bash
cd agent_template_backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Teste uma mensagem:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste","user_id":"u1","session_id":"s1"}}'
```

Verifique uso/custo:

```bash
curl http://localhost:8000/debug/usage
```

### Para rodar com padrão mais próximo de produção

```env
SESSION_REPOSITORY_PROVIDER=sqlite
MEMORY_REPOSITORY_PROVIDER=sqlite
CHECKPOINT_REPOSITORY_PROVIDER=sqlite
USAGE_REPOSITORY_PROVIDER=sqlite
CACHE_BACKEND_PROVIDER=sqlite
VECTOR_STORE_PROVIDER=sqlite
ENABLE_LANGFUSE=true
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

Para Autonomous Database:

```env
SESSION_REPOSITORY_PROVIDER=oracle
MEMORY_REPOSITORY_PROVIDER=oracle
CHECKPOINT_REPOSITORY_PROVIDER=oracle
USAGE_REPOSITORY_PROVIDER=oracle
CACHE_BACKEND_PROVIDER=oracle
VECTOR_STORE_PROVIDER=oracle
GRAPH_STORE_PROVIDER=oracle
ADB_USER=...
ADB_PASSWORD=...
ADB_DSN=...
ADB_WALLET_LOCATION=...
ADB_TABLE_PREFIX=AGENTFW
```

### Validação complementar do supervisor

> Conteúdo consolidado a partir de `docs/docs_GLOBAL_SUPERVISOR_VALIDATION.txt`.

VALIDAÇÃO - GLOBAL SUPERVISOR

Alterações implementadas:

1. Framework
- agent_framework.global_supervisor.models
- agent_framework.global_supervisor.config
- agent_framework.global_supervisor.session_store
- agent_framework.global_supervisor.router
- agent_framework.global_supervisor.client

2. Novo serviço
- agent_gateway/app/main.py
- agent_gateway/app/settings.py
- agent_gateway/config/backends.yaml
- agent_gateway/README.md
- agent_gateway/Dockerfile
- agent_gateway/docs/ARQUITETURA_GLOBAL_SUPERVISOR.md

3. Docker Compose
- serviço agent-gateway adicionado na porta 8010.

Validações executadas:

- python3 -m compileall -q agent_framework/src/agent_framework/global_supervisor agent_gateway/app
  Resultado: OK

- Smoke test do roteamento híbrido:
  Entrada 1: "Minha fatura veio alta" -> contas
  Entrada 2: "e esse valor?" na mesma session_id -> contas por active_backend
  Resultado: OK

- Smoke test de import do app FastAPI:
  from app.main import app, registry, router
  Resultado: OK

Observação:
- O proxy SSE do gateway foi deixado como etapa futura. O endpoint /gateway/message/sse já roteia e encaminha como mensagem normal; para SSE fim-a-fim, pode-se implementar proxy de /gateway/events/{session_id} para o backend ativo.

### Arquivos de origem

Os arquivos abaixo foram consolidados neste manual:

- `Documentacao/README_FIRST_READY.md`
- `Documentacao/README_FIRST_ENTERPRISE_PLUS.md`
- `Documentacao/README_FIRST_ENTERPRISE_DELTA.md`
- `Documentacao/README_MAX_OPERACIONAL.md`
- `docs/docs_GLOBAL_SUPERVISOR_VALIDATION.txt`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.
