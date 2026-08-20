# Langfuse single trace observer fix

This backend now uses `TelemetryBackedAgentObserver` instead of publishing IC/NOC/GRL through `AgentObserver(analytics=...)`.

Why: when analytics includes the Langfuse provider, observer events such as `IC.AGENT_COMPLETED` and `NOC.006` may create a second root trace with little detail. Emitting those events through `Telemetry.event(...)` keeps them inside the active request/workflow trace.
