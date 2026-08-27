"""Blocklist determinística para toxicidade óbvia em PT-BR.

Fast-path para ToxRail. Captura apenas casos inequívocos de ofensa,
xingamento ou ameaça direta. Casos ambíguos (sarcasmo, frustração,
gírias) passam para o LLM.
"""
import re

_EXPLICIT_TERMS = re.compile(
    r"\b(vai\s+se\s+f[ou]der|vtnc|vsf|filho\s+da\s+puta|fdp|"
    r"puta\s+que\s+p[ao]riu|sua\s+m[aã]e|corno|viado\s+filho|"
    r"idiota\s+incompetente|bando\s+de\s+lad[rr][oõo]es?|"
    r"vou\s+te\s+processar\s+e\s+destruir|vou\s+matar|me\s+matando\s+de\s+raiva)\b",
    re.IGNORECASE,
)

_THREAT_PATTERNS = re.compile(
    r"\b(processo\s+criminal|ameac(o|ei)\s+a?\s*tim|vou\s+destruir)\b",
    re.IGNORECASE,
)


def is_obvious_toxic(text: str) -> bool:
    """Retorna True apenas para toxicidade inequívoca. Casos ambíguos → False (LLM decide)."""
    return bool(_EXPLICIT_TERMS.search(text) or _THREAT_PATTERNS.search(text))


__all__ = ["is_obvious_toxic"]
