from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI

from .authentication import DenyAuthenticationProvider
from .factory import create_authentication_provider, create_provider_from_config
from .middleware import AuthenticationMiddleware, AuthenticationPolicy, PolicyAuthenticationMiddleware


def _csv(value: str | None, default: str = "") -> list[str]:
    return [item.strip() for item in (value if value is not None else default).split(",") if item.strip()]


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_authentication_policies(path: str | Path) -> tuple[list[AuthenticationPolicy], Any]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    providers = {
        name: create_provider_from_config(config or {})
        for name, config in (raw.get("providers") or {}).items()
    }
    policies: list[AuthenticationPolicy] = []
    for index, item in enumerate(raw.get("policies") or []):
        provider_name = item.get("provider")
        if provider_name not in providers:
            raise ValueError(f"Unknown authentication provider in policy: {provider_name}")
        policies.append(AuthenticationPolicy(
            name=str(item.get("name") or f"policy-{index + 1}"),
            provider=providers[provider_name],
            paths=tuple(item.get("paths") or ["*"]),
            methods=frozenset(str(method).upper() for method in (item.get("methods") or [])),
            required_roles=frozenset(str(role) for role in (item.get("required_roles") or [])),
            required_scopes=frozenset(str(scope) for scope in (item.get("required_scopes") or [])),
        ))
    default_name = raw.get("default_provider")
    default_provider = providers.get(default_name) if default_name else DenyAuthenticationProvider()
    return policies, default_provider


def install_authentication(app: FastAPI, prefix: str = "AGENT_AUTH") -> bool:
    """Install optional authentication using an isolated environment prefix.

    Returns True when middleware was installed. Authentication remains disabled
    unless ``<PREFIX>_ENABLED=true`` or a non-``none`` mode/policy file is set.
    """
    policy_file = os.getenv(f"{prefix}_POLICIES_FILE")
    mode = os.getenv(f"{prefix}_MODE", "none").strip().lower()
    enabled = _bool(os.getenv(f"{prefix}_ENABLED"), default=bool(policy_file or mode not in {"none", "disabled"}))
    if not enabled:
        return False

    if policy_file:
        policies, default_provider = load_authentication_policies(policy_file)
        app.add_middleware(PolicyAuthenticationMiddleware, policies=policies, default_provider=default_provider)
        return True

    provider = create_authentication_provider(prefix)
    public_paths = _csv(os.getenv(f"{prefix}_PUBLIC_PATHS"), "/health,/ready,/live,/docs,/openapi.json,/redoc")
    public_prefixes = _csv(os.getenv(f"{prefix}_PUBLIC_PREFIXES"))
    app.add_middleware(AuthenticationMiddleware, provider=provider, public_paths=public_paths, public_prefixes=public_prefixes)
    return True
