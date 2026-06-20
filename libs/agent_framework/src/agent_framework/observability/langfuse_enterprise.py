from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agent_framework.langfuse_enterprise")

class LangfuseEnterpriseAdapter:
    """Camada de compatibilidade Langfuse v2/v3 no padrão FIRST.

    Centraliza trace update, score e prompt registry sem espalhar detalhes do SDK
    pelo framework. A fachada principal continua sendo Telemetry.
    """
    def __init__(self, langfuse):
        self.langfuse = langfuse

    def trace_update(self, *, name: str | None = None, session_id: str | None = None, user_id: str | None = None,
                     input: Any = None, output: Any = None, metadata: dict[str, Any] | None = None,
                     tags: list[str] | None = None):
        if not self.langfuse: return
        try:
            if hasattr(self.langfuse, "update_current_trace"):
                self.langfuse.update_current_trace(name=name, session_id=session_id, user_id=user_id, input=input, output=output, metadata=metadata, tags=tags)
            elif hasattr(self.langfuse, "trace"):
                self.langfuse.trace(name=name, session_id=session_id, user_id=user_id, input=input, output=output, metadata=metadata, tags=tags)
        except Exception:
            logger.debug("Langfuse trace_update ignorado por incompatibilidade do SDK", exc_info=True)

    def score(self, *, name: str, value: float, comment: str | None = None, metadata: dict[str, Any] | None = None):
        if not self.langfuse: return
        try:
            if hasattr(self.langfuse, "score_current_trace"):
                self.langfuse.score_current_trace(name=name, value=value, comment=comment, metadata=metadata)
            elif hasattr(self.langfuse, "score"):
                self.langfuse.score(name=name, value=value, comment=comment, metadata=metadata)
        except Exception:
            logger.debug("Langfuse score ignorado por incompatibilidade do SDK", exc_info=True)

    def prompt(self, *, name: str, prompt: str, labels: list[str] | None = None, config: dict[str, Any] | None = None):
        if not self.langfuse: return None
        try:
            if hasattr(self.langfuse, "create_prompt"):
                return self.langfuse.create_prompt(name=name, prompt=prompt, labels=labels, config=config)
        except Exception:
            logger.debug("Langfuse prompt registry não disponível", exc_info=True)
        return None
