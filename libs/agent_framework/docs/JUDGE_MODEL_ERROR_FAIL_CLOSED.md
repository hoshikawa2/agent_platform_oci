# Judge model/profile error handling

The calibrated judges (`response_quality`, `groundedness`, `sentiment`, `tone`, `llm_judge`) are LLM-based unless an entry explicitly declares `type: deterministic`.

Because they depend on the model configured in `llm_profiles.yaml`, the default behavior is now **fail-closed**:

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.7
  - name: groundedness
    enabled: true
    threshold: 0.6
```

With this configuration, if the profile `judge` points to an invalid model, for example:

```yaml
profiles:
  judge:
    provider: oci_openai
    model: xopenai.gpt-4.1
```

then the judge result is returned as `passed=false`, with `score=0.0`, the exception metadata, and a reason similar to:

```text
Falha no judge calibrado RQLT: ...
```

To intentionally keep the old fail-open behavior, configure it explicitly in `judges.yaml`:

```yaml
fail_closed: false
judges:
  - name: response_quality
    enabled: true
    threshold: 0.7
```

Or per judge:

```yaml
judges:
  - name: response_quality
    enabled: true
    threshold: 0.7
    fail_closed: false
```

Deterministic judges do not call the LLM profile:

```yaml
judges:
  - name: response_quality
    type: deterministic
    enabled: true
    threshold: 0.7
```
