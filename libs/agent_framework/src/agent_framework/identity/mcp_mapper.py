from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from .models import BusinessContext

class MCPParameterMapper:
    """Mapeia BusinessContext para parâmetros reais de cada tool MCP."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.tools = (self.config.get("mcp_parameter_mapping") or self.config).get("tools") or {}
        self.defaults = (self.config.get("mcp_parameter_mapping") or self.config).get("defaults") or {}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "MCPParameterMapper":
        p = Path(path)
        if not p.exists():
            return cls({})
        return cls(yaml.safe_load(p.read_text(encoding="utf-8")) or {})

    def map(self, tool_name: str, business_context: BusinessContext | dict[str, Any] | None, *, original_context: dict[str, Any] | None = None, extra_args: dict[str, Any] | None = None) -> dict[str, Any]:
        ctx = business_context if isinstance(business_context, BusinessContext) else BusinessContext.from_mapping(business_context or {})
        original_context = dict(original_context or {})
        args = {k: v for k, v in (extra_args or {}).items() if v not in (None, "")}
        rule = self.tools.get(tool_name) or {}
        mappings = rule.get("map") or {}
        # também aceita formato simples: customer_key: msisdn
        for src_key, target in rule.items():
            if src_key in {"map", "defaults", "required"}:
                continue
            mappings.setdefault(src_key, target)
        for canonical_key, target_field in mappings.items():
            value = getattr(ctx, canonical_key, None)
            if value not in (None, ""):
                args[str(target_field)] = value
        for key, value in {**self.defaults, **(rule.get("defaults") or {})}.items():
            args.setdefault(key, value)
        # preserva parâmetros específicos já capturados no canal, sem o framework conhecer seus nomes.
        for key, value in original_context.items():
            if key not in args and value not in (None, "", {}, []):
                args[key] = value
        return args
