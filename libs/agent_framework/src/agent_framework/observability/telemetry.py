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
from typing import Any
from uuid import uuid4

from .context import (
    context_metadata,
    get_current_observation_id,
    get_observability_context,
    reset_current_observation_id,
    set_current_observation_id,
    set_observability_context,
)
from .event_bus import TelemetryEventBus
from .otel import OpenTelemetryProvider

logger = logging.getLogger("agent_framework.telemetry")

_LANGFUSE_OBSERVATION_TYPES = {"span", "generation", "agent", "tool", "chain", "retriever", "embedding", "evaluator", "guardrail"}

def _langfuse_type(kind: str | None) -> str:
    # Langfuse SDKs do not accept arbitrary event types such as "event"; FIRST pattern
    # stores those as spans with rich metadata to avoid noisy warnings.
    if kind in _LANGFUSE_OBSERVATION_TYPES:
        return kind
    return "span"


_LANGFUSE_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


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
    raw_id = _raw_correlation_id(attrs)
    trace_id = _langfuse_trace_id(raw_id)
    parent_id = (
        attrs.get("parent_observation_id")
        or attrs.get("parent_span_id")
        or kwargs.get("parent_observation_id")
        or kwargs.get("parent_span_id")
        or get_current_observation_id()
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

class Telemetry:
    def __init__(self, settings):
        self.settings = settings
        self.langfuse = None
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
            self.langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
            logger.info("Langfuse habilitado host=%s", host)
        except Exception as exc:
            logger.exception("Falha ao inicializar Langfuse: %s", exc)
            self.enabled = False
            self.langfuse = None

    def is_enabled(self) -> bool:
        return bool(self.enabled and self.langfuse)

    def bind_context(self, **kwargs: Any):
        return set_observability_context(**kwargs)

    def context(self) -> dict[str, Any]:
        return get_observability_context().clean()

    @asynccontextmanager
    async def span(self, name: str, **attrs):
        """Cria span correlacionado em logs, Langfuse e OpenTelemetry."""
        start = time.time()
        attrs = context_metadata(attrs)
        if not attrs.get("request_id"):
            attrs["request_id"] = str(uuid4())
        if not attrs.get("trace_id"):
            attrs["trace_id"] = str(attrs.get("request_id"))
        set_observability_context(request_id=attrs.get("request_id"), trace_id=attrs.get("trace_id"))
        observation_cm = None
        observation = None
        observation_token = None
        parent_observation_id = attrs.get("parent_observation_id") or get_current_observation_id()
        if parent_observation_id:
            attrs.setdefault("parent_observation_id", str(parent_observation_id))
        logger.info("span.start %s %s", name, _safe(attrs))

        otel_cm = self.otel.span(name, attrs)
        otel_span = otel_cm.__enter__()
        if self.is_enabled():
            observation_cm = self._start_observation(
                name=name,
                as_type="span",
                input=attrs.get("input"),
                metadata={k: v for k, v in attrs.items() if k != "input"},
            )
        try:
            if observation_cm is not None:
                observation = observation_cm.__enter__()
                observation_id = _extract_observation_id(observation)
                if observation_id:
                    observation_token = set_current_observation_id(observation_id)
                    attrs.setdefault("observation_id", observation_id)
                self._update_trace_from_attrs(observation, attrs)
            # Publish span.started only after the Langfuse observation is current,
            # so secondary analytics/exporters can attach it as a child instead
            # of creating a sibling/root entry.
            await self.event_bus.publish(f"{name}.started", attrs, kind="span")
            yield observation
            duration_ms = int((time.time() - start) * 1000)
            out = {"status": "ok", "duration_ms": duration_ms}
            self._update_observation(observation, output=out, metadata={"duration_ms": duration_ms})
            if otel_span is not None:
                otel_span.set_attribute("duration_ms", duration_ms)
            await self.event_bus.publish(f"{name}.completed", {**attrs, **out}, kind="span")
            logger.info("span.end %s duration_ms=%s", name, duration_ms)
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            out = {"status": "error", "error": str(exc), "duration_ms": duration_ms}
            self._update_observation(observation, level="ERROR", status_message=str(exc), output=out, metadata={"duration_ms": duration_ms})
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
            if observation_cm is not None:
                try: observation_cm.__exit__(None, None, None)
                except Exception: logger.exception("Falha ao finalizar span Langfuse %s", name)
            if observation_token is not None:
                reset_current_observation_id(observation_token)
            try: otel_cm.__exit__(None, None, None)
            except Exception: logger.debug("Falha ao fechar span OTEL", exc_info=True)

    async def event(self, name: str, payload: dict[str, Any] | None = None, *, kind: str = "event"):
        payload = context_metadata(payload or {})
        logger.info("event %s %s", name, _safe(payload))
        await self.event_bus.publish(name, payload, kind=kind)
        if not self.is_enabled():
            return
        # IMPORTANT: do not call ``langfuse.event(...)`` directly here. In SDK
        # versions where there is no active parent observation, that API creates
        # a new trace row for every telemetry event. We create a correlated
        # observation instead, using request_id/trace_id as the stable trace id.
        try:
            cm = self._start_observation(name=name, as_type=_langfuse_type(kind), metadata={**payload, "event_kind": kind})
            if cm is not None:
                with cm: pass
        except Exception:
            logger.exception("Falha ao enviar event via observation")

    async def generation(self, name: str, model: str, input: list | dict | str, output: str,
                         metadata: dict[str, Any] | None = None, usage: dict[str, Any] | None = None):
        metadata = context_metadata(metadata or {})
        # Keep the actual LLM model visible both in Langfuse's generation.model field
        # and in metadata for filtering/debugging across SDK versions.
        metadata.setdefault("model", model)
        metadata.setdefault("llm_model", model)
        metadata.setdefault("component", metadata.get("profile_name") or name)
        if usage:
            metadata["usage"] = usage
        logger.info("generation %s model=%s component=%s profile=%s metadata=%s", name, model, metadata.get("component"), metadata.get("profile_name"), _safe(metadata))
        await self.event_bus.publish(name, {"model": model, "llm_model": model, "output_chars": len(output or ""), **metadata}, kind="generation")
        if not self.is_enabled():
            return
        try:
            kwargs = dict(name=name, as_type="generation", input=input, output=output, model=model, metadata=metadata)
            if usage:
                kwargs["usage"] = usage
                kwargs["usage_details"] = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "reasoning_tokens") if k in usage}

            # Prefer current/correlated generation APIs. Avoid raw
            # ``langfuse.generation(...)`` first because it can create a separate
            # trace row per LLM call when no current observation exists.
            if hasattr(self.langfuse, "start_as_current_generation"):
                clean = {k: v for k, v in kwargs.items() if k != "as_type" and v is not None}
                clean = _inject_langfuse_trace_context(clean, metadata)
                try:
                    with self.langfuse.start_as_current_generation(**clean) as obs:
                        self._update_observation(obs, output=output, model=model, metadata=metadata)
                    return
                except TypeError:
                    clean.pop("trace_context", None)
                    with self.langfuse.start_as_current_generation(**clean) as obs:
                        self._update_observation(obs, output=output, model=model, metadata=metadata)
                    return

            cm = self._start_observation(**kwargs)
            if cm is not None:
                with cm as obs:
                    self._update_observation(obs, output=output, model=model, metadata=metadata)
        except Exception:
            logger.exception("Falha ao registrar generation no Langfuse")

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
        if hasattr(self.langfuse, "start_as_current_observation"):
            clean = {k: v for k, v in kwargs.items() if v is not None}
            if "as_type" in clean:
                clean["as_type"] = _langfuse_type(clean.get("as_type"))
            clean = _inject_langfuse_trace_context(clean, clean.get("metadata") or {})
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

    def _update_trace_from_attrs(self, observation, attrs: dict[str, Any]):
        if observation is None: return
        trace_attrs = {}
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
