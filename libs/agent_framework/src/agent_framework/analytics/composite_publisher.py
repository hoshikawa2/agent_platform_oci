from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

from .publisher import AnalyticsPublisher

logger = logging.getLogger("agent_framework.analytics.composite")


class CompositeAnalyticsPublisher(AnalyticsPublisher):
    """Publica o mesmo evento em múltiplos destinos.

    Use para rodar OCI Streaming e Pub/Sub em paralelo durante transição,
    homologação ou estratégia multi-cloud.
    """

    def __init__(self, publishers: Iterable[AnalyticsPublisher], *, fail_silent: bool = True):
        self.publishers = list(publishers)
        self.fail_silent = fail_silent

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.publishers:
            return

        async def _safe_publish(publisher: AnalyticsPublisher) -> None:
            try:
                await publisher.publish(event_type, payload)
            except Exception:
                logger.exception("analytics.publisher_failed provider=%s event_type=%s", publisher.__class__.__name__, event_type)
                if not self.fail_silent:
                    raise

        await asyncio.gather(*[_safe_publish(p) for p in self.publishers])
