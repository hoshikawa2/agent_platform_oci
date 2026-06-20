# Dynamic LLM Profiles

`llm_profiles.yaml` is optional.

If the file does not exist, the backend keeps the current behavior and uses `.env`:

```env
LLM_PROVIDER=oci_openai
OCI_GENAI_MODEL=openai.gpt-4.1
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2048
```

If `llm_profiles.yaml` exists, each inference point resolves parameters in this order:

```text
specific profile -> default profile -> .env
```

Supported inference points:

| Profile | Used by |
|---|---|
| `default` | global fallback when YAML exists |
| `supervisor` | global supervisor / LLM supervisor |
| `router` | EnterpriseRouter LLM classification |
| `guardrail` | optional LLM guardrail rail |
| `grl` | optional output supervisor / GRL LLM rail and GRL advisor |
| `judge` | LLM judge when enabled in `config/judges.yaml` |
| `rag_rewriter` | RAG query rewriting |
| `rag_compressor` | RAG context compression |
| `rag_generation` | direct RAG answer generation |
| `summary_memory` | ConversationSummaryMemory |
| `noc` | optional NOC reasoning advisor |
| `<agent_name>` | agent runtime, for example `billing_agent` |

Optional LLM inference points are disabled by default to preserve current behavior:

```env
ENABLE_LLM_GUARDRAIL=false
ENABLE_LLM_GRL=false
ENABLE_RAG_QUERY_REWRITE=false
ENABLE_RAG_CONTEXT_COMPRESSION=false
ENABLE_RAG_GENERATION=false
```

To enable guardrails/GRL, inject the same backend LLM object into the corresponding component and set the flags above as needed. For judges, do not use an extra LLM flag: enable or disable the LLM judge in `config/judges.yaml`.


## Provider per profile

Recommendation: declare `provider` explicitly in every profile. The resolver can inherit it from `default`, but explicit provider avoids ambiguity and makes tests with invalid models/providers deterministic.

Judge activation is controlled by `config/judges.yaml`; `llm_profiles.yaml` only chooses the `judge` model/provider/params.
