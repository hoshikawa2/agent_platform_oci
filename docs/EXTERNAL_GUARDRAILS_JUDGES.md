# External Guardrails and Judges SPI

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

The core must not reference a concrete agent package, company, product, telecom identifier or domain-specific policy. Domain-specific variants belong to the agent and should receive distinct public codes/names.

## Compatibility rule
Domain policies must not be replaced by cosmetically generic text inside the core while losing the original policy. The generic core implementation and the agent-specific implementation may coexist; the embedding agent explicitly selects its own code/name in YAML.

Legacy business validators should migrate to the agent domain. A temporary compatibility shim is acceptable for old imports, but new application code must import the agent-owned implementation.
