# RAG Sample PDFs for agent_template_backend

These PDF files are synthetic, searchable sample documents created to validate the RAG embedding and retrieval flow of `agent_template_backend`.

## Files

- `01_billing_agent_invoice_policy.pdf` - sample knowledge for `billing_agent`
- `02_orders_agent_lifecycle_policy.pdf` - sample knowledge for `orders_agent`
- `03_product_agent_catalog_policy.pdf` - sample knowledge for `product_agent`
- `04_support_agent_sla_policy.pdf` - sample knowledge for `support_agent`
- `05_business_context_rag_flow.pdf` - sample knowledge about BusinessContext, identity.yaml and MCP parameter mapping

## How to use

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

## Suggested retrieval test questions

- What is a prorated charge?
- When can the OrdersAgent open an exchange request?
- Which SKU represents the AI Agents book?
- What is the target response for a critical support ticket?
- How does BusinessContext map customer_key to MCP tool parameters?
