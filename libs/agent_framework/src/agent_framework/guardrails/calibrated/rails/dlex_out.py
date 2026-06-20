"""DlexOutRail — stub de Data Leakage Output (coberto por OOS e sanitizador).

Este rail foi descartado porque o escopo de detecção de exfiltração de dados
no output é coberto pelo rail OOS (bloqueio semântico) e pelo sanitizador de
PII de output (mascarar_pii_output em output_sanitization.py).
Manter como stub garante retrocompatibilidade enquanto documenta a decisão.

Decisão de descarte documentada em guardrails-refactory-plan-v1.md (AT-08).
"""
from __future__ import annotations

import logging

from ..contracts import GuardRailContext, RailDecision

logger = logging.getLogger(__name__)


class DlexOutRail:
    """Stub para DLEX_OUT — sempre retorna allowed=True.

    O escopo de detecção de data leakage no output é coberto pelo rail OOS
    e pelo sanitizador mascarar_pii_output. Este stub existe para
    retrocompatibilidade e documentação.
    """

    _warned: bool = False

    def __init__(self) -> None:
        if not DlexOutRail._warned:
            logger.info(
                "DlexOutRail instanciado: rail DLEX_OUT está obsoleto — "
                "escopo coberto por OOS + sanitizador de PII (output_sanitization). "
                "Retorna always-allowed. Remover instância para eliminar este aviso."
            )
            DlexOutRail._warned = True

    @property
    def code(self) -> str:
        return "DLEX_OUT"

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
        """Retorna always-allowed. DLEX_OUT coberto por OOS + sanitizador."""
        logger.info(
            "dlex_out_rail.skipped session=%s — coberto por OOS + sanitizador",
            context.session_id,
        )
        return RailDecision(
            allowed=True,
            code=self.code,
            reason="coberto_por_oos_e_sanitizador",
        )


__all__ = ["DlexOutRail"]
