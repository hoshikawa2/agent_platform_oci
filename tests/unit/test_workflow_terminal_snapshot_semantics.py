from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

import pytest

from agent_framework.workflows import FileWorkflowRepository, WorkflowActionRegistry, WorkflowRuntime


def _write_workflow(tmp_path: Path) -> None:
    (tmp_path / "terminal.active.yaml").write_text("version: 1\n", encoding="utf-8")
    (tmp_path / "terminal.v1.yaml").write_text(
        """name: terminal
version: 1
start: finish
nodes:
  - id: finish
    action: finish
edges:
  - from: finish
    to: END
""",
        encoding="utf-8",
    )


def _terminal_state(execution_id: str) -> dict:
    return {
        "execution_id": execution_id,
        "workflow_name": "terminal",
        "workflow_version": 1,
        "input": {},
        "nodes": {"finish": {"success": True}},
        "vars": {"finish": {"success": True}},
        "output": {"success": True},
        "trace": [{"node": "finish", "action": "finish", "attempt": 1, "status": "COMPLETED"}],
        "current_node": "finish",
    }


class _FakeGraph:
    def __init__(self, state: dict, snapshot):
        self.state = state
        self.snapshot = snapshot

    async def ainvoke(self, *args, **kwargs):
        return self.state

    async def aget_state(self, config):
        return self.snapshot


@pytest.mark.asyncio
async def test_arun_truthy_next_without_interrupt_is_completed_when_definition_is_terminal(tmp_path: Path, monkeypatch):
    _write_workflow(tmp_path)
    runtime = WorkflowRuntime(FileWorkflowRepository(tmp_path), actions=WorkflowActionRegistry())
    state = _terminal_state("exec-1")
    # Regression shape observed in production: LangGraph still exposes a truthy
    # next, but there is no real interrupt and the current node routes to END.
    snapshot = SimpleNamespace(next=("finish__continue",), tasks=(), values=state)
    monkeypatch.setattr(runtime, "_compile", lambda definition: _FakeGraph(state, snapshot))

    result = await runtime.arun("terminal", {}, execution_id="exec-1")

    assert result.status == "COMPLETED"
    assert result.pause is None
    assert result.state["current_node"] == "finish"


@pytest.mark.asyncio
async def test_aresume_truthy_next_without_interrupt_is_completed_when_definition_is_terminal(tmp_path: Path, monkeypatch):
    _write_workflow(tmp_path)
    runtime = WorkflowRuntime(FileWorkflowRepository(tmp_path), actions=WorkflowActionRegistry())
    state = _terminal_state("exec-2")
    snapshot = SimpleNamespace(next=("finish__continue",), tasks=(), values=state)
    monkeypatch.setattr(runtime, "_compile", lambda definition: _FakeGraph(state, snapshot))
    # aresume imports langgraph.types.Command before invoking the compiled graph.
    langgraph_module = ModuleType("langgraph")
    types_module = ModuleType("langgraph.types")
    class _Command:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
    types_module.Command = _Command
    monkeypatch.setitem(sys.modules, "langgraph", langgraph_module)
    monkeypatch.setitem(sys.modules, "langgraph.types", types_module)

    result = await runtime.aresume("terminal", "exec-2", "sim")

    assert result.status == "COMPLETED"
    assert result.pause is None


@pytest.mark.asyncio
async def test_real_interrupt_still_has_precedence_over_structural_terminal(tmp_path: Path, monkeypatch):
    _write_workflow(tmp_path)
    runtime = WorkflowRuntime(FileWorkflowRepository(tmp_path), actions=WorkflowActionRegistry())
    state = _terminal_state("exec-3")
    interrupt = SimpleNamespace(value={"node": "finish", "expected_input": {"key": "confirm"}})
    task = SimpleNamespace(interrupts=(interrupt,))
    snapshot = SimpleNamespace(next=("finish__pause",), tasks=(task,), values=state)
    monkeypatch.setattr(runtime, "_compile", lambda definition: _FakeGraph(state, snapshot))

    result = await runtime.arun("terminal", {}, execution_id="exec-3")

    assert result.status == "PAUSED"
    assert result.pause == {"node": "finish", "expected_input": {"key": "confirm"}}


@pytest.mark.asyncio
async def test_pending_nonterminal_without_interrupt_fails_closed_instead_of_faking_pause(tmp_path: Path, monkeypatch):
    (tmp_path / "nonterminal.active.yaml").write_text("version: 1\n", encoding="utf-8")
    (tmp_path / "nonterminal.v1.yaml").write_text(
        """name: nonterminal
version: 1
start: one
nodes:
  - id: one
    action: one
  - id: two
    action: two
edges:
  - from: one
    to: two
  - from: two
    to: END
""",
        encoding="utf-8",
    )
    runtime = WorkflowRuntime(FileWorkflowRepository(tmp_path), actions=WorkflowActionRegistry())
    state = {
        "execution_id": "exec-4",
        "workflow_name": "nonterminal",
        "workflow_version": 1,
        "input": {},
        "nodes": {"one": {"success": True}},
        "vars": {},
        "output": {},
        "trace": [{"node": "one", "action": "one", "attempt": 1, "status": "COMPLETED"}],
        "current_node": "one",
    }
    snapshot = SimpleNamespace(next=("two",), tasks=(), values=state)
    monkeypatch.setattr(runtime, "_compile", lambda definition: _FakeGraph(state, snapshot))

    result = await runtime.arun("nonterminal", {}, execution_id="exec-4")

    assert result.status == "FAILED"
    assert "trabalho pendente sem interrupt real" in (result.error or "")
    assert result.pause is None

@pytest.mark.asyncio
async def test_persisted_interrupt_in_snapshot_values_is_real_pause(tmp_path: Path, monkeypatch):
    """LangGraph may persist interrupts in values['__interrupt__'] only.

    Regression: this shape used to be mistaken for non-terminal pending work
    when snapshot.next pointed at a framework-generated ``__pause`` node.
    """
    _write_workflow(tmp_path)
    runtime = WorkflowRuntime(FileWorkflowRepository(tmp_path), actions=WorkflowActionRegistry())
    state = _terminal_state("exec-values-interrupt")
    pause_payload = {
        "node": "finish",
        "prompt": "Confirma?",
        "expected_input": {"key": "resposta_usuario", "allowed_values": ["SIM", "NAO"]},
    }
    state["__interrupt__"] = [{"value": pause_payload, "id": "pause-1"}]
    # current_node is deliberately non-terminal so the PAUSED decision must
    # come from the persisted interrupt, not structural-terminal detection.
    state["current_node"] = None
    snapshot = SimpleNamespace(next=("finish__pause",), tasks=(), values=state)
    monkeypatch.setattr(runtime, "_compile", lambda definition: _FakeGraph(state, snapshot))

    result = await runtime.arun("terminal", {}, execution_id="exec-values-interrupt")

    assert result.status == "PAUSED"
    assert result.pause == pause_payload
    assert result.error is None


def test_snapshot_interrupts_deduplicates_task_and_persisted_shapes(tmp_path: Path):
    _write_workflow(tmp_path)
    runtime = WorkflowRuntime(FileWorkflowRepository(tmp_path), actions=WorkflowActionRegistry())
    payload = {"node": "finish", "expected_input": {"key": "confirm"}}
    task = SimpleNamespace(interrupts=(SimpleNamespace(value=payload),))
    snapshot = SimpleNamespace(
        tasks=(task,),
        values={"__interrupt__": [{"value": payload, "id": "same-pause"}]},
        interrupts=(),
    )

    assert runtime._snapshot_interrupts(snapshot) == [payload]
