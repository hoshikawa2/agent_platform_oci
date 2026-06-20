from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml


def _canonical_profile_name(value: str | None) -> str:
    name = (value or "default").strip()
    name = name.replace("-", "_").replace(".", "_").replace(" ", "_")
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return re.sub(r"_+", "_", name).strip("_") or "default"


class LLMProfileResolver:
    def __init__(self, settings: Any):
        self.settings = settings
        self.path = self._find_profiles_file()
        self.enabled = self.path is not None
        self._profiles = self._load_profiles(self.path) if self.enabled else {}

    def _find_profiles_file(self) -> Path | None:
        root = getattr(self.settings, "project_root", Path.cwd())
        configured = Path(getattr(self.settings, "LLM_PROFILES_PATH", "") or "").expanduser()
        candidates = []
        if configured:
            candidates.append(configured if configured.is_absolute() else Path(root) / configured)
        candidates += [
            Path(root) / "llm_profiles.yaml",
            Path(root) / "configs/llm_profiles/llm_profiles.yaml",
            Path(root) / "config/llm_profiles.yaml",
            Path("llm_profiles.yaml"),
            Path("configs/llm_profiles/llm_profiles.yaml"),
        ]
        for path in candidates:
            if path and path.exists() and path.is_file():
                return path
        return None

    def _load_profiles(self, path: Path) -> dict[str, dict[str, Any]]:
        # Expand ${VAR} placeholders, matching the way env-driven framework config is commonly used.
        text = os.path.expandvars(path.read_text(encoding="utf-8"))
        data = yaml.safe_load(text) or {}
        raw = data.get("profiles", data)
        profiles = {}
        for name, value in raw.items():
            if isinstance(value, dict):
                profiles[_canonical_profile_name(str(name))] = dict(value)
        return profiles

    def env_defaults(self) -> dict[str, Any]:
        return {
            "provider": getattr(self.settings, "LLM_PROVIDER", "mock"),
            "model": getattr(self.settings, "OCI_GENAI_MODEL", "mock-llm"),
            "temperature": getattr(self.settings, "LLM_TEMPERATURE", 0.0),
            "max_tokens": getattr(self.settings, "LLM_MAX_TOKENS", 900),
            "timeout_seconds": getattr(self.settings, "LLM_TIMEOUT_SECONDS", 120),
            "base_url": getattr(self.settings, "OCI_GENAI_BASE_URL", None),
            "api_key": getattr(self.settings, "OCI_GENAI_API_KEY", None),
            "project_ocid": getattr(self.settings, "OCI_GENAI_PROJECT_OCID", None),
        }

    def resolve(self, profile_name: str | None = None, **overrides) -> dict[str, Any]:
        profile_key = _canonical_profile_name(profile_name)
        effective = self.env_defaults()

        if self.enabled:
            effective.update(copy.deepcopy(self._profiles.get("default") or {}))
            effective.update(copy.deepcopy(self._profiles.get(profile_key) or {}))

        for key, value in overrides.items():
            if value is not None:
                effective[key] = value

        effective["profile_name"] = profile_key
        return effective
