### Observability, Persistence, and Operational Readiness

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **telemetry, IC/NOC/GRL, correlation, sequencing, persistence, and operational diagnostics**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

Telemetry, IC/NOC/GRL, correlation, sequencing, persistence, and operational diagnostics.

### Consolidated technical content

### Observability, Persistence, and Operational Readiness

Consolidated guide to FIRST-ready capabilities: end-to-end correlation, Langfuse, OpenTelemetry, observable SSE, Oracle persistence, token/cost accounting, cache, and LangGraph telemetry.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### FIRST-ready foundation and observability

> Content consolidated from `Documentacao/README_FIRST_READY.md`.

This version preserves the `meu_projeto_agent_framework` architecture and adds the operational patterns found in the FIRST project.

### Added features

1. **SSE following the FIRST pattern**
   - `GET /gateway/events/{session_id}` for a `text/event-stream`.
   - `POST /gateway/message/sse` to process a message while emitting SSE events.
   - Events: `connected`, `flow.start`, `session.upserted`, `message.received`, `workflow.started`, `workflow.completed`, `message.responded`, `flow.end`.
   - Keepalive configurable through `SSE_KEEPALIVE_SECONDS`.
   - Per-session lock to prevent concurrency within the same conversation.
   - Event replay through `Last-Event-ID` or the `last_event_id` query parameter.

2. **Session and message persistence**
   - Implemented `sqlite` provider, runnable locally.
   - `SESSION_REPOSITORY_PROVIDER=sqlite`.
   - `MEMORY_REPOSITORY_PROVIDER=sqlite`.
   - Local tables: `agent_sessions`, `agent_messages`.
   - Idempotency by `message_id`.

3. **Persistent checkpoint**
   - Implemented `sqlite` provider for the workflow's final checkpoint.
   - `CHECKPOINT_REPOSITORY_PROVIDER=sqlite`.
   - Read endpoint: `GET /sessions/{session_id}/checkpoint`.

4. **Message history**
   - Endpoint: `GET /sessions/{session_id}/messages`.
   - History is used as conversational memory before invoking LangGraph.

5. **Cache**
   - New module `agent_framework.cache.cache`.
   - Supports local in-memory cache and Redis when `ENABLE_REDIS_CACHE=true`.

6. **RAG / Vector Store**
   - `agent_framework.rag.vector_store` now includes `InMemoryVectorStore`, `SQLiteVectorStore`, and the `AutonomousVectorStore` contract.
   - The SQLite version uses local lexical search for development.
   - The contract allows replacement by Oracle Vector Search without changing the application layer.

7. **Observability**
   - Preserves existing Langfuse integration.
   - Adds gateway/SSE/workflow events with `session_id`, `agent_id`, `tenant_id`, `message_id`, route, and intent.

### Resulting architecture

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

### How to run locally

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

Open:

```text
http://localhost:3000
```

### Main variables

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

### Test with curl

Normal message:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste","message":"teste","session_id":"s1","user_id":"u1","message_id":"m1"}}'
```

Message with SSE:

```bash
curl -N http://localhost:8000/gateway/events/s1
```

In another terminal:

```bash
curl -X POST http://localhost:8000/gateway/message/sse \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste","message":"teste","session_id":"s1","user_id":"u1","message_id":"m2"}}'
```

History:

```bash
curl http://localhost:8000/sessions/s1/messages
```

Checkpoint:

```bash
curl http://localhost:8000/sessions/s1/checkpoint
```

### Important note

The added version is locally executable with SQLite. The `AutonomousSessionRepository`, `DatabaseMessageHistory`, `AutonomousCheckpointRepository`, and `AutonomousVectorStore` classes preserve the Oracle Autonomous Database contract, but in this delivery they use SQLite as the local backend so the project can run and be tested without Oracle infrastructure.

### FIRST-style Observability evolution

This version adds an enterprise observability layer to the framework while keeping reusable components inside `agent_framework`.

### Added components

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

### End-to-end correlation

Each HTTP call creates or propagates `x-request-id`, and the message flow links:

```text
request_id → tenant_id → agent_id → session_id → user_id → channel → message_id → workflow_id
```

The context uses `ContextVar`, so it works across async calls, FastAPI, LangGraph, and LLM providers.

### Langfuse OpenAI auto-instrumentation policy

The official framework template configuration is:

```env
ENABLE_LANGFUSE=true
ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION=false
```

The `false` value is intentional. The framework already records model calls through `Telemetry.generation(...)` and keeps each generation inside the request trace. Enabling `langfuse.openai` at the same time adds a second instrumentation layer and may produce standalone `OpenAI-generation` root traces, duplicate observations, and duplicate token/cost accounting.

Use `true` only to capture direct OpenAI/OpenAI-compatible SDK calls that occur outside the framework telemetry layer. This is a compatibility/diagnostic mode, not the operational default. Every `.env.example` in the repository must explicitly keep the value set to `false`.

### Langfuse

Enable in `.env`:

```env
ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

The framework records:

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

Enable in `.env`:

```env
ENABLE_OTEL=true
OTEL_SERVICE_NAME=agent-framework-template
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
```

With this configuration, the same spans are exported through OTLP to Elastic, Grafana Tempo, Jaeger, Collector, or another compatible backend.

### Observable SSE

`SSEHub` now records events for:

- opened connection;
- event replay;
- emitted event;
- keepalive;
- per-session lock during message processing.

### Guardrails and Judges

In addition to aggregate events (`guardrails.input.completed`, `judges.completed`), each individual decision generates its own telemetry:

```text
guardrail.MSK.evaluated
guardrail.OOS.blocked
judge.response_quality.evaluated
judge.groundedness.evaluated
```

### Extension to other backends

The `Telemetry.event_bus` class allows new handlers to be plugged in without changing the workflow. Example:

```python
async def enviar_para_elastic(event):
    ...

telemetry.event_bus.subscribe(enviar_para_elastic)
```


---

### Complete FIRST Enterprise evolution

This version received the components that were missing to bring the framework closer to the operational standard of the FIRST project:

### Oracle Autonomous Database persistence

Real Oracle providers were added:

- `OracleSessionRepository`
- `OracleMessageHistory`
- `OracleCheckpointRepository`
- `OracleCache`
- `OracleVectorStore`
- `OracleGraphStore`
- `OracleStore`

Tables are created automatically with configurable `ADB_TABLE_PREFIX`:

- `<PREFIX>_AGENT_SESSION`
- `<PREFIX>_AGENT_MESSAGE`
- `<PREFIX>_WORKFLOW_CHECKPOINT`
- `<PREFIX>_WORKFLOW_CHECKPOINT_WRITE`
- `<PREFIX>_WORKFLOW_CHECKPOINT_BLOB`
- `<PREFIX>_SSE_EVENT`
- `<PREFIX>_CACHE_ENTRY`
- `<PREFIX>_RAG_DOCUMENT`
- `<PREFIX>_GRAPH_EDGE`

### Oracle configuration

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

### Enterprise SSE

SSE now includes:

- per-session lock (`SessionLockManager`)
- configurable keepalive
- replay through `Last-Event-ID`
- event persistence in SQLite or Oracle
- connection, replay, keepalive, and disconnection telemetry

Endpoint:

```text
GET /gateway/events/{session_id}?last_event_id=123
```

### LangGraph Deep Telemetry

`LangGraphDeepTelemetry` was added with events:

- `langgraph.node.started`
- `langgraph.node.completed`
- `langgraph.node.failed`
- `langgraph.edge.selected`

These events are sent to Event Bus, Langfuse, and OpenTelemetry when enabled.

### Token and Cost Accounting

The following were added:

- `TokenUsageCollector`
- `CostTracker`
- calculation of `prompt_tokens`, `completion_tokens`, `cached_tokens`, `total_tokens`
- calculation of `cost_usd` and `cost_brl`

Optional configuration:

```env
USD_BRL_RATE=5.0
MODEL_PRICES_JSON={"openai.gpt-4.1":{"input_per_1m":"2.00","output_per_1m":"8.00"}}
```

### Enterprise Cache

Cache is now layered:

```text
L1: InMemory
L2: Redis, SQLite ou Oracle
```

Configuration:

```env
ENABLE_REDIS_CACHE=true
REDIS_URL=redis://localhost:6379/0
```

or:

```env
CACHE_BACKEND_PROVIDER=oracle
```

### Oracle 23ai RAG

`OracleVectorStore` was added, with support for a `VECTOR` column and `VECTOR_DISTANCE()` when an embedding provider is connected.  
Without an embedding provider, it keeps a lexical fallback for local development.

`OracleGraphStore` was also added with an edge table, ready to evolve to PGQL/Property Graph.

### Langfuse

Each LLM call now generates a `generation` with:

- input
- output
- model
- provider
- token usage
- cost metadata

In addition, workflow, guardrail, judge, RAG, cache, checkpoint, SSE, and LangGraph spans are published through the same Event Bus.

### Enterprise Plus extensions

> Content consolidated from `Documentacao/README_FIRST_ENTERPRISE_PLUS.md`.

This version evolves the framework in the four requested areas:

1. **Complete Langfuse Enterprise**
   - `Telemetry.span()` with trace/session/user/metadata/tags.
   - `Telemetry.generation()` with `usage`, token/cost metadata, and Langfuse v2/v3 compatibility.
   - `Telemetry.score()` for judges/evaluations.
   - Arbitrary events are recorded as safe spans to avoid `Unknown observation type` in Langfuse.

2. **Complete Token/Cost Accounting**
   - `TokenUsageCollector` supports `prompt_tokens`, `completion_tokens`, `cached_tokens`, `reasoning_tokens`, and `total_tokens`.
   - Per-model pricing table through `MODEL_PRICES_JSON`.
   - USD→BRL conversion through `USD_BRL_RATE`.
   - Persistence in `UsageRepository` and `/debug/usage` endpoint.

3. **Distributed Redis**
   - `DistributedCache`: L1 memory + L2 Redis/SQLite/Oracle.
   - `RedisCache` with `redis.asyncio` when available and sync fallback.
   - Namespace through `CACHE_KEY_PREFIX`.
   - Cache hit/miss/set/delete telemetry.

4. **Real Oracle Vector + PGQL**
   - `OracleVectorStore` uses `VECTOR_DISTANCE(..., COSINE)` and `TO_VECTOR()` in Oracle 23ai.
   - Automatically attempts to create a vector index when supported.
   - `OracleGraphStore` uses `GRAPH_NODE` and `GRAPH_EDGE` tables.
   - Supports Property Graph creation and `GRAPH_TABLE`/PGQL queries, with SQL fallback.

The SSE duplication problem caused by replay + live queue was also fixed using `max_replayed_id` control in `SSEHub.subscribe()`.

### Tests

```bash
PYTHONPATH=agent_framework/src pytest -q tests/unit
```

Result validated in this generation:

```text
17 passed
```

### Security

The `.env` files were sanitized so they do not contain real keys. Configure your credentials locally before using OCI/Langfuse.

### Delta to FIRST standard

> Content consolidated from `Documentacao/README_FIRST_ENTERPRISE_DELTA.md`.

This version fixes the priorities identified in the comparison with FIRST:

1. Real Oracle Session Repository
2. Real Oracle Message History
3. Real Oracle LangGraph Checkpoint Repository
4. LangGraph Deep Telemetry
5. Token Accounting
6. Cost Accounting
7. SSE Session Lock
8. SSE Replay Buffer
9. SSE KeepAlive
10. Recovery through Last-Event-ID
11. Redis Provider and Distributed Cache
12. Oracle Vector Provider
13. Oracle Graph Provider
14. RAG Telemetry
15. Langfuse Generation Tracking
16. Compatible OpenTelemetry/Event Bus
17. Preserved OCI Streaming Exporter

Domain logic remains generic; the framework does not copy FIRST-specific billing rules.

### Maximum operations and accounting

> Content consolidated from `Documentacao/README_MAX_OPERACIONAL.md`.

This version adds the operational adjustments that were missing to bring the framework closer to the FIRST production standard.

### Adjustments included in this version

### 1. Langfuse Enterprise Adapter

New module:

```text
agent_framework/observability/langfuse_enterprise.py
```

Includes an adapter compatible with Langfuse SDKs v2/v3 for:

- trace updates;
- trace scoring/evaluation;
- prompt registry when supported by the SDK;
- isolation of Langfuse API differences.

### 2. Persistent Token and Cost Accounting

New package:

```text
agent_framework/billing/
```

Includes:

- `UsageRecord`
- `SQLiteUsageRepository`
- `OracleUsageRepository`
- `create_usage_repository(settings)`

The LLM provider now records automatically:

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

New endpoint:

```http
GET /debug/usage
GET /debug/usage?tenant_id=default
GET /debug/usage?session_id=<id>
```

### 3. Operational RAG Service

New module:

```text
agent_framework/rag/rag_service.py
```

Includes:

- `RagService.add_documents()`
- `RagService.retrieve()`
- `RagResult.as_prompt_context()`
- telemetry for latency, document count, top scores, and graph.

### 4. New configuration

Variable added:

```env
USAGE_REPOSITORY_PROVIDER=sqlite
```

Values:

```text
sqlite
oracle
autonomous
```

### 5. Local operational compatibility

By default, usage accounting uses SQLite even when everything else is in memory. This makes it possible to test locally without Oracle.

### Quick test

```bash
cd agent_template_backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Test a message:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"teste","user_id":"u1","session_id":"s1"}}'
```

Check usage/cost:

```bash
curl http://localhost:8000/debug/usage
```

### To run closer to a production pattern

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

For Autonomous Database:

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

### Complementary supervisor validation

> Content consolidated from `docs/docs_GLOBAL_SUPERVISOR_VALIDATION.txt`.

VALIDATION - GLOBAL SUPERVISOR

Implemented changes:

1. Framework
- agent_framework.global_supervisor.models
- agent_framework.global_supervisor.config
- agent_framework.global_supervisor.session_store
- agent_framework.global_supervisor.router
- agent_framework.global_supervisor.client

2. New service
- agent_gateway/app/main.py
- agent_gateway/app/settings.py
- agent_gateway/config/backends.yaml
- agent_gateway/README.md
- agent_gateway/Dockerfile
- agent_gateway/docs/ARQUITETURA_GLOBAL_SUPERVISOR.md

3. Docker Compose
- agent-gateway service added on port 8010.

Validations performed:

- python3 -m compileall -q agent_framework/src/agent_framework/global_supervisor agent_gateway/app
  Result: OK

- Hybrid-routing smoke test:
  Input 1: "My bill is too high" -> billing
  Input 2: "and this amount?" on the same session_id -> billing via active_backend
  Result: OK

- FastAPI app import smoke test:
  from app.main import app, registry, router
  Result: OK

Note:
- The gateway SSE proxy was left as a future step. The `/gateway/message/sse` endpoint already routes and forwards as a normal message; for end-to-end SSE, a proxy from `/gateway/events/{session_id}` to the active backend can be implemented.

### Source files

The files below were consolidated into this manual:

- `Documentacao/README_FIRST_READY.md`
- `Documentacao/README_FIRST_ENTERPRISE_PLUS.md`
- `Documentacao/README_FIRST_ENTERPRISE_DELTA.md`
- `Documentacao/README_MAX_OPERACIONAL.md`
- `docs/docs_GLOBAL_SUPERVISOR_VALIDATION.txt`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
