from __future__ import annotations
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Any

class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"

class ItemStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

class ConversationMessage(BaseModel):
    role: str
    content: str
    created_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class ConversationRecord(BaseModel):
    trace_id: str | None = None
    session_id: str
    message_id: str | None = None
    agent_id: str | None = None
    channel: str | None = None
    input_text: str = ""
    output_text: str = ""
    messages: list[ConversationMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)

class TraceJudgeResult(BaseModel):
    judgeScore: float
    accuracyScore: float
    alucinationScore: float
    rationale: str = ""
    judge_name: str = "trace_metrics"
    judge_type: str = "trace"

class SessionJudgeResult(BaseModel):
    inferredCsiScore: float
    resolution: int
    conversationPrecision: int
    rationale: str = ""
    judge_name: str = "session_metrics"
    judge_type: str = "session"

class CombinedJudgeResult(BaseModel):
    trace: TraceJudgeResult
    session: SessionJudgeResult | None = None
