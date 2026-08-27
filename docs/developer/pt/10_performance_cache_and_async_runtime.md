
### Performance, Cache e Runtime Assíncrono

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **concorrência, cache, redução de chamadas LLM e correções cross-loop**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

Concorrência, cache, redução de chamadas llm e correções cross-loop.

### Conteúdo técnico consolidado

### Performance, Cache, Concorrência e Runtime Assíncrono

Manual das otimizações no caminho crítico de MCP, RAG e Judges, redução de chamadas LLM, preempção determinística e correção de deadlock cross-loop no sequenciamento.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### Otimizações MCP, RAG e Judges

> Conteúdo consolidado a partir de `docs/PERFORMANCE_OPTIMIZATIONS_MCP_JUDGES_RAG.md`.

- `mcp_tools` permanece allowlist; somente a consulta selecionada por `selection_keywords` é executada.
- Extração `strategy: hybrid` tenta `pattern` regex antes do perfil LLM.
- RAG é ignorado quando MCP bem-sucedido é suficiente, salvo perguntas de política/regra.
- `mcp_results` é fornecido como evidência ao groundedness judge.
- `judges.yaml` aceita `sample_rate` e `always_run_for_transactional`.
- Consultas estruturadas simples podem retornar resposta determinística sem LLM do agente.

### Mudança de consulta para ação transacional

A route stickiness é preemptada quando uma keyword explícita configurada em `routing.yaml` identifica outra intent/agente. Assim, uma sessão em `retail_order_tracking` muda para `retail_support_exchange_return` ao receber pedidos como “devolver pedido”. Além disso, respostas diretas de tools read-only são bloqueadas quando a mensagem contém `selection_keywords` de qualquer tool transacional registrada.

As palavras de ação ficam em `config/tools.yaml`; o runtime não mantém aliases de domínio hardcoded.


### Preempção determinística de mudança explícita de intent

A stickiness não chama um segundo LLM quando a mensagem contém uma mudança explícita que pode ser reconhecida deterministicamente. Keywords multi-token configuradas em `routing.yaml` aceitam até três tokens intermediários, preservando a ordem. Assim, `cancelar pedido` reconhece `quero cancelar meu pedido`, `cancelar o meu pedido` e `pode cancelar esse pedido`. Nesse caso a nova intent preempta a stickiness e o metadado `keyword_match_strategy=ordered_tokens` permite auditar a decisão. Mensagens sem sinal explícito continuam usando a route stickiness normalmente.

### Correção de deadlock cross-loop

> Conteúdo consolidado a partir de `Documentacao/FIX_DEADLOCK_SEQUENCE_CROSS_LOOP.md`.

### Problema

A API síncrona `agent_framework.observer.event()` podia ser chamada em uma worker thread sem event loop ativo. Nesse caso, a implementação anterior executava `asyncio.run(aevent(...))`, criando um novo event loop temporário. Ao mesmo tempo, `analytics/tim_sequence.py` compartilhava instâncias globais de `asyncio.Lock` (`_mongo_index_lock` e `_memory_lock`) entre chamadas que podiam vir de event loops diferentes.

Na primeira operação Mongo, `_ensure_mongo_ttl_index_once()` mantinha `_mongo_index_lock` durante a criação do índice TTL. A contenção por outro loop podia deixar a segunda chamada aguardando indefinidamente.

### Alterações aplicadas

1. `observer.py`
   - removido `asyncio.run()` do caminho síncrono de `event()`;
   - adicionado um event loop dedicado e reutilizável para chamadas síncronas;
   - submissão cross-thread feita com `asyncio.run_coroutine_threadsafe()`;
   - encerramento best-effort do loop no shutdown do processo.

2. `analytics/tim_sequence.py`
   - `_mongo_index_lock`: `asyncio.Lock` -> `threading.Lock`;
   - `_memory_lock`: `asyncio.Lock` -> `threading.Lock`;
   - inicialização do índice TTL movida para uma função síncrona protegida por lock de thread e chamada via `asyncio.to_thread()`;
   - o contador de fallback em memória usa uma seção crítica curta e thread-safe.

3. Testes
   - `tests/test_observer_cross_loop_deadlock_fix.py` valida:
     - múltiplas worker threads usando `event()` compartilham o mesmo loop síncrono do observer;
     - sequence em memória permanece monotônica entre event loops independentes;
     - criação do índice TTL ocorre apenas uma vez sob contenção cross-loop.

### Validação executada

```bash
PYTHONPATH=libs/agent_framework/src pytest -q tests/test_observer_cross_loop_deadlock_fix.py
```

Resultado: `3 passed`.

A suíte completa do repositório possui falhas preexistentes/independentes desta alteração, incluindo conflitos de coleta de arquivos `test_long_term_memory.py`, caminhos estáticos de template e testes de checkpoint/workflow. Esses itens não foram alterados por esta correção.

### Recursos operacionais de performance

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

### Ajustes finais de cache, RAG e telemetria

> Conteúdo consolidado a partir de `Documentacao/README_FIRST_MAX_OPERATIONAL_FIXES.md`.

Esta versão corrige os gaps identificados na comparação contra o FIRST.

### Correções aplicadas

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

### Como testar

```bash
cd projeto_agent_framework_first_ready
pip install -r agent_template_backend/requirements.txt
pytest -q tests/unit
```

### Arquivos de origem

Os arquivos abaixo foram consolidados neste manual:

- `docs/PERFORMANCE_OPTIMIZATIONS_MCP_JUDGES_RAG.md`
- `Documentacao/FIX_DEADLOCK_SEQUENCE_CROSS_LOOP.md`
- `Documentacao/README_MAX_OPERACIONAL.md`
- `Documentacao/README_FIRST_MAX_OPERATIONAL_FIXES.md`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.
