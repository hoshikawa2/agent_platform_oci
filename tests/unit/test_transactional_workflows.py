from pathlib import Path

import pytest

from agent_framework.workflows import (
    FileWorkflowRepository,
    WorkflowActionRegistry,
    WorkflowRuntime,
    WorkflowToolExecutor,
)


@pytest.mark.asyncio
async def test_deterministic_workflow_routes_and_caches(tmp_path: Path):
    (tmp_path / "refund.active.yaml").write_text("version: 1\n", encoding="utf-8")
    (tmp_path / "refund.v1.yaml").write_text(
        """name: refund
version: 1
start: validate
nodes:
  - id: validate
    action: validate
    input: {order_id: $.input.order_id}
  - id: execute
    action: execute
    input: {order_id: $.input.order_id}
edges:
  - from: validate
    to: execute
    when: {path: $.nodes.validate.valid, equals: true}
  - from: validate
    to: END
    when: {path: $.nodes.validate.valid, equals: false}
  - from: execute
    to: END
""",
        encoding="utf-8",
    )
    actions = WorkflowActionRegistry()
    actions.register("validate", lambda params, state: {"valid": params["order_id"] == "123"})
    actions.register("execute", lambda params, state: {"protocol": "P-1"})
    runtime = WorkflowRuntime(FileWorkflowRepository(tmp_path), actions=actions)

    ok = await runtime.arun("refund", {"order_id": "123"})
    assert ok.status == "COMPLETED"
    assert ok.output["execute"]["protocol"] == "P-1"
    assert len(runtime._compiled) == 1

    rejected = await runtime.arun("refund", {"order_id": "999"})
    assert rejected.status == "COMPLETED"
    assert "execute" not in rejected.output
    assert len(runtime._compiled) == 1


@pytest.mark.asyncio
async def test_policy_adapter_runs_only_workflow_mode(tmp_path: Path):
    (tmp_path / "job.active.yaml").write_text("version: 1\n", encoding="utf-8")
    (tmp_path / "job.v1.yaml").write_text(
        """name: job
version: 1
start: one
nodes:
  - id: one
    action: one
edges:
  - from: one
    to: END
""",
        encoding="utf-8",
    )
    actions = WorkflowActionRegistry()
    actions.register("one", lambda params, state: {"ok": True})
    adapter = WorkflowToolExecutor(WorkflowRuntime(FileWorkflowRepository(tmp_path), actions=actions))
    assert await adapter.execute_from_policy(tool_name="x", arguments={}, policy={"execution": {"mode": "direct_tool"}}) is None
    result = await adapter.execute_from_policy(tool_name="x", arguments={}, policy={"execution": {"mode": "workflow", "workflow": "job", "version": "active"}})
    assert result["status"] == "COMPLETED"

@pytest.mark.asyncio
async def test_offline_regression_mode_forces_deterministic_backend_even_if_langgraph_is_available(tmp_path: Path, monkeypatch):
    (tmp_path / "offline.active.yaml").write_text("version: 1\n", encoding="utf-8")
    (tmp_path / "offline.v1.yaml").write_text(
        """name: offline
version: 1
start: one
nodes:
  - id: one
    action: one
edges:
  - from: one
    to: END
""",
        encoding="utf-8",
    )
    actions = WorkflowActionRegistry()
    actions.register("one", lambda params, state: {"ok": True})
    runtime = WorkflowRuntime(
        FileWorkflowRepository(tmp_path),
        actions=actions,
        allow_deterministic_fallback=True,
    )

    def _must_not_compile(_definition):
        raise AssertionError("offline regression mode must not compile LangGraph")

    monkeypatch.setattr(runtime, "_compile", _must_not_compile)
    result = await runtime.arun("offline", {})

    assert result.status == "COMPLETED"
    assert result.output["one"]["ok"] is True
    assert runtime._compiled == {}
