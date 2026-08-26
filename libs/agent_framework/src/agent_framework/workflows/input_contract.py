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
