# Multi-item result preservation fix

## Objective
Preserve the terminal outcome of each item executed by the primary transactional tool. A failure in a later auxiliary/composite step must not erase successful item outcomes or turn an already-completed multi-item operation into a total failure.

## Framework-only change
No agent/template business logic is required for this fix. The runtime now recognizes an explicit structural contract on the requested tool: a `results` array with two or more entries carrying boolean `success` or `ok` fields.

For workflow-backed tools the authoritative source is preferentially:

`workflow.output[tool_name].results`

The framework derives one of:
- `SUCCESS`
- `PARTIAL_SUCCESS`
- `FAILED`

and publishes a generic `metadata.multi_item` summary with item counts.

When one or more primary items completed successfully but the outer wrapper is `ok=false` because a later auxiliary/post-processing step failed, the normalized result preserves the original failure as `original_ok=false` / `secondary_error` while exposing the requested operation as operationally successful (`ok=true`).

The LLM context also receives an explicit generic instruction that successful per-item terminal evidence cannot be overwritten by a secondary error and that mixed outcomes must be reported individually.

## Regression tests
Added `tests/test_multi_item_result_normalization.py` covering:
- 2 success + 1 failure -> `PARTIAL_SUCCESS`;
- all primary items successful + later secondary failure -> primary `SUCCESS` preserved;
- single-item behavior unchanged;
- unrelated nested tool results cannot override failure of the requested primary tool.
