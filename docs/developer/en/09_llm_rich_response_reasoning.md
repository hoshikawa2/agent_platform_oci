### LLM Rich Response and reasoning_content

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **`ainvoke_response()`, inference metadata, and optional `reasoning_content`**.
- Historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

`ainvoke_response()`, inference metadata, and optional `reasoning_content`.

### Consolidated technical content

### LLM Rich Response and reasoning_content

Guide for using the opt-in structured LLM response API without breaking the legacy `ainvoke()` contract, including `reasoning_content`, usage, model, provider, fallback, and tests.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### Rich LLM response API

> Content consolidated from `docs/LLM_RICH_RESPONSE.md`.

### Goal

The framework keeps `ainvoke()` as the backward-compatible API, returning only `str`, and adds `ainvoke_response()` for consumers that need additional inference metadata, including `reasoning_content` when the model/provider/API makes it available.

### APIs

### Legacy API — unchanged

```python
answer = await llm.ainvoke(messages)
assert isinstance(answer, str)
```

No existing agent needs to be changed.

### New rich API — opt-in

```python
response = await llm.ainvoke_response(messages)

answer = response.content
reasoning = response.reasoning_content
usage = response.usage
model = response.model
provider = response.provider
```

`reasoning_content` is `str | None`. `None` is the expected behavior when the model, provider, or API does not expose textual reasoning.

### Backoffice

A consumer that previously did:

```python
answer = await llm.ainvoke(messages)
template = extract_response(answer)
```

can instead do:

```python
response = await llm.ainvoke_response(messages)
template = extract_response(response.content)
reasoning_content = response.reasoning_content
```

Logic that expects text continues to receive `response.content`; reasoning remains separate and does not contaminate response, cache, memory, judges, or guardrails.

### Custom-provider compatibility

`LLMProvider.ainvoke_response()` has a fallback. An external provider that implements only `ainvoke()` continues to work and automatically receives `LLMResponse(content=<texto>)`, with `reasoning_content=None`.

Native providers (`mock`, OpenAI-compatible/OCI OpenAI, and OCI SDK) implement the rich response and attempt to preserve reasoning when present.

### Compatibility guarantees

- `ainvoke()` continues to return `str`.
- No existing router, judge, RAG, memory, cache, or runtime has been migrated to the new API.
- `reasoning_content` is never fabricated by the framework.
- Missing reasoning does not generate an error.
- Existing telemetry output continues to be the final content, without automatically appending reasoning.

### Tests

Specific tests are in `tests/unit/test_llm_rich_response.py` and verify:

1. a legacy provider that implements only `ainvoke()`;
2. preservation of the `str` return from `ainvoke()`;
3. `LLMResponse` return from `ainvoke_response()`;
4. reasoning through a direct attribute;
5. reasoning through `model_extra`;
6. missing reasoning and extraction in OCI SDK format.

### Source files

The files below were consolidated into this manual:

- `docs/LLM_RICH_RESPONSE.md`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
