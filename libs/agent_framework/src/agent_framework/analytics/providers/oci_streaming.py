from __future__ import annotations

from typing import Any

from agent_framework.analytics.publisher import AnalyticsPublisher


class OCIStreamingAnalyticsPublisher(AnalyticsPublisher):
    """Adapter para reutilizar o publisher OCI Streaming existente do framework."""

    def __init__(self, settings: Any | None = None, event_publisher: Any | None = None):
        if event_publisher is not None:
            self.event_publisher = event_publisher
        else:
            from agent_framework.config.settings import settings as default_settings
            from agent_framework.events.oci_streaming import create_event_publisher
            self.event_publisher = create_event_publisher(settings or default_settings)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        await self.event_publisher.publish(event_type, payload)
