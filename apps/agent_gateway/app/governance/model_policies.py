from __future__ import annotations

from typing import Any


class ModelPolicyError(RuntimeError):
    pass


class ModelPolicyResolver:
    def __init__(self, config: dict[str, Any]):
        self.config = config or {}

    def resolve_profile(
        self,
        *,
        tenant_id: str,
        agent_id: str | None,
        operation: str,
        requested_profile: str | None = None,
    ) -> dict[str, Any]:
        profiles = self.config.get("profiles", {}) or {}
        operation_profiles = self.config.get("operation_profiles", {}) or {}

        profile_name = requested_profile or operation_profiles.get(operation) or "default"
        profile = profiles.get(profile_name)
        if not profile:
            raise ModelPolicyError(f"Model profile not found: {profile_name}")

        self._validate_policy(
            tenant_id=tenant_id,
            agent_id=agent_id,
            profile_name=profile_name,
            profile=profile,
        )

        return {
            "profile": profile_name,
            "provider": profile.get("provider"),
            "model": profile.get("model"),
            "parameters": {
                k: v for k, v in profile.items()
                if k not in {"provider", "model"}
            },
        }

    def _validate_policy(
        self,
        *,
        tenant_id: str,
        agent_id: str | None,
        profile_name: str,
        profile: dict[str, Any],
    ) -> None:
        policies = self.config.get("policies", {}) or {}
        tenant_policies = policies.get("tenants", {}) or {}
        tenant_policy = tenant_policies.get(tenant_id) or tenant_policies.get("default") or {}

        allowed_profiles = tenant_policy.get("allowed_profiles")
        if allowed_profiles and profile_name not in allowed_profiles:
            raise ModelPolicyError(f"Profile not allowed for tenant={tenant_id}: {profile_name}")

        allowed_providers = tenant_policy.get("allowed_providers")
        provider = profile.get("provider")
        if allowed_providers and provider not in allowed_providers:
            raise ModelPolicyError(f"Provider not allowed for tenant={tenant_id}: {provider}")
