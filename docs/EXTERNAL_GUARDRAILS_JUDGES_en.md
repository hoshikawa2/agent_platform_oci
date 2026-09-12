# External guardrails and judges: implementation guide

External extensions keep domain policy in the agent package instead of coupling it to `agent_framework`. The complete executable reference, including copy-and-paste implementations, is [the Portuguese guide](EXTERNAL_GUARDRAILS_JUDGES.md); its tagged examples are exercised by `tests/test_external_guardrails_judges_documentation.py`.

## Required contracts

- A guardrail normally extends `Guardrail` and implements `evaluate(text, context) -> RailDecision`. Its YAML section selects `input`, `retrieval`, `tool`, or `output`; `policy.on_deny` selects `block`, `retry`, `handover`, `sanitize`, `observe`, or `allow`.
- A judge implements `evaluate(question, answer, context) -> JudgeResult`. Its constructor can receive injected `llm` and `settings`, plus `threshold`, `profile_name`, `fail_closed`, `max_context_chars`, and `fallback_on_block`.
- Class paths accept `package.module:Class` (recommended) or `package.module.Class`; that package must be importable by the backend.
- Synchronous methods run in worker threads; asynchronous methods run on the event loop. Judges execute concurrently while result order follows YAML order.

## Where the external guardrail prompt lives

The documented `FinancialAmountRail` is deterministic and therefore has no prompt. For an LLM-backed external guardrail, the prompt belongs to the agent package, preferably under `financial_agent/extensions/prompts/`. The external SPI does not define standard `prompt` or `prompt_path` YAML fields; such fields work only if the external class explicitly accepts and implements them through `kwargs`.

Keep the prompt builder and `PROMPT_VERSION` in a dedicated agent module, import it from `guardrails.py`, and call only the LLM exposed as `context["guardrail_llm"]` or `context["llm"]`. `guardrails.yaml` owns activation, class, constructor options, and deny action; the prompt module owns policy text/output contract; the rail owns parsing and fail-closed behavior; `llm_profiles.yaml` owns provider/model parameters; and `AgentWorkflow` must construct `GuardrailPipeline(llm=llm, ...)`.

The complete copyable prompt builder and LLM guardrail are in the [Portuguese executable guide](EXTERNAL_GUARDRAILS_JUDGES.md) and are validated by `tests/test_external_guardrails_judges_documentation.py`.

```yaml
# guardrails.yaml
fail_fast: true
tool:
  - code: FIN_AMOUNT
    type: external
    class: financial_agent.extensions.guardrails:FinancialAmountRail
    kwargs: {max_amount: 1500.0}
    policy: {on_deny: handover}
```

```yaml
# judges.yaml
enabled: true
sample_rate: 1.0
always_run_for_transactional: true
fail_closed: true
judges:
  - name: financial_evidence
    type: external
    class: financial_agent.extensions.judges:FinancialEvidenceJudge
    threshold: 0.8
```

## Current template limitation

`agent_template_backend` currently builds one guardrail pipeline and one judge pipeline at startup. Per-agent `guardrails_config_path` and `judges_config_path` entries in `agents.yaml` do not by themselves switch pipelines for each request. Until per-profile pipeline selection is implemented by the application, startup YAML is effectively global.

The template also constructs guardrails without `llm` and judges without `llm/settings`. Deterministic extensions work, but LLM-dependent extensions require `GuardrailPipeline(llm=llm, ...)` and `JudgePipeline(llm=llm, settings=settings, ...)`. Guardrail constructors do not receive LLM injection; a configured pipeline exposes it through `context["guardrail_llm"]` or `context["llm"]`.

Use fail-closed for authorization, safety, and transaction controls. Catch expected external judge failures inside the implementation because an unhandled exception may propagate from concurrent evaluation. Never log prompts, credentials, PII, or financial payloads.

```bash
pytest -q tests/test_external_guardrails_judges_documentation.py
```
