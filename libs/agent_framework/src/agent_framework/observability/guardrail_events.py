from __future__ import annotations
from typing import Any

class GuardrailTelemetry:
    def __init__(self, telemetry): self.telemetry = telemetry
    async def evaluated(self, stage: str, decision: Any, latency_ms: int | None = None):
        payload = decision.model_dump() if hasattr(decision, "model_dump") else dict(decision or {})
        payload.update({"stage": stage, "latency_ms": latency_ms})
        await self.telemetry.event(f"guardrail.{payload.get('code', 'unknown')}.evaluated", payload, kind="guardrail")
    async def blocked(self, stage: str, decision: Any):
        payload = decision.model_dump() if hasattr(decision, "model_dump") else dict(decision or {})
        payload.update({"stage": stage})
        await self.telemetry.event(f"guardrail.{payload.get('code', 'unknown')}.blocked", payload, kind="guardrail")
