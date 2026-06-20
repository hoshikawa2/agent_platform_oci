from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any

from agent_framework.analytics.publisher import AnalyticsPublisher

try:  # Avoid making analytics import fragile in old deployments.
    from agent_framework.observability.context import get_current_observation_id, get_observability_context
except Exception:  # pragma: no cover
    get_observability_context = None  # type: ignore
    get_current_observation_id = None  # type: ignore

logger = logging.getLogger("agent_framework.analytics.langfuse")


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _safe_metadata(value: Any) -> Any:
    """Remove/mascara segredos antes de enviar metadata para Langfuse."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lk = str(key).lower()
            if any(token in lk for token in ("password", "secret", "token", "api_key", "authorization")):
                out[key] = "***"
            else:
                out[key] = _safe_metadata(item)
        return out
    if isinstance(value, list):
        return [_safe_metadata(item) for item in value]
    return value


_LANGFUSE_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_INTERNAL_PREFIXES = ("IC.", "AGA.", "NOC.", "GRL.")
_TECHNICAL_PREFIXES = (
    "langgraph.",
    "mcp.",
    "guardrail.",
    "judge.",
    "workflow.",
    "rag.",
    "cache.",
    "checkpoint.",
)


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(*values: Any) -> str | None:
    for value in values:
        text = _clean_str(value)
        if text:
            return text
    return None


def _current_context() -> dict[str, Any]:
    if get_observability_context is None:
        return {}
    try:
        return get_observability_context().clean()
    except Exception:
        return {}


def _current_parent_observation_id() -> str | None:
    if get_current_observation_id is None:
        return None
    try:
        value = get_current_observation_id()
        return str(value) if value else None
    except Exception:
        return None


def _is_internal_name(name: Any) -> bool:
    text = _clean_str(name) or ""
    return text.startswith(_INTERNAL_PREFIXES)


def _is_technical_name(name: Any) -> bool:
    text = _clean_str(name) or ""
    return text.startswith(_TECHNICAL_PREFIXES)


def _is_control_or_technical(name: Any) -> bool:
    return _is_internal_name(name) or _is_technical_name(name)


def _extract_envelope_event_type(envelope: dict[str, Any]) -> str | None:
    return _first(
        envelope.get("eventType"),
        envelope.get("event_type"),
        envelope.get("name"),
        envelope.get("type"),
    )


def _is_wrapped_internal_event(event_type: str, envelope: dict[str, Any]) -> bool:
    """Detecta caso que gerava trace raiz errado.

    Exemplo observado no Langfuse:
      name=http.request.completed
      input={"eventType": "NOC.006", ...}
      output={"published": true}

    Isso não é o trace real da request; é apenas o publisher de analytics
    emitindo um envelope IC/NOC/GRL através de um evento técnico. Esse registro
    deve ser suprimido para não poluir a tela Tracing -> Traces.
    """
    envelope_event_type = _extract_envelope_event_type(envelope)
    return bool(
        envelope_event_type
        and _is_internal_name(envelope_event_type)
        and str(event_type) != envelope_event_type
        and str(event_type).startswith(("http.request.", "gateway.", "telemetry."))
    )


def _raw_correlation_id(metadata: dict[str, Any]) -> str | None:
    # IMPORTANT: prefer request/trace ids over transaction/session ids. Using
    # transaction/session as first choice created duplicate root traces for
    # IC/NOC/GRL events while the HTTP trace used request_id.
    value = (
        metadata.get("traceId")
        or metadata.get("trace_id")
        or metadata.get("requestId")
        or metadata.get("request_id")
        or metadata.get("transactionId")
        or metadata.get("transaction_id")
        or metadata.get("sessionId")
        or metadata.get("session_id")
    )
    return str(value) if value else None


def _langfuse_trace_id(value: Any) -> str | None:
    """Normaliza ids do framework/business para o formato aceito pelo Langfuse.

    Langfuse SDK v3 exige 32 caracteres hex minúsculos. UUIDs com hífens são
    compactados; ids de negócio/sessão viram hash md5 determinístico.
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


def _correlation_trace_id(metadata: dict[str, Any]) -> str | None:
    return _langfuse_trace_id(_raw_correlation_id(metadata))


def _with_trace_context(kwargs: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    raw_id = _raw_correlation_id(metadata)
    trace_id = _langfuse_trace_id(raw_id)
    parent_id = (
        metadata.get("parent_observation_id")
        or metadata.get("parent_span_id")
        or kwargs.get("parent_observation_id")
        or kwargs.get("parent_span_id")
        or _current_parent_observation_id()
    )
    if trace_id:
        trace_context = dict(kwargs.get("trace_context") or {})
        trace_context.setdefault("trace_id", trace_id)
        if parent_id:
            trace_context.setdefault("parent_span_id", str(parent_id))
        kwargs["trace_context"] = trace_context
        meta = kwargs.setdefault("metadata", {})
        if isinstance(meta, dict):
            meta.setdefault("framework_trace_id", raw_id)
            meta.setdefault("langfuse_trace_id", trace_id)
            if parent_id:
                meta.setdefault("parent_observation_id", str(parent_id))
    return kwargs


def _allow_standalone_internal_events() -> bool:
    # Default false: IC/NOC/GRL sem contexto de request não devem criar linhas
    # soltas na tela principal de Traces. Habilite só para debug isolado.
    return _truthy(os.getenv("LANGFUSE_ALLOW_STANDALONE_INTERNAL_EVENTS"), False)


class LangfuseAnalyticsPublisher(AnalyticsPublisher):
    """Publica eventos IC/NOC/GRL no Langfuse sem criar traces raiz duplicados.

    Regra principal:
      - 1 request/workflow = 1 trace raiz;
      - IC/NOC/GRL e eventos técnicos entram como observations/spans dentro do
        trace corrente;
      - envelopes internos embrulhados em eventos HTTP/gateway não criam trace
        próprio com output {"published": true}.
    """

    def __init__(self, settings: Any | None = None, langfuse: Any | None = None):
        self.settings = settings
        self.langfuse = langfuse
        self.enabled = True

        if self.langfuse is not None:
            return

        if settings is None:
            from agent_framework.config.settings import settings as default_settings
            settings = default_settings
            self.settings = settings

        public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", None) or os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", None) or os.getenv("LANGFUSE_SECRET_KEY")
        host = getattr(settings, "LANGFUSE_HOST", None) or os.getenv("LANGFUSE_HOST") or "https://cloud.langfuse.com"

        if not public_key or not secret_key:
            self.enabled = False
            logger.warning("LangfuseAnalyticsPublisher desabilitado: LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY ausentes")
            return

        try:
            from langfuse import Langfuse  # type: ignore
            self.langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
            logger.info("LangfuseAnalyticsPublisher habilitado host=%s", host)
        except Exception:
            self.enabled = False
            self.langfuse = None
            logger.exception("Falha ao inicializar LangfuseAnalyticsPublisher")

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.enabled or self.langfuse is None:
            return

        event_type = str(event_type)
        envelope = dict(payload or {})

        # Prevent the exact pollution seen in Langfuse: http.request.completed
        # traces whose input is a NOC/IC envelope and output is {published:true}.
        if _is_wrapped_internal_event(event_type, envelope):
            logger.debug(
                "langfuse.analytics.skip_wrapped_internal event_type=%s envelope_event_type=%s",
                event_type,
                _extract_envelope_event_type(envelope),
            )
            return

        body = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
        metadata = envelope.get("metadata") if isinstance(envelope.get("metadata"), dict) else {}
        ctx = _current_context()

        source = envelope.get("source") or "agent_framework"
        event_date = envelope.get("eventDate")
        envelope_event_type = _extract_envelope_event_type(envelope)
        effective_event_type = envelope_event_type if _is_internal_name(envelope_event_type) else event_type

        # Correlation priority: current ObservabilityContext > payload metadata >
        # transaction/session fallback. This keeps IC/NOC/GRL in the same HTTP trace.
        correlation_request_id = _first(
            ctx.get("request_id"),
            ctx.get("trace_id"),
            body.get("request_id"), metadata.get("request_id"),
            body.get("requestId"), metadata.get("requestId"),
            envelope.get("request_id"), envelope.get("requestId"),
        )
        correlation_trace_id = _first(
            ctx.get("trace_id"),
            ctx.get("request_id"),
            body.get("trace_id"), metadata.get("trace_id"),
            body.get("traceId"), metadata.get("traceId"),
            correlation_request_id,
        )
        correlation_session_id = _first(
            ctx.get("session_id"),
            body.get("session_id"), metadata.get("session_id"),
            body.get("sessionId"), metadata.get("sessionId"),
            body.get("transaction_id"), metadata.get("transaction_id"),
            body.get("transactionId"), metadata.get("transactionId"),
        )

        is_internal = _is_internal_name(effective_event_type)
        is_technical = _is_technical_name(effective_event_type)

        # IC/NOC/GRL without current/request correlation are usually emitted by
        # background/legacy publishers. Do not create standalone trace rows unless
        # explicitly requested for debugging.
        if (is_internal or is_technical) and not correlation_trace_id and not _allow_standalone_internal_events():
            logger.debug("langfuse.analytics.skip_unrelated_internal event_type=%s", effective_event_type)
            return

        langfuse_metadata = _safe_metadata({
            "eventType": effective_event_type,
            "original_event_type": event_type if event_type != effective_event_type else None,
            "source": source,
            "eventDate": event_date,
            "payload": body,
            "metadata": metadata,
            "ic": _is_ic(str(effective_event_type), metadata),
            "noc": _is_noc(str(effective_event_type), metadata),
            "grl": _is_grl(str(effective_event_type), metadata),
            "tag": body.get("tag") or metadata.get("tag") or effective_event_type,
            "request_id": correlation_request_id,
            "trace_id": correlation_trace_id,
            "transaction_id": body.get("transaction_id") or metadata.get("transaction_id") or body.get("transactionId") or metadata.get("transactionId"),
            "sessionId": correlation_session_id,
            "session_id": correlation_session_id,
            "messageId": body.get("messageId") or metadata.get("messageId") or body.get("message_id") or metadata.get("message_id") or ctx.get("message_id"),
            "agentId": body.get("agentId") or metadata.get("agentId") or body.get("agent_id") or metadata.get("agent_id") or ctx.get("agent_id"),
            "channelId": body.get("channelId") or metadata.get("channelId") or body.get("channel") or metadata.get("channel") or ctx.get("channel"),
            "workflow_id": body.get("workflow_id") or metadata.get("workflow_id") or ctx.get("workflow_id"),
            "tenant_id": body.get("tenant_id") or metadata.get("tenant_id") or ctx.get("tenant_id"),
            "parent_observation_id": body.get("parent_observation_id") or metadata.get("parent_observation_id") or _current_parent_observation_id(),
        })

        self._update_current_trace(langfuse_metadata)

        # Prefer current/correlated observation API. For internal/technical events,
        # do not fall back to standalone span/trace APIs if this fails.
        try:
            if hasattr(self.langfuse, "start_as_current_observation"):
                kwargs = _with_trace_context({
                    "name": str(effective_event_type),
                    "as_type": "span",
                    "input": envelope,
                    "metadata": langfuse_metadata,
                }, langfuse_metadata)
                try:
                    cm = self.langfuse.start_as_current_observation(**kwargs)
                except (TypeError, ValueError):
                    kwargs.pop("trace_context", None)
                    cm = self.langfuse.start_as_current_observation(**kwargs)
                with cm as observation:
                    _update_observation(observation, output={"published": True})
                return
        except Exception:
            logger.debug("Falha ao publicar Langfuse observation para %s", effective_event_type, exc_info=True)
            if is_internal or is_technical:
                return

        if is_internal or is_technical:
            return

        # Legacy fallbacks only for non-internal, high-level events.
        try:
            trace_id = _correlation_trace_id(langfuse_metadata)
            if trace_id and hasattr(self.langfuse, "trace"):
                trace = self.langfuse.trace(
                    id=str(trace_id),
                    name=str(langfuse_metadata.get("request_id") or langfuse_metadata.get("sessionId") or "agent_framework.request"),
                    session_id=langfuse_metadata.get("sessionId"),
                    user_id=langfuse_metadata.get("user_id") or langfuse_metadata.get("userId"),
                    metadata={k: v for k, v in langfuse_metadata.items() if v is not None},
                )
                if hasattr(trace, "span"):
                    span = trace.span(name=str(effective_event_type), input=envelope, metadata=langfuse_metadata)
                    if hasattr(span, "end"):
                        span.end(output={"published": True})
                    return
        except Exception:
            logger.debug("Falha ao publicar Langfuse span correlacionado para %s", effective_event_type, exc_info=True)

        try:
            if hasattr(self.langfuse, "span"):
                span = self.langfuse.span(name=str(effective_event_type), input=envelope, metadata=langfuse_metadata)
                if hasattr(span, "end"):
                    span.end(output={"published": True})
                return
        except Exception:
            logger.debug("Falha ao publicar Langfuse span legado para %s", effective_event_type, exc_info=True)

    def _update_current_trace(self, metadata: dict[str, Any]) -> None:
        try:
            kwargs: dict[str, Any] = {
                "metadata": {k: v for k, v in metadata.items() if v is not None},
                "tags": [tag for tag, enabled in (
                    ("ic", metadata.get("ic")),
                    ("noc", metadata.get("noc")),
                    ("grl", metadata.get("grl")),
                    (str(metadata.get("tag")), metadata.get("tag")),
                ) if enabled],
            }
            session_id = metadata.get("sessionId") or metadata.get("session_id")
            if session_id:
                kwargs["session_id"] = str(session_id)
            if hasattr(self.langfuse, "update_current_trace"):
                self.langfuse.update_current_trace(**kwargs)
        except Exception:
            logger.debug("Langfuse update_current_trace ignorado", exc_info=True)


def _update_observation(observation: Any, **kwargs: Any) -> None:
    if observation is None:
        return
    try:
        if hasattr(observation, "update"):
            observation.update(**{k: v for k, v in kwargs.items() if v is not None})
    except Exception:
        logger.debug("Langfuse observation update ignorado", exc_info=True)


def _is_noc(event_type: str, metadata: dict[str, Any]) -> bool:
    return event_type.startswith("NOC.") or _truthy(metadata.get("noc"))


def _is_grl(event_type: str, metadata: dict[str, Any]) -> bool:
    return event_type.startswith("GRL.") or _truthy(metadata.get("grl"))


def _is_ic(event_type: str, metadata: dict[str, Any]) -> bool:
    return event_type.startswith(("IC.", "AGA.")) or _truthy(metadata.get("ic"))
