from __future__ import annotations

import inspect
from copy import deepcopy
from typing import Any
from uuid import uuid4

from .models import WorkflowDefinition, WorkflowPause, WorkflowRunResult
from .registry import DEFAULT_WORKFLOW_ACTIONS, WorkflowActionRegistry
from .repository import FileWorkflowRepository


def _resolve(path: Any, state: dict[str, Any]) -> Any:
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


def _condition_value(value: Any, state: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$."):
        return _resolve(value, state)
    return value


def _matches(condition: dict[str, Any] | None, state: dict[str, Any]) -> bool:
    """Evaluate both framework and legacy/TIM workflow condition syntaxes."""
    if not condition:
        return True
    if "all" in condition:
        return all(_matches(item, state) for item in condition["all"])
    if "any" in condition:
        return any(_matches(item, state) for item in condition["any"])
    if "not" in condition:
        return not _matches(condition["not"], state)
    if "eq" in condition:
        left, right = condition["eq"]
        return _condition_value(left, state) == _condition_value(right, state)
    if "neq" in condition:
        left, right = condition["neq"]
        return _condition_value(left, state) != _condition_value(right, state)
    if "exists" in condition and isinstance(condition["exists"], str):
        return _resolve(condition["exists"], state) is not None

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


def _normalize_resume(value: Any, pause: WorkflowPause) -> Any:
    expected = pause.expected_input
    if expected is None:
        return value
    normalized = value
    if isinstance(value, str):
        if expected.normalize == "upper_strip":
            normalized = value.strip().upper()
        elif expected.normalize == "lower_strip":
            normalized = value.strip().lower()
        elif expected.normalize == "strip":
            normalized = value.strip()
    if expected.allowed_values and normalized not in expected.allowed_values:
        raise ValueError(
            f"Entrada de retomada inválida para '{expected.key}': {normalized!r}; "
            f"esperado um de {expected.allowed_values!r}"
        )
    return normalized


def _exception_details(exc: Exception) -> dict[str, Any]:
    """Preserve structured external-error facts without coupling the framework to a provider."""
    details: dict[str, Any] = {"type": type(exc).__name__}
    for attr in ("status_code", "body", "attempts", "code", "metadata"):
        value = getattr(exc, attr, None)
        if value not in (None, "", [], {}):
            details[attr] = value
    return details


class WorkflowRuntime:
    """Executor determinístico genérico; LangGraph é detalhe interno do framework.

    Pause/resume é implementado com ``langgraph.types.interrupt`` em um nó
    separado do action node. Isso é importante: uma retomada nunca reexecuta a
    action anterior (que pode ter efeitos externos).
    """

    def __init__(
        self,
        repository: FileWorkflowRepository,
        *,
        actions: WorkflowActionRegistry | None = None,
        checkpointer: Any | None = None,
        telemetry: Any | None = None,
        allow_deterministic_fallback: bool = False,
    ) -> None:
        self.repository = repository
        self.actions = actions or DEFAULT_WORKFLOW_ACTIONS
        self.checkpointer = checkpointer
        self.telemetry = telemetry
        self.allow_deterministic_fallback = bool(allow_deterministic_fallback)
        self._compiled: dict[tuple[str, int], Any] = {}
        self._fallback_paused: dict[str, dict[str, Any]] = {}

    def _outgoing(self, definition: WorkflowDefinition) -> dict[str, list[Any]]:
        outgoing: dict[str, list[Any]] = {}
        for edge in definition.edges:
            outgoing.setdefault(edge.source, []).append(edge)
        for edges in outgoing.values():
            edges.sort(key=lambda e: e.priority)
        return outgoing

    def _next_node(self, source: str, state: dict[str, Any], outgoing: dict[str, list[Any]]) -> str | None:
        edges = outgoing.get(source, [])
        if not edges:
            return None
        for edge in edges:
            if _matches(edge.when, state):
                return None if edge.target in {"END", "__end__"} else edge.target
        raise RuntimeError("Nenhuma transição do workflow correspondeu ao estado")

    async def _execute_action_fallback(self, node: Any, state: dict[str, Any]) -> dict[str, Any]:
        action = self.actions.get(node.action)
        params = _render(node.input, state)
        attempts = node.retry + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                result = action(params, state)
                if inspect.isawaitable(result):
                    result = await result
                if not isinstance(result, dict):
                    raise TypeError(f"Action {node.action} deve retornar dict")
                updated = deepcopy(state)
                updated.setdefault("nodes", {})[node.id] = result
                updated.setdefault("vars", {})[node.id] = result
                updated["output"] = result
                updated["current_node"] = node.id
                updated.setdefault("trace", []).append({
                    "node": node.id,
                    "action": node.action,
                    "attempt": attempt,
                    "status": "COMPLETED",
                })
                return updated
            except Exception as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def _run_fallback(
        self,
        definition: WorkflowDefinition,
        state: dict[str, Any],
        *,
        start_node: str,
        execution_id: str,
    ) -> WorkflowRunResult:
        """Deterministic offline test backend.

        This backend is deliberately opt-in and never selected in production by
        default.  It exercises the framework DSL/actions/branching/pause-resume
        when the external LangGraph package cannot be installed in a restricted
        build environment.
        """
        outgoing = self._outgoing(definition)
        by_id = {node.id: node for node in definition.nodes}
        current: str | None = start_node
        try:
            while current is not None:
                node = by_id[current]
                state = await self._execute_action_fallback(node, state)
                pause = node.pause if node.pause and node.pause.enabled else None
                if pause and (pause.when is None or _matches(pause.when, state)):
                    prompt = _resolve(pause.return_from, state)
                    expected = pause.expected_input
                    descriptor = {
                        "node": node.id,
                        "prompt": prompt,
                        "expected_input": expected.model_dump() if expected else None,
                        "resume_from": pause.resume_from,
                    }
                    self._fallback_paused[execution_id] = {
                        "definition": definition,
                        "state": deepcopy(state),
                        "pause": pause,
                        "next": pause.resume_from or self._next_node(node.id, state, outgoing),
                    }
                    return WorkflowRunResult(
                        execution_id=execution_id,
                        workflow_name=definition.name,
                        workflow_version=definition.version,
                        status="PAUSED",
                        output=dict(state.get("nodes") or {}),
                        state=state,
                        pause=descriptor,
                        trace=list(state.get("trace") or []),
                    )
                current = self._next_node(node.id, state, outgoing)
            return self._result_from_state(definition, execution_id, state)
        except Exception as exc:
            return WorkflowRunResult(
                execution_id=execution_id,
                workflow_name=definition.name,
                workflow_version=definition.version,
                status="FAILED",
                error=str(exc),
                error_details=_exception_details(exc),
                output=dict(state.get("nodes") or {}),
                state=state,
                trace=list(state.get("trace") or []),
            )

    async def _resume_fallback(
        self,
        name: str,
        execution_id: str,
        resume_value: Any,
        *,
        version: int | None = None,
    ) -> WorkflowRunResult:
        saved = self._fallback_paused.pop(execution_id, None)
        if not saved:
            definition = self.repository.get_version(name, version) if version else self.repository.get_active(name)
            return WorkflowRunResult(
                execution_id=execution_id,
                workflow_name=definition.name,
                workflow_version=definition.version,
                status="FAILED",
                error="workflow pausado não encontrado",
                state={},
            )
        definition = saved["definition"]
        state = deepcopy(saved["state"])
        pause = saved["pause"]
        expected = pause.expected_input
        if expected:
            value = resume_value.get(expected.key) if isinstance(resume_value, dict) and expected.key in resume_value else resume_value
            state.setdefault("input", {})[expected.key] = _normalize_resume(value, pause)
        elif isinstance(resume_value, dict):
            state.setdefault("input", {}).update(resume_value)
        else:
            state.setdefault("input", {})["resume_value"] = resume_value
        state["pause"] = None
        # Keep parity with LangGraph trace semantics: resume is technical, not a business action.
        state.setdefault("trace", []).append({
            "node": state.get("current_node"),
            "action": "pause_resume",
            "status": "RESUMED",
        })
        next_node = saved.get("next")
        if next_node is None:
            return self._result_from_state(definition, execution_id, state)
        return await self._run_fallback(definition, state, start_node=next_node, execution_id=execution_id)

    def _compile(self, definition: WorkflowDefinition):
        try:
            from langgraph.graph import END, StateGraph
            from langgraph.types import interrupt
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

        def add_normal_routing(source: str, edges: list[Any]) -> None:
            if not edges:
                builder.add_edge(source, END)
            elif len(edges) == 1 and not edges[0].when:
                builder.add_edge(source, END if edges[0].target in {"END", "__end__"} else edges[0].target)
            else:
                def route(state: dict[str, Any], *, _edges=tuple(edges)) -> str:
                    for edge in _edges:
                        if _matches(edge.when, state):
                            return "__end__" if edge.target in {"END", "__end__"} else edge.target
                    raise RuntimeError("Nenhuma transição do workflow correspondeu ao estado")
                targets = {"__end__": END}
                targets.update({e.target: e.target for e in edges if e.target not in {"END", "__end__"}})
                builder.add_conditional_edges(source, route, targets)

        for node in definition.nodes:
            action = self.actions.get(node.action)

            async def execute(state: dict[str, Any], *, _node=node, _action=action):
                params = _render(_node.input, state)
                attempts = _node.retry + 1
                last_error: Exception | None = None
                for attempt in range(1, attempts + 1):
                    try:
                        result = _action(params, state)
                        if inspect.isawaitable(result):
                            result = await result
                        if not isinstance(result, dict):
                            raise TypeError(f"Action {_node.action} deve retornar dict")
                        updated = deepcopy(state)
                        updated.setdefault("nodes", {})[_node.id] = result
                        updated.setdefault("vars", {})[_node.id] = result
                        updated["output"] = result
                        updated["current_node"] = _node.id
                        updated.setdefault("trace", []).append({
                            "node": _node.id,
                            "action": _node.action,
                            "attempt": attempt,
                            "status": "COMPLETED",
                        })
                        return updated
                    except Exception as exc:
                        last_error = exc
                assert last_error is not None
                raise last_error

            builder.add_node(node.id, execute)
            edges = outgoing.get(node.id, [])
            pause = node.pause if node.pause and node.pause.enabled else None
            if pause:
                pause_id = f"{node.id}__pause"

                def should_pause(state: dict[str, Any], *, _pause=pause) -> str:
                    if _pause.when is None or _matches(_pause.when, state):
                        return "pause"
                    return "continue"

                async def pause_node(state: dict[str, Any], *, _node=node, _pause=pause):
                    prompt = _resolve(_pause.return_from, state)
                    expected = _pause.expected_input
                    descriptor = {
                        "node": _node.id,
                        "prompt": prompt,
                        "expected_input": expected.model_dump() if expected else None,
                        "resume_from": _pause.resume_from,
                    }
                    resumed = interrupt(descriptor)
                    updated = deepcopy(state)
                    if expected:
                        value = resumed.get(expected.key) if isinstance(resumed, dict) and expected.key in resumed else resumed
                        updated.setdefault("input", {})[expected.key] = _normalize_resume(value, _pause)
                    elif isinstance(resumed, dict):
                        updated.setdefault("input", {}).update(resumed)
                    else:
                        updated.setdefault("input", {})["resume_value"] = resumed
                    updated["pause"] = None
                    updated.setdefault("trace", []).append({
                        "node": _node.id,
                        "action": "pause_resume",
                        "status": "RESUMED",
                    })
                    return updated

                builder.add_node(pause_id, pause_node)
                builder.add_conditional_edges(
                    node.id,
                    should_pause,
                    {"pause": pause_id, "continue": f"{node.id}__continue"},
                )
                # tiny pass-through node lets us attach the original routing only once
                continue_id = f"{node.id}__continue"
                builder.add_node(continue_id, lambda state: state)
                add_normal_routing(continue_id, edges)

                if pause.resume_from:
                    builder.add_edge(pause_id, pause.resume_from)
                else:
                    add_normal_routing(pause_id, edges)
            else:
                add_normal_routing(node.id, edges)

        builder.set_entry_point(definition.start)
        graph = builder.compile(checkpointer=self.checkpointer)
        self._compiled[key] = graph
        return graph

    def _result_from_state(self, definition: WorkflowDefinition, eid: str, state: dict[str, Any]) -> WorkflowRunResult:
        return WorkflowRunResult(
            execution_id=eid,
            workflow_name=definition.name,
            workflow_version=definition.version,
            status="COMPLETED",
            output=dict(state.get("nodes") or {}),
            state=state,
            trace=list(state.get("trace") or []),
        )

    async def arun(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        version: int | None = None,
        execution_id: str | None = None,
    ) -> WorkflowRunResult:
        definition = self.repository.get_version(name, version) if version else self.repository.get_active(name)
        eid = execution_id or str(uuid4())
        initial = {
            "execution_id": eid,
            "workflow_name": definition.name,
            "workflow_version": definition.version,
            "input": deepcopy(payload),
            "nodes": {},
            "vars": {},
            "output": {},
            "trace": [],
            "current_node": None,
        }
        config = {"configurable": {"thread_id": eid}}
        if self.allow_deterministic_fallback:
            try:
                import langgraph  # noqa: F401
            except ModuleNotFoundError:
                return await self._run_fallback(definition, initial, start_node=definition.start, execution_id=eid)
        try:
            graph = self._compile(definition)
            state = await graph.ainvoke(initial, config=config)
            snapshot = await graph.aget_state(config)
            if getattr(snapshot, "next", None):
                interrupts = []
                for task in getattr(snapshot, "tasks", ()) or ():
                    for item in getattr(task, "interrupts", ()) or ():
                        interrupts.append(getattr(item, "value", item))
                pause = interrupts[-1] if interrupts else {"node": state.get("current_node")}
                return WorkflowRunResult(
                    execution_id=eid,
                    workflow_name=name,
                    workflow_version=definition.version,
                    status="PAUSED",
                    output=dict(state.get("nodes") or {}),
                    state=state,
                    pause=pause if isinstance(pause, dict) else {"value": pause},
                    trace=list(state.get("trace") or []),
                )
            return self._result_from_state(definition, eid, state)
        except Exception as exc:
            # Preserve the last durable LangGraph snapshot instead of discarding
            # every node completed before the failure. This is critical for
            # transactional workflows: a protocol/tool may have succeeded before
            # a later external API failed, and callers need that evidence for
            # recovery, idempotency and customer messaging.
            partial = initial
            try:
                graph = locals().get("graph")
                if graph is not None:
                    snapshot = await graph.aget_state(config)
                    values = getattr(snapshot, "values", None)
                    if isinstance(values, dict) and values:
                        partial = values
            except Exception:
                partial = initial
            return WorkflowRunResult(
                execution_id=eid,
                workflow_name=name,
                workflow_version=definition.version,
                status="FAILED",
                error=str(exc),
                error_details=_exception_details(exc),
                output=dict(partial.get("nodes") or {}),
                state=partial,
                trace=list(partial.get("trace") or []),
            )

    async def aresume(
        self,
        name: str,
        execution_id: str,
        resume_value: Any,
        *,
        version: int | None = None,
    ) -> WorkflowRunResult:
        definition = self.repository.get_version(name, version) if version else self.repository.get_active(name)
        config = {"configurable": {"thread_id": execution_id}}
        if self.allow_deterministic_fallback:
            try:
                import langgraph  # noqa: F401
            except ModuleNotFoundError:
                return await self._resume_fallback(name, execution_id, resume_value, version=version)
        try:
            from langgraph.types import Command
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError("langgraph não está instalado") from exc
        try:
            graph = self._compile(definition)
            state = await graph.ainvoke(Command(resume=resume_value), config=config)
            snapshot = await graph.aget_state(config)
            if getattr(snapshot, "next", None):
                interrupts = []
                for task in getattr(snapshot, "tasks", ()) or ():
                    for item in getattr(task, "interrupts", ()) or ():
                        interrupts.append(getattr(item, "value", item))
                pause = interrupts[-1] if interrupts else {"node": state.get("current_node")}
                return WorkflowRunResult(
                    execution_id=execution_id,
                    workflow_name=name,
                    workflow_version=definition.version,
                    status="PAUSED",
                    output=dict(state.get("nodes") or {}),
                    state=state,
                    pause=pause if isinstance(pause, dict) else {"value": pause},
                    trace=list(state.get("trace") or []),
                )
            return self._result_from_state(definition, execution_id, state)
        except Exception as exc:
            partial: dict[str, Any] = {}
            try:
                graph = locals().get("graph")
                if graph is not None:
                    snapshot = await graph.aget_state(config)
                    values = getattr(snapshot, "values", None)
                    if isinstance(values, dict):
                        partial = values
            except Exception:
                partial = {}
            return WorkflowRunResult(
                execution_id=execution_id,
                workflow_name=name,
                workflow_version=definition.version,
                status="FAILED",
                error=str(exc),
                error_details=_exception_details(exc),
                output=dict(partial.get("nodes") or {}),
                state=partial,
                trace=list(partial.get("trace") or []),
            )
