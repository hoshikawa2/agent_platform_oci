# Langfuse trace correlation fix

## Problem

The Langfuse **Tracing > Traces** list was showing one row per internal framework event, for example:

- `langgraph.node.started`
- `langgraph.node.fetch_ticket`
- `OpenAI-generation`
- `TaisKbClient.search_documents`
- `NOC.001`

That is not the intended observability model.

The intended model is:

```text
1 REST/SSE/workflow request = 1 Langfuse trace
internal steps = observations/spans/generations inside that trace
```

## Root causes

1. `Telemetry.event(...)` used raw `langfuse.event(...)` when available. Depending on the SDK/context, this creates a new top-level trace for every event.
2. `Telemetry.generation(...)` preferred raw `langfuse.generation(...)`, which can also create top-level traces when no current Langfuse observation is active.
3. `LangfuseAnalyticsPublisher` for IC/NOC/GRL also created standalone observations without a deterministic trace context.
4. The LLM provider used `langfuse.openai.AsyncOpenAI` whenever Langfuse was enabled. This auto-instrumentation can create separate `OpenAI-generation` traces. The framework already emits correlated LLM generations through `Telemetry.generation(...)`, so the wrapper caused noisy duplicate top-level traces.

## What was changed

### `agent_framework/observability/telemetry.py`

- Added deterministic Langfuse trace correlation using `trace_id` / `request_id` / `session_id`.
- Injects `trace_context={"trace_id": ...}` when starting Langfuse observations/generations, with backward-compatible TypeError fallback.
- `Telemetry.event(...)` no longer calls raw `langfuse.event(...)` first.
- `Telemetry.generation(...)` no longer prefers raw `langfuse.generation(...)`; it prefers correlated current generation/observation APIs.
- When a span has no explicit `trace_id`, it uses the request id as the trace id and stores it in the observability context.

### `agent_framework/analytics/providers/langfuse.py`

- Added deterministic trace correlation for IC/NOC/GRL analytics events.
- Injects `trace_context` into `start_as_current_observation(...)`.
- Avoids raw `langfuse.event(...)` fallback.
- For legacy SDKs, attempts to create/reuse a deterministic trace with `langfuse.trace(id=...)` and attach spans to it.

### `agent_framework/llm/providers.py`

- Langfuse OpenAI auto-instrumentation is now opt-in.
- Default behavior uses the standard `openai.AsyncOpenAI` client and relies on the framework's own `Telemetry.generation(...)` to create correlated Langfuse generations.
- To re-enable wrapper-based auto-instrumentation, set:

```env
ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION=true
```

For this framework, the recommended default is to keep it disabled.

## Expected result

In Langfuse **Tracing > Traces**, you should see one row per business execution, for example:

```text
POST /agent/process-and-stream | man-da8657ac
POST /agent/process-ticket | man-fec67d60
```

When opening a trace, you should see internal observations such as:

```text
http.request
channel_gateway
backoffice.workflow.dispatch
langgraph.node.framework_input_guardrails
langgraph.node.fetch_ticket
langgraph.node.validation
langgraph.node.imdb_enrichment
mcp.tool_call.consultar_imdb_cliente
langgraph.node.treatment_decision
langgraph.node.siebel_sr_opening
framework_output_guardrails
framework_judges
```

## Validation

Run the backend and execute one request. Then verify:

1. The `Traces` screen has one trace row for the request, not one row per node.
2. `OpenAI-generation` no longer appears as a separate top-level trace unless `ENABLE_LANGFUSE_OPENAI_AUTO_INSTRUMENTATION=true`.
3. LangGraph node events and IC/NOC/GRL events appear under the same request trace.


## Fix adicional: formato do trace_id no Langfuse SDK v3

O Langfuse SDK v3 exige que `trace_context.trace_id` seja exatamente um valor hexadecimal minúsculo com 32 caracteres.
Como o framework usa IDs de negócio como UUID com hífens (`d411b925-a096-...`) ou session ids (`man-bcbe3e05`), esses valores agora são normalizados antes de serem enviados ao Langfuse:

- UUID com hífens: remove hífens e reaproveita o hexadecimal de 32 caracteres;
- qualquer outro identificador: gera um hash MD5 determinístico de 32 caracteres;
- o valor original continua preservado em metadata como `framework_trace_id`;
- o valor aceito pelo Langfuse fica em `langfuse_trace_id`.

Isso evita erros como:

```text
ValueError: invalid literal for int() with base 16: 'd411b925-a096-465c-adf2-186623b82c19'
```
