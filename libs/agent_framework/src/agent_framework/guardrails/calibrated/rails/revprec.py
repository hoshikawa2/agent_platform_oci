"""RevprecRail — rail LLM de verbalização prematura de ação operacional.

Detecta se o agente prometeu executar uma ação financeira futura sem
autorização do cliente (ex.: "Vou retirar o valor da sua fatura.").
Usa o prompt de prompts/revprec.py via GuardRailLLMClient.

Rail com LLM: invoca o modelo de guardrail para classificação binária
OK / PREMATURA. Implementa o Protocol ``Rail`` de contracts.py.

Contexto de migração:
    A lógica de verificação de REVPREC existia inline em pipeline.py como
    bloco comentado (``_verbalizacao_prematura``). Este módulo é a
    implementação desacoplada para uso via Protocol Rail.
    O bloco em pipeline.py foi removido em Sprint 1 / AT-08.
"""
from __future__ import annotations

import json
import logging

from ..contracts import GuardRailContext, GuardRailLLMClient, RailDecision
from ..llm_adapter import AgentLLMClientAdapter

logger = logging.getLogger(__name__)

_FALLBACK_TEXT = (
    "No momento não consigo confirmar essa ação dessa forma. "
    "Vou continuar verificando as informações disponíveis."
)


class RevprecRail:
    """Rail LLM de detecção de verbalização prematura (REVPREC).

    Implementa o Protocol Rail. Usa ``GuardRailLLMClient.invoke("REVPREC", ...)``
    para classificar se o agente verbalizou uma promessa operacional futura
    sem permissão/confirmação do cliente.

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
        return "REVPREC"

    @property
    def fallback_text(self) -> str | None:
        from ..pipeline import _FALLBACK_BY_CODE
        return _FALLBACK_BY_CODE.get("REVPREC")

    @property
    def regen_flag(self) -> str | None:
        from ..prompts.fallback import _REGEN_FLAG_BY_CODE
        return _REGEN_FLAG_BY_CODE.get("REVPREC")

    @property
    def is_soft_alert(self) -> bool:
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia se o texto do agente contém promessa operacional prematura.

        Args:
            context: GuardRailContext com ``user_text`` contendo a resposta
                do agente a auditar e ``conversation_history`` opcional para
                contexto adicional.

        Returns:
            RailDecision com ``allowed=True`` quando OK (sem promessa prematura)
            ou ``allowed=False, code="REVPREC"`` quando detectada.
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
                "revprec_rail.invoke_error session=%s exc=%r — assuming allowed",
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
                "revprec_rail.blocked session=%s reason=%r",
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


__all__ = ["RevprecRail"]
