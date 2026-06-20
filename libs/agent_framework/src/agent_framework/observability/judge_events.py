from __future__ import annotations
from typing import Any

class JudgeTelemetry:
    def __init__(self, telemetry): self.telemetry = telemetry
    async def evaluated(self, result: Any, latency_ms: int | None = None):
        payload = result.model_dump() if hasattr(result, "model_dump") else dict(result or {})
        payload.update({"latency_ms": latency_ms})
        await self.telemetry.event(f"judge.{payload.get('name', 'unknown')}.evaluated", payload, kind="judge")
