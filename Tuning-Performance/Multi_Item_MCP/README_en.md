# Multi-Item MCP

Reference capability for MCP operations that process more than one item under a single logical user intent.

> Multi-item support is **not enabled by `type: array`**. The input may be scalar (`subject`, `id`, `query`) or a collection. Multi-item behavior comes from resolving/executing several items and returning per-item `results[]`.

```text
Agent               selects the operation; no business fan-out
  -> tools.yaml     declares the natural input contract: scalar OR collection
  -> tool_policies  confirmation/requires/pre-validation; no special multi-item syntax
  -> validator      resolves/canonicalizes and may expand one value into items[]
  -> MCP/workflow   executes 1 or N items and returns results[]
  -> framework      preserves per-item evidence and derives SUCCESS/PARTIAL_SUCCESS/FAILED
  -> presentation   reports each success/failure
```

## Scalar pattern

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

`subject` may represent one or many entities. The validator/workflow may expand it into canonical `items[]`.

## Explicit batch pattern

```yaml
args_schema:
  items:
    type: array
```

This is supported, but it is **an interface option, not a requirement**.

## Result contract

```json
{
  "results": [
    {"name": "A", "success": true},
    {"name": "B", "success": false},
    {"name": "C", "success": true}
  ]
}
```

The runtime derives `PARTIAL_SUCCESS` and preserves the successful items.

For full details, read `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE_en.md`.
