# MCP Multi-item — Developer Guide

## Purpose

Use this guide when one user intent must operate on **more than one item of the same kind**. The framework already supports item resolution/canonicalization, transactional confirmation, MCP/workflow execution, per-item evidence preservation, and `SUCCESS` / `PARTIAL_SUCCESS` / `FAILED` normalization.

> **Core rule:** multi-item is a property of resolution, execution, and results. **It is not defined by the input parameter type.** A tool may receive `subject: string`, `id: string`, `items: array`, or another natural domain contract and still process multiple items.

## Main rule

**Do not implement business fan-out in the agent.** The agent selects the intent/tool and uses the runtime. Expansion to multiple items may happen in the pre-validator, MCP tool, or domain workflow.

```text
User names N items
  -> Router/Agent selects the tool
  -> Runtime collects the parameters declared by the tool
  -> Input may be scalar or a collection
  -> optional pre-validation resolves/expands/canonicalizes N items
  -> Runtime requests ONE coherent confirmation for the effective set
  -> MCP tool/workflow processes 1 or N items
  -> Primary tool returns results[] with success/ok per item
  -> Framework normalizes SUCCESS / PARTIAL_SUCCESS / FAILED
  -> Final composition reports successes and failures individually
```

## 1. Declare the natural operation contract in `tools.yaml`

The framework **does not require `array/list`** for multi-item support.

Use:
- a scalar (`subject`, `id`, `query`, etc.) when the natural interface accepts an expression that may represent one or many entities;
- `array/list` when the MCP interface is naturally batch-oriented.

### Pattern A — scalar expanded later

```yaml
tools:
  cancelar_vas_avulso:
    args_schema:
      subject:
        type: string
```

Possible input:

```text
subject = "TIM Fashion, Aya Audiobooks, Neymar Jr"
```

### Pattern B — explicit collection

```yaml
tools:
  cancelar_produtos:
    args_schema:
      items:
        type: array
```

Both patterns are valid. **Do not change an existing scalar interface to array only to enable multi-item.**

## 2. `tool_policies.yaml` has no special multi-item syntax

Example:

```yaml
tool_policies:
  cancelar_vas_avulso:
    operation_type: transactional
    require_confirmation: true
    requires:
      - subject
    pre_validation:
      enabled: true
      tool: validar_vas_subject
      fail_open: false
```

`subject` may represent one or multiple entities.

## 3. Pre-validation may expand a scalar into multiple canonical items

```json
{
  "eligible": true,
  "resolved_subjects": ["A", "B", "C"],
  "transaction_decision": {
    "resolved_arguments": {
      "subject": "A, B, C",
      "items": [
        {"name": "A"},
        {"name": "B"},
        {"name": "C"}
      ]
    }
  }
}
```

`resolved_arguments.items[]` is a useful canonical execution representation, but it does **not** require `tools.yaml` to expose `items` as its input parameter.

With `fail_open: false`, do not return global `eligible: false` merely because one item fails while other items remain actionable. Keep `eligible: true`, preserve per-item eligibility, and let the primary tool produce terminal `results[]`.

## 4. MCP input contract: one logical operation, not necessarily an explicit collection

Prefer one logical MCP operation for the agent. It may:
1. receive a scalar and expand it in validator/workflow;
2. receive an explicit collection;
3. receive an expression/identifier and discover items inside the tool/workflow.

If the backend only exposes a unit API, keep fan-out inside the **MCP Server or domain workflow**, not inside the agent.

## 5. Required per-item result contract

Automatic multi-item normalization is driven by the **primary tool result**, not by the input schema. The primary tool must expose `results` with at least two items and each item must contain boolean `success` or `ok`.

```json
{
  "results": [
    {"subject": "A", "success": true},
    {"subject": "B", "success": false, "reason": "not_found"},
    {"subject": "C", "success": true}
  ]
}
```

For workflow-backed tools, the preferred authoritative path is:

```text
workflow.output[tool_name].results
```

## 6. Framework normalization

| Situation | `multi_item_status` |
|---|---|
| all items succeed | `SUCCESS` |
| some succeed and some fail | `PARTIAL_SUCCESS` |
| all fail | `FAILED` |

A later auxiliary error must not erase terminal per-item evidence already produced by the primary tool.

## 7. Do not

Do not create an MCP loop in the agent, reduce mixed results to one global boolean, or redesign a working scalar contract merely to make it an array.

## 8. Checklist

- [ ] Agent selects the operation and does not implement business fan-out.
- [ ] `tools.yaml` declares the natural contract, scalar or collection.
- [ ] No special `multi_item: true` setting is required.
- [ ] `tool_policies.yaml` keeps the real domain `requires`; `subject` does not need to become `items`.
- [ ] Validator/tool/workflow expands and canonicalizes multiple entities when needed.
- [ ] Confirmation represents the effective resolved set.
- [ ] With `fail_open: false`, one invalid item does not force global `eligible: false` if other items remain actionable.
- [ ] Primary tool returns `results[]` with `success`/`ok` per item.
- [ ] Workflow prefers `output[tool_name].results` for terminal evidence.
- [ ] Partial results remain visible and are reported individually.

## 9. Responsibility summary

| Layer | Responsibility |
|---|---|
| Agent | select intent/tool; do not implement a multi-item engine |
| `tools.yaml` | declare the natural input contract; scalar or collection |
| `tool_policies.yaml` | confirmation, `requires`, pre-validation; no special multi-item syntax |
| MCP pre-validator | resolve/canonicalize and optionally expand one parameter into N items |
| MCP tool/workflow | execute 1 or N items and return per-item results |
| Framework runtime | maintain state/confirmation, interpret `results[]`, preserve evidence, calculate aggregate status |
| LLM/presentation | report per-item outcomes without erasing successful/failed evidence |
