from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml

from .models import IntentDefinition, RouterStatePolicy


class RoutingConfig(BaseException):
    pass


def load_routing_config(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Arquivo de roteamento não encontrado: {path}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def load_intents(path: str) -> list[IntentDefinition]:
    data = load_routing_config(path)
    return [IntentDefinition(**item) for item in data.get("intents", [])]


def load_state_policies(path: str) -> list[RouterStatePolicy]:
    data = load_routing_config(path)
    return [RouterStatePolicy(**item) for item in data.get("state_policies", [])]


def load_router_defaults(path: str) -> dict[str, Any]:
    data = load_routing_config(path)
    return data.get("router", {})
