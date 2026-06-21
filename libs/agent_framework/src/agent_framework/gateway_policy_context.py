from __future__ import annotations

from typing import Any


def get_gateway_model_policy(state: dict[str, Any]) -> dict[str, Any] | None:
    metadata = state.get("metadata") or {}
    policy = metadata.get("model_policy")
    return policy if isinstance(policy, dict) else None


def apply_gateway_model_policy_to_llm_kwargs(
    state: dict[str, Any],
    fallback_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = get_gateway_model_policy(state)
    if not policy:
        return fallback_profile or {}

    params = dict(policy.get("parameters") or {})
    if policy.get("model"):
        params["model"] = policy["model"]
    if policy.get("provider"):
        params["provider"] = policy["provider"]
    if policy.get("profile"):
        params["profile"] = policy["profile"]
    return params
