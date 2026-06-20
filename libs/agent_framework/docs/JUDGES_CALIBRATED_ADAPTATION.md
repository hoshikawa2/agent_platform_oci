# Calibrated Judges Adaptation

This project now carries the calibrated judge package inside the framework while preserving the existing architecture.

## What changed

The calibrated judge prompts were added under:

```text
src/agent_framework/judges/calibrated/
```

The main integration point remains:

```text
src/agent_framework/judges/judge.py
```

The framework still uses:

- `JudgePipeline`
- `config/judges.yaml` as the source of truth for which judges run
- `llm_profiles.yaml` profile `judge` for provider/model/temperature/max tokens
- the existing framework LLM provider, Langfuse instrumentation and token accounting
- `.env` fallback when `llm_profiles.yaml` is absent

There is intentionally no `ENABLE_LLM_JUDGE` gate.

## Current mapping

With this YAML:

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.7
  - name: groundedness
    enabled: true
    threshold: 0.6
```

The framework runs:

| YAML name | Calibrated task | Purpose |
| --- | --- | --- |
| `response_quality` | `RQLT` | response quality |
| `groundedness` | `ALUC` | hallucination / unsupported factual claims |

Both use the `judge` LLM profile unless another profile is set on the YAML item.

## Testing model enforcement

If this is configured:

```yaml
profiles:
  judge:
    provider: oci_openai
    model: xopenai.gpt-4.1
    temperature: 0
    max_tokens: 800
```

Then `response_quality` and `groundedness` will try to use `xopenai.gpt-4.1`. If that model does not exist, the calibrated judge call should fail according to the entry/global `fail_closed` behavior.

## Keeping the old heuristic judges

To force the old deterministic behavior for a specific judge:

```yaml
judges:
  - name: response_quality
    type: deterministic
    enabled: true
    threshold: 0.7
```

## Optional calibrated judges

```yaml
judges:
  - name: tone
    enabled: true
  - name: sentiment
    enabled: true
    fail_on_negative: false
```

These map to the calibrated `VCTN` and `CSI` prompts.
