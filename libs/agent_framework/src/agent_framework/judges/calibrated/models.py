from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CalibratedJudgeResult:
    allowed: bool
    reason: str
    sanitized_text: str | None = None
    code: str | None = None
    mechanism: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
