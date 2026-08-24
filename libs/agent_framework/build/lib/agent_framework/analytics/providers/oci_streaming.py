from __future__ import annotations

from typing import Any

from agent_framework.analytics.publisher import AnalyticsPublisher
from agent_framework.analytics.tim_sequence import ensure_sequence_envelope


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
        # Carimba o contador de sequence no envelope antes do publish, espelhando o
        # PubSubAnalyticsPublisher. Sem isto o path OCI Streaming sai sem sequence
        # (a geração estava amarrada apenas ao Pub/Sub na migração do framework).
        # ensure_sequence_envelope não quebra observabilidade: se faltar sessionId
        # ou o backend do contador falhar, o evento segue sem o campo.
        if isinstance(payload, dict):
            payload = await ensure_sequence_envelope(payload)
        await self.event_publisher.publish(event_type, payload)
