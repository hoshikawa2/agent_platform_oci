"""Event bus interno para telemetria e auditoria.

Permite plugar Langfuse, OpenTelemetry, OCI Streaming, logs, SSE e futuros sinks
sem acoplar guardrails/judges/workflows a um fornecedor específico.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .context import context_metadata

logger = logging.getLogger("agent_framework.observability.event_bus")

@dataclass(slots=True)
class TelemetryEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    kind: str = "event"
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def model_dump(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "ts": self.ts, "payload": self.payload}

EventHandler = Callable[[TelemetryEvent], Awaitable[None] | None]

class TelemetryEventBus:
    def __init__(self):
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def publish(self, name: str, payload: dict[str, Any] | None = None, *, kind: str = "event") -> TelemetryEvent:
        event = TelemetryEvent(name=name, payload=context_metadata(payload or {}), kind=kind)
        logger.info("telemetry.event %s", event.model_dump())
        for handler in list(self._handlers):
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Falha em handler de telemetria para %s", name)
        return event
