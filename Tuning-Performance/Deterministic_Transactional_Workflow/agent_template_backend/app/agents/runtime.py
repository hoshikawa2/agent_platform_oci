from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agent_framework.runtime import (
    AgentRuntimeMixin as FrameworkAgentRuntimeMixin,
    MessageBuilder,
    RuntimeContext,
)
from agent_framework.workflows import FileWorkflowRepository, WorkflowRuntime, WorkflowToolExecutor

# Importa as actions do domínio para registrá-las no registry global do framework.
import app.workflow_actions  # noqa: F401

logger = logging.getLogger("app.agents.transactional_workflow_runtime")


class AgentRuntimeMixin(FrameworkAgentRuntimeMixin):
    """Runtime do template com execução determinística opt-in por tool policy.

    O fluxo conversacional, clarification e confirmação continuam no runtime
    oficial. Depois da confirmação, tools com ``execution.mode: workflow`` são
    desviadas para o WorkflowToolExecutor. Todas as demais seguem pelo MCP.
    """

    _workflow_tool_executor: WorkflowToolExecutor | None = None

    def _transactional_workflows_enabled(self) -> bool:
        return bool(getattr(getattr(self, "settings", None), "ENABLE_TRANSACTIONAL_WORKFLOWS", False))

    def _get_workflow_tool_executor(self) -> WorkflowToolExecutor:
        executor = getattr(self, "_workflow_tool_executor", None)
        if executor is not None:
            return executor

        settings = getattr(self, "settings", None)
        configured_path = getattr(settings, "WORKFLOWS_PATH", "./workflows") if settings else "./workflows"
        workflow_path = Path(configured_path)
        if not workflow_path.is_absolute():
            workflow_path = Path.cwd() / workflow_path

        runtime = WorkflowRuntime(FileWorkflowRepository(workflow_path))
        executor = WorkflowToolExecutor(runtime)
        self._workflow_tool_executor = executor
        logger.info("Transactional workflow runtime initialized path=%s", workflow_path)
        return executor

    async def _call_mcp_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        args = dict(arguments or {})
        policy = self._resolve_tool_execution_policy(tool_name, args)
        execution = dict(policy.get("execution") or {})

        if self._transactional_workflows_enabled() and execution.get("mode") == "workflow":
            executor = self._get_workflow_tool_executor()
            await self._emit_ic(
                "IC.TRANSACTIONAL_WORKFLOW_STARTED",
                state,
                {
                    "tool_name": tool_name,
                    "workflow_name": execution.get("workflow") or tool_name,
                    "workflow_version": execution.get("version", "active"),
                },
                component="agent_runtime.transactional_workflow",
            )
            result = await executor.execute_from_policy(
                tool_name=tool_name,
                arguments=args,
                policy=policy,
            )
            if result is None:
                return await super()._call_mcp_tool(tool_name, args, state)

            completed = result.get("status") == "COMPLETED"
            normalized = {
                "ok": completed,
                "tool_name": tool_name,
                "execution_mode": "workflow",
                "workflow_name": result.get("workflow_name"),
                "workflow_version": result.get("workflow_version"),
                "workflow_execution_id": result.get("execution_id"),
                "status": result.get("status"),
                "data": result.get("output") or {},
                "workflow_state": result.get("state") or {},
                "error": result.get("error"),
                "cached": False,
            }
            state["workflow_execution"] = {
                "execution_id": normalized["workflow_execution_id"],
                "workflow_name": normalized["workflow_name"],
                "workflow_version": normalized["workflow_version"],
                "status": normalized["status"],
            }
            await self._emit_ic(
                "IC.TRANSACTIONAL_WORKFLOW_COMPLETED" if completed else "IC.TRANSACTIONAL_WORKFLOW_FAILED",
                state,
                {
                    "tool_name": tool_name,
                    **state["workflow_execution"],
                    "error": normalized.get("error"),
                },
                component="agent_runtime.transactional_workflow",
            )
            return normalized

        return await super()._call_mcp_tool(tool_name, args, state)

    def build_direct_mcp_answer(
        self,
        state: dict[str, Any],
        tool_results: list[dict[str, Any]],
        *,
        agent_label: str,
    ) -> str | None:
        for result in tool_results or []:
            if result.get("execution_mode") != "workflow" or not result.get("ok"):
                continue
            nodes = result.get("data") or {}
            registration = nodes.get("registrar_devolucao") or {}
            protocol = registration.get("protocol")
            status = registration.get("status")
            if protocol:
                return (
                    f"[{agent_label}] Devolução registrada com sucesso. "
                    f"Protocolo {protocol}, status {status}. "
                    f"Execução do workflow: {result.get('workflow_execution_id')}."
                )
        return super().build_direct_mcp_answer(state, tool_results, agent_label=agent_label)


__all__ = ["AgentRuntimeMixin", "MessageBuilder", "RuntimeContext"]
