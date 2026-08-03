from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowNode(BaseModel):
    id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    retry: int = Field(default=0, ge=0, le=10)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source: str = Field(alias="from", min_length=1)
    target: str = Field(alias="to", min_length=1)
    when: dict[str, Any] | None = None
    priority: int = 100


class WorkflowDefinition(BaseModel):
    name: str = Field(min_length=1)
    version: int = Field(ge=1)
    start: str = Field(min_length=1)
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]

    @model_validator(mode="after")
    def validate_graph(self) -> "WorkflowDefinition":
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Workflow possui IDs de nós duplicados")
        known = set(ids)
        if self.start not in known:
            raise ValueError(f"Nó inicial inexistente: {self.start}")
        for edge in self.edges:
            if edge.source not in known:
                raise ValueError(f"Origem inexistente: {edge.source}")
            if edge.target not in known and edge.target not in {"END", "__end__"}:
                raise ValueError(f"Destino inexistente: {edge.target}")
        return self


class WorkflowRunResult(BaseModel):
    execution_id: str
    workflow_name: str
    workflow_version: int
    status: Literal["COMPLETED", "FAILED"]
    output: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
