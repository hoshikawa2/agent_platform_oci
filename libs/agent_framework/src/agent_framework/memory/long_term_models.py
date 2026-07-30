from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass(slots=True)
class LongTermMemoryItem:
    memory_id: str
    tenant_id: str
    agent_id: str
    subject_key: str
    category: str
    key: str
    value: str
    confidence: float = 1.0
    source_session_id: str | None = None
    source_message_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
