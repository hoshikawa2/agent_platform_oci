from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

from agent_framework.analytics.tim_payload_mapper import map_analytics_event_to_tim_flat_payload

logger = logging.getLogger("agent_framework.observability.noc_otel")
_NOC_INTERNAL_FIELDS = {"description", "type", "step", "noc", "sequence"}


def _flatten_noc_payload(payload: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _NOC_INTERNAL_FIELDS:
            continue
        if value is None:
            flattened[key] = ""
        elif isinstance(value, (str, int, float, bool)):
            flattened[key] = value
        elif isinstance(value, (dict, list, tuple, set)):
            flattened[key] = json.dumps(value, default=str, ensure_ascii=False)
        else:
            flattened[key] = str(value)
    return flattened


class NocOpenTelemetryLogExporter:
    """Dedicated NOC exporter using OpenTelemetry Logs.

    This intentionally does not use the trace/span provider. It mirrors the old
    framework behavior: NOC events are mapped to the canonical flat schema,
    flattened to scalar OTel attributes, then emitted as LogRecord through OTLP.
    """

    def __init__(self, settings: Any | None = None):
        if settings is None:
            from agent_framework.config.settings import settings as default_settings
            settings = default_settings

        self.enabled = (os.getenv("ENABLE_NOC_OTEL_LOGS") or str(getattr(settings, "ENABLE_NOC_OTEL_LOGS", False))).lower() in {"1", "true", "yes", "y", "on"}
        self._logger: logging.Logger | None = None
        self._handler: logging.Handler | None = None
        if not self.enabled:
            return

        endpoint = (
            os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")
            or getattr(settings, "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", None)
        )
        if not endpoint:
            logger.warning("noc_otel.disabled_missing_endpoint")
            self.enabled = False
            return

        try:
            from opentelemetry import _logs
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.sdk.resources import Resource

            service_name = (
                os.getenv("OTEL_SERVICE_NAME")
                or os.getenv("AGENT_NAME")
                or getattr(settings, "OTEL_SERVICE_NAME", "ai-agent-framework")
            )
            headers: dict[str, str] = {}
            host_header = os.getenv("OTEL_EXPORTER_OTLP_HOST_HEADER") or getattr(settings, "OTEL_EXPORTER_OTLP_HOST_HEADER", None)
            if host_header:
                headers["Host"] = str(host_header)

            provider = LoggerProvider(resource=Resource.create({"service.name": service_name}))
            exporter = OTLPLogExporter(endpoint=endpoint, headers=headers or None)
            provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
            _logs.set_logger_provider(provider)

            self._handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
            self._logger = logging.getLogger("agent_framework.noc")
            self._logger.setLevel(logging.INFO)
            self._logger.propagate = False
            self._logger.addHandler(self._handler)
            logger.info("noc_otel.enabled service=%s endpoint=%s", service_name, endpoint)
        except Exception:
            logger.exception("noc_otel.init_failed")
            self.enabled = False
            self._logger = None

    def emit(self, event_type: str, event: dict[str, Any]) -> None:
        if not self.enabled or self._logger is None:
            return
        try:
            payload = map_analytics_event_to_tim_flat_payload(event_type, event, keep_none=True)
            tag = str(payload.get("tag") or event_type or "NOC.EVENT")
            self._logger.info(tag, extra=_flatten_noc_payload(payload))
        except Exception:
            logger.exception("noc_otel.emit_failed event_type=%s", event_type)


@lru_cache(maxsize=1)
def get_noc_otel_exporter() -> NocOpenTelemetryLogExporter:
    return NocOpenTelemetryLogExporter()


def emit_noc_event(event_type: str, event: dict[str, Any]) -> None:
    get_noc_otel_exporter().emit(event_type, event)
