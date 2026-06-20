# Langfuse analytics context correlation fix

This patch fixes a remaining trace-splitting issue in the Langfuse analytics publisher.

## Problem

After the framework trace-id normalization fix, the main HTTP/workflow trace was being created correctly, but some IC/NOC/GRL events could still appear as separate root traces in Langfuse, especially events such as:

- `IC.BACKOFFICE_WORKFLOW_COMPLETED`
- `IC.BACKOFFICE_NODE_COMPLETED`
- `NOC.*`

This happened when those analytics events carried only business identifiers such as `transaction_id` or `sessionId`, while the HTTP trace was correlated by `request_id`.

## Fix

`src/agent_framework/analytics/providers/langfuse.py` now merges the current `ObservabilityContext` into analytics event payloads before computing the Langfuse trace context.

Correlation priority is now:

1. Current `trace_id` / `request_id` from `ObservabilityContext`
2. Payload `trace_id` / `request_id`
3. Business fallback: `transaction_id`, `session_id`, `sessionId`

This keeps business IDs in metadata, but ensures Langfuse observations are attached to the active request trace whenever a workflow is running.

## Expected result

In Langfuse `Tracing > Traces`, a single backoffice request should appear as one main trace, such as:

- `http.request.completed`
- or the configured request/workflow root name

Inside that trace, the internal observations should include:

- `backoffice.channel.normalized`
- `backoffice.workflow.dispatch`
- `langgraph.node.*`
- `mcp.tool_call.*`
- `IC.BACKOFFICE_*`
- `NOC.*`
- guardrails and judges

IC/NOC/GRL events should no longer create a separate trace just because they only carried `transaction_id` or `sessionId`.
