"""Semantic guardrail observability event names.

Numeric/customer-facing taxonomies must be supplied by
ObservabilityCodeMapper configuration and never embedded in the framework core.
"""
GUARDRAIL_EXECUTION_STARTED = "guardrail.execution.started"
GUARDRAIL_ALLOW = "guardrail.result.allow"
GUARDRAIL_SANITIZE = "guardrail.result.sanitize"
GUARDRAIL_BLOCK = "guardrail.result.block"
GUARDRAIL_RETRY = "guardrail.result.retry"
GUARDRAIL_HANDOVER = "guardrail.result.handover"
GUARDRAIL_OBSERVE = "guardrail.result.observe"
GUARDRAIL_FAIL_CLOSED = "guardrail.result.fail_closed"
GUARDRAIL_EXECUTION_COMPLETED = "guardrail.execution.completed"
