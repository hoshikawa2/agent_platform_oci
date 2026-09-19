# MCP Multi-item — Developer Guide

## Purpose

Use this guide when a single user intent must operate on **more than one item of the same kind** through MCP, such as multiple products, orders, assets, invoices, lines, contracts, or resources.

The framework already provides generic contracts for **list parameter collection**, **pre-validation/canonicalization**, **transaction confirmation**, **MCP execution**, and **per-item result normalization**. Do not create a second multi-item engine inside an agent.

## Main rule

**Do not implement business fan-out loops in the agent.** The agent declares the tool and parameters; the runtime owns state, confirmation, and evidence. A bulk operation should be exposed as an MCP tool that accepts a collection, or as a transactional tool backed by a domain MCP/workflow that processes the collection.

Recommended flow:

```text
User names N items
  -> Router/Agent selects the tool
  -> Runtime collects/reconciles an array/list parameter
  -> optional pre-validation canonicalizes items
  -> Runtime asks ONE coherent confirmation for the set
  -> MCP receives the collection
  -> MCP/workflow processes each item
  -> MCP returns results[] with success/ok per item
  -> Framework normalizes SUCCESS / PARTIAL_SUCCESS / FAILED
  -> Final composition reports successes and failures individually
```

## 1. Declare a list parameter in `tools.yaml`

The transaction parameter reconciler accepts `type: array` and `type: list`.

```yaml
tools:
  cancel_products:
    description: Cancels one or more customer products.
    mcp_server: accounts
    enabled: true
    tool_type: action
    confirmation_required: true
    requires: [items]
    args_schema:
      items:
        type: array
        label: the products
        description: List of products the customer wants to cancel.
        user_prompt: Which products do you want to cancel?
```

A phrase naming several products can therefore be reconciled into a logical list argument. Domain semantics and canonical name validation remain in MCP/pre-validation, not in the core.

## 2. Use pre-validation for canonicalization

Configure `tool_policies.yaml` when the list must be resolved before confirmation:

```yaml
tool_policies:
  cancel_products:
    operation_type: transactional
    require_confirmation: true
    requires: [items]
    pre_validation:
      enabled: true
      tool: validate_products_for_cancellation
      fail_open: false
```

A validator may return `eligible: true` and replace the raw list through `transaction_decision.resolved_arguments`:

```json
{
  "eligible": true,
  "transaction_decision": {
    "resolved_arguments": {
      "items": [
        {"name": "Product A", "id": "1001"},
        {"name": "Product B", "id": "1002"}
      ]
    },
    "target_tool": "cancel_products",
    "confirmation_message": "Do you confirm cancellation of Product A and Product B?"
  }
}
```

### Partial validation

The pre-validation `eligible` flag is global. **Do not return `eligible: false` only because one list item failed** when other items can still run; that would terminate the entire transaction.

For partial outcomes, the recommended pattern is:

1. return `eligible: true` when at least one item is actionable;
2. canonicalize/preserve the collection in `resolved_arguments`;
3. let the primary tool publish terminal status for **every item** in `results[]`.

If no item can be processed, `eligible: false` is appropriate.

## 3. MCP input contract

Prefer one logical MCP call containing the collection:

```json
{
  "tool_name": "cancel_products",
  "arguments": {
    "customer_id": "123",
    "items": [
      {"name": "Product A", "id": "1001"},
      {"name": "Product B", "id": "1002"}
    ]
  }
}
```

Do not use the agent as an improvised loop that invokes a scalar tool N times. If the downstream backend only offers a single-item API, encapsulate fan-out in the MCP Server or domain workflow while keeping one logical tool for the agent.

## 4. Required per-item result contract

For automatic multi-item recognition, the **requested primary tool** must expose a `results` list with **two or more entries**, and every entry must contain boolean `success` or `ok`.

```json
{
  "ok": true,
  "result": {
    "results": [
      {"id": "1001", "subject": "Product A", "success": true},
      {"id": "1002", "subject": "Product B", "success": false, "reason": "not_found"},
      {"id": "1003", "subject": "Product C", "success": true}
    ]
  }
}
```

Fields such as `id`, `subject`, `name`, `reason`, `error`, and `protocol` are domain-specific and optional. The structural signal required by the normalizer is per-item `success: true|false` or `ok: true|false`.

### Workflow-backed tools

For workflow-backed execution, the preferred authoritative location is:

```text
workflow.output[tool_name].results
```

This prevents an auxiliary/post-processing failure from overwriting terminal outcomes of the requested primary operation.

## 5. What the runtime adds automatically

With a valid `results[]`, the runtime derives:

```json
{
  "multi_item_status": "PARTIAL_SUCCESS",
  "partial_success": true,
  "metadata": {
    "multi_item": {
      "status": "PARTIAL_SUCCESS",
      "items_count": 3,
      "items_succeeded_count": 2,
      "items_failed_count": 1,
      "primary_tool": "cancel_products"
    }
  }
}
```

| Situation | `multi_item_status` |
|---|---|
| all items succeeded | `SUCCESS` |
| mixed success/failure | `PARTIAL_SUCCESS` |
| all items failed | `FAILED` |

If a later step makes the outer wrapper `ok=false` while at least one primary item succeeded, the framework preserves audit information as `original_ok=false` and `secondary_error`, while keeping the executed item outcomes authoritative.

## 6. Anti-patterns

Do not implement a business loop in the agent:

```python
for product in products:
    await tool_router.call("cancel_product", {"product": product})
```

Do not return only a global decision such as:

```json
{"approved": false, "error": "one item failed"}
```

or a single aggregate `success=false` when the actual outcomes are mixed. These formats lose per-item terminal evidence.

## 7. Read-only multi-item calls

The same result contract can be used for bulk queries. Usually only the policy changes:

```yaml
tool_policies:
  query_orders:
    operation_type: read_only
    require_confirmation: false
```

Returning `results[]` with `success/ok` per item ensures one unavailable item does not hide successful queries.

## 8. Idempotency and protocols

For side-effecting operations:

- use a request idempotency key and, when necessary, an item-level key;
- return protocol/operation id on the item itself;
- do not rely only on an aggregate text message;
- on retry, preserve completed items and execute only what domain policy allows.

The runtime preserves evidence; downstream idempotency remains the responsibility of the domain MCP/workflow.

## 9. Developer checklist

- [ ] The tool accepts `array/list` for a multi-item use case.
- [ ] There is no business MCP loop inside the agent class.
- [ ] Canonicalization belongs to pre-validation/MCP, not hardcoded agent logic.
- [ ] Confirmation describes the effective item set.
- [ ] The primary tool returns `results[]` with per-item `success` or `ok`.
- [ ] Partial outcome is not collapsed into a single global failure flag.
- [ ] Workflow-backed tools use `output[tool_name].results` for primary terminal evidence.
- [ ] Tests cover all-success, partial, all-failure, and later auxiliary failure.
- [ ] Final response reports both successes and failures for `PARTIAL_SUCCESS`.

## 10. Framework implementation references

```text
libs/agent_framework/src/agent_framework/runtime/transaction_parameters.py
  - array/list coercion

libs/agent_framework/src/agent_framework/runtime/agent_runtime.py
  - pre-validation and resolved_arguments
  - _primary_multi_item_outcomes()
  - _normalize_multi_item_tool_result()
  - multi-item LLM composition instruction

tests/test_multi_item_result_normalization.py
  - SUCCESS/PARTIAL_SUCCESS regressions and auxiliary-failure protection
```

## 11. Responsibility summary

| Layer | Responsibility |
|---|---|
| Agent | select/declaratively use the tool; do not implement a multi-item engine |
| `tools.yaml` | declare `array/list` parameter and schema |
| `tool_policies.yaml` | confirmation and pre-validation |
| MCP pre-validator | resolve/canonicalize entities and arguments |
| MCP tool/workflow | execute the collection and return per-item outcomes |
| Framework runtime | state, confirmation, multi-item normalization, evidence preservation |
| LLM/presentation | verbalize evidence without hiding per-item success/failure |
