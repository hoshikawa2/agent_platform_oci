
### RAG, BusinessContext e Grounding

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **RAG, providers, BusinessContext, contexto recuperado e grounding**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

Rag, providers, businesscontext, contexto recuperado e grounding.

### Conteúdo técnico consolidado

### RAG, Providers Enterprise, BusinessContext e Grounding

Guia de integração de conhecimento recuperado, seleção entre providers de RAG, configuração KBDB, amostras, suficiência MCP e uso do BusinessContext como contrato de dados.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### Provider RAG Standard versus KBDB Enterprise

> Conteúdo consolidado a partir de `docs/RAG_PROVIDER_KBDB.md`.

O framework passa a suportar dois backends de retrieval pelo mesmo contrato `RagService`, sem alterar os agentes nem `_retrieve_rag_context()`.

### Seleção

```env
RAG_PROVIDER=standard  # default: comportamento anterior
# ou
RAG_PROVIDER=kbdb      # KBDB enterprise
```

A seleção é exclusiva por processo. Os dois RAGs não executam juntos e não compartilham vector store, graph store ou ingestão.

### `standard`

Mantém integralmente o RAG já existente no `agent_framework_oci`: `VECTOR_STORE_PROVIDER`, `GRAPH_STORE_PROVIDER`, embedding, query rewrite, compression, retrieval guardrails e geração continuam válidos.

### `kbdb`

O framework integra somente a porta estável de serving do projeto KBDB:

`PKG_KB_SERVING.SEARCH_KNOWLEDGE_BASE`

O pipeline enterprise continua externo ao runtime do agente e preserva sua própria arquitetura RAW → SILVER → GOLD, HVI/hybrid search, property graph, publicação, lifecycle, auditoria e observabilidade.

O envelope KBDB é adaptado para `RagResult`/`VectorDocument`; portanto os agentes existentes continuam chamando `_retrieve_rag_context()` e os retrieval guardrails do framework continuam depois do retrieval.

### Configuração

```env
RAG_PROVIDER=kbdb
RAG_TOP_K=5
KBDB_DB_USER=KB_USER
KBDB_DB_PASSWORD=...
KBDB_DB_DSN=...
KBDB_DB_WALLET_LOCATION=...
KBDB_DB_WALLET_PASSWORD=...
KBDB_SEARCH_TYPE=hybrid
KBDB_NODE_EXPANSION=true
KBDB_NODE_MAX_RELATED=8
KBDB_GRAPH_CROSS_REF=false
KBDB_MAX_CROSS_REF_HOPS=1
KBDB_DOCUMENT_TYPE=customer_safe
KBDB_METADATA_JSON=
KBDB_MIN_SCORE=
```

Quando `RAG_PROVIDER=kbdb`, `KBDB_DB_USER`, `KBDB_DB_PASSWORD` e `KBDB_DB_DSN` são obrigatórios. O KBDB usa conexão isolada porque pode residir em outro Autonomous. `KBDB_DB_DSN` segue a mesma semântica de `ADB_DSN`: use o alias TNS existente no `tnsnames.ora` da wallet indicada por `KBDB_DB_WALLET_LOCATION`, e não uma URL `tcps://...`.

### Isolamento e compatibilidade

- `RAG_PROVIDER=standard` não importa nem conecta ao KBDB.
- `RAG_PROVIDER=kbdb` não instancia vector/graph stores do RAG padrão.
- Ingestão por `RagService.add_documents()` não é permitida no modo KBDB: deve passar pelo pipeline/publicação KBDB.
- Query rewrite e context compression continuam opcionais e são aplicados pela camada comum do framework.
- `AgentRuntimeMixin._retrieve_rag_context()` e os agentes permanecem inalterados.
- Falhas do KBDB seguem a semântica existente do framework: retrieval é evidência auxiliar e a exceção é convertida em metadata técnica sem derrubar a jornada.


### Resposta direta de tool e RAG

O framework não considera mais que um resultado MCP estruturado é, por si só, uma resposta suficiente ao usuário.

Uma política `response.renderer` define somente **como** apresentar o resultado. Ela não encerra o fluxo antes de RAG/LLM. Para uma tool deliberadamente produzir uma resposta final direta, a aplicação deve declarar explicitamente:

```yaml
response:
  mode: renderer
  renderer: meu.renderer
  direct: true
```

Sem `direct: true`, o resultado da tool permanece como evidência MCP e o fluxo segue para `_retrieve_rag_context()` e composição LLM. Isso permite, por exemplo, que uma consulta operacional de plano seja combinada com conhecimento documental do KBDB quando a pergunta pedir regras, políticas ou explicações.

O core do framework não possui fallback por nome de tool (`consultar_plano`, `consultar_pedido`, etc.). Regras de apresentação pertencem à aplicação/domínio.


### Suficiência MCP e grounding

Um resultado MCP bem-sucedido **não** faz o framework pular RAG automaticamente.
O domínio só pode declarar suficiência documental explicitamente no payload com
`rag_sufficient=true` ou `knowledge_sufficient=true`. Essa decisão é genérica e
não depende do nome da tool nem de palavras-chave de telecom/retail.

No provider `kbdb`, `KBDB_GROUNDED_ONLY=true` é o padrão. Quando a busca KBDB
retorna vazia, bloqueada ou com erro, a composição LLM pode usar fatos comprovados
por MCP/business context, mas não pode completar a parte documental com conhecimento
paramétrico do modelo. Deve informar que não há evidência suficiente na base.

Eventos do ProductAgent registram `IC.PRODUCT_RAG_CONTEXT_EVALUATED` em toda
tentativa/decisão e `IC.PRODUCT_RAG_CONTEXT_RETRIEVED` somente quando há contexto
recuperado. Os metadados incluem `provider`, `status`, `document_count`, `reason`,
`error`, `query`, `namespace` e `latency_ms`.

### Amostras e testes de RAG

> Conteúdo consolidado a partir de `docs/README_rag_samples.md`.

These PDF files are synthetic, searchable sample documents created to validate the RAG embedding and retrieval flow of `agent_template_backend`.

### Files

- `01_billing_agent_invoice_policy.pdf` - sample knowledge for `billing_agent`
- `02_orders_agent_lifecycle_policy.pdf` - sample knowledge for `orders_agent`
- `03_product_agent_catalog_policy.pdf` - sample knowledge for `product_agent`
- `04_support_agent_sla_policy.pdf` - sample knowledge for `support_agent`
- `05_business_context_rag_flow.pdf` - sample knowledge about BusinessContext, identity.yaml and MCP parameter mapping

### How to use

Copy the PDF files to the backend documentation directory:

```bash
mkdir -p agent_template_backend/docs/rag_samples
cp *.pdf agent_template_backend/docs/rag_samples/
```

For a local smoke test, use:

```env
VECTOR_STORE_PROVIDER=sqlite
EMBEDDING_PROVIDER=mock
SQLITE_DB_PATH=./data/agent_framework.db
RAG_TOP_K=4
```

Then run:

```bash
python scripts/generate_rag_embeddings.py \
  --docs-dir ./agent_template_backend/docs/rag_samples \
  --namespace default
```

For production-like semantic embeddings with OCI Generative AI, use:

```env
VECTOR_STORE_PROVIDER=autonomous
EMBEDDING_PROVIDER=oci
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxx
OCI_REGION=us-chicago-1
OCI_EMBEDDING_MODEL=cohere.embed-multilingual-v3.0
```

### Suggested retrieval test questions

- What is a prorated charge?
- When can the OrdersAgent open an exchange request?
- Which SKU represents the AI Agents book?
- What is the target response for a critical support ticket?
- How does BusinessContext map customer_key to MCP tool parameters?

### BusinessContext v2

> Conteúdo consolidado a partir de `Documentacao/README_TEMPLATE_BUSINESS_CONTEXT_V2.md`.

Este pacote atualiza o `agent_template_backend` e o `agent_frontend` para refletir o framework novo, onde as chaves vindas do canal/front-end são resolvidas uma vez como chaves canônicas e propagadas pelas camadas até o MCP Server.

### Fluxo implementado

1. O front-end envia `tenant_id`, `agent_id`, `session_id` e `business_context`.
2. O backend normaliza a mensagem via `ChannelGateway` preservando todo o payload no `context`.
3. O backend usa `IdentityResolver` com `config/identity.yaml` para gerar `BusinessContext`:
   - `customer_key`
   - `contract_key`
   - `interaction_key`
   - `account_key`
   - `resource_key`
   - `session_key`
4. O workflow recebe `context.business_context`.
5. Os agentes de exemplo não montam mais argumentos específicos como `msisdn`, `invoice_id` ou `order_id` diretamente.
6. O `MCPToolRouter` usa `config/mcp_parameter_mapping.yaml` para converter chaves canônicas em parâmetros reais de cada tool MCP.

### Arquivos principais ajustados

- `agent_template_backend/app/main.py`
  - carrega `IdentityResolver`;
  - resolve `BusinessContext` por mensagem;
  - persiste as chaves na sessão/memória/metadata/SSE;
  - adiciona `/debug/identity`.

- `agent_template_backend/app/agents/runtime.py`
  - adiciona `_collect_mcp_context()` centralizado;
  - repassa `business_context` e `original_context` para o MCP Router.

- `agent_template_backend/app/agents/*_agent.py`
  - agentes passam a usar `_collect_mcp_context()` em vez de montar argumentos específicos.

- `agent_template_backend/config/identity.yaml`
  - define como campos do canal/front-end alimentam as chaves canônicas.

- `agent_template_backend/config/mcp_parameter_mapping.yaml`
  - define como chaves canônicas viram parâmetros reais por tool MCP.

- `agent_frontend/index.html` e `agent_frontend/app.js`
  - adicionam campos de `tenant`, `agent` e chaves canônicas;
  - enviam `business_context` no payload;
  - mantêm aliases de domínio para compatibilidade (`msisdn`, `invoice_id`, `order_id`, etc.).

### Teste rápido

Suba backend, frontend e MCP servers. Depois teste:

```bash
curl -s http://localhost:8000/health | jq

curl -s -X POST http://localhost:8000/debug/identity \
  -H 'Content-Type: application/json' \
  -d '{
    "channel":"web",
    "tenant_id":"default",
    "agent_id":"telecom_contas",
    "payload":{
      "message":"Minha fatura veio alta",
      "session_id":"teste-001",
      "msisdn":"11999999999",
      "invoice_id":"3000131180",
      "ura_call_id":"URA-123",
      "business_context":{
        "customer_key":"11999999999",
        "contract_key":"3000131180",
        "interaction_key":"URA-123",
        "session_key":"teste-001"
      }
    }
  }' | jq

curl -s -X POST http://localhost:8000/debug/mcp/call/consultar_fatura \
  -H 'Content-Type: application/json' \
  -d '{
    "business_context": {
      "customer_key":"11999999999",
      "contract_key":"3000131180",
      "interaction_key":"URA-123",
      "session_key":"teste-001"
    }
  }' | jq
```

No log do backend, procure por `mcp.tool.mapped`. Ele deve indicar as chaves mapeadas e `has_msisdn=true`, `has_invoice_id=true` para o domínio telecom.

### Integração operacional de RAG e cache

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

- `docs/RAG_PROVIDER_KBDB.md`
- `docs/README_rag_samples.md`
- `Documentacao/README_TEMPLATE_BUSINESS_CONTEXT_V2.md`
- `Documentacao/README_FIRST_MAX_OPERATIONAL_FIXES.md`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.
