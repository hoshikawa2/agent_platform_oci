"""Adapter OpenTelemetry opcional."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("agent_framework.observability.otel")

class OpenTelemetryProvider:
    def __init__(self, settings):
        self.enabled = bool(getattr(settings, "ENABLE_OTEL", False))
        self.tracer = None
        if not self.enabled:
            return
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            service_name = getattr(settings, "OTEL_SERVICE_NAME", "ai-agent-framework")
            endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", None)
            provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
            exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            self.tracer = trace.get_tracer(service_name)
            logger.info("OpenTelemetry habilitado service=%s endpoint=%s", service_name, endpoint)
        except Exception:
            logger.exception("Falha ao inicializar OpenTelemetry; seguindo apenas com logs/Langfuse")
            self.enabled = False
            self.tracer = None

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None):
        if not self.enabled or self.tracer is None:
            yield None
            return
        with self.tracer.start_as_current_span(name) as span:
            for k, v in (attributes or {}).items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    span.set_attribute(k, "" if v is None else v)
                else:
                    span.set_attribute(k, str(v))
            yield span
