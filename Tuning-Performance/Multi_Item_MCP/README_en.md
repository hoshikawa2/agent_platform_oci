# Multi-Item MCP

Reference capability for MCP operations that process **multiple items of the same kind** in one user intent: products, orders, services, assets, invoices, lines, contracts, or resources.

This capability is **framework-native**. It does not require a multi-item engine in the agent and does not introduce new mandatory keys in `tools.yaml` or `tool_policies.yaml`.

```text
Agent                    selects the operation; no fan-out engine
  -> tools.yaml          declares array/list
  -> tool_policies.yaml  confirmation + pre-validation
  -> MCP validator       resolves/canonicalizes items
  -> MCP tool/workflow   executes items and returns results[]
  -> Agent Framework     preserves per-item evidence and derives
                         SUCCESS / PARTIAL_SUCCESS / FAILED
  -> Presentation        reports each success/failure
```

## Minimal configuration

`tools.yaml` keeps the existing list contract:

```yaml
tools:
  cancel_products:
    requires: [items]
    args_schema:
      items:
        type: array
```

`tool_policies.yaml` also keeps the current transaction contract:

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

No `multi_item: true`, framework fan-out flag, or extra agent code is required.

## MCP result contract

The primary tool should return `results[]` with boolean `success` or `ok` per item:

```json
{
  "results": [
    {"name": "A", "success": true},
    {"name": "B", "success": false, "error": "not_found"},
    {"name": "C", "success": true}
  ]
}
```

The framework derives `PARTIAL_SUCCESS` for the example above and preserves the successful items.

If the downstream system only supports single-item APIs, put the fan-out inside the MCP Server or domain workflow, not inside the agent.

For the complete contract see:

- `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE_en.md`
- `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE.md`
- `IMPLEMENTACAO_MULTI_ITEM_MCP.md`
