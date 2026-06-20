"""Rail INPUT_SIZE: bloqueia inputs que excedem limite de tokens.

Defesa deterministica contra ataques de amplificacao que enviam payloads
grandes para estressar o modelo (CIS.16.063 - Negacao de Servico ao
Modelo). Executado antes de qualquer outro rail no pipeline de input
para curto-circuitar consumo de recursos.

Contagem de tokens via aproximacao chars/4 (conservadora, sem dependencia
externa). A precisao exata nao e necessaria: o objetivo e barrar payloads
ordens de grandeza maiores que o esperado, nao distinguir 4000 de 4100
tokens.

Configuracao via TIM_GUARDRAIL_INPUT_MAX_TOKENS (default 4096).
"""
from __future__ import annotations

import logging
import os

from ._compat import RailResult, span


logger = logging.getLogger(__name__)


_DEFAULT_MAX_TOKENS = 4096
_CHARS_PER_TOKEN = 4


def _max_tokens() -> int:
    """Le o cap do env. Default 4096 quando ausente/invalido."""
    raw = os.getenv("TIM_GUARDRAIL_INPUT_MAX_TOKENS", "")
    try:
        val = int(raw)
        return val if val > 0 else _DEFAULT_MAX_TOKENS
    except (ValueError, TypeError):
        return _DEFAULT_MAX_TOKENS


def _count_tokens(text: str) -> int:
    """Estima tokens via aproximacao chars/4.

    A precisao exata nao importa para um cap defensivo. Subestima tokens
    em CJK e codigo (raros no canal de fatura TIM), o que faz o cap
    proteger mais agressivamente nesses casos - comportamento aceitavel.
    """
    return max(1, len(text or "") // _CHARS_PER_TOKEN)


def verificar_tamanho_input(text: str, context: dict = None) -> RailResult:
    """Rail INPUT_SIZE: bloqueia text quando excede o cap configurado.

    Executa em microssegundos. Quando bloqueia, o caller substitui a
    resposta pelo fallback canonico definido em
    pipeline._FALLBACK_BY_CODE["INPUT_SIZE"], que nao revela o limite
    exato ao cliente (evita adaptacao por atacante).
    """
    cap = _max_tokens()
    with span("rail.INPUT_SIZE", mechanism="deterministic"):
        estimated = _count_tokens(text)
        if estimated > cap:
            logger.warning(
                "guardrails.input_size_excedido estimated=%s cap=%s len_chars=%s",
                estimated, cap, len(text or ""),
            )
            return RailResult(
                allowed=False,
                reason=f"input excede limite ({estimated} > {cap} tokens estimados)",
                sanitized_text=text,
                code="INPUT_SIZE",
                mechanism="deterministic",
                data={
                    "estimated_tokens": estimated,
                    "max_tokens": cap,
                    "len_chars": len(text or ""),
                },
            )
        return RailResult(
            allowed=True,
            reason="input dentro do limite",
            sanitized_text=text,
            code="INPUT_SIZE",
            mechanism="deterministic",
            data={"estimated_tokens": estimated, "max_tokens": cap},
        )
