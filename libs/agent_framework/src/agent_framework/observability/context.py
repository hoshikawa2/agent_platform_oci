"""Contexto de observabilidade assíncrono no padrão FIRST.

Centraliza correlation ids com ContextVar para manter request/session/user/agent
consistentes em FastAPI, LangGraph, guardrails, judges, RAG, MCP e providers LLM.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, asdict
from typing import Any
from uuid import uuid4

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_tenant_id: ContextVar[str | None] = ContextVar("tenant_id", default=None)
_agent_id: ContextVar[str | None] = ContextVar("agent_id", default=None)
_channel: ContextVar[str | None] = ContextVar("channel", default=None)
_ura_call_id: ContextVar[str | None] = ContextVar("ura_call_id", default=None)
_workflow_id: ContextVar[str | None] = ContextVar("workflow_id", default=None)
_message_id: ContextVar[str | None] = ContextVar("message_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_current_observation_id: ContextVar[str | None] = ContextVar("current_observation_id", default=None)

@dataclass(slots=True)
class ObservabilityContext:
    request_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
    agent_id: str | None = None
    channel: str | None = None
    ura_call_id: str | None = None
    workflow_id: str | None = None
    message_id: str | None = None
    trace_id: str | None = None

    def clean(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "")}


def get_observability_context() -> ObservabilityContext:
    return ObservabilityContext(
        request_id=_request_id.get(), session_id=_session_id.get(), user_id=_user_id.get(),
        tenant_id=_tenant_id.get(), agent_id=_agent_id.get(), channel=_channel.get(),
        ura_call_id=_ura_call_id.get(), workflow_id=_workflow_id.get(), message_id=_message_id.get(),
        trace_id=_trace_id.get(),
    )


def get_current_observation_id() -> str | None:
    """Return the current Langfuse observation/span id for parent-child linking."""
    return _current_observation_id.get()


def set_current_observation_id(observation_id: str | None):
    """Set current Langfuse observation/span id and return ContextVar token."""
    return _current_observation_id.set(str(observation_id) if observation_id else None)


def reset_current_observation_id(token) -> None:
    """Restore previous Langfuse observation/span id."""
    try:
        _current_observation_id.reset(token)
    except Exception:
        _current_observation_id.set(None)


def set_observability_context(**kwargs: Any) -> ObservabilityContext:
    if not kwargs.get("request_id") and not _request_id.get():
        kwargs["request_id"] = str(uuid4())
    mapping = {
        "request_id": _request_id, "session_id": _session_id, "user_id": _user_id,
        "tenant_id": _tenant_id, "agent_id": _agent_id, "channel": _channel,
        "ura_call_id": _ura_call_id, "workflow_id": _workflow_id, "message_id": _message_id,
        "trace_id": _trace_id,
    }
    for key, value in kwargs.items():
        if key in mapping and value is not None:
            mapping[key].set(str(value))
    return get_observability_context()


def clear_observability_context() -> None:
    for var in (_request_id, _session_id, _user_id, _tenant_id, _agent_id, _channel, _ura_call_id, _workflow_id, _message_id, _trace_id, _current_observation_id):
        var.set(None)


def context_metadata(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = get_observability_context().clean()
    if extra:
        metadata.update({k: v for k, v in extra.items() if v is not None})
    return metadata
