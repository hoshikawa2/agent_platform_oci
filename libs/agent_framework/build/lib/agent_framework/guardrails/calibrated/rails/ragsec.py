"""RagsecRail — rail LLM de segurança de RAG (RAG Security).

Detecta tentativas de prompt injection ou instruções maliciosas inseridas
em documentos recuperados pelo sistema RAG antes de serem usados como
contexto pelo agente.

Usa o prompt de prompts/ragsec.py via GuardRailLLMClient.

Rail com LLM: invoca o modelo de guardrail para classificação binária
OK / RAGSEC. Implementa o Protocol ``Rail`` de contracts.py.

Contexto de migração:
    A lógica de RAGSEC existia inline em pipeline.py como bloco comentado.
    Este módulo é a implementação desacoplada para uso via Protocol Rail.
    O bloco em pipeline.py foi removido em Sprint 1 / AT-08.
"""
from __future__ import annotations

import json
import logging

from ..contracts import GuardRailContext, GuardRailLLMClient, RailDecision
from ..llm_adapter import AgentLLMClientAdapter

logger = logging.getLogger(__name__)

_FALLBACK_TEXT = (
    "Não encontrei informações suficientes para responder isso com segurança. "
    "Pode detalhar melhor sua solicitação?"
)


class RagsecRail:
    """Rail LLM de detecção de RAG Security (RAGSEC).

    Implementa o Protocol Rail. Usa ``GuardRailLLMClient.invoke("RAGSEC", ...)``
    para classificar se o conteúdo recuperado contém instruções maliciosas,
    tentativas de prompt injection ou jailbreak vindos de documentos externos.

    Em caso de falha de parse do JSON de retorno, assume ``allowed=True``
    (conservador — não bloqueia por falha técnica).
    """

    def __init__(self, llm_client: GuardRailLLMClient | None = None) -> None:
        """Inicializa o rail.

        Args:
            llm_client: instância que implementa o Protocol GuardRailLLMClient.
                Quando None, instancia AgentLLMClientAdapter com configurações
                padrão do ambiente.
        """
        self._client: GuardRailLLMClient = llm_client or AgentLLMClientAdapter()

    @property
    def code(self) -> str:
        return "RAGSEC"

    @property
    def fallback_text(self) -> str | None:
        from ..pipeline import _FALLBACK_BY_CODE
        return _FALLBACK_BY_CODE.get("RAGSEC")

    @property
    def regen_flag(self) -> str | None:
        from ..prompts.fallback import _REGEN_FLAG_BY_CODE
        return _REGEN_FLAG_BY_CODE.get("RAGSEC")

    @property
    def is_soft_alert(self) -> bool:
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia se o texto recuperado contém instrução maliciosa de RAG.

        Args:
            context: GuardRailContext com ``user_text`` contendo o conteúdo
                recuperado a auditar (trecho de documento RAG) e
                ``conversation_history`` opcional para contexto adicional.

        Returns:
            RailDecision com ``allowed=True`` quando OK (sem injection RAG)
            ou ``allowed=False, code="RAGSEC"`` quando detectada.
        """
        text = context.user_text
        input_vars = {
            "text": text,
            "context": context.agent_metadata or {},
        }

        try:
            raw = self._client.invoke(self.code, input_vars)
            result: dict = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            logger.error(
                "ragsec_rail.invoke_error session=%s exc=%r — assuming allowed",
                context.session_id,
                exc,
            )
            return RailDecision(
                allowed=True,
                code=self.code,
                reason="evaluation_error",
            )

        allowed = bool(result.get("allowed", True))
        reason = result.get("reason", "")

        if not allowed:
            logger.warning(
                "ragsec_rail.blocked session=%s reason=%r",
                context.session_id,
                reason,
            )
            return RailDecision(
                allowed=False,
                code=self.code,
                reason=reason,
                fallback_text=_FALLBACK_TEXT,
            )

        return RailDecision(
            allowed=True,
            code=self.code,
            reason=reason,
        )


__all__ = ["RagsecRail"]
