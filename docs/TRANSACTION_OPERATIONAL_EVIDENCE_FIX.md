# Transaction Operational Evidence

## Problem

A confirmed transactional tool result was available only in the execution turn. On a later read-only turn, conversational memory could still mention the prior transaction (for example, a cancellation protocol), while the groundedness judge received only the current MCP results. This could classify a factually correct follow-up as unsupported.

## Fix

The framework now records completed/failed transactional tool outcomes as bounded operational evidence in LangGraph state/checkpoint (`transaction_evidence`). This is operational state, not Long Term Memory.

For each new turn, the runtime correlates previous transaction evidence with the current resource using generic identifiers (`*_id`, `order_id`, `invoice_id`, `asset_id`, `resource_key`, etc.). Only relevant evidence is materialized as `relevant_transaction_evidence`.

The same relevant evidence is:

- injected into the answering LLM prompt;
- merged with current MCP results for groundedness judges;
- exposed in response metadata as `transaction_evidence` for diagnostics;
- emitted with the completion telemetry event.

The history is bounded to the 10 most recent transaction outcomes, and at most 5 correlated entries are injected for a turn.

## Expected retail example

1. `cancelar_pedido(PED-1001)` returns protocol `CANCEL-2026-001`.
2. The result is persisted as transaction evidence.
3. The next `consultar_pedido(PED-1001)` returns `EM_TRANSPORTE`.
4. The answering agent and groundedness judge receive both the current order result and the prior cancellation evidence.
5. A response that mentions `CANCEL-2026-001` is grounded rather than treated as an unsupported claim.
