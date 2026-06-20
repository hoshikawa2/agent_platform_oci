# Agent Framework FIRST Enterprise Plus

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

## Testes

```bash
PYTHONPATH=agent_framework/src pytest -q tests/unit
```

Resultado validado nesta geração:

```text
17 passed
```

## Segurança

Os arquivos `.env` foram higienizados para não conter chaves reais. Configure suas credenciais localmente antes de usar OCI/Langfuse.
