from pathlib import Path

import pytest

pytest.importorskip("langgraph")

from agent_framework.workflows import FileWorkflowRepository, WorkflowRuntime, WorkflowToolExecutor
import app.workflow_actions  # noqa: F401


@pytest.mark.asyncio
async def test_devolucao_workflow_executes_deterministically():
    root = Path(__file__).resolve().parents[1]
    runtime = WorkflowRuntime(FileWorkflowRepository(root / "workflows"))
    executor = WorkflowToolExecutor(runtime)
    policy = {
        "execution": {
            "mode": "workflow",
            "workflow": "devolucao_pedido",
            "version": "active",
        }
    }
    result = await executor.execute_from_policy(
        tool_name="solicitar_devolucao",
        arguments={"order_id": "123", "reason": "arrependimento", "confirmed": True},
        policy=policy,
    )
    assert result is not None
    assert result["status"] == "COMPLETED"
    assert result["output"]["registrar_devolucao"]["protocol"] == "DEV-123"


@pytest.mark.asyncio
async def test_non_workflow_policy_keeps_direct_tool_path():
    root = Path(__file__).resolve().parents[1]
    executor = WorkflowToolExecutor(WorkflowRuntime(FileWorkflowRepository(root / "workflows")))
    result = await executor.execute_from_policy(
        tool_name="consultar_pedido",
        arguments={"order_id": "123"},
        policy={"execution": {"mode": "direct_tool"}},
    )
    assert result is None
