"""Padrões determinísticos para detecção rápida de prompt injection óbvia.

First-pass antes do LLM PINJ. Se um padrão óbvio for detectado, o LLM
não é invocado. A função `is_obvious_injection` nunca retorna falso negativo
para casos ambíguos — ela só bloqueia quando o padrão é inequívoco.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Padrões compilados de prompt injection / jailbreak
# ---------------------------------------------------------------------------

_PINJ_PATTERNS: list[re.Pattern] = [
    # Ignore previous instructions (EN)
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    # Role override ("you are now a ...")
    re.compile(r"you\s+are\s+now\s+(a\s+)?", re.IGNORECASE),
    # Pseudo-tags de sistema (XML/template injection)
    re.compile(r"\[SYSTEM\]|\[INST\]|<\|system\|>|<\|im_start\|>", re.IGNORECASE),
    # Extração de prompt do sistema
    re.compile(r"print\s+your\s+(system\s+)?prompt", re.IGNORECASE),
    # Repetir texto acima literalmente
    re.compile(r"repeat\s+the\s+text\s+above\s+verbatim", re.IGNORECASE),
    # Ignore previous prompts (variante)
    re.compile(r"ignore\s+(all\s+)?previous\s+prompts?", re.IGNORECASE),
    # From now on you/ignore/forget
    re.compile(r"from\s+now\s+on\s+(you|ignore|forget)", re.IGNORECASE),
    # PT-BR: esqueça suas instruções/regras
    re.compile(
        r"esquece?\s+(suas?\s+|as?\s+)(instru[çc][oõ]es?|regras?)",
        re.IGNORECASE,
    ),
    # PT-BR: ignore as instruções anteriores
    re.compile(
        r"ignore\s+(as\s+)?instru[çc][oõ]es?\s+anteriores?",
        re.IGNORECASE,
    ),
    # PT-BR: desconsidere o prompt
    re.compile(r"desconsidere\s+o\s+prompt", re.IGNORECASE),
    # XML injection tags (<instructions>, <system>, <prompt>, <rules>)
    re.compile(r"</?(?:instructions?|system|prompt|rules?)>", re.IGNORECASE),
    # Delimiter injection (###new rules###, ###system###)
    re.compile(r"###\s*new\s+rules?\s*###|###\s*system\s*###", re.IGNORECASE),
    # Jailbreak mode keywords
    re.compile(
        r"DAN\s+mode|developer\s+mode|jailbreak\s+mode|modo\s+livre",
        re.IGNORECASE,
    ),
    # PT-BR: atue como <LLM> sem restrições
    re.compile(
        r"atue\s+como\s+(?:chatgpt|claude|gemini|gpt|llm)\s+sem\s+restri[çc][oõ]es?",
        re.IGNORECASE,
    ),
]


def is_obvious_injection(text: str) -> bool:
    """Retorna True se o texto contém padrão inequívoco de prompt injection.

    Esta função é um first-pass determinístico: bloqueia apenas quando o
    padrão é inequívoco, evitando falsos positivos. A ausência de match
    retorna False, mas significa apenas "inconclusivo" — o rail LLM PINJ
    deve ser invocado para análise completa.

    Nunca retorna False positivo (ou seja, não bloqueia texto legítimo do
    domínio TIM). Casos ambíguos devem ser resolvidos pelo LLM.

    Args:
        text: texto do usuário a verificar.

    Returns:
        True quando pelo menos um padrão de injection óbvia casar.
        False quando nenhum padrão casar (inconclusivo).
    """
    for pattern in _PINJ_PATTERNS:
        if pattern.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Pre-messages fixos conhecidos (invariante do early-exit AT-04)
# ---------------------------------------------------------------------------

_KNOWN_PRE_MESSAGES: frozenset[str] = frozenset({
    "Perfeito!",
    "Certo!",
    "Ok!",
    "Aguarde um instante, por favor.",
    "Aguarde um momento, por favor.",
    "Entendido!",
    "Claro, aguarde um instante.",
    "Processando sua solicitação, aguarde.",
})
"""Conjunto de pre_messages fixos conhecidos.

Usado para validação da invariante do early-exit de tool_calls (AT-04):
quando `tool_calls` está presente, o `content` do AIMessage deve consistir
apenas em fragmentos presentes ou derivados desta lista — textos fixos que
não requerem verificação de guardrail.

Este conjunto NÃO é exaustivo. Serve como referência de validação em testes
e auditoria. Strings parciais podem ser usadas em `in` checks.
"""


__all__ = ["_PINJ_PATTERNS", "is_obvious_injection", "_KNOWN_PRE_MESSAGES"]
