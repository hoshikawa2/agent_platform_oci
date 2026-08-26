# RAG alternativo: Standard x KBDB Enterprise

O framework passa a suportar dois backends de retrieval pelo mesmo contrato `RagService`, sem alterar os agentes nem `_retrieve_rag_context()`.

## Seleção

```env
RAG_PROVIDER=standard  # default: comportamento anterior
# ou
RAG_PROVIDER=kbdb      # KBDB enterprise
```

A seleção é exclusiva por processo. Os dois RAGs não executam juntos e não compartilham vector store, graph store ou ingestão.

## `standard`

Mantém integralmente o RAG já existente no `agent_framework_oci`: `VECTOR_STORE_PROVIDER`, `GRAPH_STORE_PROVIDER`, embedding, query rewrite, compression, retrieval guardrails e geração continuam válidos.

## `kbdb`

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

## Isolamento e compatibilidade

- `RAG_PROVIDER=standard` não importa nem conecta ao KBDB.
- `RAG_PROVIDER=kbdb` não instancia vector/graph stores do RAG padrão.
- Ingestão por `RagService.add_documents()` não é permitida no modo KBDB: deve passar pelo pipeline/publicação KBDB.
- Query rewrite e context compression continuam opcionais e são aplicados pela camada comum do framework.
- `AgentRuntimeMixin._retrieve_rag_context()` e os agentes permanecem inalterados.
- Falhas do KBDB seguem a semântica existente do framework: retrieval é evidência auxiliar e a exceção é convertida em metadata técnica sem derrubar a jornada.


## Resposta direta de tool e RAG

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


## Suficiência MCP e grounding

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
