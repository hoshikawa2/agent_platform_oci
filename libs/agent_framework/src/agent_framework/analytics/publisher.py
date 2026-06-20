from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("agent_framework.analytics")


class AnalyticsPublisher(ABC):
    """Contrato único para eventos analíticos corporativos.

    A intenção é desacoplar o agente de OCI Streaming, GCP Pub/Sub, Kafka,
    BigQuery ou qualquer outro destino. Os agentes publicam eventos de negócio
    ou operação usando apenas este contrato.
    """

    @abstractmethod
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError


class NoopAnalyticsPublisher(AnalyticsPublisher):
    """Publisher seguro para ambientes locais/testes."""

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        logger.info("analytics.noop event_type=%s payload_keys=%s", event_type, sorted(payload.keys()))
