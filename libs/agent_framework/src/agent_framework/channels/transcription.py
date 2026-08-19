"""Correções determinísticas e conservadoras para transcrição de canal de voz."""
from __future__ import annotations

import re
from typing import Mapping

# Só falas inteiras entram nesta tabela. Nunca substitua tokens dentro de frases.
DEFAULT_WHOLE_UTTERANCE_FIXES: dict[str, str] = {
    "fim": "Sim",
    "mim": "Sim",
}

_TRAILING_PUNCT = re.compile(r"[.!?]+$")


def fix_whole_utterance_transcription(
    text: str,
    *,
    fixes: Mapping[str, str] | None = None,
) -> str:
    raw = str(text or "")
    stripped = raw.strip()
    if not stripped:
        return raw
    candidate = _TRAILING_PUNCT.sub("", stripped).strip().casefold()
    table = fixes or DEFAULT_WHOLE_UTTERANCE_FIXES
    replacement = table.get(candidate)
    return str(replacement) if replacement is not None else raw


__all__ = ["DEFAULT_WHOLE_UTTERANCE_FIXES", "fix_whole_utterance_transcription"]
