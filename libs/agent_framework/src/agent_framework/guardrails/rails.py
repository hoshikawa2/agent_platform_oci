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
from agent_framework.workflows.input_contract import has_meaningful_unmatched_policy, has_semantic_classifier


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


class CoherenceRail(Guardrail):
    """COER calibrado: fala do cliente incompreensível/negação ambígua."""
    code = "COER"
    stage = "input"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        transaction_status = str(ctx.get("transaction_status") or "").strip().upper()
        missing_parameters = [str(x) for x in (ctx.get("missing_parameters") or []) if str(x).strip()]
        if transaction_status == "COLLECTING_PARAMETERS" and missing_parameters:
            return RailDecision(
                code=self.code,
                allowed=True,
                reason="Coerência delegada ao contrato de parâmetros da transação ativa",
                sanitized_text=text,
                metadata={
                    "mechanism": "transaction_parameter_contract",
                    "calibrated": True,
                    "delegated": True,
                    "transaction_status": transaction_status,
                    "missing_parameters": missing_parameters,
                },
            )
        expected_input = ctx.get("expected_input")
        if isinstance(expected_input, dict) and expected_input.get("allowed_values"):
            # Backward-compatible default: enumerated contracts without an
            # explicit unmatched policy own coherence deterministically and
            # reprompt every value outside allowed_values.
            if has_semantic_classifier(expected_input):
                return RailDecision(
                    code=self.code,
                    allowed=True,
                    reason="Coerência e semântica delegadas ao semantic_classifier do expected_input",
                    sanitized_text=text,
                    metadata={
                        "mechanism": "expected_input_semantic_classifier",
                        "calibrated": True,
                        "delegated": True,
                    },
                )
            if not has_meaningful_unmatched_policy(expected_input):
                return RailDecision(
                    code=self.code,
                    allowed=True,
                    reason="Coerência delegada ao contrato expected_input do workflow pausado",
                    sanitized_text=text,
                    metadata={
                        "mechanism": "expected_input_contract",
                        "calibrated": True,
                        "delegated": True,
                    },
                )

            # Opt-in semantic unmatched handling: COER still classifies the
            # free-text reply, but does NOT block the graph.  Its underlying
            # signal is consumed by expected_input to choose reprompt vs the
            # workflow-declared meaningful_input action. Other safety rails
            # continue to execute and may block independently.
            out = await classify_with_framework_llm(
                _llm(ctx), "COER", {"text": text or "", "context": ctx},
                profile_name="guardrail", component_name="guardrail.coer", generation_name="guardrail.coer",
            )
            semantic_coherent = bool(out.get("allowed", True))
            return RailDecision(
                code=self.code,
                allowed=True,
                reason=(
                    "Entrada coerente; decisão delegada à política unmatched do expected_input"
                    if semantic_coherent
                    else "Entrada incoerente; decisão delegada ao reprompt do expected_input"
                ),
                sanitized_text=text,
                metadata={
                    "mechanism": "expected_input_contract",
                    "calibrated": True,
                    "delegated": True,
                    "semantic_coherent": semantic_coherent,
                    "data": out,
                },
            )
        out = await classify_with_framework_llm(
            _llm(ctx), "COER", {"text": text or "", "context": ctx},
            profile_name="guardrail", component_name="guardrail.coer", generation_name="guardrail.coer",
        )
        return RailDecision(
            code=self.code, allowed=bool(out.get("allowed", True)),
            reason=str(out.get("reason") or out.get("label") or "COER avaliado"),
            sanitized_text=text, metadata={"mechanism": "llm_rail", "data": out, "calibrated": True},
        )


class LoopRail(Guardrail):
    code = "VLOOP"
    stage = "input"

    @staticmethod
    def _transaction_status(ctx: dict[str, Any]) -> str:
        status = str(ctx.get("transaction_status") or "").strip().upper()
        if status:
            return status
        active_transaction = ctx.get("active_transaction")
        if isinstance(active_transaction, dict):
            return str(active_transaction.get("status") or "").strip().upper()
        return ""

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        transaction_status = self._transaction_status(ctx)

        # A short confirmation (for example ``sim``/``não``) may legitimately
        # appear several times in the same session because each transaction has
        # its own confirmation boundary. VLOOP protects against conversational
        # repetition; it must not consume the input that belongs to an active
        # transaction awaiting confirmation. The transaction runtime/classifier
        # remains responsible for deciding whether the utterance is actually a
        # valid confirm/reject response.
        if transaction_status == "AWAITING_CONFIRMATION":
            return RailDecision(
                code=self.code,
                allowed=True,
                reason="continuidade_transacional:AWAITING_CONFIRMATION",
                sanitized_text=text,
                metadata={
                    "history_window": len(list(ctx.get("history_texts") or [])[-6:]),
                    "repeated": False,
                    "mechanism": "deterministic_transaction_bypass",
                    "transaction_status": transaction_status,
                    "calibrated": True,
                },
            )

        normalized = _lower(text).strip()
        history = [_lower(h).strip() for h in ctx.get("history_texts", [])[-6:]]
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
            metadata={
                "mechanism": "llm_rail", "data": out, "calibrated": True,
                **({"terminal_action": "retry"} if not bool(out.get("allowed", True)) else {}),
            },
        )


class ProactiveOfferRail(Guardrail):
    """AOFERTA calibrado: bloqueia oferta proativa não solicitada no output.

    Estados transacionais determinísticos de continuidade não são uma nova
    oferta do agente. Quando o runtime já abriu uma transação e está apenas
    coletando parâmetros obrigatórios ou aguardando confirmação, AOFERTA deve
    permitir a mensagem sem consultar a LLM. Outros rails de saída (por exemplo
    FRASEOLOGIA) continuam sendo executados normalmente pelo pipeline.
    """

    code = "AOFERTA"
    stage = "output"
    _TRANSACTION_CONTINUATION_STATUSES = {
        "COLLECTING_PARAMETERS",
        "AWAITING_CONFIRMATION",
    }

    @classmethod
    def _transaction_continuation_status(cls, ctx: dict[str, Any]) -> str | None:
        status = str(ctx.get("transaction_status") or "").strip().upper()
        if status in cls._TRANSACTION_CONTINUATION_STATUSES:
            return status

        # Compatibilidade com callers que ainda só expõem o estado por meio
        # dos resultados das tools. O runtime transacional já grava o status
        # nesses resultados; não inferimos pelo texto da resposta.
        for result in reversed(list(ctx.get("mcp_results") or ctx.get("tool_result") or [])):
            if not isinstance(result, dict):
                continue
            result_status = str(result.get("transaction_status") or "").strip().upper()
            if result_status in cls._TRANSACTION_CONTINUATION_STATUSES:
                return result_status
        return None

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        continuation_status = self._transaction_continuation_status(ctx)
        if continuation_status:
            return RailDecision(
                code=self.code,
                allowed=True,
                reason=f"continuidade_transacional:{continuation_status}",
                sanitized_text=text,
                metadata={
                    "mechanism": "deterministic_transaction_bypass",
                    "transaction_status": continuation_status,
                    "calibrated": True,
                },
            )

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


class PhraseologyRail(Guardrail):
    """FRASEOLOGIA calibrado: bloqueia fraseados proibidos do agente."""
    code = "FRASEOLOGIA"
    stage = "output"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        out = await classify_with_framework_llm(
            _llm(ctx), "FRASEOLOGIA", {"text": text or "", "context": ctx},
            profile_name="grl", component_name="guardrail.fraseologia", generation_name="guardrail.fraseologia",
        )
        return RailDecision(
            code=self.code, allowed=bool(out.get("allowed", True)),
            reason=str(out.get("reason") or out.get("label") or "FRASEOLOGIA avaliado"),
            sanitized_text=text, metadata={
                "mechanism": "llm_rail", "data": out, "calibrated": True,
                "remediation": {
                    "type": "rewrite", "max_attempts": 1, "prompt_id": "FALLBACK",
                    "profile_name": "grl", "component_name": "guardrail.wording.rewrite",
                    "generation_name": "guardrail.wording.rewrite",
                },
            },
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

        original = text or ""
        expected = [str(value).strip() for value in (ctx.get("expected_protocols") or []) if str(value).strip()]

        # Quando o workflow informa os protocolos esperados, esses valores são a
        # fonte de verdade. Valide-os diretamente no texto (cru ou vocalizado)
        # antes de recorrer ao regex genérico. Isso evita tanto falso negativo
        # por distância/Markdown quanto falso positivo por um protocolo diferente.
        if expected:
            patched, missing = self._apply_protocol_fallback(original, expected)
            if not missing:
                return RailDecision(
                    code=self.code,
                    allowed=True,
                    reason="Resposta contém o(s) protocolo(s) esperado(s)",
                    sanitized_text=None,
                    metadata={
                        "expected_protocols": expected,
                        "protocol_validation": "expected_values",
                        "mechanism": "deterministic",
                        "calibrated": True,
                    },
                )

            return RailDecision(
                code=self.code,
                allowed=True,
                reason="Resposta sem protocolo obrigatório; protocolo anexado deterministicamente",
                sanitized_text=patched,
                metadata={
                    "missing_protocols_spoken": missing,
                    "expected_protocols": expected,
                    "protocol_validation": "expected_values",
                    "mechanism": "deterministic",
                    "calibrated": True,
                },
            )

        # Compatibilidade para fluxos legados que exigem protocolo, mas não
        # fornecem expected_protocols: nesse caso ainda usamos o reconhecimento
        # genérico por regex.
        if self._PROTOCOL_PATTERN.search(original):
            return RailDecision(
                code=self.code,
                allowed=True,
                reason="Resposta contém protocolo obrigatório",
                metadata={
                    "protocol_validation": "generic_regex",
                    "mechanism": "deterministic",
                    "calibrated": True,
                },
            )

        return RailDecision(
            code=self.code,
            allowed=False,
            reason="Resposta de ajuste sem número de protocolo",
            sanitized_text=text,
            metadata={
                "expected_protocols": expected,
                "protocol_validation": "generic_regex",
                "mechanism": "deterministic",
                "calibrated": True,
                "terminal_action": "retry",
            },
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


def _mask_authorized_protocol_values(value: Any, protocols: list[str]) -> Any:
    """Mask only protocol values explicitly authorized for the current turn.

    This function is used only to build the DLEX_OUT classifier payload. It does
    not mutate the runtime state or the user-visible response. Unrelated values
    remain untouched and therefore continue to be evaluated normally by DLEX.
    """

    if isinstance(value, str):
        masked = value
        for protocol in protocols:
            if protocol:
                masked = masked.replace(protocol, "<AUTHORIZED_PROTOCOL>")
        return masked
    if isinstance(value, dict):
        return {key: _mask_authorized_protocol_values(item, protocols) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_authorized_protocol_values(item, protocols) for item in value]
    if isinstance(value, tuple):
        return tuple(_mask_authorized_protocol_values(item, protocols) for item in value)
    return value


def _dlex_block_may_be_authorized_protocol(out: dict[str, Any]) -> bool:
    """Return True only when DLEX appears to object to the protocol itself.

    The recheck must not run for unrelated leakage (tokens, credentials,
    prompts, third-party data, etc.), because those violations remain blocking.
    """

    reason = str(out.get("reason") or out.get("label") or "").lower()
    protocol_terms = ("protocolo", "protocol", "identificador", "identifier")
    unrelated_terms = (
        "token", "secret", "segredo", "api key", "api_key", "chave",
        "senha", "password", "credencial", "credential", "prompt",
        "instrução interna", "instrucoes internas", "instruções internas",
        "terceiro", "third-party", "outro cliente",
    )
    return any(term in reason for term in protocol_terms) and not any(
        term in reason for term in unrelated_terms
    )


class DataLeakageOutputRail(Guardrail):
    code = "DLEX_OUT"
    stage = "output"

    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        ctx = _ctx(context)
        if not ctx.get("__guardrails_yaml_controlled") and not _truthy(os.getenv("GUARDRAIL_DLEX_OUT_ENABLED"), False):
            return RailDecision(code=self.code, allowed=True, metadata={"skipped": "covered_by_OOS_and_MSK", "calibrated": True})

        original_text = text or ""
        expected_protocols = [
            str(value).strip()
            for value in (ctx.get("expected_protocols") or [])
            if str(value).strip()
        ]
        matched_expected_protocols = [
            protocol for protocol in expected_protocols if protocol in original_text
        ]

        # Protocols explicitly produced/expected by the current workflow are
        # authorized output values. Mask only those exact values before DLEX
        # classification so that the LLM cannot mistake them for leaked internal
        # identifiers. Any other number/identifier remains visible to DLEX.
        classifier_text = original_text
        classifier_ctx: dict[str, Any] = ctx
        if matched_expected_protocols:
            classifier_text = _mask_authorized_protocol_values(
                original_text, matched_expected_protocols
            )
            classifier_ctx = _mask_authorized_protocol_values(
                ctx, matched_expected_protocols
            )

        out = await classify_with_framework_llm(
            _llm(ctx),
            "DLEX_OUT",
            {"text": classifier_text, "context": classifier_ctx},
            profile_name="grl",
            component_name="guardrail.dlex_out",
            generation_name="guardrail.dlex_out",
        )

        # A workflow-generated protocol listed in ``expected_protocols`` is an
        # explicitly authorized customer-facing value. Some LLM classifiers can
        # still reject the neutral placeholder merely because the surrounding
        # sentence contains the word "protocolo". When that happens, re-run the
        # classifier with the exact authorized value replaced by plain public
        # wording. This second pass preserves every other part of the response
        # (tokens, credentials, third-party data, internal instructions, etc.),
        # so unrelated leakage continues to be blocked. Only if the response is
        # safe without the authorized identifier do we override the false
        # positive from the first pass.
        protocol_authorization_verified = False
        protocol_recheck = None
        if (
            matched_expected_protocols
            and not bool(out.get("allowed", True))
            and _dlex_block_may_be_authorized_protocol(out)
        ):
            recheck_text = original_text
            recheck_ctx: dict[str, Any] = ctx
            for protocol in matched_expected_protocols:
                recheck_text = recheck_text.replace(
                    protocol, "referência pública autorizada para este cliente"
                )
            recheck_ctx = _mask_authorized_protocol_values(
                ctx, matched_expected_protocols
            )
            recheck_ctx = dict(recheck_ctx)
            recheck_ctx["authorized_customer_protocol"] = True
            recheck_ctx["authorization_rule"] = (
                "Protocolos presentes em expected_protocols foram produzidos "
                "pelo workflow atual e são autorizados para divulgação ao próprio cliente."
            )
            protocol_recheck = await classify_with_framework_llm(
                _llm(ctx),
                "DLEX_OUT",
                {"text": recheck_text, "context": recheck_ctx},
                profile_name="grl",
                component_name="guardrail.dlex_out.protocol_authorization_recheck",
                generation_name="guardrail.dlex_out.protocol_authorization_recheck",
            )
            if bool(protocol_recheck.get("allowed", True)):
                out = {
                    "allowed": True,
                    "label": "OK",
                    "reason": "protocolo esperado pelo workflow explicitamente autorizado",
                    "protocol_recheck": protocol_recheck,
                }
                protocol_authorization_verified = True

        metadata = {
            "mechanism": "llm_rail",
            "data": out,
            "calibrated": True,
        }
        if matched_expected_protocols:
            metadata.update(
                {
                    "protocol_authorization": "expected_values",
                    "authorized_protocols_masked": len(matched_expected_protocols),
                    "protocol_authorization_verified": protocol_authorization_verified,
                    "protocol_recheck": protocol_recheck,
                }
            )
        return RailDecision(
            code=self.code,
            allowed=bool(out.get("allowed", True)),
            reason=str(out.get("reason") or out.get("label") or "DLEX_OUT avaliado"),
            sanitized_text=text,
            metadata=metadata,
        )


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
