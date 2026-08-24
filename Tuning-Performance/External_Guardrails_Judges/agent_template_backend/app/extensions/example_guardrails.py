from __future__ import annotations
from agent_framework.guardrails.base import Guardrail, RailDecision

class ExternalBusinessPolicyRail(Guardrail):
    code = "EXTERNAL_BUSINESS_POLICY"
    stage = "output"

    def evaluate(self, text, context):
        # Synchronous on purpose: framework executes this method in a worker thread.
        blocked = bool((context or {}).get("example_block"))
        return RailDecision(code=self.code, allowed=not blocked, reason="example business policy" if blocked else "", metadata={"external": True})
