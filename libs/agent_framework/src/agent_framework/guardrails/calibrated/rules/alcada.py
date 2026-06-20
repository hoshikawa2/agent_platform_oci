"""Regra determinística de alçada de ajuste.

Função pura: zero dependências externas. Verifica se o valor de ajuste
proposto pelo agente está dentro do limite configurado. Acima do limite,
o atendimento deve ser escalado para ATH (atendimento humano).
"""
from __future__ import annotations

from decimal import Decimal

from ..contracts import RailDecision


def checar_alcada(valor: Decimal, max_value: Decimal) -> RailDecision:
    """Verifica se ``valor`` está dentro da alçada permitida.

    Args:
        valor: valor do ajuste proposto pelo agente (positivo, em BRL).
        max_value: limite máximo configurado para esta alçada. Quando
            ``max_value == 0``, interpreta-se como "sem limite configurado"
            e a função retorna ``allowed=True`` sem verificação adicional.

    Returns:
        ``RailDecision(allowed=True)`` quando dentro do limite ou sem limite
        configurado.
        ``RailDecision(allowed=False, code="ALCADA")`` quando o valor excede
        o limite.
    """
    if max_value == Decimal("0"):
        return RailDecision(
            allowed=True,
            code="ALCADA",
            reason="Sem limite de alçada configurado — ajuste permitido.",
        )

    if valor <= max_value:
        return RailDecision(
            allowed=True,
            code="ALCADA",
            reason=f"Valor {valor} dentro da alçada máxima {max_value}.",
        )

    return RailDecision(
        allowed=False,
        code="ALCADA",
        reason=(
            f"Valor {valor} excede a alçada máxima configurada de {max_value}. "
            "Escalonamento para ATH necessário."
        ),
    )


__all__ = ["checar_alcada"]
