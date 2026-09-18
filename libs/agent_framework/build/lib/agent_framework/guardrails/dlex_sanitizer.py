"""Deterministic, framework-owned sanitization for DLEX_OUT.

The DLEX classifier decides whether a candidate response contains information
that must not be exposed.  When the finding is recoverable, this module masks
only the sensitive values so the response can be revalidated and preserved.

Rules are intentionally generic and live in the framework, never in domain
agents. Deployments may extend the built-ins without changing agent code via:

* ``GUARDRAIL_DLEX_OUT_EXTRA_MASKS_JSON`` (JSON list of rule objects), or
* the DLEX_OUT rail policy key ``sanitize_patterns`` in guardrails.yaml.

Each extension rule accepts ``name``, ``pattern`` and ``replacement``. Patterns
are regular expressions. Raw matched values are never returned in findings.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class DlexMaskRule:
    name: str
    pattern: str
    replacement: str
    flags: int = re.IGNORECASE


# Conservative defaults: values that are broadly unsafe to echo verbatim and
# can be redacted without changing the semantic meaning of an answer.
_BUILTIN_RULES: tuple[DlexMaskRule, ...] = (
    DlexMaskRule(
        "payment_barcode",
        # Brazilian boleto/payment representations normally contain 44, 47 or
        # 48 digits and may be formatted with dots/spaces. Keep the match on the
        # numeric token only so surrounding prose is preserved.
        r"(?<!\d)(?=[0-9.\-\s]{44,90}(?!\d))(?:\d[.\-\s]*){44,48}(?!\d)",
        "[CODIGO_DE_PAGAMENTO_OCULTADO]",
        flags=0,
    ),
    DlexMaskRule(
        "jwt",
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
        "[TOKEN_OCULTADO]",
        flags=0,
    ),
    DlexMaskRule(
        "openai_style_secret",
        r"\bsk-[A-Za-z0-9_-]{10,}\b",
        "[CREDENCIAL_OCULTADA]",
        flags=0,
    ),
    DlexMaskRule(
        "labelled_secret",
        r"(?i)\b(api[_ -]?key|secret|segredo|token|senha|password|credential|credencial)\b(\s*[:=]\s*)([^\s,;]+)",
        r"\1\2[DADO_PROTEGIDO]",
        flags=0,
    ),
    DlexMaskRule(
        "cpf",
        r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
        "[CPF_OCULTADO]",
        flags=0,
    ),
    DlexMaskRule(
        "cnpj",
        r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
        "[CNPJ_OCULTADO]",
        flags=0,
    ),
    DlexMaskRule(
        "email",
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[EMAIL_OCULTADO]",
    ),
    DlexMaskRule(
        "labelled_phone",
        r"(?i)\b(telefone|celular|whatsapp|msisdn)\b(\s*[:=]?\s*)(?:\+?55\s*)?(?:\(?\d{2}\)?[\s.-]*)?\d{4,5}[\s.-]*\d{4}\b",
        r"\1\2[TELEFONE_OCULTADO]",
        flags=0,
    ),
    DlexMaskRule(
        "uuid",
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b",
        "[IDENTIFICADOR_OCULTADO]",
        flags=0,
    ),
)


def _parse_rule(raw: Any) -> DlexMaskRule | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "custom").strip()
    pattern = str(raw.get("pattern") or "").strip()
    replacement = str(raw.get("replacement") or "[DADO_PROTEGIDO]")
    if not pattern:
        return None
    try:
        re.compile(pattern)
    except re.error:
        return None
    return DlexMaskRule(name=name, pattern=pattern, replacement=replacement, flags=0)


def _extra_rules_from_env() -> list[DlexMaskRule]:
    raw = os.getenv("GUARDRAIL_DLEX_OUT_EXTRA_MASKS_JSON", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    return [rule for item in (data or []) if (rule := _parse_rule(item)) is not None]


def _extra_rules_from_policy(policy: dict[str, Any] | None) -> list[DlexMaskRule]:
    data = dict(policy or {}).get("sanitize_patterns") or []
    if isinstance(data, dict):
        data = [data]
    return [rule for item in data if (rule := _parse_rule(item)) is not None]


def _mask_payment_sequences(text: str) -> tuple[str, int]:
    """Mask 44/47/48-digit payment tokens without consuming surrounding prose.

    Regex alone is awkward because formatted boletos have variable punctuation.
    We scan numeric/punctuation runs, count digits, and only redact the run when
    it has a canonical payment digit count.
    """
    token_re = re.compile(r"(?<!\d)\d(?:[.\-\s]*\d){43,47}(?!\d)")
    count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal count
        token = match.group(0)
        digits = re.sub(r"\D", "", token)
        if len(digits) in {44, 47, 48}:
            count += 1
            return "[CODIGO_DE_PAGAMENTO_OCULTADO]"
        return token

    return token_re.sub(repl, text), count


def sanitize_dlex_output(
    text: str,
    *,
    policy: dict[str, Any] | None = None,
    exclude_values: Iterable[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(sanitized_text, findings)`` without exposing raw matches.

    ``exclude_values`` contains explicitly authorized values (for example a
    workflow-generated protocol). They are temporarily protected so generic
    masking never alters them.
    """
    original = text or ""
    sanitized = original
    findings: list[dict[str, Any]] = []

    protected: dict[str, str] = {}
    for index, value in enumerate(exclude_values or []):
        value = str(value or "").strip()
        if not value or value not in sanitized:
            continue
        marker = f"__DLEX_AUTHORIZED_{index}__"
        sanitized = sanitized.replace(value, marker)
        protected[marker] = value

    # Payment sequences use digit-count validation rather than a plain rule.
    sanitized, payment_count = _mask_payment_sequences(sanitized)
    if payment_count:
        findings.append({"type": "payment_barcode", "action": "redact", "count": payment_count})

    rules = [r for r in _BUILTIN_RULES if r.name != "payment_barcode"]
    rules.extend(_extra_rules_from_env())
    rules.extend(_extra_rules_from_policy(policy))

    for rule in rules:
        try:
            regex = re.compile(rule.pattern, rule.flags)
        except re.error:
            continue
        sanitized, count = regex.subn(rule.replacement, sanitized)
        if count:
            findings.append({"type": rule.name, "action": "redact", "count": count})

    for marker, value in protected.items():
        sanitized = sanitized.replace(marker, value)

    return sanitized, findings


__all__ = ["DlexMaskRule", "sanitize_dlex_output"]
