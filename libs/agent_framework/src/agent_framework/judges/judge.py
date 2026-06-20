from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .calibrated.llm_client import CalibratedJudgeLLMClient

logger = logging.getLogger("agent_framework.judges")


class JudgeResult(BaseModel):
    name: str
    score: float
    passed: bool
    reason: str = ''
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResponseQualityJudge:
    """Legacy deterministic response-quality judge.

    Kept for backward compatibility when a YAML entry explicitly declares
    `type: deterministic`. The calibrated default for `response_quality` is
    now CalibratedResponseQualityJudge.
    """

    name = 'response_quality'

    def __init__(self, threshold: float = 0.7):
        self.threshold = _clamp_score(threshold, default=0.7)

    async def evaluate(self, question: str, answer: str, context: dict) -> JudgeResult:
        score = 1.0 if len(answer.strip()) > 20 else 0.2
        return JudgeResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            reason=f'Tamanho e completude básicos; threshold={self.threshold}',
            metadata={'threshold': self.threshold, 'mechanism': 'deterministic'},
        )


class GroundednessJudge:
    """Legacy deterministic groundedness judge.

    Kept for backward compatibility when a YAML entry explicitly declares
    `type: deterministic`. The calibrated default for `groundedness` is now
    CalibratedGroundednessJudge, which uses the ALUC calibrated prompt.
    """

    name = 'groundedness'

    def __init__(self, threshold: float = 0.6):
        self.threshold = _clamp_score(threshold, default=0.6)

    async def evaluate(self, question: str, answer: str, context: dict) -> JudgeResult:
        evidence = context.get('evidence', '')
        if evidence and any(w.lower() in answer.lower() for w in evidence.split()[:10]):
            score = 0.9
            return JudgeResult(
                name=self.name,
                score=score,
                passed=score >= self.threshold,
                reason=f'Resposta usa evidência; threshold={self.threshold}',
                metadata={'threshold': self.threshold, 'has_evidence': True, 'mechanism': 'deterministic'},
            )
        score = 0.6
        return JudgeResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            reason=f'Sem evidência configurada; aprovado com ressalva; threshold={self.threshold}',
            metadata={'threshold': self.threshold, 'has_evidence': False, 'mechanism': 'deterministic'},
        )


class CalibratedJudge:
    """Base class for calibrated LLM judges.

    Activation comes from judges.yaml. Model/provider/params come from
    llm_profiles.yaml through the configured profile, normally `judge`.
    There is no ENABLE_LLM_JUDGE gate.
    """

    name = 'calibrated_judge'
    task = 'RQLT'
    default_threshold = 0.7

    def __init__(
        self,
        llm: Any,
        *,
        threshold: float | int | str | None = None,
        profile_name: str = 'judge',
        fail_closed: bool = True,
        max_context_chars: int = 12000,
        fallback_on_block: bool = False,
        settings: Any | None = None,
    ):
        self.llm = _ensure_judge_llm(llm, settings=settings)
        self.threshold = _clamp_score(threshold, default=self.default_threshold)
        self.profile_name = profile_name or 'judge'
        self.fail_closed = bool(fail_closed)
        self.max_context_chars = int(max_context_chars or 12000)
        self.fallback_on_block = bool(fallback_on_block)
        self.client = CalibratedJudgeLLMClient(self.llm, default_profile=self.profile_name)

    async def evaluate(self, question: str, answer: str, context: dict) -> JudgeResult:
        if not self.llm:
            return JudgeResult(
                name=self.name,
                score=0.0 if self.fail_closed else 1.0,
                passed=not self.fail_closed,
                reason='Judge calibrado declarado em judges.yaml, mas nenhum LLM foi fornecido ao pipeline.' if self.fail_closed else 'Judge calibrado declarado em judges.yaml, mas nenhum LLM foi fornecido; seguindo fail-open.',
                metadata={
                    'profile_name': self.profile_name,
                    'task': self.task,
                    'mechanism': 'llm_judge_calibrated',
                    'skipped': True,
                    'missing_llm': True,
                },
            )

        payload = self._payload(question, answer, context or {})
        try:
            out = await self.client.classify(
                self.task,
                payload,
                profile_name=self.profile_name,
                component_name=f'judge.{self.name}',
                generation_name=f'llm.judge.{self.name}',
            )
            score = self._score(out)
            passed = self._passed(out, score)
            metadata = {
                'profile_name': self.profile_name,
                'task': self.task,
                'label': out.get('label'),
                'threshold': self.threshold,
                'mechanism': 'llm_judge_calibrated',
                'raw_llm_answer': out,
            }
            if not passed and self.fallback_on_block:
                metadata['fallback_text'] = await self._fallback(answer, context or {}, out)
            return JudgeResult(
                name=self.name,
                score=score,
                passed=passed,
                reason=str(out.get('reason') or f'Judge calibrado {self.task}'),
                metadata=metadata,
            )
        except Exception as exc:
            logger.exception('Calibrated judge failed name=%s task=%s profile=%s', self.name, self.task, self.profile_name)
            return JudgeResult(
                name=self.name,
                score=0.0 if self.fail_closed else 1.0,
                passed=not self.fail_closed,
                reason=f'Falha no judge calibrado {self.task}: {exc}' if self.fail_closed else f'Judge calibrado {self.task} indisponível; seguindo fail-open.',
                metadata={
                    'profile_name': self.profile_name,
                    'task': self.task,
                    'threshold': self.threshold,
                    'mechanism': 'llm_judge_calibrated',
                    'exception_type': exc.__class__.__name__,
                },
            )

    def _payload(self, question: str, answer: str, context: dict) -> dict[str, Any]:
        return {'question': question, 'answer': answer, 'context': _safe_context(context)}

    def _score(self, out: dict[str, Any]) -> float:
        # Calibrated prompts generally return 0-10. The framework keeps 0-1.
        raw = out.get('score')
        if raw is None:
            return 1.0 if _truthy(out.get('allowed'), True) else 0.0
        score = _clamp_score(raw, default=0.0)
        try:
            numeric = float(raw)
        except Exception:
            return score
        if numeric > 1.0:
            return max(0.0, min(1.0, numeric / 10.0))
        return score

    def _passed(self, out: dict[str, Any], score: float) -> bool:
        allowed = _truthy(out.get('allowed'), True)
        return allowed and score >= self.threshold

    async def _fallback(self, answer: str, context: dict, out: dict[str, Any]) -> str | None:
        try:
            fallback = await self.client.classify(
                'FALLBACK',
                {
                    'text': answer,
                    'context': context,
                    'judge_code': self.task,
                    'judge_reason': out.get('reason'),
                },
                profile_name=self.profile_name,
                component_name=f'judge.{self.name}.fallback',
                generation_name=f'llm.judge.{self.name}.fallback',
            )
            return str(fallback.get('reason') or '').strip() or None
        except Exception:
            logger.exception('Calibrated judge fallback failed name=%s task=%s', self.name, self.task)
            return None


class CalibratedResponseQualityJudge(CalibratedJudge):
    name = 'response_quality'
    task = 'RQLT'
    default_threshold = 0.7

    def _payload(self, question: str, answer: str, context: dict) -> dict[str, Any]:
        return {'pergunta': question, 'resposta': answer}


class CalibratedGroundednessJudge(CalibratedJudge):
    name = 'groundedness'
    task = 'ALUC'
    default_threshold = 0.6

    def _payload(self, question: str, answer: str, context: dict) -> dict[str, Any]:
        evidence = _extract_evidence(context)
        return {'resposta': answer, 'dados_reais': evidence}

    def _score(self, out: dict[str, Any]) -> float:
        if out.get('score') is not None:
            return super()._score(out)
        return 1.0 if _truthy(out.get('allowed'), True) else 0.0

    def _passed(self, out: dict[str, Any], score: float) -> bool:
        return _truthy(out.get('allowed'), True) and score >= self.threshold


class CalibratedSentimentJudge(CalibratedJudge):
    name = 'sentiment'
    task = 'CSI'
    default_threshold = 0.0

    def _payload(self, question: str, answer: str, context: dict) -> dict[str, Any]:
        return {'text': question}

    def _passed(self, out: dict[str, Any], score: float) -> bool:
        # CSI is diagnostic by default. It only fails when explicitly configured
        # with fail_on_negative=true in YAML.
        if not getattr(self, 'fail_on_negative', False):
            return True
        return str(out.get('sentimento') or '').strip().lower() != 'negativo'


class CalibratedToneJudge(CalibratedJudge):
    name = 'tone'
    task = 'VCTN'
    default_threshold = 0.0

    def _payload(self, question: str, answer: str, context: dict) -> dict[str, Any]:
        return {'text': answer}

    def _score(self, out: dict[str, Any]) -> float:
        if out.get('score') is not None:
            return super()._score(out)
        return 1.0 if _truthy(out.get('allowed'), True) else 0.0

    def _passed(self, out: dict[str, Any], score: float) -> bool:
        return _truthy(out.get('allowed'), True)


class LLMJudge(CalibratedJudge):
    """Generic LLM judge retained for `name: llm_judge` entries."""

    name = 'llm_judge'
    task = 'GENERIC'
    default_threshold = 0.7

    async def evaluate(self, question: str, answer: str, context: dict) -> JudgeResult:
        if not self.llm:
            return JudgeResult(
                name=self.name,
                score=0.0 if self.fail_closed else 1.0,
                passed=not self.fail_closed,
                reason='LLM judge declarado em judges.yaml, mas nenhum LLM foi fornecido ao pipeline.' if self.fail_closed else 'LLM judge declarado em judges.yaml, mas nenhum LLM foi fornecido; seguindo fail-open.',
                metadata={'profile_name': self.profile_name, 'skipped': True, 'missing_llm': True, 'mechanism': 'llm_judge'},
            )

        prompt = (
            'Você é um juiz de qualidade/groundedness de resposta. Responda SOMENTE JSON válido.\n'
            'Schema: {"score": number de 0 a 1, "passed": boolean, "reason": string}.\n\n'
            f'Pergunta:\n{question[:6000]}\n\n'
            f'Resposta:\n{answer[:10000]}\n\n'
            f'Contexto/evidência:\n{json.dumps(_safe_context(context), ensure_ascii=False)[: self.max_context_chars]}'
        )
        try:
            raw = await self.llm.ainvoke(
                [
                    {'role': 'system', 'content': 'Responda apenas JSON válido, sem markdown.'},
                    {'role': 'user', 'content': prompt},
                ],
                profile_name=self.profile_name,
                component_name=self.profile_name,
                generation_name=f"llm.{self.profile_name}",
            )
            data = _parse_json(raw)
            score = _clamp_score(data.get('score'), default=0.0)
            passed = bool(data.get('passed', score >= self.threshold))
            return JudgeResult(
                name=self.name,
                score=score,
                passed=passed,
                reason=str(data.get('reason') or 'Avaliação por LLM judge'),
                metadata={'profile_name': self.profile_name, 'raw_llm_answer': str(raw)[:1000], 'mechanism': 'llm_judge'},
            )
        except Exception as exc:
            logger.exception('LLM judge failed')
            return JudgeResult(
                name=self.name,
                score=0.0 if self.fail_closed else 1.0,
                passed=not self.fail_closed,
                reason=f'Falha no judge LLM: {exc}' if self.fail_closed else 'Judge LLM indisponível; seguindo fail-open.',
                metadata={'profile_name': self.profile_name, 'exception_type': exc.__class__.__name__, 'mechanism': 'llm_judge'},
            )


class JudgePipeline:
    """Build and run judges from judges.yaml.

    Source of truth:
    - ENABLE_JUDGES can disable the entire judge stage globally.
    - judges.yaml decides which judges exist, thresholds and fail-closed behavior.
    - llm_profiles.yaml decides model/provider/params through profile `judge`.
    - There is intentionally no ENABLE_LLM_JUDGE gate.

    The simple schema remains valid:

        judges:
          - name: response_quality
            enabled: true
            threshold: 0.7
          - name: groundedness
            enabled: true
            threshold: 0.6

    In this adapted version, those two names use the calibrated LLM prompts
    RQLT and ALUC by default. To force the old heuristic behavior, use
    `type: deterministic` on the entry.
    """

    def __init__(
        self,
        judges: list[Any] | None = None,
        *,
        llm: Any | None = None,
        config_path: str | None = None,
        settings: Any | None = None,
        enabled: bool | None = None,
    ):
        self.settings = settings
        self.enabled = _resolve_global_enabled(settings, enabled)
        self.config_path = _resolve_config_path(settings, config_path)
        self.config = _load_judges_config(self.config_path)
        self.llm = _ensure_judge_llm(llm, settings=settings) if self.enabled else llm
        self.judges = list(judges) if judges is not None else self._build_judges_from_config(self.llm)

    def _build_judges_from_config(self, llm: Any | None) -> list[Any]:
        if not self.enabled:
            return []

        if not self.config:
            return [
                CalibratedResponseQualityJudge(llm, threshold=0.7, profile_name='judge', fail_closed=True, settings=self.settings),
                CalibratedGroundednessJudge(llm, threshold=0.6, profile_name='judge', fail_closed=True, settings=self.settings),
            ]

        if not _truthy(self.config.get('enabled'), True):
            return []

        # Calibrated judges are LLM-based by default. If their configured model/provider fails,
        # the safe/default behavior must be fail-closed so a bad `judge` profile is
        # visible instead of silently passing. Users can explicitly set
        # fail_closed: false in judges.yaml to opt into fail-open.
        global_fail_closed = _truthy(self.config.get('fail_closed'), True)
        global_profile = str(self.config.get('profile') or 'judge')
        global_fallback = _truthy(self.config.get('fallback_on_block'), False)
        specs = _normalize_judge_specs(self.config)
        built: list[Any] = []
        for spec in specs:
            if not _truthy(spec.get('enabled'), True):
                continue
            code = str(spec.get('code') or spec.get('name') or '').strip().lower()
            judge_type = str(spec.get('type') or spec.get('mode') or '').strip().lower()
            profile = str(spec.get('profile') or spec.get('profile_name') or global_profile or 'judge')
            threshold = spec.get('threshold')
            fail_closed = _truthy(spec.get('fail_closed'), global_fail_closed)
            max_context_chars = int(spec.get('max_context_chars') or self.config.get('max_context_chars') or 12000)
            fallback_on_block = _truthy(spec.get('fallback_on_block'), global_fallback)

            if judge_type in {'deterministic', 'deterministic_quality'} and code in {'response_quality', 'quality'}:
                built.append(ResponseQualityJudge(threshold=threshold or 0.7))
            elif judge_type in {'deterministic', 'deterministic_groundedness'} and code == 'groundedness':
                built.append(GroundednessJudge(threshold=threshold or 0.6))
            elif code in {'response_quality', 'quality', 'rqlt'} or judge_type in {'response_quality', 'quality', 'rqlt', 'calibrated_quality'}:
                built.append(CalibratedResponseQualityJudge(llm, threshold=threshold or 0.7, profile_name=profile, fail_closed=fail_closed, max_context_chars=max_context_chars, fallback_on_block=fallback_on_block, settings=self.settings))
            elif code in {'groundedness', 'aluc', 'hallucination'} or judge_type in {'groundedness', 'aluc', 'hallucination', 'calibrated_groundedness'}:
                built.append(CalibratedGroundednessJudge(llm, threshold=threshold or 0.6, profile_name=profile, fail_closed=fail_closed, max_context_chars=max_context_chars, fallback_on_block=fallback_on_block, settings=self.settings))
            elif code in {'sentiment', 'csi'} or judge_type in {'sentiment', 'csi'}:
                judge = CalibratedSentimentJudge(llm, threshold=threshold or 0.0, profile_name=profile, fail_closed=fail_closed, max_context_chars=max_context_chars, fallback_on_block=fallback_on_block, settings=self.settings)
                judge.fail_on_negative = _truthy(spec.get('fail_on_negative'), False)
                built.append(judge)
            elif code in {'tone', 'voice_tone', 'vctn'} or judge_type in {'tone', 'voice_tone', 'vctn'}:
                built.append(CalibratedToneJudge(llm, threshold=threshold or 0.0, profile_name=profile, fail_closed=fail_closed, max_context_chars=max_context_chars, fallback_on_block=fallback_on_block, settings=self.settings))
            elif code in {'llm_judge', 'llm'} or judge_type in {'llm', 'llm_judge'}:
                built.append(LLMJudge(llm, threshold=threshold or 0.7, profile_name=profile, fail_closed=fail_closed, max_context_chars=max_context_chars, fallback_on_block=fallback_on_block, settings=self.settings))
            else:
                logger.warning('Ignoring unknown judge in %s: %s', self.config_path, spec)

        return built

    async def evaluate_all(self, question, answer, context):
        if not self.enabled or not self.judges:
            return []
        return [await j.evaluate(question, answer, context or {}) for j in self.judges]



class _JudgeLLMCreationErrorProxy:
    """Truthful proxy used when the framework LLM cannot be created.

    The object is intentionally truthy so calibrated judges do not report the
    misleading "no LLM was provided" message. Instead, the real configuration
    error is raised when the judge tries to invoke the model.
    """

    def __init__(self, exc: Exception):
        self.exc = exc
        self.model = None
        self.provider_name = None

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(f"Não foi possível criar o LLM do judge a partir das configurações do framework: {self.exc}") from self.exc


def _ensure_judge_llm(llm: Any | None, *, settings: Any | None = None) -> Any | None:
    """Return a framework LLM for calibrated judges.

    Several backends instantiate JudgePipeline without passing `llm`. Guardrails
    already recover from that by creating the framework provider from Settings;
    judges need the same behavior so `judges.yaml` + `llm_profiles.yaml` remains
    the source of truth.
    """
    if llm is not None:
        return llm
    try:
        from agent_framework.config.settings import get_settings
        from agent_framework.llm.providers import create_llm

        effective_settings = settings or get_settings()
        return create_llm(effective_settings)
    except Exception as exc:
        logger.exception("Could not create framework LLM for calibrated judges")
        return _JudgeLLMCreationErrorProxy(exc)

def _resolve_global_enabled(settings: Any | None, enabled: bool | None) -> bool:
    if enabled is not None:
        return bool(enabled)
    if settings is not None and hasattr(settings, 'ENABLE_JUDGES'):
        return bool(getattr(settings, 'ENABLE_JUDGES'))
    return True


def _resolve_config_path(settings: Any | None, config_path: str | None) -> str:
    if config_path:
        return config_path
    if settings is not None and getattr(settings, 'JUDGES_CONFIG_PATH', None):
        return str(getattr(settings, 'JUDGES_CONFIG_PATH'))
    return './config/judges.yaml'


def _load_judges_config(config_path: str | None) -> dict[str, Any]:
    if not config_path:
        return {}
    path = Path(config_path).expanduser()
    if not path.exists() or not path.is_file():
        logger.info('judges.yaml not found at %s; using calibrated default judges only', path)
        return {}
    with path.open('r', encoding='utf-8') as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f'Invalid judges config {path}: expected mapping')
    return data


def _normalize_judge_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get('judges')
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [dict({'code': code}, **value) for code, value in raw.items() if isinstance(value, dict)]

    specs: list[dict[str, Any]] = []
    for code, value in config.items():
        if code in {'enabled', 'fail_closed', 'max_context_chars', 'profile', 'fallback_on_block'}:
            continue
        if isinstance(value, dict):
            specs.append(dict({'code': code}, **value))
    return specs


def _extract_evidence(context: dict[str, Any]) -> str:
    if not context:
        return ''
    for key in ('evidence', 'dados_reais', 'tool_context', 'tool_results', 'rag_context', 'documents', 'context'):
        value = context.get(key)
        if value:
            if isinstance(value, str):
                return value[:12000]
            try:
                return json.dumps(value, ensure_ascii=False, default=str)[:12000]
            except Exception:
                return str(value)[:12000]
    try:
        return json.dumps(_safe_context(context), ensure_ascii=False, default=str)[:12000]
    except Exception:
        return str(context)[:12000]


def _clamp_score(value: Any, default: float) -> float:
    try:
        score = float(value)
    except Exception:
        return float(default)
    return max(0.0, min(1.0, score))


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'y'}


def _safe_context(context: dict[str, Any]) -> dict[str, Any]:
    safe = {}
    for key, value in (context or {}).items():
        if key.lower() in {'api_key', 'token', 'secret', 'password', 'senha'}:
            safe[key] = '***MASKED***'
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        else:
            safe[key] = str(value)[:1000]
    return safe


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
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('LLM judge returned non-object JSON')
    return data
