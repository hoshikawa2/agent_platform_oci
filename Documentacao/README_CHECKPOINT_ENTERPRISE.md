# Checkpoint Enterprise no Agent Framework OCI

Esta versão adiciona quatro capacidades ao checkpointer do LangGraph usado pelo framework:

1. **Checkpoint Integrity**: cada checkpoint é salvo dentro de um envelope com `schema_version`, `checkpoint_id`, `payload_hash` SHA-256 e `created_at`. Na leitura, o hash é recalculado. Se o payload foi truncado, alterado ou corrompido, o checkpoint é ignorado no recovery.
2. **Checkpoint Compaction**: checkpoints antigos são removidos automaticamente conforme a configuração `CHECKPOINT_COMPACT_EVERY` e `CHECKPOINT_KEEP_LAST`. Isso evita crescimento infinito da tabela `workflow_checkpoints`.
3. **Resilient Checkpointer**: gravações e leituras usam retry com backoff e jitter. A camada resiliente funciona sobre memory, SQLite e Oracle/Autonomous Database.
4. **Checkpoint Recovery**: ao recuperar o estado, o framework varre os últimos checkpoints e retorna o mais recente válido, pulando checkpoints corrompidos.

## Configuração

No `.env`:

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

Para produção com múltiplos pods, prefira:

```env
CHECKPOINT_REPOSITORY_PROVIDER=autonomous
ADB_USER=...
ADB_PASSWORD=...
ADB_DSN=...
ADB_WALLET_LOCATION=...
ADB_TABLE_PREFIX=AGENTFW
```

## Uso no LangGraph

```python
from agent_framework.checkpoints import create_langgraph_checkpointer

checkpointer = create_langgraph_checkpointer(settings)
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": session_id}}
result = graph.invoke(input_state, config=config)
```

O `thread_id` continua sendo a chave de recuperação da conversa. Em ambiente com Load Balancer, qualquer pod consegue retomar a execução se usar o mesmo repositório persistente.

## Arquivos alterados

- `agent_framework/src/agent_framework/checkpoints/checkpoint_repository.py`
- `agent_framework/src/agent_framework/checkpoints/langgraph_saver.py`
- `agent_framework/src/agent_framework/checkpoints/__init__.py`
- `agent_framework/src/agent_framework/config/settings.py`
- `tests/unit/test_resilient_checkpointer.py`

## Observação importante

O provider `memory` agora também usa o `RepositoryCheckpointSaver` quando `ENABLE_RESILIENT_CHECKPOINTER=true`. Para voltar ao `MemorySaver` puro do LangGraph em testes locais, configure:

```env
ENABLE_RESILIENT_CHECKPOINTER=false
CHECKPOINT_REPOSITORY_PROVIDER=memory
```
