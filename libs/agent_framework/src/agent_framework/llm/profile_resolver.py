from __future__ import annotations

import copy
import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("agent_framework.llm.profiles")


def _canonical_profile_name(value: str | None) -> str:
    """Normalize component/profile names so YAML keys are predictable.

    Examples:
    - BillingAgent -> billing_agent
    - billing_agent -> billing_agent
    - output-supervisor -> output_supervisor
    """
    name = (value or "default").strip()
    if not name:
        return "default"
    name = name.replace("-", "_").replace(".", "_").replace(" ", "_")
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "default"


class LLMProfileResolver:
    """Resolve model/provider parameters per inference point.

    Compatibility rule:
    - If no llm_profiles.yaml is found, this resolver is disabled and callers must use
      the current .env based settings exactly as before.
    - If llm_profiles.yaml exists, profile values override only the configured keys.
      Missing keys fall back to the YAML `default` profile and then to .env settings.
    """

    ENV_BACKED_KEYS = {
        "provider",
        "model",
        "temperature",
        "max_tokens",
        "timeout_seconds",
        "base_url",
        "api_key",
        "project_ocid",
        "auth_mode",
        "endpoint",
        "region",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
    }

    def __init__(self, settings: Any, path: str | None = None):
        self.settings = settings
        self.path = self._find_profiles_file(settings, path)
        self.enabled = self.path is not None
        self._profiles: dict[str, dict[str, Any]] = {}

        if self.enabled:
            self._profiles = self._load_profiles(self.path)
            logger.info("LLM profiles enabled path=%s profiles=%s", self.path, sorted(self._profiles.keys()))
        else:
            logger.info("LLM profiles disabled; using .env settings only")

    @classmethod
    def from_settings(cls, settings: Any) -> "LLMProfileResolver":
        return cls(settings, getattr(settings, "LLM_PROFILES_PATH", None))

    def _find_profiles_file(self, settings: Any, configured_path: str | None) -> Path | None:
        candidates: list[Path] = []
        if configured_path:
            candidates.append(Path(configured_path).expanduser())
        candidates.extend([
            Path("llm_profiles.yaml"),
            Path("config/llm_profiles.yaml"),
            Path("./llm_profiles.yaml"),
            Path("./config/llm_profiles.yaml"),
        ])
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _load_profiles(self, path: Path) -> dict[str, dict[str, Any]]:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        raw_profiles = data.get("profiles", data)
        if not isinstance(raw_profiles, dict):
            raise ValueError(f"Invalid LLM profiles file {path}: expected mapping or profiles mapping")
        profiles: dict[str, dict[str, Any]] = {}
        for name, value in raw_profiles.items():
            if not isinstance(value, dict):
                logger.warning("Ignoring invalid LLM profile %s: expected object", name)
                continue
            original_name = str(name)
            canonical_name = _canonical_profile_name(original_name)
            profile = dict(value)
            profile.setdefault("profile_key", canonical_name)
            profile.setdefault("profile_source_name", original_name)
            profiles[canonical_name] = profile
            # Keep the original key as an alias too, for backward compatibility.
            profiles.setdefault(original_name, profile)
        return profiles

    def env_defaults(self) -> dict[str, Any]:
        return {
            "provider": getattr(self.settings, "LLM_PROVIDER", "mock"),
            "model": getattr(self.settings, "OCI_GENAI_MODEL", "mock-llm"),
            "temperature": getattr(self.settings, "LLM_TEMPERATURE", 0.2),
            "max_tokens": getattr(self.settings, "LLM_MAX_TOKENS", 2048),
            "timeout_seconds": getattr(self.settings, "LLM_TIMEOUT_SECONDS", 120),
            "base_url": getattr(self.settings, "OCI_GENAI_BASE_URL", None),
            "api_key": getattr(self.settings, "OCI_GENAI_API_KEY", None),
            "project_ocid": getattr(self.settings, "OCI_GENAI_PROJECT_OCID", None),
            "auth_mode": getattr(self.settings, "OCI_AUTH_MODE", "config_file"),
            "endpoint": getattr(self.settings, "OCI_GENAI_ENDPOINT", None),
            "region": getattr(self.settings, "OCI_REGION", None),
        }

    def resolve(self, profile_name: str | None = None, **runtime_overrides: Any) -> dict[str, Any]:
        """Return the effective profile.

        Runtime kwargs passed by the caller win over YAML. This preserves existing
        callsites such as `ainvoke(..., temperature=0)` while still allowing the
        profile to define the model/provider for that inference point.
        """
        effective = self.env_defaults()
        selected_name = self.normalize_profile_name(profile_name)

        if self.enabled:
            default_profile = self._profiles.get("default") or {}
            specific_profile = self._profiles.get(selected_name) or {}
            effective.update(copy.deepcopy(default_profile))
            effective.update(copy.deepcopy(specific_profile))
            effective["profile_name"] = selected_name
            effective["requested_profile_name"] = profile_name or "default"
            effective["profile_found"] = bool(specific_profile)
            effective["profile_source"] = "specific" if specific_profile else ("default" if default_profile else "env")
            effective["profiles_enabled"] = True
            effective["profiles_path"] = str(self.path)
        else:
            effective["profile_name"] = selected_name
            effective["requested_profile_name"] = profile_name or "default"
            effective["profile_found"] = False
            effective["profile_source"] = "env"
            effective["profiles_enabled"] = False
            effective["profiles_path"] = None

        for key, value in runtime_overrides.items():
            if key == "profile_name":
                continue
            if value is not None:
                effective[key] = value

        return effective

    def normalize_profile_name(self, profile_name: str | None) -> str:
        return _canonical_profile_name(profile_name)

    def has_profile(self, profile_name: str) -> bool:
        return self.enabled and self.normalize_profile_name(profile_name) in self._profiles
