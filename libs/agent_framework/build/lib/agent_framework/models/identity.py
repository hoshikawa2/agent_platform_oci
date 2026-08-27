from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_TENANT_ID = "default"
DEFAULT_AGENT_ID = "default_agent"


def _clean(value: Any, default: str) -> str:
    text = str(value or default).strip()
    return text.replace("/", "_").replace(" ", "_") or default


@dataclass(frozen=True)
class AgentIdentity:
    """Identidade lógica usada para isolar agentes no mesmo backend.

    tenant_id separa clientes/ambientes. agent_id separa cada template/agente.
    session_id continua sendo a sessão do usuário, mas nunca deve ser usado sozinho
    para memória, checkpoint ou telemetria quando houver mais de um agente.
    """

    tenant_id: str = DEFAULT_TENANT_ID
    agent_id: str = DEFAULT_AGENT_ID
    session_id: str = ""

    @classmethod
    def from_context(cls, context: dict[str, Any] | None, session_id: str | None = None) -> "AgentIdentity":
        ctx = context or {}
        session = ctx.get("session") or {}
        return cls(
            tenant_id=_clean(ctx.get("tenant_id") or session.get("tenant_id"), DEFAULT_TENANT_ID),
            agent_id=_clean(ctx.get("agent_id") or session.get("agent_id"), DEFAULT_AGENT_ID),
            session_id=_clean(session_id or ctx.get("session_id") or session.get("session_id"), ""),
        )

    def scope_key(self) -> str:
        return f"{self.tenant_id}:{self.agent_id}"

    def conversation_key(self) -> str:
        if not self.session_id:
            return self.scope_key()
        return f"{self.tenant_id}:{self.agent_id}:{self.session_id}"


def build_conversation_key(session_id: str, agent_id: str | None = None, tenant_id: str | None = None) -> str:
    return AgentIdentity(
        tenant_id=_clean(tenant_id, DEFAULT_TENANT_ID),
        agent_id=_clean(agent_id, DEFAULT_AGENT_ID),
        session_id=_clean(session_id, ""),
    ).conversation_key()
