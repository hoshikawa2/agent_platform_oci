# Judges YAML as the source of truth

This version removes the extra `ENABLE_LLM_JUDGE` activation gate.

The judge stage now follows this rule:

1. `ENABLE_JUDGES=false` disables the whole judge stage.
2. `config/judges.yaml` decides which judges are active.
3. If a judge has `type: llm` and `enabled: true`, the framework calls the LLM.
4. `llm_profiles.yaml` decides which model/provider that LLM judge uses through the configured profile, usually `judge`.
5. If `llm_profiles.yaml` is absent, the LLM judge falls back to the global `.env` LLM configuration.

Example:

```yaml
judges:
  - code: llm_judge
    type: llm
    enabled: true
    profile: judge
    fail_closed: true
```

And in `llm_profiles.yaml`:

```yaml
profiles:
  judge:
    provider: oci_openai
    model: openai.gpt-4.1
    temperature: 0
    max_tokens: 800
```

If you intentionally configure a nonexistent model for `judge`, the LLM judge will try to use it. The final behavior depends on `fail_closed`:

- `fail_closed: true` blocks/fails the judge result.
- `fail_closed: false` reports the LLM judge as unavailable and follows fail-open.

`ENABLE_LLM_JUDGE` is intentionally not used anymore.
