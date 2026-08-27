from __future__ import annotations

import json
import logging
from typing import Any

from .prompts.aluc import build_aluc_prompt
from .prompts.csi import build_csi_prompt
from .prompts.fallback import build_fallback_prompt
from .prompts.rqlt import build_rqlt_prompt
from .prompts.vctn import build_vctn_prompt

logger = logging.getLogger('agent_framework.judges.calibrated')


class CalibratedJudgeLLMClient:
    """Adapter between the calibrated judge prompts and the framework LLM provider.

    The calibrated package originally created its own LangChain LLM. In this
    framework, LLM calls must go through the existing provider so that
    llm_profiles.yaml, Langfuse, token accounting and .env fallback keep working.
    """

    def __init__(self, llm: Any, *, default_profile: str = 'judge') -> None:
        self.llm = llm
        self.default_profile = default_profile or 'judge'

    async def classify(
        self,
        task: str,
        payload: dict[str, Any],
        *,
        profile_name: str | None = None,
        component_name: str | None = None,
        generation_name: str | None = None,
    ) -> dict[str, Any]:
        if not self.llm:
            raise RuntimeError('Calibrated judge requires an LLM provider from the framework')

        task = task.upper().strip()
        prompt = self._build_prompt(task, payload)
        profile = profile_name or self.default_profile
        component = component_name or f'judge.{task.lower()}'
        generation = generation_name or f'llm.{component}'

        raw = await self.llm.ainvoke(
            [
                {'role': 'system', 'content': 'Responda apenas JSON válido, sem markdown.'},
                {'role': 'user', 'content': prompt},
            ],
            profile_name=profile,
            component_name=component,
            generation_name=generation,
        )
        return _parse_json(raw)

    def _build_prompt(self, task: str, payload: dict[str, Any]) -> str:
        if task == 'CSI':
            return build_csi_prompt(str(payload.get('text') or ''))
        if task == 'VCTN':
            return build_vctn_prompt(str(payload.get('text') or ''))
        if task == 'ALUC':
            return build_aluc_prompt(
                str(payload.get('resposta') or payload.get('answer') or ''),
                payload.get('dados_reais') or payload.get('context') or '',
            )
        if task == 'RQLT':
            return build_rqlt_prompt(
                str(payload.get('pergunta') or payload.get('question') or ''),
                str(payload.get('resposta') or payload.get('answer') or ''),
            )
        if task == 'FALLBACK':
            return build_fallback_prompt(
                str(payload.get('text') or ''),
                guardrail_code=payload.get('guardrail_code') or payload.get('judge_code'),
                guardrail_reason=payload.get('guardrail_reason') or payload.get('judge_reason'),
                context=payload.get('context') if isinstance(payload.get('context'), dict) else None,
            )
        raise ValueError(f'Unsupported calibrated judge task: {task}')


def _parse_json(raw: Any) -> dict[str, Any]:
    text = str(raw or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:].strip()
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end >= start:
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except Exception as exc:
        raise ValueError(f'Calibrated judge returned invalid JSON: {str(raw)[:500]}') from exc
    if not isinstance(data, dict):
        raise ValueError('Calibrated judge returned non-object JSON')
    return data
