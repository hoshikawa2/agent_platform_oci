from __future__ import annotations

from typing import Any


def normalize_expected_input(text: str, expected_input: dict[str, Any] | None) -> str:
    """Normalize a workflow reply according to the declarative pause contract.

    The framework intentionally supports only explicit, deterministic normalizers.
    Unknown normalizers fall back to ``strip`` instead of guessing semantics.
    """
    rule = str((expected_input or {}).get("normalize") or "strip").strip().lower()
    value = str(text or "")
    if rule == "upper_strip":
        return value.strip().upper()
    if rule == "lower_strip":
        return value.strip().lower()
    return value.strip()


def match_expected_input(text: str, expected_input: dict[str, Any] | None) -> str | None:
    """Return the normalized value only when it satisfies the workflow contract.

    With no ``allowed_values`` the normalized value is accepted when non-empty.
    This keeps the capability generic for free-text pause contracts while making
    enumerated contracts (SIM/NAO, choices, etc.) deterministic.
    """
    if not isinstance(expected_input, dict):
        return None
    normalized = normalize_expected_input(text, expected_input)
    if not normalized:
        return None
    allowed = expected_input.get("allowed_values")
    if not allowed:
        return normalized
    allowed_normalized = {
        normalize_expected_input(str(item), expected_input)
        for item in allowed
        if item is not None
    }
    return normalized if normalized in allowed_normalized else None

def expected_input_reprompt(expected_input: dict[str, Any] | None, *, pause_prompt: str | None = None) -> str:
    """Return a user-facing retry prompt for an invalid paused-workflow reply.

    Domains may declare ``reprompt`` in the workflow contract.  When absent, the
    framework builds a neutral message from ``allowed_values`` without guessing
    domain semantics.
    """
    contract = expected_input if isinstance(expected_input, dict) else {}
    declared = str(contract.get("reprompt") or "").strip()
    if declared:
        return declared
    allowed = [str(x).strip() for x in (contract.get("allowed_values") or []) if str(x).strip()]
    if allowed:
        rendered = ", ".join(allowed)
        return f"Não entendi. Responda com uma das opções: {rendered}."
    prompt = str(pause_prompt or "").strip()
    if prompt:
        return f"Não entendi. {prompt}"
    return "Não entendi sua resposta. Por favor, tente novamente."

def has_semantic_classifier(expected_input: dict[str, Any] | None) -> bool:
    """Whether an enumerated contract opts in to agent-defined semantic classification."""
    if not isinstance(expected_input, dict) or not expected_input.get("allowed_values"):
        return False
    classifier = expected_input.get("semantic_classifier")
    return (
        isinstance(classifier, dict)
        and classifier.get("enabled", True) is not False
        and bool(str(classifier.get("prompt") or "").strip())
    )


def match_semantic_classifier_output(
    output: str, expected_input: dict[str, Any] | None
) -> str | None:
    """Validate classifier output strictly against dynamic ``allowed_values``.

    No option semantics live in the framework.  The returned value is the same
    normalized representation used by deterministic ``match_expected_input``.
    """
    if not isinstance(expected_input, dict):
        return None
    candidate = str(output or "").strip().strip("` \n\r\t\"'")
    if not candidate:
        return None
    allowed = expected_input.get("allowed_values") or []
    allowed_map = {
        normalize_expected_input(str(item), expected_input): normalize_expected_input(str(item), expected_input)
        for item in allowed
        if item is not None
    }
    normalized = normalize_expected_input(candidate, expected_input)
    return allowed_map.get(normalized)


def has_meaningful_unmatched_policy(expected_input: dict[str, Any] | None) -> bool:
    """Whether the contract explicitly opts in to semantic handling of unmatched text."""
    if not isinstance(expected_input, dict):
        return False
    unmatched = expected_input.get("unmatched")
    if not isinstance(unmatched, dict):
        return False
    meaningful = unmatched.get("meaningful_input")
    return (
        isinstance(meaningful, dict)
        and str(meaningful.get("action") or "").strip().lower() == "resume_as"
        and meaningful.get("value") is not None
    )


def meaningful_unmatched_resume_value(
    expected_input: dict[str, Any] | None,
    *,
    semantic_coherent: bool | None,
) -> str | None:
    """Resolve a configured ``resume_as`` value for coherent unmatched input.

    The framework never invents domain semantics here.  It only applies the
    value declared by the workflow after the coherence rail classified the
    free-text reply as meaningful.
    """
    if semantic_coherent is not True or not has_meaningful_unmatched_policy(expected_input):
        return None
    unmatched = expected_input.get("unmatched") or {}
    meaningful = unmatched.get("meaningful_input") or {}
    raw = meaningful.get("value")
    if raw is None:
        return None
    return normalize_expected_input(str(raw), expected_input)


def semantic_coherence_from_guardrails(state: dict[str, Any]) -> bool | None:
    """Read the non-blocking COER signal emitted for a paused workflow contract."""
    decisions = state.get("guardrail_decisions") or state.get("guardrails") or []
    if not isinstance(decisions, list):
        return None
    for decision in reversed(decisions):
        if hasattr(decision, "model_dump"):
            decision = decision.model_dump()
        if not isinstance(decision, dict) or str(decision.get("code") or "").upper() != "COER":
            continue
        metadata = decision.get("metadata") or {}
        if isinstance(metadata, dict) and isinstance(metadata.get("semantic_coherent"), bool):
            return metadata["semantic_coherent"]
        data = metadata.get("data") if isinstance(metadata, dict) else None
        if isinstance(data, dict) and isinstance(data.get("allowed"), bool):
            return data["allowed"]
    return None

