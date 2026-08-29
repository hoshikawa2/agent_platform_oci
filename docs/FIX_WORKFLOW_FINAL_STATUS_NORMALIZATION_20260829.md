# Workflow final status normalization

A resumed domain workflow may be returned by a legacy adapter with `status=PAUSED` even after its terminal node has emitted `workflow_response_final=true`.

The framework now treats `workflow_response_final=true` as the authoritative interaction-lifecycle signal and normalizes that stale adapter status to `COMPLETED` before capturing the workflow latch. This clears the paused workflow/expected-input state, persists an operational-context boundary for the next user turn, and keeps the same session identifiers.

Contextual re-entry routing now also degrades safely to the configured fallback when an LLM router response cannot be parsed, rather than propagating a structured-output exception to the HTTP endpoint.
