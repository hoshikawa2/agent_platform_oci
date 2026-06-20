from __future__ import annotations

import logging
from typing import Any

from agent_framework.analytics import AnalyticsPublisher, build_analytics_event, create_analytics_publisher
from agent_framework.observability.noc_otel import emit_noc_event

logger = logging.getLogger("agent_framework.observability.observer")


def _normalize_ic_code(code: str) -> str:
    code = str(code).strip()
    return code if code.startswith(("IC.", "AGA.", "NOC.", "GRL.")) else f"IC.{code}"


def _normalize_noc_code(code: str) -> str:
    code = str(code).strip()
    return code if code.startswith("NOC.") else f"NOC.{code}"


def _normalize_grl_code(code: str) -> str:
    code = str(code).strip()
    return code if code.startswith("GRL.") else f"GRL.{code}"


def _apply_control_defaults(event_type: str, payload: dict[str, Any] | None, metadata: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    body = dict(payload or {})
    meta = dict(metadata or {})
    body.setdefault("tag", event_type)
    if event_type.startswith(("IC.", "AGA.")):
        meta.setdefault("ic", True)
    if event_type.startswith("NOC."):
        meta.setdefault("noc", True)
    if event_type.startswith("GRL."):
        meta.setdefault("grl", True)
    return body, meta


class AgentObserver:
    """Observer corporativo para eventos IC, NOC e GRL.

    Centraliza emissão de eventos estruturados. O agente chama observer.emit(...)
    e o observer decide como publicar em analytics, NOC/OTEL e EventBus interno.
    """

    def __init__(
        self,
        analytics: AnalyticsPublisher | None = None,
        *,
        event_bus: Any | None = None,
        emit_analytics: bool = True,
        emit_event_bus: bool = True,
    ):
        self.analytics = analytics or create_analytics_publisher()
        self.event_bus = event_bus
        self.emit_analytics = emit_analytics
        self.emit_event_bus = emit_event_bus

    async def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        metadata: dict[str, Any] | None = None,
        source: str = "agent_framework",
    ) -> dict[str, Any]:
        payload, metadata = _apply_control_defaults(event_type, payload, metadata)
        event = build_analytics_event(event_type, payload, source=source, metadata=metadata)

        is_noc = str(event_type).startswith("NOC.") or metadata.get("noc") is True
        if is_noc:
            emit_noc_event(event_type, event)

        if self.emit_analytics:
            await self.analytics.publish(event_type, event)

        if self.emit_event_bus and self.event_bus is not None:
            try:
                await self.event_bus.publish(event_type, event)
            except Exception:
                logger.exception("observer.event_bus_failed event_type=%s", event_type)

        return event

    async def emit_ic(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        meta = {**dict(metadata), "ic": True}
        return await self.emit(_normalize_ic_code(code), payload, metadata=meta)

    async def emit_noc(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        meta = {**dict(metadata), "noc": True}
        return await self.emit(_normalize_noc_code(code), payload, metadata=meta)

    async def emit_grl(self, code: str, payload: dict[str, Any] | None = None, **metadata: Any) -> dict[str, Any]:
        meta = {**dict(metadata), "grl": True}
        return await self.emit(_normalize_grl_code(code), payload, metadata=meta)
