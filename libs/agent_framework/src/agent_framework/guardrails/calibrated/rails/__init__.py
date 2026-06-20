"""Implementações de rails individuais do pipeline de guardrails TIM.

Cada módulo neste pacote implementa o Protocol `Rail` de contracts.py.
Rails determinísticos (sem LLM) ficam aqui junto dos rails LLM para
manter coesão de interface.

Módulos disponíveis:
    anatel      — AnatelRail: compliance de protocolo ANATEL (determinístico).
    confirmation — ConfirmationRail: classifica confirmação do cliente (LLM).
    alcada      — AlcadaRail: alçada de ajuste (determinístico).
    revprec     — RevprecRail: verbalização prematura de ação operacional (LLM).
    ragsec      — RagsecRail: segurança de RAG / context poisoning (LLM).
    dlex_in     — DlexInRail: stub DLEX_IN (coberto por PINJ, always-allowed).
    dlex_out    — DlexOutRail: stub DLEX_OUT (coberto por OOS+sanitizador, always-allowed).
    tox         — ToxRail: toxicidade no input (blocklist + LLM leve, AT-05).
    supervision — pacote de rails de supervisão executados em paralelo.
"""

from .anatel import AnatelRail
from .confirmation import ConfirmationRail
from .alcada import AlcadaRail
from .revprec import RevprecRail
from .ragsec import RagsecRail
from .dlex_in import DlexInRail
from .dlex_out import DlexOutRail
from .tox import ToxRail

__all__ = [
    "AnatelRail",
    "ConfirmationRail",
    "AlcadaRail",
    "RevprecRail",
    "RagsecRail",
    "DlexInRail",
    "DlexOutRail",
    "ToxRail",
]
