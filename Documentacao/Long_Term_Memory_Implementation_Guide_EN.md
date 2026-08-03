### Long-Term Memory Implementation Guide

### Concept

Long-Term Memory (LTM) is the `agent_framework` capability that stores and retrieves durable facts beyond the lifetime of a conversation session.

Unlike message history, which is normally associated with a `session_id`, Long-Term Memory is associated with the business identity of the user or customer. In the current implementation, this identity consists of:

```text
tenant_id
agent_id
customer_key
```

This allows an agent to retrieve preferences, identity information, projects and constraints even when a new session is created.

### Purpose

Long-Term Memory is used to:

- maintain continuity across sessions;
- personalize responses;
- prevent users from repeating previously supplied information;
- reduce the need to send the full conversation history to the model;
- store preferences, current projects, preferred names and constraints;
- isolate memory across tenants, agents and customers.

Example:

```text
Session A:
"Call me Cris. My preferred language is Python."

Session B, with another session_id and the same customer_key:
"What do you remember about me?"

Expected response:
"Your preferred name is Cris and your preferred language is Python."
```

### Memory type differences

#### Conversation Memory

Stores messages from the current conversation and is normally associated with the `session_id`.

#### Summary Memory

Stores a summary of the conversation to reduce the context size sent to the model.

#### Long-Term Memory

Stores durable facts across sessions and is associated with the business identity, primarily the `customer_key`.

### Components

#### LongTermMemoryManager

Coordinates:

- memory loading;
- identity-based retrieval;
- context rendering;
- durable fact extraction;
- fact persistence;
- deduplication and updates.

#### LongTermMemoryStore

Persistence interface used by the manager.

#### SQLiteLongTermMemoryStore

Reference implementation based on SQLite.

It is suitable for:

- local development;
- testing;
- demonstrations;
- low-scale environments.

#### InMemoryLongTermMemoryStore

In-memory implementation used for quick tests.

Its content is lost when the backend process stops.

#### LongTermMemoryExtractor

Identifies durable facts in messages.

Examples:

```text
preferred_name = Cris
preferred_language = Python
current_project = Atlas
```

#### LongTermMemoryItem

Data model representing a persisted item, including identity, key, value, category, confidence and metadata.

#### AgentRuntime

Loads memory before agent execution and injects the rendered context into the prompt.

#### persist_long_term_memory node

LangGraph node responsible for persisting facts after the final response has been generated and validated.

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
User message
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
            Agent prompt
                 │
                 ▼
               Agent
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

Copy:

```text
libs/agent_framework/src/agent_framework/memory/long_term_extractor.py
libs/agent_framework/src/agent_framework/memory/long_term_memory.py
libs/agent_framework/src/agent_framework/memory/long_term_models.py
libs/agent_framework/src/agent_framework/memory/long_term_store.py
```

### Update memory/__init__.py

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

### Update settings.py

Add:

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

### AgentRuntime integration

The runtime must:

1. verify that the feature is enabled;
2. create the manager when needed;
3. retrieve facts using the identity;
4. populate the workflow state;
5. inject the rendered context into the prompt.

State fields:

```python
long_term_memories: list[dict]
long_term_memory_context: str
long_term_memory_write_result: dict
```

### AgentWorkflow initialization

Create the manager in `AgentWorkflow`:

```python
self.long_term_memory_manager = create_long_term_memory_manager(
    settings,
    telemetry=telemetry,
)
```

### Correct agent initialization

Do not pass `long_term_memory_manager` through `agent_kwargs` when the constructors of `BillingAgent`, `ProductAgent`, `OrdersAgent` and `SupportAgent` do not declare that parameter.

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

The recommended approach is to create agents using their existing signatures and inject the manager as an attribute after initialization:

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

This approach avoids changing every agent constructor and keeps the feature encapsulated in the framework.

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

Update the edges:

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

Implement:

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

A relative path is resolved from the directory in which the backend is started.

To prevent different databases from being created accidentally, prefer an absolute path in development environments:

```env
LONG_TERM_MEMORY_SQLITE_PATH=/mnt/c/Asus_Projects/agent_platform_oci_long_term_memory/data/agent_framework.db
```

Create the directory before starting:

```bash
mkdir -p data
```

### Testing

### Test 1 — Persistence

Send:

```json
{
  "session_id": "default:telecom_contas:memory-session-a",
  "customer_key": "11999999999",
  "message": "Call me Cris. My preferred language is Python and my current project is Atlas."
}
```

### Test 2 — Retrieval in another session

Use another `session_id` while keeping the same `customer_key`:

```json
{
  "session_id": "default:telecom_contas:memory-session-b",
  "customer_key": "11999999999",
  "message": "What do you remember about me, my preferences and my project?"
}
```

Expected result:

```text
Your preferred name is Cris.
Your preferred language is Python.
Your current project is Atlas.
```

### Test 3 — Isolation

Use another customer:

```json
{
  "session_id": "default:telecom_contas:memory-session-c",
  "customer_key": "another-customer",
  "message": "What is my preferred name and current project?"
}
```

The data associated with `11999999999` must not be returned.

### Test 4 — Frontend reset

Restart or reset the frontend and verify that it still sends the same `customer_key`.

Memory must survive a `session_id` change. Resetting the frontend does not delete the SQLite database.

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

memory is lost when the process stops.

### Direct SQLite verification

Find the database:

```bash
find . -name "agent_framework.db" -type f
```

Open it:

```bash
sqlite3 ./data/agent_framework.db
```

Query:

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
- restarting the backend does not erase memory when using SQLite;
- the `persist_long_term_memory` node runs;
- the prompt receives `long_term_memory_context`.

### Best practices

- Persist only durable facts.
- Do not store the complete conversation as Long-Term Memory.
- Isolate data by `tenant_id`, `agent_id` and `customer_key`.
- Do not use `session_id` as the permanent user identity.
- Persist only after final validations.
- Avoid persisting temporary tool results.
- Record telemetry for reads, writes, updates and failures.
- Define retention and deletion policies.
- Use an absolute SQLite path in environments with multiple working directories.
- Move to an enterprise database for production and high-availability environments.

### Reference implementation limitations

The current implementation uses rule-based extraction and SQLite as the reference provider.

Recommended future enhancements:

- LLM-based fact extraction;
- vector-based semantic memory;
- episodic memory;
- expiration and versioning;
- semantic deduplication;
- consent policies;
- query and deletion APIs;
- Oracle Autonomous Database provider;
- encryption and sensitive-data classification.
