from __future__ import annotations

import json
import logging
from typing import Any

from .base import Guardrail, RailDecision

logger = logging.getLogger("agent_framework.guardrails.llm")


class LLMGuardrailRail(Guardrail):
    """Optional LLM-based guardrail.

    This rail is intentionally fail-open by default because deterministic rails
    should remain responsible for hard blocks. When it calls the LLM, it always
    uses the `guardrail` inference profile, so llm_profiles.yaml can select a
    small/cheap model for this step.
    """

    code = "LLM_GUARDRAIL"
    stage = "input_output"

    def __init__(self, llm: Any, *, profile_name: str = "guardrail", fail_closed: bool = False):
        self.llm = llm
        self.profile_name = profile_name
        self.fail_closed = fail_closed

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        if not self.llm:
            return RailDecision(code=self.code, allowed=True, metadata={"skipped": "llm_not_configured"})

        stage = context.get("stage") or context.get("guardrail_stage") or self.stage
        prompt = (
            "Você é um guardrail corporativo. Avalie o texto e responda SOMENTE JSON válido.\n"
            "Schema: {\"allowed\": boolean, \"reason\": string, \"sanitized_text\": string|null, "
            "\"risk_level\": \"none|low|medium|high\", \"guidance\": string}.\n"
            "Regras: bloqueie apenas risco alto real; prefira sanitize/observe quando possível.\n\n"
            f"Stage: {stage}\n"
            f"Contexto: {json.dumps(_safe_context(context), ensure_ascii=False)[:4000]}\n"
            f"Texto:\n{text[:12000]}"
        )
        try:
            raw = await self.llm.ainvoke(
                [
                    {"role": "system", "content": "Responda apenas JSON válido, sem markdown."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=600,
                profile_name=self.profile_name,
                component_name=self.profile_name,
                generation_name=f"llm.{self.profile_name}",
            )
            data = _parse_json(raw)
            allowed = bool(data.get("allowed", True))
            sanitized = data.get("sanitized_text")
            if sanitized is not None:
                sanitized = str(sanitized)
            return RailDecision(
                code=self.code,
                allowed=allowed,
                reason=str(data.get("reason") or "Avaliação LLM guardrail"),
                sanitized_text=sanitized if sanitized and sanitized != text else None,
                metadata={
                    "profile_name": self.profile_name,
                    "risk_level": data.get("risk_level"),
                    "guidance": data.get("guidance"),
                    "raw_llm_answer": str(raw)[:1000],
                },
            )
        except Exception as exc:
            logger.exception("LLM guardrail failed")
            return RailDecision(
                code=self.code,
                allowed=not self.fail_closed,
                reason=f"Falha no guardrail LLM: {exc}" if self.fail_closed else "Guardrail LLM indisponível; seguindo fail-open.",
                metadata={"profile_name": self.profile_name, "exception_type": exc.__class__.__name__},
            )


class LLMOutputGRLRail(LLMGuardrailRail):
    """LLM guardrail specialized for GRL/output-supervisor decisions."""

    code = "LLM_GRL"
    stage = "output"

    def __init__(self, llm: Any, *, fail_closed: bool = False):
        super().__init__(llm, profile_name="grl", fail_closed=fail_closed)


def _safe_context(context: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in (context or {}).items():
        if key.lower() in {"api_key", "token", "secret", "password", "senha"}:
            safe[key] = "***MASKED***"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        else:
            safe[key] = str(value)[:500]
    return safe


def _parse_json(raw: Any) -> dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start:end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM guardrail returned non-object JSON")
    return data
