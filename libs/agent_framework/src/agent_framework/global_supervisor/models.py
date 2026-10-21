from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


RoutingMode = Literal["router", "supervisor", "hybrid"]


class BackendDefinition(BaseModel):
    """Contrato de um backend de agente registrado no Global Supervisor."""

    backend_id: str = Field(..., description="Identificador lógico. Ex.: contas, ofertas, suporte")
    name: str | None = None
    url: str = Field(..., description="Base URL do backend, sem barra final")
    description: str = ""
    domains: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    priority: int = 100
    enabled: bool = True
    protocol: Literal["native", "a2a"] = "native"
    a2a_version: Literal["1.0", "0.3"] = "1.0"
    a2a_agent_card_path: str = "/.well-known/agent-card.json"
    a2a_rpc_path: str = "/a2a"
    a2a_headers_env: dict[str, str] = Field(default_factory=dict)
    a2a_poll_interval_seconds: float = Field(default=0.5, gt=0)
    health_path: str = "/health"
    message_path: str = "/gateway/message"
    sse_message_path: str = "/gateway/message/sse"
    events_path_template: str = "/gateway/events/{session_id}"
    default_agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def base_url(self) -> str:
        return self.url.rstrip("/")


class BackendRegistryConfig(BaseModel):
    default_backend: str | None = None
    backends: list[BackendDefinition] = Field(default_factory=list)


class GlobalRouteRequest(BaseModel):
    channel: str = "web"
    payload: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str | None = None
    session_id: str | None = None
    current_backend: str | None = None
    force_backend: str | None = None
    mode: RoutingMode | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GlobalRouteDecision(BaseModel):
    backend_id: str
    confidence: float = 0.0
    reason: str = ""
    mode: RoutingMode = "hybrid"
    used_llm: bool = False
    keep_active_backend: bool = False
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BackendCallResult(BaseModel):
    backend_id: str
    backend_url: str
    status_code: int
    response: dict[str, Any]
    route_decision: GlobalRouteDecision
    elapsed_ms: int


@dataclass
class GlobalSessionState:
    session_id: str
    tenant_id: str = "default"
    active_backend: str | None = None
    active_domain: str | None = None
    turn_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
