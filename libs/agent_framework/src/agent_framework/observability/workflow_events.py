from __future__ import annotations
from typing import Any

class WorkflowTelemetry:
    def __init__(self, telemetry): self.telemetry = telemetry
    async def started(self, workflow: str, state: dict[str, Any]):
        await self.telemetry.event("workflow.started", {"workflow": workflow, "state_keys": list(state.keys())}, kind="workflow")
    async def node_started(self, node: str, state: dict[str, Any]):
        await self.telemetry.event("workflow.node.started", {"node": node, "state_keys": list(state.keys())}, kind="workflow")
    async def node_completed(self, node: str, output: dict[str, Any] | None = None):
        await self.telemetry.event("workflow.node.completed", {"node": node, "output_keys": list((output or {}).keys())}, kind="workflow")
    async def edge_selected(self, source: str, target: str, reason: str | None = None):
        await self.telemetry.event("workflow.edge.selected", {"source": source, "target": target, "reason": reason}, kind="workflow")
    async def completed(self, workflow: str, result: dict[str, Any]):
        await self.telemetry.event("workflow.completed", {"workflow": workflow, "result_keys": list(result.keys())}, kind="workflow")
    async def failed(self, workflow: str, error: Exception):
        await self.telemetry.event("workflow.failed", {"workflow": workflow, "error": str(error)}, kind="workflow")
