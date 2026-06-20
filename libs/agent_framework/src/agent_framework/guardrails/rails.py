"""Guardrails calibrados integrados à arquitetura atual do agent_framework.

Este módulo mantém a interface pública existente (`Guardrail.evaluate(text, context)`),
a execução paralela, fail-fast e emissão GRL do framework. A calibração de
regex, prompts e critérios foi importada do pacote anexado em
`guardrails/calibrated`.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

# Some calibrated rails use environment switches directly. Ensure .env is visible
# through os.getenv, not only through pydantic Settings.
load_dotenv(override=False)

from .base import Guardrail, RailDecision
from .calibrated.input_size import verificar_tamanho_input
from .calibrated.output_sanitization import mascarar_pii_output, sanitizar_toxicidade_output
from .calibrated.rules.pinj_patterns import _PINJ_PATTERNS, is_obvious_injection
from .calibrated.rules.tox_blocklist import _EXPLICIT_TERMS, _THREAT_PATTERNS, is_obvious_toxic
from .framework_llm_client import classify_with_framework_llm


def _lower(text: str) -> str:
    return (text or "").lower()


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _ctx(context: dict[str, Any] | None) -> dict[str, Any]:
    return dict(context or {})


def _session_id(context: dict[str, Any]) -> str:
    return str(context.get("session_id") or context.get("session_key") or "guardrail")


def _llm(context: dict[str, Any]) -> Any:
    return context.get("guardrail_llm") or context.get("llm") or context.get("model")


def _matched_pattern(patterns: list[Any] | tuple[Any, ...], text: str) -> str | None:
    for pattern in patterns:
        try:
            if pattern.search(text or ""):
                return getattr(pattern, "pattern", str(pattern))
        except AttributeError:
            if re.search(str(pattern), text or "", re.IGNORECASE):
                return str(pattern)
    return None


def _decision_from_calibrated(result: Any, *, fallback: str | None = None, sanitized_as_sanitize: bool = True) -> RailDecision:
    allowed = bool(getattr(result, "allowed", True))
    code = str(getattr(result, "code", None) or "UNKNOWN")
    sanitized = getattr(result, "sanitized_text", None)
    data = getattr(result, "data", None) or {}
    metadata = {
        "mechanism": getattr(result, "mechanism", None),
        "data": data,
        "calibrated": True,
    }
    if getattr(result, "timings_ms", None):
        metadata["timings_ms"] = getattr(result, "timings_ms")
    return RailDecision(
        code=code,
        allowed=allowed,
        reason=str(getattr(result, "reason", "") or ""),
        sanitized_text=sanitized if sanitized_as_sanitize and sanitized is not None else None,
        metadata={k: v for k, v in metadata.items() if v is not None},
    )


class PiiMaskRail(Guardrail):
    """MSK calibrado: mascara PII no input usando a implementação do pacote anexado."""

    code = "MSK"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        result = mascarar_pii_output(text or "", _ctx(context))
        decision = _decision_from_calibrated(result)
        decision.code = self.code
        return decision


class OutputPiiMaskRail(PiiMaskRail):
    """MSK também no output, mantendo o código MSK para busca consistente no Langfuse."""

    code = "MSK"
    stage = "output"


class MessageSizeRail(Guardrail):
    """INPUT_SIZE calibrado: limite defensivo por tokens estimados."""

    code = "INPUT_SIZE"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        result = verificar_tamanho_input(text or "", _ctx(context))
        return _decision_from_calibrated(result)


class PromptInjectionRail(Guardrail):
    """PINJ calibrado: first-pass determinístico + LLM de guardrail opcional."""

    code = "PINJ"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        if is_obvious_injection(text or ""):
            matched = _matched_pattern(_PINJ_PATTERNS, text or "")
            return RailDecision(
                code=self.code,
                allowed=False,
                reason=(
                    f"prompt injection/jailbreak detectado pelo padrão determinístico '{matched}'"
                    if matched
                    else "prompt injection/jailbreak detectado por regra determinística"
                ),
                sanitized_text=text,
                metadata={"mechanism": "deterministic", "matched_pattern": matched, "calibrated": True},
            )
        out = await classify_with_framework_llm(
            _llm(ctx),
            "PINJ",
            {"text": text or "", "context": ctx},
            profile_name="guardrail",
            component_name="guardrail.pinj",
            generation_name="guardrail.pinj",
        )
        allowed = bool(out.get("allowed", True))
        return RailDecision(
            code=self.code,
            allowed=allowed,
            reason=str(out.get("reason") or out.get("label") or "PINJ avaliado"),
            sanitized_text=text,
            metadata={"mechanism": "llm_rail", "data": out, "calibrated": True},
        )


class JailbreakRail(PromptInjectionRail):
    """Alias compatível: jailbreak é coberto pelo PINJ expandido calibrado."""

    code = "PINJ"
    stage = "input"


class ToxicityRail(Guardrail):
    """TOX calibrado: blocklist determinística + LLM leve quando habilitado."""

    code = "TOX"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        if is_obvious_toxic(text or ""):
            matched = _matched_pattern((_EXPLICIT_TERMS, _THREAT_PATTERNS), text or "")
            return RailDecision(
                code=self.code,
                allowed=False,
                reason=(
                    f"toxicidade óbvia detectada pelo padrão determinístico '{matched}'"
                    if matched
                    else "toxicidade óbvia detectada por blocklist determinística"
                ),
                sanitized_text=text,
                metadata={"mechanism": "deterministic", "matched_pattern": matched, "calibrated": True},
            )
        if not ctx.get("__guardrails_yaml_controlled") and not _truthy(os.getenv("GUARDRAIL_TOX_ENABLED"), False):
            return RailDecision(code=self.code, allowed=True, metadata={"skipped": "GUARDRAIL_TOX_ENABLED=false", "calibrated": True})
        out = await classify_with_framework_llm(
            _llm(ctx),
            "TOX",
            {"text": text or "", "context": ctx},
            profile_name="guardrail",
            component_name="guardrail.tox",
            generation_name="guardrail.tox",
        )
        return RailDecision(
            code=self.code,
            allowed=bool(out.get("allowed", True)),
            reason=str(out.get("reason") or out.get("label") or "TOX avaliado"),
            sanitized_text=text,
            metadata={"mechanism": "llm_rail", "data": out, "calibrated": True},
        )


class OutputToxicitySanitizationRail(Guardrail):
    """TOXOUT calibrado: sanitiza toxicidade no output sem hard-block."""

    code = "TOXOUT"
    stage = "output"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        result = sanitizar_toxicidade_output(text or "")
        sanitized = getattr(result, "sanitized_text", None)
        changed = sanitized is not None and sanitized != text
        return RailDecision(
            code=self.code,
            allowed=True,
            reason=str(getattr(result, "reason", "") or ("output sanitizado" if changed else "sem toxicidade no output")),
            sanitized_text=sanitized if changed else None,
            metadata={"mechanism": getattr(result, "mechanism", None), "data": getattr(result, "data", None), "calibrated": True},
        )


class OutOfScopeRail(Guardrail):
    """OOS calibrado: classificador LLM para escopo de contas/faturas TIM."""

    code = "OOS"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        out = await classify_with_framework_llm(
            _llm(ctx),
            "OOS",
            {"text": text or "", "context": ctx},
            profile_name="guardrail",
            component_name="guardrail.oos",
            generation_name="guardrail.oos",
        )
        return RailDecision(
            code=self.code,
            allowed=bool(out.get("allowed", True)),
            reason=str(out.get("reason") or out.get("label") or "OOS avaliado"),
            sanitized_text=text,
            metadata={"mechanism": "llm_supervisor", "data": out, "calibrated": True},
        )


class LoopRail(Guardrail):
    code = "VLOOP"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        normalized = _lower(text).strip()
        history = [_lower(h).strip() for h in _ctx(context).get("history_texts", [])[-6:]]
        repeated = history.count(normalized) >= 2 if normalized else False
        return RailDecision(
            code=self.code,
            allowed=not repeated,
            reason="Possível loop conversacional" if repeated else "",
            metadata={"history_window": len(history), "repeated": repeated, "mechanism": "deterministic"},
        )


class PrematureActionRail(Guardrail):
    """REVPREC calibrado: promessa operacional futura sem confirmação."""

    code = "REVPREC"
    stage = "output"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        out = await classify_with_framework_llm(
            _llm(ctx),
            "REVPREC",
            {"text": text or "", "context": ctx},
            profile_name="grl",
            component_name="guardrail.revprec",
            generation_name="guardrail.revprec",
        )
        return RailDecision(
            code=self.code,
            allowed=bool(out.get("allowed", True)),
            reason=str(out.get("reason") or out.get("label") or "REVPREC avaliado"),
            sanitized_text=text,
            metadata={"mechanism": "llm_rail", "data": out, "calibrated": True},
        )


class ProactiveOfferRail(Guardrail):
    """AOFERTA calibrado: bloqueia oferta proativa não solicitada no output."""

    code = "AOFERTA"
    stage = "output"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        out = await classify_with_framework_llm(
            _llm(ctx),
            "AOFERTA",
            {"text": text or "", "context": ctx},
            profile_name="grl",
            component_name="guardrail.aoferta",
            generation_name="guardrail.aoferta",
        )
        return RailDecision(
            code=self.code,
            allowed=bool(out.get("allowed", True)),
            reason=str(out.get("reason") or out.get("label") or "AOFERTA avaliado"),
            sanitized_text=text,
            metadata={"mechanism": "llm_supervisor", "data": out, "calibrated": True},
        )


class ComplianceRail(Guardrail):
    """CMP calibrado: protocolo obrigatório em fluxo de ajuste/ANATEL."""

    code = "CMP"
    stage = "output"

    _DIGIT_WORDS_RE = r"(?:zero|um|dois|tr[êe]s|quatro|cinco|seis|sete|oito|nove)"
    _SPOKEN_TOKEN_RE = rf"(?:{_DIGIT_WORDS_RE}|[a-z])"
    _SPOKEN_PROTOCOL_RE = rf"(?:{_SPOKEN_TOKEN_RE}\s+){{5,}}{_SPOKEN_TOKEN_RE}\b"
    _PROTOCOL_PATTERN = re.compile(
        r"(?i)\bprotocolo\b"
        r"[\s\S]{0,40}?"
        r"(?:"
        r"\d{6,}"
        r"|PRT-[A-Z0-9]{6,}"
        rf"|{_SPOKEN_PROTOCOL_RE}"
        r")"
    )
    _DIGIT_TO_WORD = {"0":"zero","1":"um","2":"dois","3":"três","4":"quatro","5":"cinco","6":"seis","7":"sete","8":"oito","9":"nove"}
    _LETTER_TO_WORD = {"a":"a","b":"bê","c":"cê","d":"dê","e":"e","f":"efe","g":"gê","h":"agá","i":"i","j":"jota","k":"ká","l":"ele","m":"eme","n":"ene","o":"o","p":"pê","q":"quê","r":"erre","s":"esse","t":"tê","u":"u","v":"vê","w":"dáblio","x":"xis","y":"ípsilon","z":"zê"}

    def _vocalize(self, value: str) -> str:
        tokens: list[str] = []
        for ch in str(value or "").lower():
            if ch in self._DIGIT_TO_WORD:
                tokens.append(self._DIGIT_TO_WORD[ch])
            elif ch in self._LETTER_TO_WORD:
                tokens.append(self._LETTER_TO_WORD[ch])
        return " ".join(tokens)

    def _apply_protocol_fallback(self, text: str, expected_protocols: list[str]) -> tuple[str, list[str]]:
        missing_spoken: list[str] = []
        for raw in expected_protocols:
            spoken = self._vocalize(raw)
            if spoken and spoken in text:
                continue
            if raw and raw in text:
                continue
            if spoken:
                missing_spoken.append(spoken)
        if not missing_spoken:
            return text, []
        suffix = " ".join(f"Seu número de protocolo é {s}." for s in missing_spoken)
        return f"{text.rstrip()} {suffix}".strip(), missing_spoken

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        requer = ctx.get("tipo_fluxo") == "ajuste" or ctx.get("requer_protocolo") is True
        if not requer:
            return RailDecision(code=self.code, allowed=True, sanitized_text=None, reason="Compliance Anatel não aplicável", metadata={"calibrated": True})
        expected = list(ctx.get("expected_protocols") or [])
        if self._PROTOCOL_PATTERN.search(text or ""):
            return RailDecision(code=self.code, allowed=True, reason="Resposta contém protocolo obrigatório", metadata={"calibrated": True})
        patched, missing = self._apply_protocol_fallback(text or "", expected)
        if patched != (text or ""):
            return RailDecision(
                code=self.code,
                allowed=True,
                reason="Resposta sem protocolo obrigatório; protocolo anexado deterministicamente",
                sanitized_text=patched,
                metadata={"missing_protocols_spoken": missing, "expected_protocols": expected, "mechanism": "deterministic", "calibrated": True},
            )
        return RailDecision(
            code=self.code,
            allowed=False,
            reason="Resposta de ajuste sem número de protocolo",
            sanitized_text=text,
            metadata={"expected_protocols": expected, "mechanism": "deterministic", "calibrated": True},
        )


class GroundednessRail(Guardrail):
    code = "GND"
    stage = "output"
    SPECIFICITY_HINTS = ["protocolo", "valor", "data", "fatura", "contrato", "cancelamento", "contestação", "rma"]

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        has_support = bool(ctx.get("evidence") or ctx.get("sources") or ctx.get("retrieval_count") or ctx.get("tool_result") or ctx.get("tool_executed"))
        is_specific = any(h in _lower(text) for h in self.SPECIFICITY_HINTS) or bool(re.search(r"\b\d+[,.]?\d*\b", text or ""))
        risk = "high" if is_specific and not has_support else "low"
        return RailDecision(code=self.code, allowed=True, metadata={"grounded": has_support or not is_specific, "risk": risk, "is_specific": is_specific})


class HallucinationRiskRail(Guardrail):
    code = "ALUC_RISK"
    stage = "output"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        support_count = int(bool(ctx.get("evidence"))) + int(bool(ctx.get("sources"))) + int(bool(ctx.get("tool_result")))
        uncertainty = any(term in _lower(text) for term in ["talvez", "provavelmente", "aparentemente", "não tenho certeza"])
        risk = "medium" if uncertainty and support_count == 0 else "low"
        if ctx.get("hallucination_risk") == "high":
            risk = "high"
        return RailDecision(code=self.code, allowed=True, metadata={"risk": risk, "support_count": support_count})


class RagSecurityRail(Guardrail):
    code = "RAGSEC"
    stage = "retrieval"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        out = await classify_with_framework_llm(_llm(ctx), "RAGSEC", {"text": text or "", "context": ctx}, profile_name="guardrail", component_name="guardrail.ragsec", generation_name="guardrail.ragsec")
        return RailDecision(code=self.code, allowed=bool(out.get("allowed", True)), reason=str(out.get("reason") or out.get("label") or "RAGSEC avaliado"), sanitized_text=text, metadata={"mechanism": "llm_rail", "data": out, "calibrated": True})


class DataLeakageInputRail(Guardrail):
    code = "DLEX_IN"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        if not ctx.get("__guardrails_yaml_controlled") and not _truthy(os.getenv("GUARDRAIL_DLEX_IN_ENABLED"), False):
            return RailDecision(code=self.code, allowed=True, metadata={"skipped": "covered_by_PINJ", "calibrated": True})
        out = await classify_with_framework_llm(_llm(ctx), "DLEX_IN", {"text": text or "", "context": ctx}, profile_name="guardrail", component_name="guardrail.dlex_in", generation_name="guardrail.dlex_in")
        return RailDecision(code=self.code, allowed=bool(out.get("allowed", True)), reason=str(out.get("reason") or out.get("label") or "DLEX_IN avaliado"), sanitized_text=text, metadata={"mechanism": "llm_rail", "data": out, "calibrated": True})


class DataLeakageOutputRail(Guardrail):
    code = "DLEX_OUT"
    stage = "output"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        if not ctx.get("__guardrails_yaml_controlled") and not _truthy(os.getenv("GUARDRAIL_DLEX_OUT_ENABLED"), False):
            return RailDecision(code=self.code, allowed=True, metadata={"skipped": "covered_by_OOS_and_MSK", "calibrated": True})
        out = await classify_with_framework_llm(_llm(ctx), "DLEX_OUT", {"text": text or "", "context": ctx}, profile_name="grl", component_name="guardrail.dlex_out", generation_name="guardrail.dlex_out")
        return RailDecision(code=self.code, allowed=bool(out.get("allowed", True)), reason=str(out.get("reason") or out.get("label") or "DLEX_OUT avaliado"), sanitized_text=text, metadata={"mechanism": "llm_rail", "data": out, "calibrated": True})


class RetrievalRelevanceRail(Guardrail):
    code = "RET_REL"
    stage = "retrieval"

    def __init__(self, min_score: float = 0.4):
        self.min_score = min_score

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        score = _ctx(context).get("score")
        allowed = score is None or float(score) >= self.min_score
        return RailDecision(code=self.code, allowed=allowed, reason="Chunk descartado por baixa relevância" if not allowed else "", metadata={"score": score, "min_score": self.min_score})


class ToolValidationRail(Guardrail):
    code = "TOOL_VAL"
    stage = "tool"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        tool_name = ctx.get("tool_name")
        args = ctx.get("tool_args") or {}
        required = ctx.get("required_args") or []
        missing = [name for name in required if args.get(name) in (None, "")]
        invalid_numeric = [name for name, value in args.items() if isinstance(value, (int, float, Decimal)) and name in {"valor", "amount", "quantity", "quantidade"} and value < 0]
        allowed_tools = ctx.get("allowed_tools")
        not_allowed = bool(allowed_tools and tool_name and tool_name not in allowed_tools)
        allowed = not missing and not invalid_numeric and not not_allowed
        return RailDecision(code=self.code, allowed=allowed, reason="Chamada de ferramenta inválida ou não permitida" if not allowed else "", metadata={"tool_name": tool_name, "missing_args": missing, "invalid_numeric_args": invalid_numeric, "not_allowed": not_allowed})


# Aliases compatíveis com nomes usados em documentações/códigos anteriores.
AOfertaRail = ProactiveOfferRail
RevprecRail = PrematureActionRail
RagsecRail = RagSecurityRail
DlexInRail = DataLeakageInputRail
DlexOutRail = DataLeakageOutputRail
