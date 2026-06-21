from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_gateway_governance_config(path: str | None = None) -> dict[str, Any]:
    config_path = Path(path or os.getenv("AGENT_GATEWAY_GOVERNANCE_CONFIG", "config/gateway_governance.yaml"))
    if not config_path.exists():
        return {}
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
