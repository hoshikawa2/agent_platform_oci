from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv

# Keep os.getenv-based switches such as USE_MOCK_LLM aligned with .env.
load_dotenv(override=False)

from .calibrated.prompts._context import format_context_block
from .calibrated.prompts.ausencia_oferta_proativa import build_aoferta_prompt
from .calibrated.prompts.dlex_in import build_dlex_in_prompt
from .calibrated.prompts.dlex_out import build_dlex_out_prompt
from .calibrated.prompts.fallback import build_fallback_prompt
from .calibrated.prompts.out_of_scope import build_oos_prompt
from .calibrated.prompts.pinj import build_pinj_prompt
from .calibrated.prompts.ragsec import build_ragsec_prompt
from .calibrated.prompts.revprec import build_revprec_prompt
from .calibrated.prompts.tox import build_tox_prompt
from .calibrated.prompts.toxicidade_output import build_toxout_rewrite_prompt

_AOFERTA_TRIGGERS = (
    "quer aproveitar", "que tal tambem", "que tal também", "posso ja", "posso já",
    "ja que esta", "já que está", "aproveita e", "aproveite e", "tambem cancelar", "também cancelar",
)
_REVPREC_MARKERS = (
    "vou retirar o valor", "vou retirar a cobranca", "vou retirar a cobrança",
    "vou cancelar o servico", "vou cancelar o serviço", "vou cancelar a cobranca", "vou cancelar a cobrança",
    "vou devolver o valor", "vou retornar o valor", "sera devolvido para voce", "será devolvido para você",
    "já cancelei", "ja cancelei", "já contestei", "ja contestei", "ajuste realizado", "foi cancelado",
    "foi contestado", "foi ajustado", "foi removido", "reativação concluída", "reativacao concluida", "protocolo aberto",
)
_OOS_TRIGGERS = ("política", "politica", "religião", "religiao", "presidente", "concorrente", "vivo", "claro", "netflix", "futebol")
_TOX_PATTERNS = (
    r"\b(idiota|imbecil|burro|est[uú]pido|in[uú]til|maldito|miser[aá]vel|incompetente)\b",
    r"\b(filho da puta|fdp|vai se foder|vai tomar no cu)\b",
    r"\b(idiots?|stupid|useless|moron)\b",
)
_PINJ_PATTERNS = (
    r"ignore (all )?(previous|prior) instructions",
    r"ignore todas as instru[cç][oõ]es",
    r"esque[cç]a (as|todas as) regras",
    r"reveal (the )?(system prompt|hidden prompt|instructions)",
    r"mostre (o )?(prompt|system prompt|prompt oculto|instru[cç][oõ]es internas)",
    r"developer message",
    r"system message",
    r"modo desenvolvedor",
    r"bypass",
    r"DAN\b",
)


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _extract_text(raw: Any) -> str:
    if hasattr(raw, "content"):
        raw = getattr(raw, "content")
    if isinstance(raw, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw).strip()
    return str(raw or "").strip()


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text or "")
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {"allowed": False, "label": "ERROR", "reason": (text or "")[:500]}


def _first_substring_match(text: str, triggers: tuple[str, ...]) -> str | None:
    for trigger in triggers:
        if trigger and trigger in text:
            return trigger
    return None


def _first_regex_match(raw: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        if re.search(pattern, raw, re.IGNORECASE):
            return pattern
    return None


def _mock_classify(task: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fallback local para desenvolvimento/testes sem LLM real.

    Mesmo quando USE_MOCK_LLM=true, o retorno não deve aparecer no GRL como
    "mock <rail> calibrado". O framework precisa registrar a razão de negócio
    que levou à decisão: qual marcador, padrão ou ausência de indício foi usado.
    """
    raw = payload.get("text") or ""
    text = raw.lower()

    if task == "AOFERTA":
        trigger = _first_substring_match(text, _AOFERTA_TRIGGERS)
        blocked = trigger is not None
        return {
            "allowed": not blocked,
            "label": "OFERTA_PROATIVA_INDEVIDA" if blocked else "OFERTA_OK",
            "reason": (
                f"oferta proativa detectada pelo marcador '{trigger}'"
                if blocked
                else "não há oferta proativa não solicitada no trecho avaliado"
            ),
            "score": 0 if blocked else 10,
            "detector": "local_fallback",
            "matched": trigger,
        }

    if task == "REVPREC":
        marker = _first_substring_match(text, _REVPREC_MARKERS)
        blocked = marker is not None
        return {
            "allowed": not blocked,
            "label": "PREMATURA" if blocked else "OK",
            "reason": (
                f"verbalização prematura detectada pelo marcador '{marker}' antes de confirmação/evidência operacional"
                if blocked
                else "não há promessa de execução operacional antes de confirmação ou evidência"
            ),
            "score": 0 if blocked else 10,
            "detector": "local_fallback",
            "matched": marker,
        }

    if task == "OOS":
        trigger = _first_substring_match(text, _OOS_TRIGGERS)
        blocked = trigger is not None
        return {
            "allowed": not blocked,
            "label": "OUT_OF_SCOPE" if blocked else "IN_SCOPE",
            "reason": (
                f"tema fora do escopo de contas/faturas TIM detectado pelo marcador '{trigger}'"
                if blocked
                else "mensagem permanece dentro do escopo esperado de atendimento"
            ),
            "score": 0 if blocked else 10,
            "detector": "local_fallback",
            "matched": trigger,
        }

    if task == "TOXOUT":
        cleaned = raw
        matched: list[str] = []
        for pattern in _TOX_PATTERNS:
            if re.search(pattern, cleaned, flags=re.IGNORECASE):
                matched.append(pattern)
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return {
            "text": " ".join(cleaned.split()),
            "reason": (
                "toxicidade removida do output por blocklist local"
                if matched
                else "nenhuma toxicidade encontrada no output"
            ),
            "detector": "local_fallback",
            "matched": matched,
        }

    if task == "TOX":
        pattern = _first_regex_match(raw, _TOX_PATTERNS)
        blocked = pattern is not None
        return {
            "allowed": not blocked,
            "label": "TOXICO" if blocked else "NORMAL",
            "reason": (
                f"toxicidade direta detectada por padrão '{pattern}'"
                if blocked
                else "não há ofensa, ameaça ou toxicidade direta no texto avaliado"
            ),
            "score": 0 if blocked else 10,
            "detector": "local_fallback",
            "matched": pattern,
        }

    if task == "PINJ":
        pattern = _first_regex_match(raw, _PINJ_PATTERNS)
        blocked = pattern is not None
        return {
            "allowed": not blocked,
            "label": "PROMPT_INJECTION" if blocked else "OK",
            "reason": (
                f"prompt injection/jailbreak detectado por padrão '{pattern}'"
                if blocked
                else "não há tentativa de sobrescrever instruções, extrair prompt ou burlar políticas"
            ),
            "score": 0 if blocked else 10,
            "detector": "local_fallback",
            "matched": pattern,
        }

    if task == "RAGSEC":
        patterns = (
            r"ignore (all )?(previous|prior) instructions",
            r"ignore todas as instru[cç][oõ]es",
            r"desconsidere (o|a|as) (contexto|instru[cç][oõ]es|regras)",
            r"use este contexto para revelar",
            r"system prompt",
            r"prompt oculto",
        )
        pattern = _first_regex_match(raw, patterns)
        blocked = pattern is not None
        return {
            "allowed": not blocked,
            "label": "RAGSEC" if blocked else "OK",
            "reason": (
                f"possível injeção/poisoning no contexto RAG detectado por padrão '{pattern}'"
                if blocked
                else "contexto recuperado não contém instrução de override ou tentativa de poisoning"
            ),
            "score": 0 if blocked else 10,
            "detector": "local_fallback",
            "matched": pattern,
        }

    if task == "DLEX_IN":
        patterns = (
            r"(mostre|revele|exiba).*(senha|token|apikey|api key|secret|credencial)",
            r"(system prompt|developer message|instru[cç][oõ]es internas)",
            r"(cpf|cnpj|cart[aã]o|senha).*(de outro cliente|de terceiros)",
        )
        pattern = _first_regex_match(raw, patterns)
        blocked = pattern is not None
        return {
            "allowed": not blocked,
            "label": "DLEX_IN" if blocked else "OK",
            "reason": (
                f"pedido de exposição de dado sensível detectado por padrão '{pattern}'"
                if blocked
                else "input não solicita exposição de segredo, credencial ou dado pessoal de terceiros"
            ),
            "score": 0 if blocked else 10,
            "detector": "local_fallback",
            "matched": pattern,
        }

    if task == "DLEX_OUT":
        patterns = (
            r"sk-[A-Za-z0-9_-]{10,}",
            r"(?i)(api[_ -]?key|secret|token|senha)\s*[:=]\s*[^\s]+",
            r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
            r"\b\d{16}\b",
        )
        pattern = _first_regex_match(raw, patterns)
        blocked = pattern is not None
        return {
            "allowed": not blocked,
            "label": "DLEX_OUT" if blocked else "OK",
            "reason": (
                f"saída contém possível vazamento de dado sensível por padrão '{pattern}'"
                if blocked
                else "output não contém segredo, credencial ou identificador sensível aparente"
            ),
            "score": 0 if blocked else 10,
            "detector": "local_fallback",
            "matched": pattern,
        }

    return {
        "allowed": True,
        "label": "OK",
        "reason": f"{task} sem indício de violação no fallback local",
        "score": 5,
        "detector": "local_fallback",
    }


def _build_prompt(task: str, text: str, context: dict[str, Any]) -> str:
    context_str = format_context_block(context or {})
    if task == "AOFERTA":
        return build_aoferta_prompt(text, context_str)
    if task == "REVPREC":
        return build_revprec_prompt(text, context_str)
    if task == "OOS":
        return build_oos_prompt(text, context_str)
    if task == "TOXOUT":
        return build_toxout_rewrite_prompt(text)
    if task == "TOX":
        return build_tox_prompt(text)
    if task == "PINJ":
        return build_pinj_prompt(text, context_str)
    if task == "RAGSEC":
        return build_ragsec_prompt(text, context_str)
    if task == "DLEX_IN":
        return build_dlex_in_prompt(text)
    if task == "DLEX_OUT":
        return build_dlex_out_prompt(text, context_str)
    if task == "FALLBACK":
        return build_fallback_prompt(text, guardrail_code=context.get("guardrail_code"), guardrail_reason=context.get("guardrail_reason"), context=context)
    raise ValueError(f"Task não suportada: {task}")




def _selected_profile_for_task(task: str, profile_name: str | None = None) -> str:
    return profile_name or ("grl" if task in {"AOFERTA", "REVPREC", "DLEX_OUT"} else "guardrail")


def _profile_forces_real_llm(llm: Any, selected_profile: str) -> bool:
    """Return True when llm_profiles.yaml explicitly routes this profile to a real provider.

    This is intentionally stronger than USE_MOCK_LLM. In this framework,
    llm_profiles.yaml is the per-inference contract. Therefore, if the
    guardrail/grl profile is present and provider != mock, the guardrail must
    call the configured model. This makes wrong model names fail visibly instead
    of silently falling back to local mock heuristics.
    """
    resolver = getattr(llm, "profile_resolver", None)
    if resolver is None or not getattr(resolver, "enabled", False):
        return False
    try:
        effective = resolver.resolve(selected_profile)
    except Exception:
        return False
    provider = str(effective.get("provider") or "").strip().lower()
    profile_found = bool(effective.get("profile_found"))
    return profile_found and provider not in {"", "mock"}


def _ensure_framework_llm(llm: Any) -> Any:
    """Use the framework LLM if provided; otherwise create one from Settings.

    The previous adapter returned local mock whenever `llm` was None. That made
    the guardrails ignore llm_profiles.yaml in boot paths where the pipeline was
    instantiated without an explicit llm. Creating the framework provider here
    keeps the architecture centralized and still uses the same profile resolver,
    telemetry-capable provider class, .env, and llm_profiles.yaml.
    """
    if llm is not None:
        return llm
    try:
        from agent_framework.config.settings import get_settings
        from agent_framework.llm.providers import create_llm

        return create_llm(get_settings())
    except Exception:
        return None

async def classify_with_framework_llm(
    llm: Any,
    task: str,
    payload: dict[str, Any],
    *,
    profile_name: str | None = None,
    component_name: str | None = None,
    generation_name: str | None = None,
) -> dict[str, Any]:
    """Classifica guardrail usando os prompts calibrados e o LLM do framework.

    Mantém a telemetria/modelo no Langfuse porque chama `llm.ainvoke` com
    `profile_name`, `component_name` e `generation_name`, em vez de criar um
    cliente LLM paralelo fora da arquitetura do framework.
    """
    selected_profile = _selected_profile_for_task(task, profile_name)
    llm = _ensure_framework_llm(llm)

    # USE_MOCK_LLM remains useful for local development, but it must not hide an
    # explicit real provider configured in llm_profiles.yaml for guardrail/grl.
    # With profiles.guardrail.model = xopenai.gpt-4.1, this path now calls the
    # provider and surfaces the bad model/provider error instead of returning a
    # local fallback result.
    force_real_from_profile = _profile_forces_real_llm(llm, selected_profile) if llm is not None else False
    if (llm is None) or (_truthy(os.getenv("USE_MOCK_LLM"), True) and not force_real_from_profile):
        out = _mock_classify(task, payload)
        out.setdefault("profile_name", selected_profile)
        out.setdefault("profile_forced_real_llm", False)
        return out

    text = payload.get("text") or ""
    context = payload.get("context") or {}
    prompt = _build_prompt(task, text, context)
    selected_component = component_name or f"guardrail.{task.lower()}"
    selected_generation = generation_name or f"guardrail.{task.lower()}"
    raw = await llm.ainvoke(
        [
            {"role": "system", "content": "Responda apenas JSON válido, sem markdown."},
            {"role": "user", "content": prompt},
        ],
        profile_name=selected_profile,
        component_name=selected_component,
        generation_name=selected_generation,
    )
    output = _extract_text(raw)
    if task == "TOXOUT":
        return {"text": output}
    return _parse_json(output)
