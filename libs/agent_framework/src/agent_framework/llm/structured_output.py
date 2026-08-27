"""Robust parsing helpers for structured LLM outputs.

LLMs do not always honor a strict JSON-only contract. In particular, a model
may wrap the payload in prose/markdown or emit a Python-literal-like mapping
using single quotes, ``True``/``False`` and ``None``. This module provides the
single normalization boundary for *LLM-originated* structured output.

It must not be used for persistence/configuration JSON, which should remain
strict.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any, TypeVar

T = TypeVar("T")


class StructuredOutputError(ValueError):
    """Raised when an LLM response cannot be parsed as the expected structure."""


def _response_text(raw: Any) -> str:
    """Best-effort extraction of textual content from common LLM response shapes."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (dict, list)):
        # Already structured: caller can pass it directly to parse_structured_output.
        return str(raw)
    content = getattr(raw, "content", None)
    if content is not None:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(str(part.get("text") or part.get("content") or ""))
                else:
                    parts.append(str(getattr(part, "text", part)))
            return "".join(parts)
        return str(content)
    return str(raw)


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    # Only strip an outer fence. Embedded fences are handled by structure extraction.
    match = re.fullmatch(
        r"```(?:json|javascript|python|py)?\s*(.*?)\s*```",
        stripped,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else stripped


def _balanced_candidates(text: str) -> list[str]:
    """Return balanced top-level object/array substrings, respecting quoted strings."""
    candidates: list[str] = []
    pairs = {"{": "}", "[": "]"}
    i = 0
    while i < len(text):
        opener = text[i]
        if opener not in pairs:
            i += 1
            continue

        stack: list[str] = [pairs[opener]]
        in_string = False
        quote = ""
        escaped = False
        j = i + 1
        while j < len(text):
            ch = text[j]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    in_string = False
                j += 1
                continue

            if ch in {"'", '"'}:
                in_string = True
                quote = ch
            elif ch in pairs:
                stack.append(pairs[ch])
            elif stack and ch == stack[-1]:
                stack.pop()
                if not stack:
                    candidates.append(text[i : j + 1])
                    i = j
                    break
            j += 1
        i += 1
    return candidates


def _parse_candidate(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Safe fallback for Python-literal-like model output, e.g.
    # {'decision': 'KEEP', 'confidence': 0.9, 'ok': True, 'reason': None}
    try:
        return ast.literal_eval(candidate)
    except (ValueError, SyntaxError) as exc:
        raise StructuredOutputError("candidate is neither valid JSON nor a safe Python literal") from exc


def parse_structured_output(
    raw: Any,
    *,
    expected_type: type[T] | tuple[type[Any], ...] | None = None,
) -> Any | T:
    """Parse structured output returned by an LLM.

    Accepted forms include:
    - strict JSON;
    - an already-materialized dict/list;
    - fenced JSON/Python literals;
    - prose before/after a balanced ``{...}`` or ``[...]`` payload;
    - Python-literal-style mappings using single quotes/True/False/None.

    ``eval`` is intentionally never used. ``ast.literal_eval`` is the final,
    safe syntax fallback.
    """
    if expected_type is not None and isinstance(raw, expected_type):
        return raw
    if isinstance(raw, (dict, list)):
        value: Any = raw
    else:
        text = _strip_markdown_fences(_response_text(raw))
        if not text:
            raise StructuredOutputError("LLM returned an empty structured response")

        try:
            value = _parse_candidate(text)
        except StructuredOutputError:
            value = None
            errors: list[str] = []
            for candidate in _balanced_candidates(text):
                try:
                    parsed = _parse_candidate(candidate)
                except StructuredOutputError as exc:
                    errors.append(str(exc))
                    continue
                if expected_type is None or isinstance(parsed, expected_type):
                    value = parsed
                    break
            if value is None:
                preview = text[:500].replace("\n", "\\n")
                raise StructuredOutputError(
                    f"Could not parse structured LLM response: {preview!r}"
                )

    if expected_type is not None and not isinstance(value, expected_type):
        if isinstance(expected_type, tuple):
            expected = ", ".join(t.__name__ for t in expected_type)
        else:
            expected = expected_type.__name__
        raise StructuredOutputError(
            f"Structured LLM response must be {expected}; got {type(value).__name__}"
        )
    return value


def parse_json_object(raw: Any) -> dict[str, Any]:
    """Convenience wrapper for the most common framework contract: a JSON object."""
    return parse_structured_output(raw, expected_type=dict)


__all__ = ["StructuredOutputError", "parse_structured_output", "parse_json_object"]
