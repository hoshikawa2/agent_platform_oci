from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "libs" / "agent_framework" / "src"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

from agent_framework.llm.profile_resolver import LLMProfileResolver


def _settings(path: Path):
    return SimpleNamespace(
        LLM_PROFILES_PATH=str(path),
        LLM_PROVIDER="oci_openai",
        OCI_GENAI_MODEL="openai.gpt-4.1",
        LLM_TEMPERATURE=0.2,
        LLM_MAX_TOKENS=2048,
        LLM_TIMEOUT_SECONDS=120,
        OCI_GENAI_BASE_URL="",
        OCI_GENAI_API_KEY=None,
        OCI_GENAI_PROJECT_OCID=None,
        OCI_AUTH_MODE="config_file",
        OCI_GENAI_ENDPOINT=None,
        OCI_REGION="",
        model_fields_set=set(),
    )


def test_profile_max_tokens_wins_over_env_and_legacy_fallback(tmp_path, monkeypatch):
    profile = tmp_path / "llm_profiles.yaml"
    profile.write_text(
        "profiles:\n"
        "  default:\n"
        "    provider: oci_openai\n"
        "  router:\n"
        "    max_tokens: 768\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LLM_MAX_TOKENS", "999")
    resolver = LLMProfileResolver.from_settings(_settings(profile))
    assert resolver.resolve_configured_value(
        "router", "max_tokens", env_var="LLM_MAX_TOKENS", fallback=512
    ) == 768


def test_env_max_tokens_wins_when_profiles_file_is_absent(tmp_path, monkeypatch):
    missing = tmp_path / "missing.yaml"
    monkeypatch.setenv("LLM_MAX_TOKENS", "901")
    resolver = LLMProfileResolver.from_settings(_settings(missing))
    assert resolver.resolve_configured_value(
        "router", "max_tokens", env_var="LLM_MAX_TOKENS", fallback=512
    ) == 901


def test_legacy_fallback_is_kept_when_yaml_and_env_are_absent(tmp_path, monkeypatch):
    missing = tmp_path / "missing.yaml"
    monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)
    resolver = LLMProfileResolver.from_settings(_settings(missing))
    assert resolver.resolve_configured_value(
        "router", "max_tokens", env_var="LLM_MAX_TOKENS", fallback=512
    ) == 512


def test_canonical_profiles_keep_existing_budgets_and_router_uses_largest_value():
    profile_path = ROOT / "libs" / "agent_framework" / "config" / "llm_profiles.yaml"
    profiles = yaml.safe_load(profile_path.read_text(encoding="utf-8"))["profiles"]
    assert profiles["router"]["max_tokens"] == 768
    assert profiles["processing_interruption_classifier"]["max_tokens"] == 8
    assert profiles["mcp_parameter_extraction"]["max_tokens"] == 80
    assert profiles["guardrail"]["max_tokens"] == 600
    assert profiles["rag_rewriter"]["max_tokens"] == 300
    assert profiles["rag_compressor"]["max_tokens"] == 1200
    assert profiles["summary_memory"]["max_tokens"] == 1200


def test_inference_points_use_fallback_max_tokens_instead_of_direct_max_tokens():
    checks = {
        "libs/agent_framework/src/agent_framework/routing/enterprise_router.py": [256, 512, 768],
        "libs/agent_framework/src/agent_framework/runtime/agent_runtime.py": [80],
        "libs/agent_framework/src/agent_framework/channels/interruption.py": [8],
        "libs/agent_framework/src/agent_framework/guardrails/llm_rails.py": [600],
        "libs/agent_framework/src/agent_framework/rag/rag_service.py": [300],
    }
    for relative, values in checks.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for value in values:
            assert f"fallback_max_tokens={value}" in text
            assert f"max_tokens={value}," not in text.replace(f"fallback_max_tokens={value},", "")
