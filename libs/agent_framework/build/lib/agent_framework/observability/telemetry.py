"""Observabilidade central do framework no padrão FIRST.

Recursos incluídos:
- ContextVar para correlation ids assíncronos;
- Langfuse com trace/span/event/generation e fallback por versão de SDK;
- OpenTelemetry opcional via OTLP;
- Event bus interno para plugar logs, SSE, OCI Streaming, Elastic, Phoenix etc.;
- spans de workflow, guardrail, judge, RAG, MCP, cache, checkpoint e LLM;
- token/cost metadata quando informado pelos providers.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .context import (
    context_metadata,
    get_current_observation_id,
    get_current_span_events,
    get_observability_context,
    record_current_span_event,
    reset_current_observation_id,
    reset_current_span_events,
    set_current_observation_id,
    set_current_span_events,
    set_observability_context,
)
from .event_bus import TelemetryEventBus
from .otel import OpenTelemetryProvider
from .code_mapper import create_observability_code_mapper

logger = logging.getLogger("agent_framework.telemetry")

_LANGFUSE_OBSERVATION_TYPES = {"span", "generation", "agent", "tool", "chain", "retriever", "embedding", "evaluator", "guardrail"}
_LANGFUSE_START_OBSERVATION_KWARGS = {
    "trace_context",
    "name",
    "as_type",
    "input",
    "output",
    "metadata",
    "version",
    "level",
    "status_message",
    "completion_start_time",
    "model",
    "model_parameters",
    "usage_details",
    "cost_details",
    "prompt",
    "end_on_exit",
}

def _langfuse_type(kind: str | None) -> str:
    # Langfuse SDKs do not accept arbitrary event types such as "event"; FIRST pattern
    # stores those as spans with rich metadata to avoid noisy warnings.
    if kind in _LANGFUSE_OBSERVATION_TYPES:
        return kind
    return "span"


_LANGFUSE_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_COMPACT_SUPPRESSED_SPAN_PREFIXES = (
    "llm.chat_completion",
    "workflow.agent.",
    "workflow.handoff",
    "workflow.input_guardrails",
    "workflow.judge",
    "workflow.output_guardrails",
    "workflow.output_supervisor",
    "workflow.persist",
    "workflow.routing_decision",
    "workflow.supervisor_review",
)
# Control events remain first-class observations even in compact mode. Compact
# mode suppresses low-level workflow noise, but IC/NOC payloads are operational
# evidence and must stay inspectable as child spans in Langfuse.
_COMPACT_VISIBLE_EVENT_PREFIXES = ("IC.", "AGA.", "NOC.")


def _raw_correlation_id(attrs: dict[str, Any] | None = None) -> str | None:
    """Return the framework correlation id before Langfuse normalization."""
    attrs = attrs or {}
    ctx = get_observability_context().clean()
    value = (
        attrs.get("trace_id")
        or ctx.get("trace_id")
        or attrs.get("request_id")
        or ctx.get("request_id")
        or attrs.get("transaction_id")
        or attrs.get("session_id")
        or ctx.get("session_id")
    )
    return str(value) if value else None


def _langfuse_trace_id(value: Any) -> str | None:
    """Convert any framework correlation id into a valid Langfuse trace id.

    Langfuse SDK v3 requires trace ids to be exactly 32 lowercase hexadecimal
    characters. Framework ids are often UUIDs with dashes or business/session ids
    such as ``man-bcbe3e05``. Passing those raw values makes the SDK raise
    ``ValueError: invalid literal for int() with base 16``.

    The mapping below is stable and deterministic:
    - a valid 32-char hex id is reused as-is;
    - a UUID with dashes is converted by removing dashes;
    - every other id is md5-hashed into 32 lowercase hex chars.
    """
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    compact = raw.replace("-", "")
    if _LANGFUSE_TRACE_ID_RE.match(compact):
        return compact
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _correlation_trace_id(attrs: dict[str, Any] | None = None) -> str | None:
    """Return a Langfuse-safe stable trace id for the current request."""
    return _langfuse_trace_id(_raw_correlation_id(attrs))


def _inject_langfuse_trace_context(kwargs: dict[str, Any], attrs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Best-effort trace/span correlation for Langfuse SDK v3.

    Langfuse needs two different ids to preserve a tree:
    - trace_id: stable root execution id;
    - parent_span_id: current parent observation/span id.

    Earlier fixes normalized trace_id but did not propagate parent_span_id,
    which grouped everything in one trace while flattening the tree.
    """
    attrs = attrs or kwargs.get("metadata") or {}
    ignore_current_parent = bool(attrs.get("_ignore_current_parent") or kwargs.get("_ignore_current_parent"))
    raw_id = _raw_correlation_id(attrs)
    trace_id = _langfuse_trace_id(raw_id)
    parent_id = (
        attrs.get("parent_observation_id")
        or attrs.get("parent_span_id")
        or kwargs.get("parent_observation_id")
        or kwargs.get("parent_span_id")
        or (None if ignore_current_parent else get_current_observation_id())
    )
    if trace_id:
        trace_context = dict(kwargs.get("trace_context") or {})
        trace_context.setdefault("trace_id", trace_id)
        if parent_id:
            trace_context.setdefault("parent_span_id", str(parent_id))
        kwargs["trace_context"] = trace_context
        metadata = kwargs.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("framework_trace_id", raw_id)
            metadata.setdefault("langfuse_trace_id", trace_id)
            if parent_id:
                metadata.setdefault("parent_observation_id", str(parent_id))
            metadata.pop("_ignore_current_parent", None)
    kwargs.pop("_ignore_current_parent", None)
    return kwargs


def _extract_observation_id(observation: Any) -> str | None:
    """Best-effort extraction of Langfuse observation/span id.

    Langfuse SDK versions expose the id with slightly different attribute names.
    Keeping this flexible avoids coupling the framework to one SDK build.
    """
    if observation is None:
        return None
    for attr in ("id", "observation_id", "span_id", "generation_id"):
        value = getattr(observation, attr, None)
        if value:
            return str(value)
    # Some wrappers keep raw data in dict-like fields.
    for attr in ("dict", "model_dump"):
        fn = getattr(observation, attr, None)
        if callable(fn):
            try:
                data = fn()
                if isinstance(data, dict):
                    for key in ("id", "observation_id", "span_id"):
                        if data.get(key):
                            return str(data[key])
            except Exception:
                pass
    return None


def _is_compact_visible_event(name: str) -> bool:
    return str(name or "").startswith(_COMPACT_VISIBLE_EVENT_PREFIXES)


class _SpanHandle:
    """Mutable handle yielded by Telemetry.span for setting final output."""

    def __init__(self, observation: Any | None = None) -> None:
        self.observation = observation
        self.output: Any = None
        self.has_output = False
        self.metadata: dict[str, Any] = {}

    def set_observation(self, observation: Any | None) -> None:
        self.observation = observation

    def set_output(self, output: Any) -> None:
        self.output = output
        self.has_output = True

    def set_metadata(self, **metadata: Any) -> None:
        self.metadata.update({k: v for k, v in metadata.items() if v is not None})

    def __getattr__(self, name: str) -> Any:
        if self.observation is None:
            raise AttributeError(name)
        return getattr(self.observation, name)


class _GenerationHandle:
    """Mutable handle yielded by Telemetry.generation_span."""

    def __init__(self, observation: Any | None = None) -> None:
        self.observation = observation
        self.output: Any = None
        self.has_output = False
        self.metadata: dict[str, Any] = {}
        self.usage: dict[str, Any] | None = None
        self.model_parameters: dict[str, Any] = {}

    def set_observation(self, observation: Any | None) -> None:
        self.observation = observation

    def set_output(self, output: Any) -> None:
        self.output = output
        self.has_output = True

    def set_usage(self, usage: dict[str, Any] | None) -> None:
        self.usage = dict(usage or {})

    def set_metadata(self, **metadata: Any) -> None:
        self.metadata.update({k: v for k, v in metadata.items() if v is not None})

    def set_model_parameters(self, **model_parameters: Any) -> None:
        self.model_parameters.update({k: v for k, v in model_parameters.items() if v is not None})

    def __getattr__(self, name: str) -> Any:
        if self.observation is None:
            raise AttributeError(name)
        return getattr(self.observation, name)


def _usage_details_from_usage(usage: dict[str, Any] | None) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None

    def int_value(*keys: str) -> int | None:
        for key in keys:
            value = usage.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    input_tokens = int_value("input", "input_tokens", "prompt_tokens")
    output_tokens = int_value("output", "output_tokens", "completion_tokens")
    total_tokens = int_value("total", "total_tokens")

    # Langfuse self-hosted versions may sum all custom usage keys into totalUsage.
    # Send split fields only when available; send total only when there is no split.
    details: dict[str, int] = {}
    if input_tokens is not None:
        details["input"] = input_tokens
    if output_tokens is not None:
        details["output"] = output_tokens
    if not details and total_tokens is not None:
        details["total"] = total_tokens
    return details or None


def _cost_details_from_usage(usage: dict[str, Any] | None) -> dict[str, float] | None:
    if not isinstance(usage, dict):
        return None
    details: dict[str, float] = {}
    if usage.get("cost_usd") is not None:
        try:
            details["total"] = float(usage["cost_usd"])
        except (TypeError, ValueError):
            pass
    if usage.get("cost_brl") is not None:
        try:
            details["total_brl"] = float(usage["cost_brl"])
        except (TypeError, ValueError):
            pass
    return details or None


def _clean_mapping(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    clean = {k: v for k, v in value.items() if v is not None}
    return clean or None


def _utc_iso_ms() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Telemetry:
    def __init__(self, settings):
        self.settings = settings
        self.code_mapper = create_observability_code_mapper(settings)
        self.langfuse = None
        # Langfuse SDK v4 exposes propagate_attributes as a module-level
        # context manager (from langfuse import propagate_attributes), not as
        # a Langfuse client method. Keep the callable on the Telemetry instance
        # so the framework can support v4 while preserving legacy fallbacks.
        self._langfuse_propagate_attributes = None
        self.enabled = bool(getattr(settings, "ENABLE_LANGFUSE", False))
        self.event_bus = TelemetryEventBus()
        self.otel = OpenTelemetryProvider(settings)
        if getattr(settings, "ENABLE_OCI_STREAMING", False):
            try:
                from .streaming_exporter import OCIStreamingTelemetryExporter
                self.event_bus.subscribe(OCIStreamingTelemetryExporter(settings))
                logger.info("OCI Streaming telemetry exporter habilitado")
            except Exception:
                logger.exception("Falha ao inicializar exporter OCI Streaming")

        if not self.enabled:
            logger.info("Langfuse desabilitado")
            return

        public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", None)
        secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", None)
        host = getattr(settings, "LANGFUSE_HOST", None)
        if not public_key or not secret_key:
            logger.warning("ENABLE_LANGFUSE=true, mas LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY não foram configuradas")
            self.enabled = False
            return
        try:
            from langfuse import Langfuse
            try:
                from langfuse import propagate_attributes as langfuse_propagate_attributes
            except ImportError:
                langfuse_propagate_attributes = None
            self.langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
            self._langfuse_propagate_attributes = langfuse_propagate_attributes
            logger.info("Langfuse habilitado host=%s", host)
        except Exception as exc:
            logger.exception("Falha ao inicializar Langfuse: %s", exc)
            self.enabled = False
            self.langfuse = None

    def is_enabled(self) -> bool:
        return bool(self.enabled and self.langfuse)

    def is_compact_mode(self) -> bool:
        mode = getattr(self.settings, "LANGFUSE_TRACE_MODE", "verbose") or "verbose"
        return str(mode).lower() == "compact"

    def _should_emit_langfuse_span(self, name: str) -> bool:
        if not self.is_compact_mode():
            return True
        return not str(name).startswith(_COMPACT_SUPPRESSED_SPAN_PREFIXES)

    def bind_context(self, **kwargs: Any):
        return set_observability_context(**kwargs)

    def context(self) -> dict[str, Any]:
        return get_observability_context().clean()

    @asynccontextmanager
    async def span(self, name: str, **attrs):
        """Cria span correlacionado em logs, Langfuse e OpenTelemetry."""
        start = time.time()
        attrs = context_metadata(attrs)
        name, attrs = self.code_mapper.normalize_name(name, attrs)
        attrs.setdefault("_span_name", name)
        is_root_span = bool(attrs.get("_root_span")) or name == "agent.gateway_message"
        if self.is_compact_mode() and is_root_span and not attrs.get("parent_observation_id"):
            attrs["_ignore_current_parent"] = True
        if not attrs.get("request_id"):
            attrs["request_id"] = str(uuid4())
        if not attrs.get("trace_id"):
            attrs["trace_id"] = str(attrs.get("request_id"))
        set_observability_context(request_id=attrs.get("request_id"), trace_id=attrs.get("trace_id"))
        observation_cm = None
        observation = None
        handle = _SpanHandle()
        observation_token = None
        propagation_cm = None
        legacy_io_update: dict[str, Any] | None = None
        ignore_current_parent = bool(attrs.get("_ignore_current_parent"))
        parent_observation_id = attrs.get("parent_observation_id")
        if not parent_observation_id and not ignore_current_parent:
            parent_observation_id = get_current_observation_id()
        if parent_observation_id:
            attrs.setdefault("parent_observation_id", str(parent_observation_id))
        logger.info("span.start %s %s", name, _safe(attrs))

        otel_cm = self.otel.span(name, attrs)
        otel_span = otel_cm.__enter__()
        emit_langfuse_span = self.is_enabled() and self._should_emit_langfuse_span(name)
        span_events: list[dict[str, Any]] | None = [] if emit_langfuse_span and self.is_compact_mode() else None
        span_events_token = set_current_span_events(span_events) if span_events is not None else None
        observation_metadata = {k: v for k, v in attrs.items() if k != "input" and not str(k).startswith("_")}
        if emit_langfuse_span:
            observation_cm = self._start_observation(
                name=name,
                as_type="span",
                input=attrs.get("input"),
                metadata=observation_metadata,
                _ignore_current_parent=attrs.get("_ignore_current_parent"),
            )
        try:
            if observation_cm is not None:
                observation = observation_cm.__enter__()
                handle.set_observation(observation)
                observation_id = _extract_observation_id(observation)
                if observation_id:
                    observation_token = set_current_observation_id(observation_id)
                    attrs.setdefault("observation_id", observation_id)
                if is_root_span:
                    self._update_trace_from_attrs(observation, attrs)
                    self._set_trace_io(observation, input=attrs.get("input"))
                    propagation_cm = self._start_trace_attribute_propagation(name, attrs)
                    if propagation_cm is not None:
                        propagation_cm.__enter__()
            # Publish span.started only after the Langfuse observation is current,
            # so secondary analytics/exporters can attach it as a child instead
            # of creating a sibling/root entry.
            await self.event_bus.publish(f"{name}.started", attrs, kind="span")
            yield handle
            duration_ms = int((time.time() - start) * 1000)
            status = {"status": "ok", "duration_ms": duration_ms}
            out = handle.output if handle.has_output else status
            metadata = {**observation_metadata, **status, **handle.metadata}
            if span_events is not None:
                metadata["aggregated_event_count"] = len(span_events)
                metadata["aggregated_events"] = span_events
            self._update_observation(observation, input=attrs.get("input"), output=out, metadata=metadata)
            if is_root_span:
                self._set_trace_io(observation, input=attrs.get("input"), output=out)
                legacy_io_update = {
                    "input": attrs.get("input"),
                    "output": out,
                    "metadata": metadata,
                }
            if otel_span is not None:
                otel_span.set_attribute("duration_ms", duration_ms)
            completed_payload = {**attrs, **status}
            if handle.has_output:
                completed_payload["output"] = out
            await self.event_bus.publish(f"{name}.completed", completed_payload, kind="span")
            logger.info("span.end %s duration_ms=%s", name, duration_ms)
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            out = {"status": "error", "error": str(exc), "duration_ms": duration_ms}
            metadata = {**observation_metadata, "duration_ms": duration_ms}
            if span_events is not None:
                metadata["aggregated_event_count"] = len(span_events)
                metadata["aggregated_events"] = span_events
            self._update_observation(observation, level="ERROR", status_message=str(exc), input=attrs.get("input"), output=out, metadata=metadata)
            if is_root_span:
                self._set_trace_io(observation, input=attrs.get("input"), output=out)
                legacy_io_update = {
                    "input": attrs.get("input"),
                    "output": out,
                    "metadata": metadata,
                    "level": "ERROR",
                    "status_message": str(exc),
                }
            if otel_span is not None:
                try:
                    otel_span.record_exception(exc)
                    otel_span.set_attribute("error", True)
                except Exception:
                    pass
            await self.event_bus.publish(f"{name}.failed", {**attrs, **out}, kind="span")
            logger.exception("span.error %s %s", name, exc)
            raise
        finally:
            if propagation_cm is not None:
                try: propagation_cm.__exit__(None, None, None)
                except Exception: logger.debug("Falha ao encerrar propagação Langfuse", exc_info=True)
            if observation_cm is not None:
                try: observation_cm.__exit__(None, None, None)
                except Exception: logger.exception("Falha ao finalizar span Langfuse %s", name)
            if legacy_io_update is not None:
                self._legacy_observation_update(
                    observation,
                    observation_type="span",
                    name=name,
                    **legacy_io_update,
                )
            if observation_token is not None:
                reset_current_observation_id(observation_token)
            if span_events_token is not None:
                reset_current_span_events(span_events_token)
            try: otel_cm.__exit__(None, None, None)
            except Exception: logger.debug("Falha ao fechar span OTEL", exc_info=True)

    async def event(self, name: str, payload: dict[str, Any] | None = None, *, kind: str = "event"):
        name, payload, mapping_metadata = self.code_mapper.normalize_payload(name, payload, None)
        if mapping_metadata:
            payload = {**payload, **mapping_metadata}
        payload = context_metadata(payload or {})
        logger.info("event %s %s", name, _safe(payload))
        await self.event_bus.publish(name, payload, kind=kind)
        if self.is_compact_mode():
            if get_current_span_events() is not None:
                record_current_span_event({
                    "name": name,
                    "kind": kind,
                    "payload": payload,
                })
            if not _is_compact_visible_event(name) or not self.is_enabled():
                return
            try:
                metadata = {**payload, "event_kind": kind}
                cm = self._start_observation(name=name, as_type="span", input=payload, metadata=metadata)
                if cm is not None:
                    with cm as obs:
                        self._update_observation(obs, input=payload, output={"status": "ok"}, metadata=metadata)
            except Exception:
                logger.exception("Falha ao enviar event compacto via observation")
            return
        if not self.is_enabled():
            return
        # IMPORTANT: do not call ``langfuse.event(...)`` directly here. In SDK
        # versions where there is no active parent observation, that API creates
        # a new trace row for every telemetry event. We create a correlated
        # observation instead, using request_id/trace_id as the stable trace id.
        try:
            metadata = {**payload, "event_kind": kind}
            if self.is_compact_mode():
                metadata["_ignore_current_parent"] = True
            cm = self._start_observation(name=name, as_type=_langfuse_type(kind), metadata=metadata)
            if cm is not None:
                with cm: pass
        except Exception:
            logger.exception("Falha ao enviar event via observation")

    @asynccontextmanager
    async def generation_span(
        self,
        name: str,
        model: str,
        input: list | dict | str,
        *,
        metadata: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        model_parameters: dict[str, Any] | None = None,
    ):
        metadata = context_metadata(metadata or {})
        name, metadata = self.code_mapper.normalize_name(name, metadata)
        # Keep the actual LLM model visible both in Langfuse's generation.model field
        # and in metadata for filtering/debugging across SDK versions.
        metadata.setdefault("model", model)
        metadata.setdefault("llm_model", model)
        metadata.setdefault("component", metadata.get("profile_name") or name)
        clean_model_parameters = _clean_mapping(model_parameters)
        if clean_model_parameters:
            metadata.setdefault("model_parameters", clean_model_parameters)
        handle = _GenerationHandle()
        observation_cm = None
        observation = None
        observation_token = None
        legacy_io_update: dict[str, Any] | None = None
        logger.info("generation.start %s model=%s component=%s profile=%s metadata=%s", name, model, metadata.get("component"), metadata.get("profile_name"), _safe(metadata))
        try:
            if self.is_enabled():
                try:
                    observation_cm = self._start_observation(
                        name=name,
                        as_type="generation",
                        input=input,
                        model=model,
                        model_parameters=clean_model_parameters,
                        usage_details=_usage_details_from_usage(usage),
                        cost_details=_cost_details_from_usage(usage),
                        metadata=metadata,
                    )
                    if observation_cm is not None:
                        observation = observation_cm.__enter__()
                        handle.set_observation(observation)
                        observation_id = _extract_observation_id(observation)
                        if observation_id:
                            observation_token = set_current_observation_id(observation_id)
                except Exception:
                    observation_cm = None
                    observation = None
                    logger.exception("Falha ao iniciar generation Langfuse %s", name)
            yield handle
            final_usage = handle.usage if handle.usage is not None else usage
            final_model_parameters = {
                **(clean_model_parameters or {}),
                **handle.model_parameters,
            } or None
            final_metadata = {**metadata, **handle.metadata}
            if final_usage:
                final_metadata["usage"] = final_usage
            output = handle.output if handle.has_output else None
            usage_details = _usage_details_from_usage(final_usage)
            cost_details = _cost_details_from_usage(final_usage)
            self._update_observation(
                observation,
                input=input,
                output=output,
                model=model,
                metadata=final_metadata,
                model_parameters=final_model_parameters,
                usage_details=usage_details,
                cost_details=cost_details,
            )
            legacy_io_update = {
                "input": input,
                "output": output,
                "model": model,
                "metadata": final_metadata,
                "model_parameters": final_model_parameters,
                "usage_details": usage_details,
                "cost_details": cost_details,
            }
            await self.event_bus.publish(
                name,
                {
                    "model": model,
                    "llm_model": model,
                    "output_chars": len(output or "") if isinstance(output, str) else 0,
                    **final_metadata,
                },
                kind="generation",
            )
            logger.info("generation.end %s model=%s", name, model)
        except Exception as exc:
            final_usage = handle.usage if handle.usage is not None else usage
            final_model_parameters = {
                **(clean_model_parameters or {}),
                **handle.model_parameters,
            } or None
            final_metadata = {**metadata, **handle.metadata}
            if final_usage:
                final_metadata["usage"] = final_usage
            usage_details = _usage_details_from_usage(final_usage)
            cost_details = _cost_details_from_usage(final_usage)
            output = handle.output if handle.has_output else None
            self._update_observation(
                observation,
                level="ERROR",
                status_message=str(exc),
                input=input,
                output=output,
                model=model,
                metadata=final_metadata,
                model_parameters=final_model_parameters,
                usage_details=usage_details,
                cost_details=cost_details,
            )
            legacy_io_update = {
                "input": input,
                "output": output,
                "model": model,
                "metadata": final_metadata,
                "model_parameters": final_model_parameters,
                "usage_details": usage_details,
                "cost_details": cost_details,
                "level": "ERROR",
                "status_message": str(exc),
            }
            await self.event_bus.publish(f"{name}.failed", {"model": model, "llm_model": model, "error": str(exc), **final_metadata}, kind="generation")
            logger.exception("generation.error %s model=%s exc=%s", name, model, exc)
            raise
        finally:
            if observation_cm is not None:
                try: observation_cm.__exit__(None, None, None)
                except Exception: logger.exception("Falha ao finalizar generation Langfuse %s", name)
            if legacy_io_update is not None:
                self._legacy_observation_update(
                    observation,
                    observation_type="generation",
                    name=name,
                    **legacy_io_update,
                )
            if observation_token is not None:
                reset_current_observation_id(observation_token)

    async def generation(
        self,
        name: str,
        model: str,
        input: list | dict | str,
        output: str,
        metadata: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        model_parameters: dict[str, Any] | None = None,
    ):
        async with self.generation_span(
            name=name,
            model=model,
            input=input,
            metadata=metadata,
            usage=usage,
            model_parameters=model_parameters,
        ) as generation:
            generation.set_output(output)
            if usage:
                generation.set_usage(usage)

    async def rag_event(self, name: str, query: str, results_count: int, metadata: dict[str, Any] | None = None):
        await self.event(f"rag.{name}", {"query": query, "results_count": results_count, **(metadata or {})}, kind="rag")

    async def cache_event(self, name: str, key: str, hit: bool | None = None, metadata: dict[str, Any] | None = None):
        await self.event(f"cache.{name}", {"key": key, "hit": hit, **(metadata or {})}, kind="cache")

    async def checkpoint_event(self, name: str, thread_id: str, metadata: dict[str, Any] | None = None):
        await self.event(f"checkpoint.{name}", {"thread_id": thread_id, **(metadata or {})}, kind="checkpoint")

    async def score(self, name: str, value: float, *, comment: str | None = None, metadata: dict[str, Any] | None = None):
        metadata = context_metadata(metadata or {})
        logger.info("score %s value=%s metadata=%s", name, value, _safe(metadata))
        await self.event_bus.publish(f"score.{name}", {"value": value, "comment": comment, **metadata}, kind="score")
        if not self.is_enabled():
            return
        try:
            if hasattr(self.langfuse, "score_current_trace"):
                self.langfuse.score_current_trace(name=name, value=value, comment=comment, metadata=metadata)
            elif hasattr(self.langfuse, "score"):
                self.langfuse.score(name=name, value=value, comment=comment, metadata=metadata)
        except Exception:
            logger.exception("Falha ao registrar score Langfuse")

    def flush(self):
        if not self.is_enabled(): return
        try:
            if hasattr(self.langfuse, "flush"):
                self.langfuse.flush(); logger.info("Langfuse flush executado")
        except Exception: logger.exception("Falha no Langfuse flush")

    def shutdown(self):
        if not self.is_enabled(): return
        try:
            if hasattr(self.langfuse, "shutdown"):
                self.langfuse.shutdown(); logger.info("Langfuse shutdown executado"); return
            self.flush()
        except Exception: logger.exception("Falha no Langfuse shutdown")

    def _start_observation(self, **kwargs):
        if not self.is_enabled(): return None

        # Final normalization boundary for every Langfuse observation created
        # through Telemetry.  Callers normally normalize in span()/generation_span(),
        # but keeping the contract here prevents future/direct internal call sites
        # from bypassing OBSERVABILITY_CODE_MAPPING.
        raw_name = kwargs.get("name")
        if raw_name is not None:
            mapped_name, mapped_metadata = self.code_mapper.normalize_name(
                str(raw_name),
                kwargs.get("metadata") if isinstance(kwargs.get("metadata"), dict) else {},
            )
            kwargs["name"] = mapped_name
            kwargs["metadata"] = mapped_metadata

        if hasattr(self.langfuse, "start_as_current_observation"):
            clean = {k: v for k, v in kwargs.items() if v is not None and k in _LANGFUSE_START_OBSERVATION_KWARGS}
            if "as_type" in clean:
                clean["as_type"] = _langfuse_type(clean.get("as_type"))
            if self.is_compact_mode():
                clean.pop("_ignore_current_parent", None)
            else:
                clean = _inject_langfuse_trace_context(clean, clean.get("metadata") or {})
            metadata = clean.get("metadata")
            if isinstance(metadata, dict):
                clean["metadata"] = {k: v for k, v in metadata.items() if not str(k).startswith("_")}
            try:
                return self.langfuse.start_as_current_observation(**clean)
            except (TypeError, ValueError):
                # SDK version mismatch or invalid external trace id. The trace id
                # is normalized above, but this guard keeps telemetry from
                # breaking business execution if Langfuse changes validation.
                clean.pop("trace_context", None)
                try:
                    return self.langfuse.start_as_current_observation(**clean)
                except TypeError:
                    return self.langfuse.start_as_current_observation(name=kwargs["name"], as_type=kwargs.get("as_type", "span"))
        if hasattr(self.langfuse, "trace") and hasattr(self.langfuse, "span"):
            # Legacy SDK fallback: create/reuse a deterministic trace and attach
            # the span to it when the SDK supports trace(...).span(...).
            legacy_metadata = dict(kwargs.get("metadata") or {})
            trace_id = _correlation_trace_id(legacy_metadata)
            try:
                if trace_id:
                    trace = self.langfuse.trace(
                        id=str(trace_id),
                        name=str(legacy_metadata.get("root_name") or legacy_metadata.get("workflow_id") or legacy_metadata.get("request_id") or "agent_framework.request"),
                        session_id=legacy_metadata.get("session_id"),
                        user_id=legacy_metadata.get("user_id"),
                        metadata={k: v for k, v in legacy_metadata.items() if v is not None},
                    )
                    span = trace.span(name=kwargs["name"], input=kwargs.get("input"), output=kwargs.get("output"), metadata=legacy_metadata)
                    return _LegacyObservationContext(span)
            except Exception:
                logger.debug("Falha ao criar span correlacionado via trace legado", exc_info=True)
        if hasattr(self.langfuse, "span"):
            legacy_metadata = dict(kwargs.get("metadata") or {})
            if kwargs.get("model") is not None:
                legacy_metadata.setdefault("model", kwargs.get("model"))
                legacy_metadata.setdefault("llm_model", kwargs.get("model"))
            span = self.langfuse.span(name=kwargs["name"], input=kwargs.get("input"), output=kwargs.get("output"), metadata=legacy_metadata)
            return _LegacyObservationContext(span)
        return None

    def _update_observation(self, observation, **kwargs):
        if observation is None: return
        clean = {k: v for k, v in kwargs.items() if v is not None}
        try:
            if hasattr(observation, "update"): observation.update(**clean)
        except Exception: logger.debug("Observation update não suportado", exc_info=True)

    def _legacy_observation_update(self, observation, *, observation_type: str, name: str, **kwargs):
        """Compatibility fallback for Langfuse servers that drop OTEL observation I/O."""
        if not self.is_enabled() or not bool(getattr(self.settings, "LANGFUSE_LEGACY_IO_FALLBACK", True)):
            return
        if observation is None:
            return
        obs_id = _extract_observation_id(observation)
        trace_id = getattr(observation, "trace_id", None)
        if not obs_id or not trace_id:
            return
        api = getattr(self.langfuse, "api", None)
        ingestion = getattr(api, "ingestion", None)
        if ingestion is None or not hasattr(ingestion, "batch"):
            return

        clean = {k: v for k, v in kwargs.items() if v is not None}
        if not any(k in clean for k in ("input", "output", "metadata")):
            return
        try:
            if hasattr(self.langfuse, "flush"):
                self.langfuse.flush()

            if observation_type == "generation":
                from langfuse.api.ingestion.types import (
                    IngestionEvent_GenerationUpdate,
                    UpdateGenerationBody,
                )

                body = UpdateGenerationBody(id=str(obs_id), trace_id=str(trace_id), name=name, **clean)
                event = IngestionEvent_GenerationUpdate(
                    id=str(uuid4()),
                    timestamp=_utc_iso_ms(),
                    body=body,
                    metadata={"source": "agent_framework", "fallback": "legacy_observation_io"},
                )
            else:
                from langfuse.api.ingestion.types import IngestionEvent_SpanUpdate, UpdateSpanBody

                body = UpdateSpanBody(id=str(obs_id), trace_id=str(trace_id), name=name, **clean)
                event = IngestionEvent_SpanUpdate(
                    id=str(uuid4()),
                    timestamp=_utc_iso_ms(),
                    body=body,
                    metadata={"source": "agent_framework", "fallback": "legacy_observation_io"},
                )

            response = ingestion.batch(
                batch=[event],
                metadata={"source": "agent_framework", "fallback": "legacy_observation_io"},
            )
            if getattr(response, "errors", None):
                logger.debug("Langfuse legacy I/O fallback retornou erros: %s", response.errors)
        except Exception:
            logger.debug("Falha no fallback legado de input/output Langfuse", exc_info=True)

    def _update_trace_from_attrs(self, observation, attrs: dict[str, Any]):
        if observation is None: return
        trace_attrs = {}
        if attrs.get("_span_name"):
            trace_attrs["name"] = attrs["_span_name"]
        for key in ("session_id", "user_id"):
            if attrs.get(key): trace_attrs[key] = attrs[key]
        if attrs.get("input"): trace_attrs["input"] = attrs["input"]
        if attrs.get("tags"): trace_attrs["tags"] = attrs["tags"]
        if attrs.get("request_id") or attrs.get("trace_id") or attrs.get("agent_id") or attrs.get("tenant_id"):
            trace_attrs["metadata"] = {k: attrs.get(k) for k in ("request_id", "trace_id", "agent_id", "tenant_id", "channel", "message_id", "ura_call_id", "workflow_id") if attrs.get(k)}
        if not trace_attrs: return
        try:
            if hasattr(observation, "update_trace"): observation.update_trace(**trace_attrs)
        except Exception: logger.debug("Trace update não suportado", exc_info=True)

    def _set_trace_io(self, observation, *, input: Any | None = None, output: Any | None = None):
        if observation is None: return
        try:
            if hasattr(observation, "set_trace_io"):
                observation.set_trace_io(input=input, output=output)
                return
            if hasattr(observation, "update_trace"):
                payload = {}
                if input is not None:
                    payload["input"] = input
                if output is not None:
                    payload["output"] = output
                if payload:
                    observation.update_trace(**payload)
        except Exception: logger.debug("Trace input/output update não suportado", exc_info=True)

    def _start_trace_attribute_propagation(self, name: str, attrs: dict[str, Any]):
        """Propagate native Langfuse trace attributes, including session_id.

        Langfuse Python SDK v4 moved ``propagate_attributes`` to a module-level
        context manager. Calling ``observation.update_trace(session_id=...)`` is
        not sufficient/recommended in v4 and, in practice, left ``sessionId``
        unset on traces even though the framework metadata contained
        ``session_id``.

        Prefer the v4 module-level callable imported during initialization. A
        client-method fallback is retained for older/custom SDK versions.
        """
        if not self.is_enabled():
            return None

        metadata = {
            k: attrs.get(k)
            for k in ("request_id", "trace_id", "agent_id", "tenant_id", "channel", "message_id", "ura_call_id", "workflow_id")
            if attrs.get(k)
        }
        tags = attrs.get("tags") if isinstance(attrs.get("tags"), list) else None
        kwargs = {
            "user_id": str(attrs["user_id"]) if attrs.get("user_id") is not None else None,
            "session_id": str(attrs["session_id"]) if attrs.get("session_id") is not None else None,
            "metadata": metadata or None,
            "tags": [str(tag) for tag in tags] if tags else None,
            "trace_name": name,
        }

        try:
            # Langfuse SDK v4: ``from langfuse import propagate_attributes``.
            if callable(self._langfuse_propagate_attributes):
                return self._langfuse_propagate_attributes(**kwargs)

            # Backward compatibility for SDK builds/wrappers that exposed the
            # propagation context manager on the client instance.
            legacy_propagate = getattr(self.langfuse, "propagate_attributes", None)
            if callable(legacy_propagate):
                return legacy_propagate(**kwargs)
        except Exception:
            logger.debug("Trace attribute propagation não suportada", exc_info=True)
        return None

class _LegacyObservationContext:
    def __init__(self, observation): self.observation = observation
    def __enter__(self): return self.observation
    def __exit__(self, exc_type, exc, tb):
        try:
            if hasattr(self.observation, "end"):
                if exc: self.observation.end(level="ERROR", status_message=str(exc))
                else: self.observation.end()
        except Exception: logger.debug("Falha ao encerrar observation legada", exc_info=True)
        return False

def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        masked = {}
        for k, v in value.items():
            lk = str(k).lower()
            if "key" in lk or "secret" in lk or "password" in lk or "token" in lk:
                masked[k] = "***"
            else: masked[k] = _safe(v)
        return masked
    if isinstance(value, list): return [_safe(v) for v in value]
    return value
