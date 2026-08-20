from __future__ import annotations

# Compatibilidade local do template/backend.
# A implementação oficial agora fica no framework para evitar duplicação entre agentes.
from agent_framework.runtime import AgentRuntimeMixin, MessageBuilder, RuntimeContext
from app.presentation import register_tool_renderers

register_tool_renderers()

__all__ = ["AgentRuntimeMixin", "MessageBuilder", "RuntimeContext"]
