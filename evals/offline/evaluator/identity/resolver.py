from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _deep_get(data: dict, path: str):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


class IdentityResolver:
    def __init__(self, path: str = "configs/identity.yaml"):
        self.path = Path(path)
        self.config = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.identity = self.config.get("identity", {})
        self.keys = self.identity.get("keys", {})

    def resolve(self, payload: dict[str, Any]) -> dict[str, Any]:
        out = {}

        for key, spec in self.keys.items():
            value = None
            for source in spec.get("sources", []):
                value = _deep_get(payload, source)
                if value not in (None, ""):
                    break
            out[key] = str(value) if value not in (None, "") else None

        out["metadata"] = {
            "identity_version": self.identity.get("version"),
            "identity_source": str(self.path),
        }

        return out