from __future__ import annotations

from typing import Any

from .runtime import WorkflowRuntime


class WorkflowToolExecutor:
    """Ponte entre `tool_policies.yaml` e o runtime determinístico."""

    def __init__(self, workflow_runtime: WorkflowRuntime):
        self.workflow_runtime = workflow_runtime

    async def execute_from_policy(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        policy: dict[str, Any],
    ) -> dict[str, Any] | None:
        execution = dict(policy.get("execution") or {})
        if execution.get("mode", "direct_tool") != "workflow":
            return None
        workflow_name = execution.get("workflow") or tool_name
        configured_version = execution.get("version", "active")
        version = None if configured_version == "active" else int(configured_version)
        result = await self.workflow_runtime.arun(
            workflow_name,
            arguments,
            version=version,
            execution_id=arguments.get("workflow_execution_id"),
        )
        return result.model_dump()
