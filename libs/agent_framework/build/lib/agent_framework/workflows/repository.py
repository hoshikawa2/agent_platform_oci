from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml

from .models import WorkflowDefinition


class FileWorkflowRepository:
    """Carrega `<name>.active.yaml` e `<name>.vN.yaml` sem acoplar domínio ao framework."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def get_active(self, name: str) -> WorkflowDefinition:
        marker = self.root / f"{name}.active.yaml"
        if not marker.exists():
            raise FileNotFoundError(f"Workflow ativo não encontrado: {marker}")
        raw: dict[str, Any] = yaml.safe_load(marker.read_text(encoding="utf-8")) or {}
        version = raw.get("version")
        if not isinstance(version, int):
            raise ValueError(f"Marcador ativo inválido: {marker}")
        return self.get_version(name, version)

    def get_version(self, name: str, version: int) -> WorkflowDefinition:
        path = self.root / f"{name}.v{version}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Workflow não encontrado: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        definition = WorkflowDefinition.model_validate(raw)
        if definition.name != name or definition.version != version:
            raise ValueError(f"Nome/versão do conteúdo diverge do arquivo: {path}")
        return definition
