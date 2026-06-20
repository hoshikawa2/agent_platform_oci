# Ajustes operacionais finais — padrão FIRST

Esta versão corrige os gaps identificados na comparação contra o FIRST.

## Correções aplicadas

### 1. Checkpoint LangGraph operacional

O workflow não compila mais com `MemorySaver()` diretamente. Foi criado o adaptador:

```text
agent_framework/checkpoints/langgraph_saver.py
```

Ele conecta o LangGraph ao repository configurado do framework:

- `memory`
- `sqlite`
- `oracle` / `autonomous`

No workflow:

```python
builder.compile(checkpointer=create_langgraph_checkpointer(self.settings))
```

### 2. Telemetria LangGraph envolvendo a execução real

Foi adicionado wrapper de nó no workflow:

```python
self._node("billing_agent", self.billing_agent)
```

Assim o span/evento `langgraph.node.*` envolve a execução real do nó, não apenas um bloco vazio.

Eventos emitidos:

- `langgraph.node.started`
- `langgraph.node.completed`
- `langgraph.node.failed`
- `langgraph.edge.selected`

### 3. RAG integrado aos agentes

Os agentes agora recebem `RagService` e usam o contexto recuperado no prompt:

- BillingAgent
- ProductAgent
- OrdersAgent
- SupportAgent

O RAG usa:

- `VECTOR_STORE_PROVIDER=memory|sqlite|oracle|autonomous`
- `GRAPH_STORE_PROVIDER=memory|oracle|autonomous`
- `RAG_TOP_K`

### 4. Cache integrado ao runtime dos agentes

Criado mixin:

```text
agent_template_backend/app/agents/runtime.py
```

Ele adiciona:

- busca RAG padronizada;
- chave de cache para chamada LLM;
- hit/miss com telemetria;
- cache distribuído via `create_cache(settings)`.

### 5. Testes unitários

Criada pasta:

```text
tests/unit
```

Cobertura inicial:

- cache;
- SSE;
- RAG;
- checkpoint saver;
- telemetria LangGraph;
- runtime dos agentes;
- verificação estática do workflow;
- imports principais.

Validação local executada:

```text
12 passed
```

## Como testar

```bash
cd projeto_agent_framework_first_ready
pip install -r agent_template_backend/requirements.txt
pytest -q tests/unit
```
