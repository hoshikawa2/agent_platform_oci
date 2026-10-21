"""Gateway-only bootstrap for the Global Supervisor LLM.

Resolve the supervisor entry in llm_profiles.yaml *before* create_llm().
This matters because create_llm() selects OCISDKProvider immediately when
LLM_PROVIDER=oci_sdk; OCISDKProvider does not dynamically switch providers.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from agent_framework.llm.providers import create_llm

logger = logging.getLogger("agent_gateway.supervisor_llm")


def _profile_file(settings) -> Path:
    explicit = (
        os.getenv("GLOBAL_SUPERVISOR_LLM_PROFILES_PATH")
        or getattr(settings, "GLOBAL_SUPERVISOR_LLM_PROFILES_PATH", None)
        or os.getenv("LLM_PROFILES_PATH")
        or getattr(settings, "LLM_PROFILES_PATH", None)
    )
    if explicit:
        path = Path(str(explicit)).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"Supervisor LLM profile YAML not found: {path}")
        return path

    candidates = (
        "config/llm_profiles.yaml",
        "llm_profiles.yaml",
        "apps/agent_gateway/config/llm_profiles.yaml",
        "apps/agent_template_backend/config/llm_profiles.yaml",
        "apps/agent_template_backend/llm_profiles.yaml",
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path.resolve()
    raise RuntimeError(
        "No llm_profiles.yaml found for Gateway supervisor. Set "
        "GLOBAL_SUPERVISOR_LLM_PROFILES_PATH to the EXISTING YAML file path."
    )


def build_supervisor_llm(settings):
    """Create LLM from the supervisor profile without mutating global settings."""
    path = _profile_file(settings)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profile = (data.get("profiles") or {}).get("supervisor")
    if not isinstance(profile, dict):
        raise RuntimeError(f"Missing profiles.supervisor in {path}")

    effective_provider = str(profile.get("provider") or settings.LLM_PROVIDER).strip()
    allowed = {"oci_openai", "openai_compatible", "oci_sdk", "mock"}
    if effective_provider not in allowed:
        raise RuntimeError(f"Unsupported supervisor provider: {effective_provider}")

    configured_url = (
        profile.get("base_url")
        or profile.get("service_endpoint")
        or getattr(settings, "OCI_GENAI_BASE_URL", None)
    )
    url = str(configured_url or "").strip().rstrip("/")
    if effective_provider == "oci_openai":
        # OCI native URL is commonly used by the process-wide .env when the
        # default provider is oci_sdk. Translate only the well-known OCI host.
        if url.startswith("https://inference.generativeai.") and url.endswith(".oci.oraclecloud.com"):
            url += "/openai/v1"
        if not url.endswith("/openai/v1"):
            raise RuntimeError(
                f"Supervisor OpenAI-compatible base URL must end with /openai/v1, got {url!r}. "
                "Set base_url under profiles.supervisor to the working endpoint."
            )

    key = profile.get("api_key") or getattr(settings, "OCI_GENAI_API_KEY", None) or os.getenv("OCI_GENAI_API_KEY")
    if effective_provider in {"oci_openai", "openai_compatible"} and not key:
        raise RuntimeError(
            "Supervisor profile requires OCI_GENAI_API_KEY (or profiles.supervisor.api_key). "
            "OCI SDK config_file signing is NOT an OpenAI-compatible bearer API key."
        )

    overrides = {
        "LLM_PROVIDER": effective_provider,
        "OCI_GENAI_MODEL": str(profile.get("model") or settings.OCI_GENAI_MODEL),
        "OCI_GENAI_BASE_URL": url,
        "LLM_TEMPERATURE": float(profile.get("temperature", settings.LLM_TEMPERATURE)),
        "LLM_MAX_TOKENS": int(profile.get("max_tokens", settings.LLM_MAX_TOKENS)),
    }
    if key:
        overrides["OCI_GENAI_API_KEY"] = str(key)

    supervisor_settings = settings.model_copy(update=overrides)
    logger.info(
        "Supervisor LLM profile loaded path=%s provider=%s model=%s base_url=%s",
        path, effective_provider, overrides["OCI_GENAI_MODEL"], url,
    )
    return create_llm(supervisor_settings)
