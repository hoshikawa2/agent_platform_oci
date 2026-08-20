from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class WorkflowExecutionPolicy(BaseModel):
    mode: Literal["direct_tool", "workflow", "agent"] = "direct_tool"
    workflow: str | None = None
    version: int | Literal["active"] = "active"


class ToolPreValidationPolicy(BaseModel):
    """Optional MCP business pre-validation executed before user confirmation."""

    enabled: bool = False
    tool: str | None = None
    fail_open: bool = False


class ToolPolicy(BaseModel):
    """Política de execução aplicada antes da chamada MCP ou workflow."""

    operation_type: Literal["read_only", "transactional", "conversational", "internal"] = "read_only"
    require_confirmation: bool = False
    requires: list[str] = Field(default_factory=list)
    execution: WorkflowExecutionPolicy = Field(default_factory=WorkflowExecutionPolicy)
    pre_validation: ToolPreValidationPolicy = Field(default_factory=ToolPreValidationPolicy)


class ToolPolicyRegistry:
    """Carrega políticas opcionais sem tornar o novo arquivo obrigatório."""

    def __init__(self, path: str | None = None):
        self.path = path
        self.defaults = ToolPolicy()
        self.policies: dict[str, ToolPolicy] = {}
        self.configured = False
        if path:
            self._load(path)

    def _load(self, path: str) -> None:
        config_path = Path(path)
        if not config_path.exists():
            return
        with config_path.open("r", encoding="utf-8") as stream:
            raw: dict[str, Any] = yaml.safe_load(stream) or {}
        defaults = raw.get("defaults") or {}
        self.defaults = self._parse(defaults, base=ToolPolicy())
        for name, value in (raw.get("tool_policies") or {}).items():
            self.policies[name] = self._parse(value or {}, base=self.defaults)
        self.configured = True

    @staticmethod
    def _parse(raw: dict[str, Any], *, base: ToolPolicy) -> ToolPolicy:
        operation_type = raw.get("operation_type", raw.get("type", base.operation_type))
        confirmation = raw.get(
            "require_confirmation",
            raw.get("requires_confirmation", raw.get("confirmation_required", base.require_confirmation)),
        )
        execution_raw = raw.get("execution") or {}
        base_execution = base.execution.model_dump()
        base_execution.update(execution_raw)
        pre_validation_raw = raw.get("pre_validation") or {}
        base_pre_validation = base.pre_validation.model_dump()
        if isinstance(pre_validation_raw, bool):
            base_pre_validation["enabled"] = pre_validation_raw
        elif isinstance(pre_validation_raw, dict):
            base_pre_validation.update(pre_validation_raw)
        return ToolPolicy(
            operation_type=operation_type,
            require_confirmation=bool(confirmation),
            requires=list(raw.get("requires", base.requires) or []),
            execution=WorkflowExecutionPolicy.model_validate(base_execution),
            pre_validation=ToolPreValidationPolicy.model_validate(base_pre_validation),
        )

    def get(self, tool_name: str) -> ToolPolicy | None:
        """Retorna somente política explícita; ausência preserva o legado."""
        return self.policies.get(tool_name)

