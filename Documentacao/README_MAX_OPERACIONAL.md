# Projeto Agent Framework — FIRST Operational Max

Esta versão adiciona os ajustes operacionais que faltavam para aproximar o framework do padrão FIRST em produção.

## Ajustes incluídos nesta versão

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

## Teste rápido

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

## Para rodar com padrão mais próximo de produção

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
