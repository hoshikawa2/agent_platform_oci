from __future__ import annotations

import re
from typing import Any


def _normalize(text: Any) -> str:
    """Same deterministic spirit as Agent Framework VLOOP: lower + strip.

    We also collapse whitespace because offline telemetry can contain line breaks,
    repeated spaces, or formatting differences from Langfuse observations.
    """
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def _message_role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or "").lower()
    return str(getattr(message, "role", "") or "").lower()


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def user_texts_from_record(record_or_raw: Any) -> list[str]:
    """Extract user/human texts from ConversationRecord or its JSON dict."""
    if isinstance(record_or_raw, dict):
        messages = record_or_raw.get("messages") or []
        input_text = record_or_raw.get("input_text") or ""
    else:
        messages = getattr(record_or_raw, "messages", []) or []
        input_text = getattr(record_or_raw, "input_text", "") or ""

    out: list[str] = []
    for message in messages:
        role = _message_role(message)
        if role in {"user", "human", "cliente", "customer"}:
            text = _normalize(_message_content(message))
            if text:
                out.append(text)

    # Ensure the canonical current user input participates even if messages were
    # reconstructed only from observations and missed the trace-level input.
    canonical = _normalize(input_text)
    if canonical and canonical not in out:
        out.append(canonical)
    return out


def detect_vloop(record_or_raw: Any, history_window: int = 6, min_previous_repetitions: int = 2) -> bool:
    """Offline equivalent of Agent Framework VLOOP.

    Framework logic:
        normalized = lower(text).strip()
        history = lower(history_texts)[-6:]
        repeated = history.count(normalized) >= 2

    Offline telemetry does not provide the exact guardrail context, so we rebuild
    it from user messages. The current user text is the last user message. The
    previous history is the prior messages in the same reconstructed trace/session.
    """
    texts = user_texts_from_record(record_or_raw)
    if not texts:
        return False

    current = texts[-1]
    if not current:
        return False

    history = texts[:-1][-history_window:]
    if history.count(current) >= min_previous_repetitions:
        return True

    # Defensive fallback: if the reconstructed messages do not preserve a clear
    # current turn, flag any user utterance repeated 3+ times in the recent window.
    recent = texts[-(history_window + 1):]
    return any(recent.count(t) >= (min_previous_repetitions + 1) for t in set(recent) if t)


def vloop_flag(record_or_raw: Any) -> int:
    return 1 if detect_vloop(record_or_raw) else 0
