from __future__ import annotations
from agent_framework.observability.event_bus import TelemetryEvent

class OCIStreamingTelemetryExporter:
    """Exporta todos os TelemetryEvent para OCI Streaming."""
    def __init__(self, settings):
        from agent_framework.events.oci_streaming import create_event_publisher
        self.publisher=create_event_publisher(settings)
    async def __call__(self, event: TelemetryEvent):
        await self.publisher.publish(event.name, event.model_dump())
