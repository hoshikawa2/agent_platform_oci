from __future__ import annotations

import inspect
from copy import deepcopy
from typing import Any
from uuid import uuid4

from .models import WorkflowDefinition, WorkflowRunResult
from .registry import DEFAULT_WORKFLOW_ACTIONS, WorkflowActionRegistry
from .repository import FileWorkflowRepository


def _resolve(path: str, state: dict[str, Any]) -> Any:
    if not isinstance(path, str) or not path.startswith("$."):
        return path
    value: Any = state
    for part in path[2:].split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _render(value: Any, state: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return _resolve(value, state)
    if isinstance(value, dict):
        return {k: _render(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [_render(v, state) for v in value]
    return value


def _matches(condition: dict[str, Any] | None, state: dict[str, Any]) -> bool:
    if not condition:
        return True
    actual = _resolve(str(condition.get("path", "")), state)
    if "equals" in condition:
        return actual == condition["equals"]
    if "not_equals" in condition:
        return actual != condition["not_equals"]
    if "exists" in condition:
        return (actual is not None) is bool(condition["exists"])
    if "in" in condition:
        return actual in condition["in"]
    raise ValueError(f"Condição não suportada: {condition}")


class WorkflowRuntime:
    """Executor determinístico genérico. O LangGraph é detalhe interno do framework."""

    def __init__(
        self,
        repository: FileWorkflowRepository,
        *,
        actions: WorkflowActionRegistry | None = None,
        checkpointer: Any | None = None,
        telemetry: Any | None = None,
    ) -> None:
        self.repository = repository
        self.actions = actions or DEFAULT_WORKFLOW_ACTIONS
        self.checkpointer = checkpointer
        self.telemetry = telemetry
        self._compiled: dict[tuple[str, int], Any] = {}

    def _compile(self, definition: WorkflowDefinition):
        try:
            from langgraph.graph import END, StateGraph
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "langgraph não está instalado; instale as dependências do agent-framework para habilitar workflows"
            ) from exc
        key = (definition.name, definition.version)
        if key in self._compiled:
            return self._compiled[key]
        outgoing: dict[str, list[Any]] = {}
        for edge in definition.edges:
            outgoing.setdefault(edge.source, []).append(edge)
        for edges in outgoing.values():
            edges.sort(key=lambda e: e.priority)

        builder = StateGraph(dict)
        for node in definition.nodes:
            action = self.actions.get(node.action)

            async def execute(state: dict[str, Any], *, _node=node, _action=action):
                params = _render(_node.input, state)
                attempts = _node.retry + 1
                last_error: Exception | None = None
                for _ in range(attempts):
                    try:
                        result = _action(params, state)
                        if inspect.isawaitable(result):
                            result = await result
                        if not isinstance(result, dict):
                            raise TypeError(f"Action {_node.action} deve retornar dict")
                        updated = deepcopy(state)
                        updated.setdefault("nodes", {})[_node.id] = result
                        updated["current_node"] = _node.id
                        return updated
                    except Exception as exc:  # retry configurado por nó
                        last_error = exc
                assert last_error is not None
                raise last_error

            builder.add_node(node.id, execute)
            edges = outgoing.get(node.id, [])
            if not edges:
                builder.add_edge(node.id, END)
            elif len(edges) == 1 and not edges[0].when:
                builder.add_edge(node.id, END if edges[0].target in {"END", "__end__"} else edges[0].target)
            else:
                def route(state: dict[str, Any], *, _edges=tuple(edges)) -> str:
                    for edge in _edges:
                        if _matches(edge.when, state):
                            return "__end__" if edge.target in {"END", "__end__"} else edge.target
                    raise RuntimeError("Nenhuma transição do workflow correspondeu ao estado")
                targets = {"__end__": END}
                targets.update({e.target: e.target for e in edges if e.target not in {"END", "__end__"}})
                builder.add_conditional_edges(node.id, route, targets)
        builder.set_entry_point(definition.start)
        graph = builder.compile(checkpointer=self.checkpointer)
        self._compiled[key] = graph
        return graph

    async def arun(self, name: str, payload: dict[str, Any], *, version: int | None = None, execution_id: str | None = None) -> WorkflowRunResult:
        definition = self.repository.get_version(name, version) if version else self.repository.get_active(name)
        eid = execution_id or str(uuid4())
        initial = {"execution_id": eid, "input": deepcopy(payload), "nodes": {}, "current_node": None}
        try:
            state = await self._compile(definition).ainvoke(initial, config={"configurable": {"thread_id": eid}})
            return WorkflowRunResult(execution_id=eid, workflow_name=name, workflow_version=definition.version, status="COMPLETED", output=dict(state.get("nodes") or {}), state=state)
        except Exception as exc:
            return WorkflowRunResult(execution_id=eid, workflow_name=name, workflow_version=definition.version, status="FAILED", error=str(exc), state=initial)
