from __future__ import annotations

# Compatibilidade local do template/backend.
# A implementação oficial agora fica no framework para evitar duplicação entre agentes.
from agent_framework.runtime import AgentRuntimeMixin, MessageBuilder, RuntimeContext

__all__ = ["AgentRuntimeMixin", "MessageBuilder", "RuntimeContext"]
