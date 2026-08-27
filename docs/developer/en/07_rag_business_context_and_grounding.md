### RAG, BusinessContext, and Grounding

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **RAG, providers, BusinessContext, retrieved context, and grounding**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

RAG, providers, BusinessContext, retrieved context, and grounding.

### Consolidated technical content

### RAG, Enterprise Providers, BusinessContext, and Grounding

Guide for integrating retrieved knowledge, selecting between RAG providers, configuring KBDB, using samples, MCP sufficiency, and using BusinessContext as a data contract.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### Standard RAG Provider versus KBDB Enterprise

> Content consolidated from `docs/RAG_PROVIDER_KBDB.md`.

The framework now supports two retrieval backends through the same `RagService` contract, without changing agents or `_retrieve_rag_context()`.

### Selection

```env
RAG_PROVIDER=standard  # default: comportamento anterior
# ou
RAG_PROVIDER=kbdb      # KBDB enterprise
```

Selection is exclusive per process. The two RAG implementations do not run together and do not share vector store, graph store, or ingestion.

### `standard`

Fully preserves the existing RAG in `agent_framework_oci`: `VECTOR_STORE_PROVIDER`, `GRAPH_STORE_PROVIDER`, embedding, query rewrite, compression, retrieval guardrails, and generation remain valid.

### `kbdb`

The framework integrates only the stable serving port of the KBDB project:

`PKG_KB_SERVING.SEARCH_KNOWLEDGE_BASE`

The enterprise pipeline remains external to the agent runtime and preserves its own RAW → SILVER → GOLD architecture, HVI/hybrid search, property graph, publishing, lifecycle, audit, and observability.

The KBDB envelope is adapted to `RagResult`/`VectorDocument`; therefore existing agents continue calling `_retrieve_rag_context()` and the framework's retrieval guardrails continue after retrieval.

### Configuration

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

When `RAG_PROVIDER=kbdb`, `KBDB_DB_USER`, `KBDB_DB_PASSWORD`, and `KBDB_DB_DSN` are required. KBDB uses an isolated connection because it may reside in another Autonomous database. `KBDB_DB_DSN` follows the same semantics as `ADB_DSN`: use the existing TNS alias in the `tnsnames.ora` from the wallet indicated by `KBDB_DB_WALLET_LOCATION`, not a `tcps://...` URL.

### Isolation and compatibility

- `RAG_PROVIDER=standard` does not import or connect to KBDB.
- `RAG_PROVIDER=kbdb` does not instantiate the standard RAG vector/graph stores.
- Ingestion through `RagService.add_documents()` is not allowed in KBDB mode: it must go through the KBDB pipeline/publishing process.
- Query rewrite and context compression remain optional and are applied by the framework's common layer.
- `AgentRuntimeMixin._retrieve_rag_context()` and agents remain unchanged.
- KBDB failures follow the framework's existing semantics: retrieval is auxiliary evidence and the exception is converted into technical metadata without breaking the user journey.


### Direct tool response and RAG

The framework no longer considers a structured MCP result, by itself, to be a sufficient user response.

A `response.renderer` policy defines only **how** to present the result. It does not terminate the flow before RAG/LLM. For a tool to deliberately produce a direct final response, the application must explicitly declare:

```yaml
response:
  mode: renderer
  renderer: meu.renderer
  direct: true
```

Without `direct: true`, the tool result remains MCP evidence and the flow continues to `_retrieve_rag_context()` and LLM composition. This allows, for example, an operational plan query to be combined with KBDB documentary knowledge when the question asks for rules, policies, or explanations.

The framework core has no fallback by tool name (`consultar_plano`, `consultar_pedido`, etc.). Presentation rules belong to the application/domain.


### MCP sufficiency and grounding

A successful MCP result **does not** make the framework skip RAG automatically.  
The domain may declare documentary sufficiency only explicitly in the payload with `rag_sufficient=true` or `knowledge_sufficient=true`. This decision is generic and does not depend on the tool name or telecom/retail keywords.

For the `kbdb` provider, `KBDB_GROUNDED_ONLY=true` is the default. When KBDB search returns empty, blocked, or error, LLM composition may use facts proven by MCP/business context, but it must not fill the documentary portion using parametric model knowledge. It must state that there is insufficient evidence in the knowledge base.

ProductAgent events record `IC.PRODUCT_RAG_CONTEXT_EVALUATED` for every attempt/decision and `IC.PRODUCT_RAG_CONTEXT_RETRIEVED` only when context was retrieved. Metadata includes `provider`, `status`, `document_count`, `reason`, `error`, `query`, `namespace`, and `latency_ms`.

### RAG samples and tests

> Content consolidated from `docs/README_rag_samples.md`.

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

> Content consolidated from `Documentacao/README_TEMPLATE_BUSINESS_CONTEXT_V2.md`.

This package updates `agent_template_backend` and `agent_frontend` to reflect the new framework, where keys coming from the channel/front end are resolved once into canonical keys and propagated through the layers to the MCP Server.

### Implemented flow

1. The front end sends `tenant_id`, `agent_id`, `session_id`, and `business_context`.
2. The backend normalizes the message through `ChannelGateway`, preserving the full payload in `context`.
3. The backend uses `IdentityResolver` with `config/identity.yaml` to generate `BusinessContext`:
   - `customer_key`
   - `contract_key`
   - `interaction_key`
   - `account_key`
   - `resource_key`
   - `session_key`
4. The workflow receives `context.business_context`.
5. Example agents no longer build specific arguments such as `msisdn`, `invoice_id`, or `order_id` directly.
6. `MCPToolRouter` uses `config/mcp_parameter_mapping.yaml` to convert canonical keys into the actual parameters of each MCP tool.

### Main files adjusted

- `agent_template_backend/app/main.py`
  - loads `IdentityResolver`;
  - resolves `BusinessContext` per message;
  - persists keys in session/memory/metadata/SSE;
  - adds `/debug/identity`.

- `agent_template_backend/app/agents/runtime.py`
  - adds centralized `_collect_mcp_context()`;
  - forwards `business_context` and `original_context` to the MCP Router.

- `agent_template_backend/app/agents/*_agent.py`
  - agents now use `_collect_mcp_context()` instead of building specific arguments.

- `agent_template_backend/config/identity.yaml`
  - defines how channel/front-end fields feed canonical keys.

- `agent_template_backend/config/mcp_parameter_mapping.yaml`
  - defines how canonical keys become real parameters per MCP tool.

- `agent_frontend/index.html` and `agent_frontend/app.js`
  - add `tenant`, `agent`, and canonical-key fields;
  - send `business_context` in the payload;
  - retain domain aliases for compatibility (`msisdn`, `invoice_id`, `order_id`, etc.).

### Quick test

Start backend, frontend, and MCP servers. Then test:

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

In the backend log, look for `mcp.tool.mapped`. It should indicate the mapped keys and `has_msisdn=true`, `has_invoice_id=true` for the telecom domain.

### Operational RAG and cache integration

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

- `docs/RAG_PROVIDER_KBDB.md`
- `docs/README_rag_samples.md`
- `Documentacao/README_TEMPLATE_BUSINESS_CONTEXT_V2.md`
- `Documentacao/README_FIRST_MAX_OPERATIONAL_FIXES.md`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
