"""AlcadaRail — rail determinístico de alçada de ajuste.

Verifica se o valor de ajuste proposto pelo agente está dentro do limite
configurado via metadados do agente. Acima do limite, bloqueia e orienta
escalonamento para ATH (atendimento humano).

Rail determinístico (sem LLM): zero chamadas externas, latência desprezível.
Implementa o Protocol ``Rail`` de contracts.py.

Exemplo de uso:
    from agente_contas_tim.guardrails.rails.alcada import AlcadaRail
    from ..contracts import GuardRailContext

    rail = AlcadaRail()
    ctx = GuardRailContext(
        session_id="abc",
        user_text="Vou aplicar o ajuste de R$ 150,00 na sua fatura.",
        agent_metadata={
            "valor_ajuste": Decimal("150.00"),
            "alcada_max_value": Decimal("100.00"),
        },
    )
    decision = rail.evaluate(ctx)
    # decision.allowed == False
    # decision.fallback_text contém orientação para ATH
"""
from __future__ import annotations

import logging
from decimal import Decimal

from ..contracts import GuardRailContext, RailDecision
from ..rules.alcada import checar_alcada

logger = logging.getLogger(__name__)


class AlcadaRail:
    """Rail determinístico de alçada de ajuste.

    Obtém ``valor_ajuste`` e ``alcada_max_value`` de
    ``context.agent_metadata``. Delega a lógica de verificação para
    ``checar_alcada`` (função pura em rules/alcada.py).

    Quando ``valor_ajuste`` não está nos metadados, retorna ``allowed=True``
    (comportamento conservador — sem valor não há o que verificar).
    """

    @property
    def code(self) -> str:
        return "ALCADA"

    @property
    def fallback_text(self) -> str | None:
        from ..pipeline import _FALLBACK_BY_CODE
        return _FALLBACK_BY_CODE.get("ALCADA")

    @property
    def regen_flag(self) -> str | None:
        from ..prompts.fallback import _REGEN_FLAG_BY_CODE
        return _REGEN_FLAG_BY_CODE.get("ALCADA")

    @property
    def is_soft_alert(self) -> bool:
        return False

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Avalia se o valor de ajuste está dentro da alçada configurada.

        Args:
            context: GuardRailContext com ``agent_metadata`` contendo
                opcionalmente:
                - ``valor_ajuste`` (Decimal | float | str): valor do ajuste.
                - ``alcada_max_value`` (Decimal | float | str): limite máximo.

        Returns:
            RailDecision com ``allowed=True`` quando dentro da alçada,
            ``allowed=False`` com ``fallback_text`` quando excede.
        """
        meta = context.agent_metadata or {}

        raw_valor = meta.get("valor_ajuste", Decimal("0"))
        raw_max = meta.get("alcada_max_value", Decimal("0"))

        try:
            valor = Decimal(str(raw_valor))
        except Exception:
            logger.warning(
                "alcada_rail.invalid_valor_ajuste raw=%r — assuming 0",
                raw_valor,
            )
            valor = Decimal("0")

        try:
            max_value = Decimal(str(raw_max))
        except Exception:
            logger.warning(
                "alcada_rail.invalid_alcada_max_value raw=%r — assuming 0 (sem limite)",
                raw_max,
            )
            max_value = Decimal("0")

        decision = checar_alcada(valor, max_value)

        if not decision.allowed:
            logger.warning(
                "alcada_rail.blocked valor=%s max_value=%s session=%s",
                valor,
                max_value,
                context.session_id,
            )
            return RailDecision(
                allowed=False,
                code=self.code,
                reason=decision.reason,
                is_soft_alert=False,
            )

        return decision


__all__ = ["AlcadaRail"]
