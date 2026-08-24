"""DlexInRail — stub de Data Leakage Input (coberto por PINJ).

Este rail foi descartado porque o escopo de detecção de exfiltração de dados
no input é integralmente coberto pelo rail PINJ expandido (Sprint 0 / AT-03).
Manter como stub garante retrocompatibilidade com código que possa referenciar
"DLEX_IN" sem gerar erro, enquanto registra um aviso explícito para revisão.

Decisão de descarte documentada em guardrails-refactory-plan-v1.md (AT-08).
"""
from __future__ import annotations

import logging

from ..contracts import GuardRailContext, RailDecision

logger = logging.getLogger(__name__)


class DlexInRail:
    """Stub para DLEX_IN — sempre retorna allowed=True.

    O escopo de detecção de data leakage no input é coberto pelo rail PINJ
    expandido. Este stub existe para retrocompatibilidade e documentação.
    Ao instanciar, loga um aviso único por processo.
    """

    _warned: bool = False

    def __init__(self) -> None:
        if not DlexInRail._warned:
            logger.info(
                "DlexInRail instanciado: rail DLEX_IN está obsoleto — "
                "escopo coberto por PINJ expandido (AT-03). "
                "Retorna always-allowed. Remover instância para eliminar este aviso."
            )
            DlexInRail._warned = True

    @property
    def code(self) -> str:
        return "DLEX_IN"

    @property
    def fallback_text(self) -> str | None:
        """Stub — always-allowed, não é hard-blocking."""
        return None

    @property
    def regen_flag(self) -> str | None:
        return None

    @property
    def is_soft_alert(self) -> bool:
        """Stub — always-allowed, tratado como soft-alert."""
        return True

    def evaluate(self, context: GuardRailContext) -> RailDecision:
        """Retorna always-allowed. DLEX_IN coberto por PINJ."""
        logger.info(
            "dlex_in_rail.skipped session=%s — coberto por PINJ",
            context.session_id,
        )
        return RailDecision(
            allowed=True,
            code=self.code,
            reason="coberto_por_pinj",
        )


__all__ = ["DlexInRail"]
