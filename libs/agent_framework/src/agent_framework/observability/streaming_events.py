from __future__ import annotations
from typing import Any

class StreamingTelemetry:
    def __init__(self, telemetry): self.telemetry = telemetry
    async def connected(self, session_id: str, last_event_id: int = 0):
        await self.telemetry.event("sse.connected", {"session_id": session_id, "last_event_id": last_event_id}, kind="sse")
    async def emitted(self, session_id: str, event: str, payload: dict[str, Any] | None = None):
        await self.telemetry.event("sse.event.emitted", {"session_id": session_id, "event": event, "payload": payload or {}}, kind="sse")
    async def keepalive(self, session_id: str):
        await self.telemetry.event("sse.keepalive", {"session_id": session_id}, kind="sse")
