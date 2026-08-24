"""Deprecated lazy compatibility shim for agent-owned contestation validation.

The generic framework no longer contains TIM/Contas business policy.  The
legacy symbol remains importable so existing agents do not fail merely by
importing :mod:`agent_framework.guardrails.calibrated`.  Resolution of the
domain implementation is delayed until the function is actually invoked.
"""
from __future__ import annotations

import importlib
import warnings
from typing import Any


def _load_domain_validator():
    warnings.warn(
        "agent_framework.guardrails.calibrated.contestation_validation is "
        "deprecated; use the agent-owned domain validator",
        DeprecationWarning,
        stacklevel=3,
    )
    try:
        module = importlib.import_module("app.domain.contas.contestation_validation")
        validator = getattr(module, "validate_contestation_items")
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "No domain contestation validator is installed. The generic "
            "framework does not provide TIM/Contas contestation policy. "
            "Install/implement app.domain.contas.contestation_validation or "
            "call the agent-owned validator directly."
        ) from exc
    return validator


def validate_contestation_items(*args: Any, **kwargs: Any):
    """Invoke the legacy Contas validator lazily.

    Keeping this proxy import-safe preserves compatibility for older agents
    while avoiding any dependency from the framework startup on ``app.domain``.
    """
    return _load_domain_validator()(*args, **kwargs)


__all__ = ["validate_contestation_items"]
