from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import os

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


@dataclass(slots=True)
class GuardrailsConfigBundle:
    loaded: bool = False
    path: str | None = None
    input_rails: list[Any] | None = None
    output_rails: list[Any] | None = None
    retrieval_rails: list[Any] | None = None
    tool_rails: list[Any] | None = None
    raw: dict[str, Any] | None = None


def _resolve_path(config_path: str | None = None) -> Path:
    raw = config_path or os.getenv("GUARDRAILS_CONFIG_PATH") or "./config/guardrails.yaml"
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _rail_factories() -> dict[str, Callable[[], Any]]:
    # Lazy import avoids circular import with pipeline.py.
    from .rails import (
        ComplianceRail,
        DataLeakageInputRail,
        DataLeakageOutputRail,
        GroundednessRail,
        HallucinationRiskRail,
        JailbreakRail,
        LoopRail,
        MessageSizeRail,
        OutOfScopeRail,
        OutputPiiMaskRail,
        OutputToxicitySanitizationRail,
        PiiMaskRail,
        PrematureActionRail,
        ProactiveOfferRail,
        PromptInjectionRail,
        RagSecurityRail,
        RetrievalRelevanceRail,
        ToolValidationRail,
        ToxicityRail,
    )
    return {
        # Input
        "INPUT_SIZE": MessageSizeRail,
        "SIZE": MessageSizeRail,
        "MSK": PiiMaskRail,
        "PII": PiiMaskRail,
        "TOX": ToxicityRail,
        "PINJ": PromptInjectionRail,
        "JAILBREAK": JailbreakRail,
        "VLOOP": LoopRail,
        "LOOP": LoopRail,
        "DLEX_IN": DataLeakageInputRail,
        "OOS": OutOfScopeRail,
        # Output
        "MSK_OUT": OutputPiiMaskRail,
        "OUTPUT_MSK": OutputPiiMaskRail,
        "TOXOUT": OutputToxicitySanitizationRail,
        "TOX_OUT": OutputToxicitySanitizationRail,
        "CMP": ComplianceRail,
        "COMPLIANCE": ComplianceRail,
        "AOFERTA": ProactiveOfferRail,
        "PROACTIVE_OFFER": ProactiveOfferRail,
        "REVPREC": PrematureActionRail,
        "PREMATURE_ACTION": PrematureActionRail,
        "DLEX_OUT": DataLeakageOutputRail,
        "GND": GroundednessRail,
        "GROUNDEDNESS": GroundednessRail,
        "ALUC_RISK": HallucinationRiskRail,
        "HALLUCINATION_RISK": HallucinationRiskRail,
        # Retrieval/tool
        "RET_REL": RetrievalRelevanceRail,
        "RETRIEVAL_RELEVANCE": RetrievalRelevanceRail,
        "RAGSEC": RagSecurityRail,
        "TOOL_VAL": ToolValidationRail,
        "TOOL_VALIDATION": ToolValidationRail,
    }


def _normalize_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"code": item, "enabled": True}
    if isinstance(item, dict):
        return dict(item)
    return {"enabled": False}


def _instantiate_rail(item: dict[str, Any], factories: dict[str, Callable[[], Any]]) -> Any | None:
    if not _truthy(item.get("enabled"), True):
        return None
    code = str(item.get("code") or item.get("name") or item.get("rail") or "").strip().upper()
    if not code:
        return None
    factory = factories.get(code)
    if factory is None:
        raise ValueError(f"Guardrail desconhecido no guardrails.yaml: {code}")
    return factory()


def _read_stage(raw: dict[str, Any], stage: str) -> list[Any]:
    factories = _rail_factories()
    entries = raw.get(stage)
    # Allows both:
    # input: [...]
    # guardrails:
    #   input: [...]
    if entries is None and isinstance(raw.get("guardrails"), dict):
        entries = raw["guardrails"].get(stage)
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise ValueError(f"A seção '{stage}' do guardrails.yaml precisa ser uma lista")
    rails: list[Any] = []
    for original in entries:
        item = _normalize_item(original)
        rail = _instantiate_rail(item, factories)
        if rail is not None:
            rails.append(rail)
    return rails


def load_guardrails_config(config_path: str | None = None) -> GuardrailsConfigBundle:
    path = _resolve_path(config_path)
    if not path.exists():
        return GuardrailsConfigBundle(loaded=False, path=str(path))
    if yaml is None:
        raise RuntimeError("PyYAML não está disponível para ler guardrails.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("guardrails.yaml precisa conter um objeto YAML no topo")
    enabled = _truthy(raw.get("enabled"), True)
    if not enabled:
        return GuardrailsConfigBundle(loaded=True, path=str(path), input_rails=[], output_rails=[], retrieval_rails=[], tool_rails=[], raw=raw)
    return GuardrailsConfigBundle(
        loaded=True,
        path=str(path),
        input_rails=_read_stage(raw, "input"),
        output_rails=_read_stage(raw, "output"),
        retrieval_rails=_read_stage(raw, "retrieval"),
        tool_rails=_read_stage(raw, "tool"),
        raw=raw,
    )
