"""Blocklist determinística para casos óbvios de Out-of-Scope.

Fast-path antes do LLM OOS. Retorna True apenas para casos inequívocos.
Nunca retorna False positivo — apenas bloqueia se absolutamente certo.
A ausência de match retorna None (inconclusivo → enviar ao LLM).
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Padrões de operadoras concorrentes com contexto de cancelamento/reclamação
# ---------------------------------------------------------------------------
# Só bloqueia quando há contexto claro de problema/pedido em outra operadora,
# não apenas menção de nome (ex.: "minha filha usa Vivo" não é OOS).

_COMPETITOR_PATTERNS: list[re.Pattern] = [
    # Cancelar serviço de operadora concorrente
    re.compile(
        r"cancelar\s+.*?(?:vivo|claro|oi|net\b|nextel)",
        re.IGNORECASE | re.DOTALL,
    ),
    # Problemas com operadora concorrente
    re.compile(
        r"problemas?\s+com\s+(?:a\s+)?(?:vivo|claro|oi\b|net\b)",
        re.IGNORECASE,
    ),
    # Sinal / serviço da operadora concorrente
    re.compile(
        r"sinal\s+d[ao]?\s+(?:vivo|claro|oi\b)",
        re.IGNORECASE,
    ),
    # Fatura de operadora concorrente
    re.compile(
        r"fatura\s+d[ao]?\s+(?:vivo|claro|oi\b|net\b)",
        re.IGNORECASE,
    ),
    # Reclamação sobre operadora concorrente
    re.compile(
        r"reclamar?\s+(?:da?\s+)?(?:vivo|claro|oi\b|net\b)",
        re.IGNORECASE,
    ),
    # Contestar cobrança de operadora concorrente
    re.compile(
        r"contestar\s+.*?(?:vivo|claro|oi\b|net\b)",
        re.IGNORECASE | re.DOTALL,
    ),
]

# ---------------------------------------------------------------------------
# Padrões políticos claramente fora do contexto de atendimento do domínio
# ---------------------------------------------------------------------------
# Apenas combina quando há intenção de discussão política explícita, não
# quando a palavra aparece em contexto neutro (ex.: "acordo governamental").

_POLITICAL_PATTERNS: list[re.Pattern] = [
    # Debate político explícito
    re.compile(
        r"\b(?:presidente|governador|eleicao|eleição|partido|voto)\b"
        r".{0,60}"
        r"\b(?:tim\b|fatura|conta|plano|celular|internet|cobrança)",
        re.IGNORECASE | re.DOTALL,
    ),
    # Pedido de opinião política
    re.compile(
        r"(?:quem\s+você\s+acha|vote\s+em|melhor\s+candidato)",
        re.IGNORECASE,
    ),
]


def is_obvious_oos(text: str) -> bool | None:
    """Retorna True se o texto é claramente Out-of-Scope; None se inconclusivo.

    Esta função é um fast-path determinístico para casos óbvios. Nunca
    retorna False — a decisão "in-scope" é exclusiva do rail LLM OOS.

    Regra de uso:
        result = is_obvious_oos(text)
        if result is True:
            # bloquear sem chamar LLM
        else:
            # enviar ao LLM OOS para decisão

    Args:
        text: texto do usuário a verificar.

    Returns:
        True quando o texto é inequivocamente OOS (concorrente com contexto
        de cancelamento/reclamação, ou discussão política explícita).
        None quando inconclusivo — o LLM deve decidir.
    """
    for pattern in _COMPETITOR_PATTERNS:
        if pattern.search(text):
            return True
    for pattern in _POLITICAL_PATTERNS:
        if pattern.search(text):
            return True
    return None


__all__ = [
    "_COMPETITOR_PATTERNS",
    "_POLITICAL_PATTERNS",
    "is_obvious_oos",
]
