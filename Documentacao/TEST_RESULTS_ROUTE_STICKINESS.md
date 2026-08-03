# Test Results - Semantic Route Stickiness and Global Session Control

Date: 2026-07-31

## Command

```bash
PYTHONPATH=libs/agent_framework/src pytest -q tests/unit/test_semantic_route_stickiness.py
```

## Result

```text
9 passed
```

## Covered scenarios

1. `CONTINUE` bypasses the Enterprise Router.
2. `ROUTE` falls back to the Enterprise Router.
3. Low-confidence `CONTINUE` falls back safely.
4. Invalid model output falls back safely.
5. With no active agent, the lightweight classifier can still detect global session actions.
6. `HUMAN_HANDOFF` returns the global `human_handoff` route and session-control metadata.
7. `END_SESSION` returns the global `end_session` route and session-control metadata.
8. Global actions work on the first turn.
9. `CONTINUE` without an active agent is normalized to `ROUTE`.

## Additional validation

```bash
python -m compileall -q libs/agent_framework/src templates/agent_template_backend/app
```

Compilation completed successfully.
