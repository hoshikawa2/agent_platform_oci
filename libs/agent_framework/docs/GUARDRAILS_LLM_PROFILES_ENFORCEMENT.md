# Guardrails and llm_profiles.yaml enforcement

This fix ensures calibrated guardrails respect `llm_profiles.yaml` for the `guardrail` and `grl` profiles.

## Problem

Some boot paths instantiated `GuardrailPipeline` without an explicit framework LLM. In that case the adapter treated `llm is None` as local mock mode and returned local fallback decisions. Also, `USE_MOCK_LLM=true` could hide the model configured in `profiles.guardrail` or `profiles.grl`.

That meant intentionally invalid models such as `xopenai.gpt-4.1` did not fail, because the guardrail never reached the configured provider.

## Fix

`framework_llm_client.py` now:

- resolves the selected profile before deciding mock vs real;
- creates the framework LLM from `Settings` when the pipeline did not receive one;
- gives precedence to an explicit non-mock `guardrail`/`grl` profile over `USE_MOCK_LLM`;
- no longer overrides `temperature` and `max_tokens` at call time, so YAML profile values are honored.

`custom_rails.py` now allows passing `llm` and `observer` into the generated `GuardrailPipeline`.

## Expected validation

With this YAML:

```yaml
profiles:
  default:
    provider: oci_openai
    model: openai.gpt-4.1
  guardrail:
    model: xopenai.gpt-4.1
    temperature: 0
    max_tokens: 600
  grl:
    model: xopenai.gpt-4.1
    temperature: 0
    max_tokens: 700
```

LLM-based guardrails such as `PINJ` fallback, `AOFERTA`, `REVPREC`, `DLEX_OUT`, `RAGSEC`, and enabled LLM checks must attempt to use `xopenai.gpt-4.1` and surface the provider/model error instead of silently returning local mock results.

Deterministic short-circuit rails may still block before calling an LLM. To validate profile usage, use a case that reaches the LLM rail or inspect Langfuse generation metadata for `profile_name`, `model`, and `profile_source`.
