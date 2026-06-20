from __future__ import annotations
import yaml
from evaluator.config.settings import settings


def load_prompt(path: str, key: str) -> str:
    p = settings.path(path)
    data = yaml.safe_load(p.read_text()) or {}
    if key not in data:
        raise KeyError(f"Prompt key {key!r} not found in {p}")
    return str(data[key])
