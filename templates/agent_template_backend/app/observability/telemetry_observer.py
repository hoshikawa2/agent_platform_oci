from __future__ import annotations

"""Observer adapter that emits IC/NOC/GRL through framework Telemetry only.

This avoids a second Langfuse root trace created by AgentObserver ->
AnalyticsPublisher while preserving the events inside the active request span.
"""

from datetime import datetime, timezone
from typing import Any


def _normalize_ic_code(code: str) -> str:
    code = str(code or "UNKNOWN").strip()
    return code if code.startswith(("IC.", "AGA.", "NOC.", "GRL.")) else f"IC.{code}"


def _normalize_noc_code(code: str) -> str:
    code = str(code or "UNKNOWN").strip()
    return code if code.startswith("NOC.") else f"NOC.{code}"


def _normalize_grl_code(code: str) -> str:
    code = str(code or "UNKNOWN").strip()
    return code if code.startswith("GRL.") else f"GRL.{code}"


def _kind_for(event_type: str) -> str:
    if event_type.startswith(("IC.", "AGA.")):
        return "ic"
    if event_type.startswith("NOC."):
        return "noc"
    if event_type.startswith("GRL."):
        return "grl"
    return "event"


class TelemetryBackedAgentObserver:
    """Drop-in subset of AgentObserver backed by Telemetry.event.

    Do not publish through AnalyticsPublisher here. Analytics publishing may be
    configured with a Langfuse provider, and that path creates an extra root
    trace for business events such as IC.AGENT_COMPLETED/NOC.006. Telemetry.event
    uses the active span/trace context, so these events appear inside the single
    request trace.
    """

    def __init__(self, telemetry: Any, *, source: str = "agent_framework") -> None:
        self.telemetry = telemetry
        self.source = source

    async def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        body = dict(payload or {})
        meta = dict(metadata or {})
        body.setdefault("tag", event_type)
        event = {
            "eventType": event_type,
            "source": source or self.source,
            "eventDate": datetime.now(timezone.utc).isoformat(),
            "body": body,
            "metadata": meta,
        }
        try:
            await self.telemetry.event(event_type, event, kind=_kind_for(event_type))
        except TypeError:
            # Compatibility with older Telemetry.event signatures.
            await self.telemetry.event(event_type, event)
        return event

    async def emit_ic(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        return await self.emit(_normalize_ic_code(code), payload, metadata={**metadata, "ic": True})

    async def emit_noc(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        return await self.emit(_normalize_noc_code(code), payload, metadata={**metadata, "noc": True})

    async def emit_grl(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        return await self.emit(_normalize_grl_code(code), payload, metadata={**metadata, "grl": True})
