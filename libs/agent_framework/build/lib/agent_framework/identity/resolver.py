from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from .models import BusinessContext

class IdentityResolver:
    """Resolve campos de canal/backend para chaves canônicas do framework."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.identity_cfg = self.config.get("identity") or self.config
        self.required = set(self.identity_cfg.get("required") or [])
        self.keys_cfg = self.identity_cfg.get("keys") or {}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "IdentityResolver":
        p = Path(path)
        if not p.exists():
            return cls({})
        return cls(yaml.safe_load(p.read_text(encoding="utf-8")) or {})

    def resolve(self, payload: dict[str, Any], *, session_id: str | None = None, previous: dict[str, Any] | BusinessContext | None = None) -> BusinessContext:
        payload = payload or {}
        prev = previous if isinstance(previous, BusinessContext) else BusinessContext.from_mapping(previous or {})
        values: dict[str, Any] = {}
        sources: dict[str, str] = dict(prev.source_fields)
        for key_name in ("customer_key", "contract_key", "interaction_key", "account_key", "resource_key", "session_key"):
            old = getattr(prev, key_name)
            # chave já definida não muda: estabilidade permanente durante a sessão.
            if old:
                values[key_name] = old
                continue
            key_cfg = self.keys_cfg.get(key_name) or {}
            source_names = key_cfg.get("sources") or []
            resolved, source = self._first_value(payload, source_names)
            if not resolved and key_name == "session_key" and session_id:
                resolved, source = str(session_id), "session_id"
            values[key_name] = resolved
            if resolved and source:
                sources[key_name] = source
        values["source_fields"] = sources
        values["metadata"] = {"identity_version": self.identity_cfg.get("version", "1")}
        return BusinessContext.from_mapping(values)

    def validate(self, ctx: BusinessContext) -> list[str]:
        missing = []
        for key in self.required:
            if not getattr(ctx, key, None):
                missing.append(key)
        return missing

    def _first_value(self, payload: dict[str, Any], sources: list[str]) -> tuple[str | None, str | None]:
        for src in sources:
            value = self._get_path(payload, src)
            text = str(value or "").strip()
            if text:
                return text, src
        return None, None

    def _get_path(self, data: dict[str, Any], path: str) -> Any:
        cur: Any = data
        for part in str(path).split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur
