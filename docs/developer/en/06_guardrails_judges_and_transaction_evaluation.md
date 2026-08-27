### Guardrails, Judges, and Transaction Evaluation

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **native/external guardrails, judges, transactional sampling, and grounding**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

Native/external guardrails, judges, transactional sampling, and grounding.

### Consolidated technical content

### Guardrails, Judges, and Transaction Evaluation

Manual for input/output guardrails, agent-specific extensions, external judges, mandatory execution on transactions, and the signals/evidence used during evaluation.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### Guardrails implemented in the framework

> Content consolidated from `Documentacao/README_GUARDRAILS_IMPLEMENTADOS.md`.

This version adds a pragmatic guardrail layer to `agent_framework`, inspired by separating rails by stage: input, output, retrieval, and execution/tool.

### Input rails

- `MSIZE` — blocks excessively large messages.
- `MSK` — masks CPF, CNPJ, phone, e-mail, card, postal code, RG, tokens, and keys.
- `TOX` — detects toxicity and records severity without blocking by default.
- `PINJ` — detects prompt injection and records a score.
- `JBRK` — detects jailbreak/bypass roleplay and records a score.
- `VLOOP` — blocks repetitive conversational loops.

### Output rails

- `PII_OUT` — masks PII in the agent response.
- `CMP` — softens absolute promises and excessive guarantee language.
- `REVPREC` — blocks verbalization of an operational action without tool confirmation.
- `GND` — signals grounding/risk when there is a specific answer without evidence.
- `ALUC_RISK` — marks hallucination risk for telemetry and judges.

### Optional rails

- `RET_REL` — validates retrieval-chunk relevance using a minimum score.
- `TOOL_VAL` — validates MCP/tool name, required arguments, negative values, and allowlist.

### Files changed

- `agent_framework/src/agent_framework/guardrails/rails.py`
- `agent_framework/src/agent_framework/guardrails/pipeline.py`
- `agent_framework/src/agent_framework/guardrails/__init__.py`

### Quick use

```python
from agent_framework.guardrails.pipeline import GuardrailPipeline

pipeline = GuardrailPipeline()

sanitized_input, input_decisions = await pipeline.run_input(
    user_text,
    {"history_texts": history_texts},
)

final_answer, output_decisions = await pipeline.run_output(
    answer,
    context,
)
```

For tools/MCP:

```python
_, decisions = await pipeline.run_tool(
    "cancelar_produto",
    {"produto": "VAS", "valor": 0},
    {
        "required_args": ["produto"],
        "allowed_tools": ["cancelar_produto", "consultar_fatura"],
    },
)
```

### SPI for external guardrails and judges

> Content consolidated from `docs/EXTERNAL_GUARDRAILS_JUDGES.md`.

`agent_framework_oci` supports agent-owned guardrails and judges without importing domain code into the core.

```yaml
output:
  - code: ACME_POLICY
    type: external
    class: app.extensions.guardrails:AcmePolicyRail
```

```yaml
judges:
  - name: acme_quality
    type: external
    class: app.extensions.judges:AcmeQualityJudge
    threshold: 0.7
```

Native entries remain unchanged. External synchronous `evaluate()` methods execute in worker threads via `asyncio.to_thread`; asynchronous methods execute concurrently on the framework event loop. Judges run concurrently with `asyncio.gather`, preserving YAML result order. Agent plugins should reuse the LLM supplied by the framework rather than instantiate a separate provider.

The core must not reference a concrete agent package, company, product, telecom identifier, or domain-specific policy. Domain-specific variants belong to the agent and should receive distinct public codes/names.

### Compatibility rule

Domain policies must not be replaced by cosmetically generic text inside the core while losing the original policy. The generic core implementation and the agent-specific implementation may coexist; the embedding agent explicitly selects its own code/name in YAML.

Legacy business validators should migrate to the agent domain. A temporary compatibility shim is acceptable for old imports, but new application code must import the agent-owned implementation.

### Mandatory judge execution for transactions

> Content consolidated from `docs/JUDGES_TRANSACTIONAL_SAMPLING_FIX.md`.

### Problem

Even with `always_run_for_transactional: true`, judges could be skipped by sampling because the `judge` node sent only `context`, `route`, `intent`, and `mcp_results`. Transactional fields produced by the runtime did not reach `JudgePipeline`.

### Fix

The `judge` node now passes:

- `transaction_status`
- `confirmation_required`
- `confirmation_received`
- `tool_policy_result`
- `selected_tool_call`
- `pending_tool_call`
- `mcp_results` as evidence

`JudgePipeline` detects transactions through multiple signals and evaluates `always_run_for_transactional` before applying `sample_rate`.

With the configuration below, common queries continue to be sampled at 25%, but `AWAITING_CONFIRMATION`, `COMPLETED`, `FAILED`, or `CANCELLED` turns always run the judges.

```yaml
enabled: true
sample_rate: 0.25
always_run_for_transactional: true
```

### Global Supervisor validation

> Content consolidated from `docs/docs_GLOBAL_SUPERVISOR_VALIDATION.txt`.

VALIDATION - GLOBAL SUPERVISOR

Implemented changes:

1. Framework
- agent_framework.global_supervisor.models
- agent_framework.global_supervisor.config
- agent_framework.global_supervisor.session_store
- agent_framework.global_supervisor.router
- agent_framework.global_supervisor.client

2. New service
- agent_gateway/app/main.py
- agent_gateway/app/settings.py
- agent_gateway/config/backends.yaml
- agent_gateway/README.md
- agent_gateway/Dockerfile
- agent_gateway/docs/ARQUITETURA_GLOBAL_SUPERVISOR.md

3. Docker Compose
- agent-gateway service added on port 8010.

Validations performed:

- python3 -m compileall -q agent_framework/src/agent_framework/global_supervisor agent_gateway/app
  Result: OK

- Hybrid-routing smoke test:
  Input 1: "My bill is too high" -> billing
  Input 2: "and this amount?" on the same session_id -> billing via active_backend
  Result: OK

- FastAPI app import smoke test:
  from app.main import app, registry, router
  Result: OK

Note:
- The gateway SSE proxy was left as a future step. The `/gateway/message/sse` endpoint already routes and forwards as a normal message; for end-to-end SSE, a proxy from `/gateway/events/{session_id}` to the active backend can be implemented.

### Guardrail event validation

> Content consolidated from `docs/docs_VALIDATION_GUARDRAILS_IC.txt`.

VALIDATION REPORT - guardrails parallel fail-fast + observer IC
Date: 2026-06-03

compileall: OK
smoke-tests: OK

### Source files

The files below were consolidated into this manual:

- `Documentacao/README_GUARDRAILS_IMPLEMENTADOS.md`
- `docs/EXTERNAL_GUARDRAILS_JUDGES.md`
- `docs/JUDGES_TRANSACTIONAL_SAMPLING_FIX.md`
- `docs/docs_GLOBAL_SUPERVISOR_VALIDATION.txt`
- `docs/docs_VALIDATION_GUARDRAILS_IC.txt`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
