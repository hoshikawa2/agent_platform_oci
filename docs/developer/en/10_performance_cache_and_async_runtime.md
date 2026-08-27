### Performance, Cache, and Async Runtime

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **concurrency, cache, reduction of LLM calls, and cross-loop fixes**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

Concurrency, cache, reduction of LLM calls, and cross-loop fixes.

### Consolidated technical content

### Performance, Cache, Concurrency, and Async Runtime

Manual for optimizations on the critical MCP, RAG, and Judge path, reduction of LLM calls, deterministic preemption, and cross-loop deadlock correction in sequencing.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### MCP, RAG, and Judge optimizations

> Content consolidated from `docs/PERFORMANCE_OPTIMIZATIONS_MCP_JUDGES_RAG.md`.

- `mcp_tools` remains an allowlist; only the query selected through `selection_keywords` is executed.
- `strategy: hybrid` extraction tries a regex `pattern` before the LLM profile.
- RAG is skipped when successful MCP evidence is sufficient, except for policy/rule questions.
- `mcp_results` is provided as evidence to the groundedness judge.
- `judges.yaml` accepts `sample_rate` and `always_run_for_transactional`.
- Simple structured queries can return a deterministic response without invoking the agent LLM.

### Shift from query to transactional action

Route stickiness is preempted when an explicit keyword configured in `routing.yaml` identifies another intent/agent. Thus, a session in `retail_order_tracking` moves to `retail_support_exchange_return` when it receives requests such as “return order”. In addition, direct responses from read-only tools are blocked when the message contains `selection_keywords` from any registered transactional tool.

Action words remain in `config/tools.yaml`; the runtime does not maintain hardcoded domain aliases.


### Deterministic preemption for an explicit intent change

Stickiness does not call a second LLM when the message contains an explicit change that can be recognized deterministically. Multi-token keywords configured in `routing.yaml` accept up to three intermediate tokens while preserving order. Therefore, `cancelar pedido` recognizes `quero cancelar meu pedido`, `cancelar o meu pedido`, and `pode cancelar esse pedido`. In this case the new intent preempts stickiness and the `keyword_match_strategy=ordered_tokens` metadata makes the decision auditable. Messages with no explicit signal continue using route stickiness normally.

### Cross-loop deadlock fix

> Content consolidated from `Documentacao/FIX_DEADLOCK_SEQUENCE_CROSS_LOOP.md`.

### Problem

The synchronous `agent_framework.observer.event()` API could be called from a worker thread with no active event loop. In that case, the previous implementation ran `asyncio.run(aevent(...))`, creating a temporary new event loop. At the same time, `analytics/tim_sequence.py` shared global `asyncio.Lock` instances (`_mongo_index_lock` and `_memory_lock`) across calls that could come from different event loops.

On the first Mongo operation, `_ensure_mongo_ttl_index_once()` held `_mongo_index_lock` while creating the TTL index. Contention from another loop could leave the second call waiting indefinitely.

### Applied changes

1. `observer.py`
   - removed `asyncio.run()` from the synchronous `event()` path;
   - added a dedicated reusable event loop for synchronous calls;
   - cross-thread submission uses `asyncio.run_coroutine_threadsafe()`;
   - best-effort loop shutdown when the process terminates.

2. `analytics/tim_sequence.py`
   - `_mongo_index_lock`: `asyncio.Lock` -> `threading.Lock`;
   - `_memory_lock`: `asyncio.Lock` -> `threading.Lock`;
   - TTL-index initialization moved to a synchronous function protected by a thread lock and called through `asyncio.to_thread()`;
   - the in-memory fallback counter uses a short thread-safe critical section.

3. Tests
   - `tests/test_observer_cross_loop_deadlock_fix.py` validates:
     - multiple worker threads using `event()` share the same synchronous observer loop;
     - in-memory sequence remains monotonic across independent event loops;
     - TTL-index creation happens only once under cross-loop contention.

### Validation performed

```bash
PYTHONPATH=libs/agent_framework/src pytest -q tests/test_observer_cross_loop_deadlock_fix.py
```

Result: `3 passed`.

The full repository suite has pre-existing/independent failures unrelated to this change, including collection conflicts for `test_long_term_memory.py`, static template paths, and checkpoint/workflow tests. Those items were not changed by this fix.

### Operational performance features

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

By default, usage accounting uses SQLite even when everything else is in memory. This makes local testing possible without Oracle.

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

### Final cache, RAG, and telemetry adjustments

> Content consolidated from `Documentacao/README_FIRST_MAX_OPERATIONAL_FIXES.md`.

This version fixes the gaps identified in the comparison against FIRST.

### Applied fixes

### 1. Operational LangGraph checkpoint

The workflow no longer compiles directly with `MemorySaver()`. The following adapter was created:

```text
agent_framework/checkpoints/langgraph_saver.py
```

It connects LangGraph to the framework's configured repository:

- `memory`
- `sqlite`
- `oracle` / `autonomous`

In the workflow:

```python
builder.compile(checkpointer=create_langgraph_checkpointer(self.settings))
```

### 2. LangGraph telemetry wrapping actual execution

A node wrapper was added to the workflow:

```python
self._node("billing_agent", self.billing_agent)
```

This way the `langgraph.node.*` span/event wraps actual node execution, not just an empty block.

Events emitted:

- `langgraph.node.started`
- `langgraph.node.completed`
- `langgraph.node.failed`
- `langgraph.edge.selected`

### 3. RAG integrated into agents

Agents now receive `RagService` and use retrieved context in the prompt:

- BillingAgent
- ProductAgent
- OrdersAgent
- SupportAgent

RAG uses:

- `VECTOR_STORE_PROVIDER=memory|sqlite|oracle|autonomous`
- `GRAPH_STORE_PROVIDER=memory|oracle|autonomous`
- `RAG_TOP_K`

### 4. Cache integrated into agent runtime

The following mixin was created:

```text
agent_template_backend/app/agents/runtime.py
```

It adds:

- standardized RAG retrieval;
- cache key for LLM calls;
- hit/miss with telemetry;
- distributed cache through `create_cache(settings)`.

### 5. Unit tests

The following directory was created:

```text
tests/unit
```

Initial coverage:

- cache;
- SSE;
- RAG;
- checkpoint saver;
- LangGraph telemetry;
- agent runtime;
- static workflow verification;
- main imports.

Local validation performed:

```text
12 passed
```

### How to test

```bash
cd projeto_agent_framework_first_ready
pip install -r agent_template_backend/requirements.txt
pytest -q tests/unit
```

### Source files

The files below were consolidated into this manual:

- `docs/PERFORMANCE_OPTIMIZATIONS_MCP_JUDGES_RAG.md`
- `Documentacao/FIX_DEADLOCK_SEQUENCE_CROSS_LOOP.md`
- `Documentacao/README_MAX_OPERACIONAL.md`
- `Documentacao/README_FIRST_MAX_OPERATIONAL_FIXES.md`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
