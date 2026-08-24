from __future__ import annotations

import json
from typing import Any

from agent_framework.analytics.publisher import AnalyticsPublisher


class KafkaAnalyticsPublisher(AnalyticsPublisher):
    """Publisher Kafka opcional.

    Recebe um producer já criado para não acoplar o framework a uma lib específica
    (confluent-kafka, aiokafka, kafka-python etc.). O producer precisa expor send
    assíncrono ou síncrono.
    """

    def __init__(self, producer: Any, topic: str):
        self.producer = producer
        self.topic = topic

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        message = json.dumps({"type": event_type, "payload": payload}, default=str).encode("utf-8")
        result = self.producer.send(self.topic, key=event_type.encode("utf-8"), value=message)
        if hasattr(result, "__await__"):
            await result
