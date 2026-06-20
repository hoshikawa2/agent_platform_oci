# judges.yaml simple schema

The framework accepts the simple judge configuration format:

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.7
  - name: groundedness
    enabled: true
    threshold: 0.6
```

In this format, `type` is optional. The framework infers deterministic judges from `name`:

- `response_quality` -> deterministic response quality judge
- `groundedness` -> deterministic groundedness judge

The `threshold` field is now applied to the deterministic judge pass/fail calculation and is also emitted in the judge result metadata.

No LLM is called by this YAML. The `llm_profiles.yaml` profile named `judge` is only used if a LLM judge is explicitly declared, for example:

```yaml
judges:
  - name: llm_judge
    type: llm
    enabled: true
    profile: judge
    fail_closed: true
```

There is no `ENABLE_LLM_JUDGE` gate. The YAML is the source of truth.
