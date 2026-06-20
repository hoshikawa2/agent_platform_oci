from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from agent_framework.analytics.tim_payload_mapper import map_analytics_event_to_tim_flat_payload
from agent_framework.analytics.tim_sequence import ensure_sequence

from agent_framework.analytics.publisher import AnalyticsPublisher

logger = logging.getLogger("agent_framework.analytics.pubsub")


class PubSubAnalyticsPublisher(AnalyticsPublisher):
    """Publisher GCP Pub/Sub real, compatível com FIRST/TIM.

    Formas aceitas de configuração:

    1. GCP_PUBSUB_TOPIC_PATH=projects/<project-id>/topics/<topic-id>
    2. AGENT_PUBSUB_TOPIC=projects/<project-id>/topics/<topic-id>
    3. GCP_PROJECT_ID=<project-id> + GCP_PUBSUB_TOPIC=<topic-id>

    Credenciais seguem o padrão Google:
    GOOGLE_APPLICATION_CREDENTIALS=/secrets/service-account.json
    """

    def __init__(
        self,
        topic_path: str | None = None,
        *,
        project_id: str | None = None,
        topic_id: str | None = None,
        ordering_key: str | None = None,
        timeout_seconds: float | None = None,
    ):
        self.topic_path = self._resolve_topic_path(topic_path, project_id=project_id, topic_id=topic_id)
        self.ordering_key = ordering_key or os.getenv("GCP_PUBSUB_ORDERING_KEY") or ""
        self.timeout_seconds = float(timeout_seconds or os.getenv("GCP_PUBSUB_TIMEOUT_SECONDS") or 30)
        self.payload_mode = (os.getenv("PUBSUB_PAYLOAD_MODE") or os.getenv("ANALYTICS_PUBSUB_PAYLOAD_MODE") or "flat").strip().lower()
        self.exclude_noc = (os.getenv("PUBSUB_EXCLUDE_NOC") or "true").strip().lower() in {"1", "true", "yes", "y", "on"}

        from google.cloud import pubsub_v1  # type: ignore

        self.client = pubsub_v1.PublisherClient()

    @staticmethod
    def _resolve_topic_path(topic_path: str | None, *, project_id: str | None, topic_id: str | None) -> str:
        explicit = (
            topic_path
            or os.getenv("GCP_PUBSUB_TOPIC_PATH")
            or os.getenv("AGENT_PUBSUB_TOPIC")
            or os.getenv("PUBSUB_TOPIC_PATH")
        )
        if explicit:
            explicit = explicit.strip()
            if explicit.startswith("projects/"):
                return explicit
            # Permite passar só o nome do tópico quando project_id estiver disponível.
            project = project_id or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
            if project:
                return f"projects/{project}/topics/{explicit}"
            raise ValueError("topic_path deve estar no formato projects/<project-id>/topics/<topic-id> quando GCP_PROJECT_ID não está definido")

        project = project_id or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        topic = topic_id or os.getenv("GCP_PUBSUB_TOPIC") or os.getenv("PUBSUB_TOPIC")
        if project and topic:
            return f"projects/{project}/topics/{topic}"

        raise ValueError("Configure GCP_PUBSUB_TOPIC_PATH, AGENT_PUBSUB_TOPIC ou GCP_PROJECT_ID + GCP_PUBSUB_TOPIC")

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        is_noc = str(event_type).startswith("NOC.") or (isinstance(metadata, dict) and metadata.get("noc") is True)
        if is_noc and self.exclude_noc:
            logger.debug("analytics.pubsub.skipped_noc event_type=%s", event_type)
            return

        if self.payload_mode in {"legacy", "envelope", "wrapped"}:
            message = {"type": event_type, "payload": payload}
        else:
            message = map_analytics_event_to_tim_flat_payload(event_type, payload, keep_none=False)
            message = await ensure_sequence(message)

        data = json.dumps(message, default=str, ensure_ascii=False).encode("utf-8")
        attributes = {
            "event_type": str(event_type),
            "source": str(payload.get("source") or "agent_framework"),
        }
        if is_noc:
            attributes["noc"] = "true"

        kwargs: dict[str, Any] = dict(attributes)
        if self.ordering_key:
            kwargs["ordering_key"] = self.ordering_key

        future = self.client.publish(self.topic_path, data=data, **kwargs)
        await asyncio.to_thread(future.result, timeout=self.timeout_seconds)
        logger.debug("analytics.pubsub.published event_type=%s topic=%s", event_type, self.topic_path)
