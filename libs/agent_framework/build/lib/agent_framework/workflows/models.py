from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkflowMeaningfulInputAction(BaseModel):
    """Legacy action for coherent unmatched input (kept for compatibility)."""

    action: Literal["resume_as"] = "resume_as"
    value: Any


class WorkflowExpectedInputUnmatched(BaseModel):
    meaningful_input: WorkflowMeaningfulInputAction | None = None


class WorkflowSemanticOptionAction(BaseModel):
    """Optional generic action attached to one classified option.

    ``contextual_reentry`` releases the paused workflow and asks the normal
    router/runtime to reinterpret the current utterance together with the
    bounded conversational context that produced the pause.  It never confirms
    user-provided facts by itself.
    """

    action: Literal["contextual_reentry"]


class WorkflowSemanticClassifier(BaseModel):
    """Agent-defined semantic classifier constrained by ``allowed_values``.

    The framework provides only execution/validation.  The prompt defines the
    domain meaning of every allowed option and may reference the runtime
    placeholders ``{{ allowed_values }}``, ``{{ pending_prompt }}``,
    ``{{ relevant_conversation_context }}`` and ``{{ user_input }}``.
    Per-option actions are also agent configuration; the framework knows only
    their generic mechanics.
    """

    enabled: bool = True
    include_relevant_context: bool = False
    prompt: str = Field(min_length=1)
    option_actions: dict[str, WorkflowSemanticOptionAction] = Field(default_factory=dict)


class WorkflowExpectedInput(BaseModel):
    key: str = Field(min_length=1)
    allowed_values: list[Any] = Field(default_factory=list)
    normalize: Literal["none", "upper_strip", "lower_strip", "strip"] = "none"
    reprompt: str | None = None
    semantic_classifier: WorkflowSemanticClassifier | None = None
    unmatched: WorkflowExpectedInputUnmatched | None = None


class WorkflowPause(BaseModel):
    enabled: bool = True
    when: dict[str, Any] | None = None
    return_from: str = "$.output"
    expected_input: WorkflowExpectedInput | None = None
    resume_from: str | None = None


class WorkflowNode(BaseModel):
    id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    retry: int = Field(default=0, ge=0, le=10)
    pause: WorkflowPause | None = None


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
        for node in self.nodes:
            if node.pause and node.pause.resume_from and node.pause.resume_from not in known:
                raise ValueError(f"resume_from inexistente em {node.id}: {node.pause.resume_from}")
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
    status: Literal["COMPLETED", "PAUSED", "FAILED"]
    output: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    pause: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    error_details: dict[str, Any] = Field(default_factory=dict)
