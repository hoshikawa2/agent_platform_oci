from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rail_action import RailAction


@dataclass(slots=True)
class RailResult:
    code: str
    action: RailAction
    reason: str = ""
    guidance: str = ""
    sanitized_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
