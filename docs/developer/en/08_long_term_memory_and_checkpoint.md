### Long-Term Memory and Checkpoint

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **LTM, conversation memory, identity-based isolation, and state persistence**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

LTM, conversation memory, identity-based isolation, and state persistence.

### Consolidated technical content

### Long-Term Memory and Enterprise Checkpointing

Implementation manual for durable memory, identity isolation, stores, extraction, LangGraph integration, persistence testing, and the differences among LTM, history, summary, and checkpoint.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### Complete Long-Term Memory implementation

> Content consolidated from `Documentacao/Manual_Long_Term_Memory_PT.md`.

### Concept

Long-Term Memory (LTM) is the `agent_framework` capability to store and retrieve durable facts beyond the lifetime of a conversation session.

Unlike message history, which is normally associated with a `session_id`, long-term memory is associated with the business identity of the user or customer. In the current implementation, this identity is composed of:

```text
tenant_id
agent_id
customer_key
```

This allows an agent to retrieve preferences, identity information, projects, and constraints even when a new session is created.

### What it is for

Long-Term Memory is used to:

- maintain continuity across sessions;
- personalize responses;
- avoid making the user repeat information already provided;
- reduce the need to send the entire history to the model;
- store preferences, current projects, preferred names, and constraints;
- isolate memory across tenants, agents, and customers.

Example:

```text
Sessão A:
"Me chame de Cris. Minha linguagem preferida é Python."

Sessão B, com outro session_id e o mesmo customer_key:
"O que você lembra sobre mim?"

Resposta esperada:
"Seu nome preferido é Cris e sua linguagem preferida é Python."
```

### Difference among memory types

### Conversation Memory

Maintains messages from the current conversation and is normally associated with `session_id`.

### Summary Memory

Maintains a conversation summary to reduce the amount of context sent to the model.

### Long-Term Memory

Maintains durable facts across sessions and is associated with business identity, especially `customer_key`.

### Feature components

### LongTermMemoryManager

Responsible for coordinating:

- memory loading;
- retrieval by identity;
- context rendering;
- extraction of new facts;
- persistence of facts;
- deduplication and updates.

### LongTermMemoryStore

Persistence interface used by the manager.

### SQLiteLongTermMemoryStore

Reference implementation based on SQLite.

It is appropriate for:

- local development;
- tests;
- demonstrations;
- low-scale environments.

### InMemoryLongTermMemoryStore

In-memory implementation used for quick tests.

Its content is lost when the backend process terminates.

### LongTermMemoryExtractor

Responsible for identifying durable facts in messages.

Examples of facts:

```text
preferred_name = Cris
preferred_language = Python
current_project = Atlas
```

### LongTermMemoryItem

Model representing a persisted item, including identity, key, value, category, confidence, and metadata.

### AgentRuntime

Loads memory before agent execution and injects the context into the prompt.

### `persist_long_term_memory` node

LangGraph node responsible for persisting facts after final-response generation and validation.

### File structure

```text
libs/
└── agent_framework/
    └── src/
        └── agent_framework/
            └── memory/
                ├── __init__.py
                ├── long_term_extractor.py
                ├── long_term_memory.py
                ├── long_term_models.py
                └── long_term_store.py
```

### Execution flow

```text
Mensagem do usuário
        │
        ▼
AgentRuntime.prepare_memory_context()
        │
        ├── Conversation Memory
        ├── Summary Memory
        └── Long-Term Memory
                    │
                    ▼
          long_term_memory_context
                    │
                    ▼
             Prompt do agente
                    │
                    ▼
                 Agente
                    │
                    ▼
       Guardrails / Judges / Supervisor
                    │
                    ▼
       persist_long_term_memory
                    │
                    ▼
          LongTermMemoryExtractor
                    │
                    ▼
           LongTermMemoryStore
```

### Framework configuration

### New modules

Copy the files:

```text
libs/agent_framework/src/agent_framework/memory/long_term_extractor.py
libs/agent_framework/src/agent_framework/memory/long_term_memory.py
libs/agent_framework/src/agent_framework/memory/long_term_models.py
libs/agent_framework/src/agent_framework/memory/long_term_store.py
```

### Updating `memory/__init__.py`

Export the Long-Term Memory components:

```python
from agent_framework.memory.long_term_memory import (
    LongTermMemoryManager,
    create_long_term_memory_manager,
)
from agent_framework.memory.long_term_models import LongTermMemoryItem
from agent_framework.memory.long_term_store import (
    InMemoryLongTermMemoryStore,
    LongTermMemoryStore,
    SQLiteLongTermMemoryStore,
    create_long_term_memory_store,
)
```

### Updating `settings.py`

Add the configurations:

```python
ENABLE_LONG_TERM_MEMORY: bool = False
LONG_TERM_MEMORY_PROVIDER: str = "sqlite"
LONG_TERM_MEMORY_SQLITE_PATH: str = "./data/agent_framework.db"
LONG_TERM_MEMORY_TABLE: str = "agentfw_long_term_memory"
LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS: int = 20
LONG_TERM_MEMORY_MIN_CONFIDENCE: float = 0.70
LONG_TERM_MEMORY_AUTO_EXTRACT: bool = True
LONG_TERM_MEMORY_INJECT_CONTEXT: bool = True
```

### Integration with AgentRuntime

The runtime must:

1. check whether the feature is enabled;
2. create the manager when necessary;
3. retrieve facts by identity;
4. populate state;
5. inject context into the prompt.

Fields added to state:

```python
long_term_memories: list[dict]
long_term_memory_context: str
long_term_memory_write_result: dict
```

### Initialization in AgentWorkflow

The manager must be created in `AgentWorkflow`:

```python
self.long_term_memory_manager = create_long_term_memory_manager(
    settings,
    telemetry=telemetry,
)
```

### Correct agent initialization

`long_term_memory_manager` must not be passed through `agent_kwargs` if the constructors of `BillingAgent`, `ProductAgent`, `OrdersAgent`, and `SupportAgent` do not declare that parameter.

This initialization causes an error:

```python
agent_kwargs = {
    "telemetry": telemetry,
    "settings": settings,
    "memory": memory,
    "summary_memory": summary_memory,
    "long_term_memory_manager": self.long_term_memory_manager,
}

self.billing = BillingAgent(llm, **agent_kwargs)
```

Resulting error:

```text
TypeError: BillingAgent.__init__() got an unexpected keyword argument
'long_term_memory_manager'
```

The recommended form is to create agents using the existing signature and inject the manager as an attribute after initialization:

```python
agent_kwargs = {
    "telemetry": telemetry,
    "tool_router": getattr(self, "tool_router", None),
    "rag_service": self.rag_service,
    "cache": self.cache,
    "settings": settings,
    "observer": self.observer,
    "memory": memory,
    "summary_memory": summary_memory,
}

self.billing = BillingAgent(llm, **agent_kwargs)
self.product = ProductAgent(llm, **agent_kwargs)
self.orders = OrdersAgent(llm, **agent_kwargs)
self.support = SupportAgent(llm, **agent_kwargs)

for agent in (
    self.billing,
    self.product,
    self.orders,
    self.support,
):
    agent.long_term_memory_manager = self.long_term_memory_manager
```

This approach avoids changing every agent constructor and keeps the capability encapsulated in the framework.

### LangGraph configuration

Register the node:

```python
builder.add_node(
    "persist_long_term_memory",
    self._node(
        "persist_long_term_memory",
        self.persist_long_term_memory,
    ),
)
```

Change the flow:

```python
builder.add_edge(
    "supervisor_review",
    "persist_long_term_memory",
)
builder.add_edge(
    "persist_long_term_memory",
    "persist",
)
```

Implement the method:

```python
async def persist_long_term_memory(
    self,
    state: AgentState,
) -> dict[str, object]:
    result = await self.long_term_memory_manager.persist_turn(state)

    return {
        "long_term_memory_write_result": result,
    }
```

Final flow:

```text
supervisor_review
        │
        ▼
persist_long_term_memory
        │
        ▼
persist
```

### Environment variables

```env
ENABLE_LONG_TERM_MEMORY=true

LONG_TERM_MEMORY_PROVIDER=sqlite
LONG_TERM_MEMORY_SQLITE_PATH=./data/agent_framework.db
LONG_TERM_MEMORY_TABLE=agentfw_long_term_memory

LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS=20
LONG_TERM_MEMORY_MIN_CONFIDENCE=0.70
LONG_TERM_MEMORY_AUTO_EXTRACT=true
LONG_TERM_MEMORY_INJECT_CONTEXT=true
```

### SQLite database path

The relative path is resolved from the directory where the backend is started.

To avoid accidentally creating different databases, prefer an absolute path in development environments:

```env
LONG_TERM_MEMORY_SQLITE_PATH=/mnt/c/Asus_Projects/agent_platform_oci_long_term_memory/data/agent_framework.db
```

Create the directory before starting:

```bash
mkdir -p data
```

### How to test

### Test 1 — Write

Send:

```json
{
  "session_id": "default:telecom_contas:memory-session-a",
  "customer_key": "11999999999",
  "message": "Me chame de Cris. Minha linguagem preferida é Python e meu projeto atual se chama Atlas."
}
```

### Test 2 — Retrieval in another session

Use another `session_id`, keeping the same `customer_key`:

```json
{
  "session_id": "default:telecom_contas:memory-session-b",
  "customer_key": "11999999999",
  "message": "O que você lembra sobre mim, minhas preferências e meu projeto?"
}
```

Expected result:

```text
Seu nome preferido é Cris.
Sua linguagem preferida é Python.
Seu projeto atual se chama Atlas.
```

### Test 3 — Isolation

Use another customer:

```json
{
  "session_id": "default:telecom_contas:memory-session-c",
  "customer_key": "outro-cliente",
  "message": "Qual é meu nome preferido e qual é meu projeto atual?"
}
```

The data for `11999999999` must not appear.

### Test 4 — Frontend restart

Restart or reset the frontend and confirm that it continues sending the same `customer_key`.

Memory must survive the `session_id` change. Resetting the frontend does not erase SQLite.

### Test 5 — Backend restart

Restart Uvicorn and repeat the query.

With:

```env
LONG_TERM_MEMORY_PROVIDER=sqlite
```

memory must remain available.

With:

```env
LONG_TERM_MEMORY_PROVIDER=memory
```

memory will be lost when the process terminates.

### Direct verification in SQLite

Locate the database:

```bash
find . -name "agent_framework.db" -type f
```

Open it:

```bash
sqlite3 ./data/agent_framework.db
```

Query it:

```sql
SELECT
    tenant_id,
    agent_id,
    customer_key,
    memory_type,
    memory_key,
    memory_value,
    confidence,
    created_at,
    updated_at
FROM agentfw_long_term_memory
ORDER BY updated_at DESC;
```

### Success criteria

The implementation is working when:

- memory is retrieved with another `session_id`;
- the same `customer_key` retrieves previous facts;
- another `customer_key` cannot access those facts;
- restarting the frontend does not erase memory;
- restarting the backend does not erase memory when the provider is SQLite;
- the `persist_long_term_memory` node executes;
- the prompt receives `long_term_memory_context`.

### Best practices

- Persist only durable facts.
- Do not store the full conversation as Long-Term Memory.
- Isolate data by `tenant_id`, `agent_id`, and `customer_key`.
- Do not use `session_id` as the user's permanent identity.
- Persist only after final validations.
- Avoid storing temporary tool results.
- Record read, write, update, and failure telemetry.
- Define retention and deletion policies.
- Use an absolute SQLite path in environments with multiple execution directories.
- Migrate to an enterprise database for production and high-availability environments.

### Reference-implementation limitations

The current implementation uses rule-based extraction and SQLite as the reference provider.

Recommended evolutions:

- fact extraction with LLM;
- semantic memory with vectors;
- episodic memory;
- expiration and versioning;
- semantic deduplication;
- consent policy;
- query and deletion API;
- Oracle Autonomous Database provider;
- encryption and sensitive-data classification.

### Enterprise Checkpointing in LangGraph

> Content consolidated from `Documentacao/README_CHECKPOINT_ENTERPRISE.md`.

This version adds four capabilities to the LangGraph checkpointer used by the framework:

1. **Checkpoint Integrity**: each checkpoint is stored inside an envelope containing `schema_version`, `checkpoint_id`, SHA-256 `payload_hash`, and `created_at`. On read, the hash is recalculated. If the payload was truncated, changed, or corrupted, the checkpoint is ignored during recovery.
2. **Checkpoint Compaction**: old checkpoints are automatically removed according to `CHECKPOINT_COMPACT_EVERY` and `CHECKPOINT_KEEP_LAST`. This prevents unbounded growth of the `workflow_checkpoints` table.
3. **Resilient Checkpointer**: writes and reads use retry with backoff and jitter. The resilient layer works over memory, SQLite, and Oracle/Autonomous Database.
4. **Checkpoint Recovery**: when restoring state, the framework scans recent checkpoints and returns the newest valid one, skipping corrupted checkpoints.

### Configuration

In `.env`:

```env
CHECKPOINT_REPOSITORY_PROVIDER=sqlite
ENABLE_RESILIENT_CHECKPOINTER=true
ENABLE_CHECKPOINT_INTEGRITY=true
ENABLE_CHECKPOINT_COMPACTION=true
CHECKPOINT_COMPACT_EVERY=50
CHECKPOINT_KEEP_LAST=20
CHECKPOINT_RECOVERY_SCAN_LIMIT=25
CHECKPOINT_RETRY_MAX_ATTEMPTS=3
CHECKPOINT_RETRY_BASE_DELAY_SECONDS=0.05
CHECKPOINT_RETRY_MAX_DELAY_SECONDS=1.0
CHECKPOINT_RETRY_JITTER_SECONDS=0.05
```

For production with multiple pods, prefer:

```env
CHECKPOINT_REPOSITORY_PROVIDER=autonomous
ADB_USER=...
ADB_PASSWORD=...
ADB_DSN=...
ADB_WALLET_LOCATION=...
ADB_TABLE_PREFIX=AGENTFW
```

### Use in LangGraph

```python
from agent_framework.checkpoints import create_langgraph_checkpointer

checkpointer = create_langgraph_checkpointer(settings)
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": session_id}}
result = graph.invoke(input_state, config=config)
```

`thread_id` remains the conversation-recovery key. In an environment with a Load Balancer, any pod can resume execution if it uses the same persistent repository.

### Files changed

- `agent_framework/src/agent_framework/checkpoints/checkpoint_repository.py`
- `agent_framework/src/agent_framework/checkpoints/langgraph_saver.py`
- `agent_framework/src/agent_framework/checkpoints/__init__.py`
- `agent_framework/src/agent_framework/config/settings.py`
- `tests/unit/test_resilient_checkpointer.py`

### Important note

The `memory` provider now also uses `RepositoryCheckpointSaver` when `ENABLE_RESILIENT_CHECKPOINTER=true`. To return to LangGraph's pure `MemorySaver` for local tests, configure:

```env
ENABLE_RESILIENT_CHECKPOINTER=false
CHECKPOINT_REPOSITORY_PROVIDER=memory
```

### Source files

The files below were consolidated into this manual:

- `Documentacao/Manual_Long_Term_Memory_PT.md`
- `Documentacao/README_CHECKPOINT_ENTERPRISE.md`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
