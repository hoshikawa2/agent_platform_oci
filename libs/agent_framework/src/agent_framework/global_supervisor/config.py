from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import BackendDefinition, BackendRegistryConfig


class BackendRegistry:
    def __init__(self, config: BackendRegistryConfig):
        self.config = config
        self.backends: dict[str, BackendDefinition] = {
            b.backend_id: b for b in config.backends if b.enabled
        }
        if not self.backends:
            raise ValueError("Nenhum backend habilitado no registry do Global Supervisor.")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "BackendRegistry":
        p = Path(path)
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        raw_backends = data.get("backends") or []
        # Aceita lista ou dict para facilitar edição humana do YAML.
        if isinstance(raw_backends, dict):
            normalized = []
            for backend_id, value in raw_backends.items():
                item = dict(value or {})
                item.setdefault("backend_id", backend_id)
                normalized.append(item)
            raw_backends = normalized
        config = BackendRegistryConfig(
            default_backend=data.get("default_backend"),
            backends=[BackendDefinition(**b) for b in raw_backends],
        )
        return cls(config)

    def get(self, backend_id: str) -> BackendDefinition:
        try:
            return self.backends[backend_id]
        except KeyError as exc:
            raise KeyError(f"Backend não registrado ou desabilitado: {backend_id}") from exc

    def default(self) -> BackendDefinition:
        if self.config.default_backend and self.config.default_backend in self.backends:
            return self.backends[self.config.default_backend]
        return sorted(self.backends.values(), key=lambda b: b.priority)[0]

    def list(self) -> list[BackendDefinition]:
        return sorted(self.backends.values(), key=lambda b: (b.priority, b.backend_id))

    def describe_for_prompt(self) -> str:
        lines: list[str] = []
        for b in self.list():
            lines.append(
                f"- {b.backend_id}: {b.description} | domínios={', '.join(b.domains)} | exemplos={'; '.join(b.examples[:3])}"
            )
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "default_backend": self.config.default_backend,
            "backends": [b.model_dump(mode="json") for b in self.list()],
        }
