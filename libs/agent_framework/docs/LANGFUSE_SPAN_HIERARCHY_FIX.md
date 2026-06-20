# Langfuse Span Hierarchy Fix

## Problem

After trace correlation was fixed, a full request no longer exploded into many independent Langfuse traces. However, observations inside the trace could appear flattened at the same level.

This happened because the framework was propagating only the Langfuse `trace_id`, but not the current parent observation/span id.

In Langfuse, a tree needs both:

- `trace_id`: identifies the root execution trace;
- `parent_span_id`: identifies which observation/span should be the parent of the new observation.

Without `parent_span_id`, all observations are correlated to the same trace but may appear as direct children of the trace root.

## Fix

The framework now keeps the current Langfuse observation id in the async observability context.

Updated files:

- `src/agent_framework/observability/context.py`
- `src/agent_framework/observability/telemetry.py`
- `src/agent_framework/analytics/providers/langfuse.py`

## Behavior

When a span starts:

1. The framework creates the Langfuse observation.
2. It extracts the observation id from the SDK object.
3. It stores that id in a ContextVar as the current parent observation.
4. Nested spans, generations and analytics events pass it as `trace_context.parent_span_id`.
5. When the span exits, the previous parent observation id is restored.

## Expected Langfuse Structure

A backoffice request should appear as one trace, with nested observations such as:

```text
http.request / backoffice.process-and-stream
└── backoffice.workflow.dispatch
    ├── langgraph.node.framework_input_guardrails
    ├── langgraph.node.fetch_ticket
    ├── langgraph.node.validation
    ├── langgraph.node.imdb_enrichment
    │   └── mcp.tool_call.consultar_imdb_cliente
    ├── langgraph.node.knowledge_base_enrichment
    │   └── mcp.tool_call.consultar_tais_kb
    ├── langgraph.node.treatment_decision
    └── langgraph.node.siebel_sr_opening
```

## Notes

This fix complements the previous trace correlation fixes. Those fixes solved root trace duplication. This fix solves parent-child hierarchy inside the trace.
