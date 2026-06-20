from __future__ import annotations

import logging
from typing import Any

from .composite_publisher import CompositeAnalyticsPublisher
from .publisher import AnalyticsPublisher, NoopAnalyticsPublisher

logger = logging.getLogger("agent_framework.analytics.factory")


def _split_csv(value: str | None) -> list[str]:
    return [item.strip().lower() for item in (value or "").split(",") if item.strip()]


def create_analytics_publisher(settings: Any | None = None) -> AnalyticsPublisher:
    """Cria publisher conforme env/config.

    Variáveis novas compatíveis:
    - ENABLE_ANALYTICS=true|false
    - ANALYTICS_PROVIDERS=oci_streaming,pubsub
    - GCP_PUBSUB_TOPIC_PATH=projects/.../topics/...
    - AGENT_PUBSUB_TOPIC=projects/.../topics/...   # compatibilidade FIRST/TIM
    - GCP_PROJECT_ID=... + GCP_PUBSUB_TOPIC=...
    """
    if settings is None:
        from agent_framework.config.settings import settings as default_settings
        settings = default_settings

    analytics_enabled = bool(getattr(settings, "ENABLE_ANALYTICS", False))
    langfuse_enabled = bool(getattr(settings, "ENABLE_LANGFUSE", False))

    # Historicamente o observer era usado para enviar IC/NOC/GRL ao Langfuse
    # mesmo quando o pipeline de analytics/streaming não estava habilitado.
    # Portanto, ENABLE_LANGFUSE=true também ativa o publisher Langfuse do observer.
    if not analytics_enabled and not langfuse_enabled:
        return NoopAnalyticsPublisher()

    providers = _split_csv(getattr(settings, "ANALYTICS_PROVIDERS", "")) or ["oci_streaming"]
    if langfuse_enabled and "langfuse" not in providers:
        providers.insert(0, "langfuse")

    # Se analytics geral estiver desligado, publica somente no Langfuse para
    # evitar inicializar OCI Streaming/PubSub por engano em ambientes locais.
    if not analytics_enabled:
        providers = [p for p in providers if p in {"langfuse", "noop", "none"}] or ["langfuse"]
    publishers: list[AnalyticsPublisher] = []

    for provider in providers:
        try:
            if provider == "langfuse":
                from .providers.langfuse import LangfuseAnalyticsPublisher
                publishers.append(LangfuseAnalyticsPublisher(settings=settings))
            elif provider == "oci_streaming":
                from .providers.oci_streaming import OCIStreamingAnalyticsPublisher
                publishers.append(OCIStreamingAnalyticsPublisher(settings=settings))
            elif provider in {"pubsub", "gcp_pubsub", "gcp"}:
                from .providers.pubsub import PubSubAnalyticsPublisher
                topic = (
                    getattr(settings, "GCP_PUBSUB_TOPIC_PATH", None)
                    or getattr(settings, "AGENT_PUBSUB_TOPIC", None)
                )
                publishers.append(PubSubAnalyticsPublisher(topic_path=topic))
            elif provider in {"noop", "none"}:
                publishers.append(NoopAnalyticsPublisher())
            else:
                logger.warning("analytics.provider_ignored provider=%s", provider)
        except Exception:
            logger.exception("analytics.provider_init_failed provider=%s", provider)

    if not publishers:
        return NoopAnalyticsPublisher()
    if len(publishers) == 1:
        return publishers[0]
    return CompositeAnalyticsPublisher(publishers)
