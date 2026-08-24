from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LLMResponse:
    """Canonical rich response returned by LLM providers.

    ``content`` preserves the legacy textual answer. ``reasoning_content`` is
    optional because not every model/provider/API exposes reasoning text.
    Consumers must never depend on it being present.
    """

    content: str
    reasoning_content: str | None = None
    provider: str | None = None
    model: str | None = None
    profile_name: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
