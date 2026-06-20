# Explicit provider in llm_profiles.yaml

Each LLM profile should declare `provider` explicitly. The resolver can still inherit
missing keys from `profiles.default` and then from `.env`, but explicit `provider`
per profile is safer because each inference point clearly states which client must
be used.

Rules:

- If `llm_profiles.yaml` exists, the selected profile overrides `.env`.
- Missing keys in a selected profile fall back to `profiles.default`.
- Missing keys in `profiles.default` fall back to `.env`.
- `judges.yaml` decides whether an LLM judge exists. There is no
  `ENABLE_LLM_JUDGE` gate and no `LLM_JUDGE_FAIL_CLOSED` setting. Judge
  fail-open/fail-closed behavior belongs in `judges.yaml`.
- `llm_profiles.yaml` only chooses provider/model/params for the judge profile.

Example test:

```yaml
profiles:
  judge:
    provider: oci_openai
    model: xopenai.gpt-4.1
    temperature: 0
    max_tokens: 800
```

And enable the LLM judge in `config/judges.yaml`:

```yaml
enabled: true
fail_closed: true
judges:
  - code: llm_judge
    type: llm
    enabled: true
    profile: judge
    fail_closed: true
```

With that setup, the invalid model must be used by the judge profile and the
judge must fail closed.
