from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.config.governance_loader import load_gateway_governance_config
from app.governance.audit import audit_event
from app.governance.evaluation_hooks import EvaluationHooks
from app.governance.model_policies import ModelPolicyError, ModelPolicyResolver
from app.governance.rate_limit import InMemoryRateLimiter, RateLimitExceeded
from app.governance.usage import UsageRecorder


class AgentGatewayGovernance:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config if config is not None else load_gateway_governance_config()
        self.model_resolver = ModelPolicyResolver((self.config.get("model_governance") or {}))
        self.rate_limiter = InMemoryRateLimiter((self.config.get("rate_limits") or {}))
        self.usage = UsageRecorder()
        self.eval_hooks = EvaluationHooks()

    def prepare_backend_request(self, gateway_request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
        tenant_id = gateway_request.get("tenant_id") or "default"
        agent_id = gateway_request.get("agent_id")
        channel = gateway_request.get("channel")
        payload = gateway_request.get("payload") or {}
        metadata = payload.setdefault("metadata", {})

        try:
            self.rate_limiter.check(tenant_id=tenant_id, agent_id=agent_id, channel=channel)

            model_policy = self.model_resolver.resolve_profile(
                tenant_id=tenant_id,
                agent_id=agent_id,
                operation=metadata.get("operation") or "agent.final_answer",
                requested_profile=metadata.get("llm_profile"),
            )
            metadata["model_policy"] = model_policy

            headers = {
                "X-Agent-Gateway-Governance": "enabled",
                "X-Model-Profile": str(model_policy.get("profile") or ""),
                "X-Model-Provider": str(model_policy.get("provider") or ""),
                "X-Model-Name": str(model_policy.get("model") or ""),
            }

            audit_event("agent_gateway.request.governed", {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "channel": channel,
                "model_policy": model_policy,
                "request_id": metadata.get("request_id"),
                "message": payload.get("message"),
            })

            self.usage.record_gateway_request({
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "channel": channel,
                "metadata": metadata,
            })

            governed = self.eval_hooks.before_backend_call(gateway_request)
            return governed, headers

        except RateLimitExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except ModelPolicyError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    def process_backend_response(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        response_payload = self.eval_hooks.after_backend_call(response_payload)
        self.usage.record_backend_response(response_payload)
        audit_event("agent_gateway.response.completed", {
            "metadata": response_payload.get("metadata") if isinstance(response_payload, dict) else {},
        })
        return response_payload
