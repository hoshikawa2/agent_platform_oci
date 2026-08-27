from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from .authentication import (
    ApiKeyAuthenticationProvider,
    BasicAuthenticationProvider,
    DenyAuthenticationProvider,
    JwtAuthenticationProvider,
    NoAuthenticationProvider,
    OAuth2IntrospectionAuthenticationProvider,
    StaticBearerAuthenticationProvider,
    TrustedProxyAuthenticationProvider,
)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ValueError(f"Required authentication environment variable is missing: {name}")
    return value


def _resolve(config: Mapping[str, Any], key: str, *, required: bool = False, default: Any = None) -> Any:
    env_key = config.get(f"{key}_env")
    if env_key:
        value = os.getenv(str(env_key))
        if required and (value is None or not value.strip()):
            raise ValueError(f"Required authentication environment variable is missing: {env_key}")
        return value if value is not None else default
    value = config.get(key, default)
    if required and (value is None or (isinstance(value, str) and not value.strip())):
        raise ValueError(f"Required authentication configuration is missing: {key}")
    return value


def create_provider_from_config(config: Mapping[str, Any]):
    """Create a provider from a secret-safe mapping.

    Secret values may be supplied indirectly with ``<field>_env`` keys so YAML
    never needs to contain credentials.
    """
    mode = str(config.get("mode", "none")).strip().lower()
    if mode in {"none", "disabled"}:
        return NoAuthenticationProvider()
    if mode in {"deny", "reject"}:
        return DenyAuthenticationProvider()
    if mode == "basic":
        return BasicAuthenticationProvider(
            str(_resolve(config, "client_id", required=True)),
            str(_resolve(config, "secret_hash", required=True)),
            str(_resolve(config, "realm", default="agent-api")),
        )
    if mode == "api_key":
        return ApiKeyAuthenticationProvider(
            str(_resolve(config, "api_key_hash", required=True)),
            str(_resolve(config, "header", default="x-api-key")),
            str(_resolve(config, "principal", default="api-client")),
        )
    if mode == "bearer_static":
        return StaticBearerAuthenticationProvider(
            str(_resolve(config, "token_hash", required=True)),
            str(_resolve(config, "principal", default="bearer-client")),
        )
    if mode == "jwt":
        algorithms = _resolve(config, "algorithms", default=["RS256"])
        if isinstance(algorithms, str):
            algorithms = [item.strip() for item in algorithms.split(",") if item.strip()]
        return JwtAuthenticationProvider(
            str(_resolve(config, "key", required=True)),
            algorithms,
            _resolve(config, "audience"),
            _resolve(config, "issuer"),
        )
    if mode == "oauth2_introspection":
        return OAuth2IntrospectionAuthenticationProvider(
            str(_resolve(config, "introspection_url", required=True)),
            str(_resolve(config, "client_id", required=True)),
            str(_resolve(config, "client_secret", required=True)),
            float(_resolve(config, "timeout_seconds", default=5)),
        )
    if mode == "trusted_proxy":
        return TrustedProxyAuthenticationProvider(
            str(_resolve(config, "subject_header", default="x-authenticated-subject")),
            _resolve(config, "shared_secret_header"),
            _resolve(config, "shared_secret_hash"),
        )
    raise ValueError(f"Unsupported authentication mode: {mode}")


def env_provider_config(prefix: str = "AGENT_AUTH") -> dict[str, Any]:
    mode = os.getenv(f"{prefix}_MODE", "none").strip().lower()
    config: dict[str, Any] = {"mode": mode}
    if mode == "basic":
        config.update(client_id=_required_env(f"{prefix}_BASIC_CLIENT_ID"), secret_hash=_required_env(f"{prefix}_BASIC_SECRET_HASH"), realm=os.getenv(f"{prefix}_BASIC_REALM", "agent-api"))
    elif mode == "api_key":
        config.update(api_key_hash=_required_env(f"{prefix}_API_KEY_HASH"), header=os.getenv(f"{prefix}_API_KEY_HEADER", "x-api-key"), principal=os.getenv(f"{prefix}_API_KEY_PRINCIPAL", "api-client"))
    elif mode == "bearer_static":
        config.update(token_hash=_required_env(f"{prefix}_BEARER_TOKEN_HASH"), principal=os.getenv(f"{prefix}_BEARER_PRINCIPAL", "bearer-client"))
    elif mode == "jwt":
        config.update(key=_required_env(f"{prefix}_JWT_KEY"), algorithms=os.getenv(f"{prefix}_JWT_ALGORITHMS", "RS256"), audience=os.getenv(f"{prefix}_JWT_AUDIENCE") or None, issuer=os.getenv(f"{prefix}_JWT_ISSUER") or None)
    elif mode == "oauth2_introspection":
        config.update(introspection_url=_required_env(f"{prefix}_OAUTH2_INTROSPECTION_URL"), client_id=_required_env(f"{prefix}_OAUTH2_CLIENT_ID"), client_secret=_required_env(f"{prefix}_OAUTH2_CLIENT_SECRET"), timeout_seconds=float(os.getenv(f"{prefix}_OAUTH2_TIMEOUT_SECONDS", "5")))
    elif mode == "trusted_proxy":
        config.update(subject_header=os.getenv(f"{prefix}_PROXY_SUBJECT_HEADER", "x-authenticated-subject"), shared_secret_header=os.getenv(f"{prefix}_PROXY_SHARED_SECRET_HEADER") or None, shared_secret_hash=os.getenv(f"{prefix}_PROXY_SHARED_SECRET_HASH") or None)
    return config


def create_authentication_provider(prefix: str = "AGENT_AUTH"):
    return create_provider_from_config(env_provider_config(prefix))
