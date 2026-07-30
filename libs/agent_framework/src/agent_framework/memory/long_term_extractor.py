from __future__ import annotations
import re
from typing import Any

_PATTERNS = [
    ('identity', 'preferred_name', re.compile(r'\b(?:me chame de|pode me chamar de|meu nome preferido é)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 _-]{1,40})', re.I)),
    ('preference', 'preferred_language', re.compile(r'\b(?:minha linguagem preferida é|prefiro programar em)\s+(Python|Java|JavaScript|TypeScript|Go|Rust|C#|C\+\+)\b', re.I)),
    ('project', 'current_project', re.compile(r'\b(?:meu projeto atual se chama|estou trabalhando no projeto|o projeto se chama)\s+([A-Za-zÀ-ÿ0-9._ -]{2,60})', re.I)),
    ('constraint', 'meeting_restriction', re.compile(r'\b(não (?:marque|agende) reuniões?[^.!?\n]{3,120})', re.I)),
    ('preference', 'communication_style', re.compile(r'\b(?:prefiro respostas|responda de forma)\s+(curtas?|detalhadas?|objetivas?|técnicas?|didáticas?)', re.I)),
]

def extract_long_term_memory(text: str, min_confidence: float = 0.70) -> list[dict[str, Any]]:
    normalized = ' '.join((text or '').split())
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for category, key, pattern in _PATTERNS:
        match = pattern.search(normalized)
        if not match or (category, key) in seen:
            continue
        seen.add((category, key))
        confidence = 0.98
        if confidence >= min_confidence:
            output.append({'category': category, 'key': key, 'value': match.group(1).strip(' .,;:'), 'confidence': confidence, 'metadata': {'extractor': 'regex-v1'}})
    return output
