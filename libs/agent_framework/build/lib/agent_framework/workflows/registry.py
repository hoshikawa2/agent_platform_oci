from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

WorkflowAction = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


class WorkflowActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, WorkflowAction] = {}

    def register(self, name: str, action: WorkflowAction, *, replace: bool = False) -> None:
        if name in self._actions and not replace:
            raise ValueError(f"Action já registrada: {name}")
        self._actions[name] = action

    def get(self, name: str) -> WorkflowAction:
        try:
            return self._actions[name]
        except KeyError as exc:
            raise KeyError(f"Action de workflow não registrada: {name}") from exc

    def action(self, name: str | None = None):
        def decorator(func: WorkflowAction) -> WorkflowAction:
            self.register(name or func.__name__, func)
            return func
        return decorator


DEFAULT_WORKFLOW_ACTIONS = WorkflowActionRegistry()
workflow_action = DEFAULT_WORKFLOW_ACTIONS.action
