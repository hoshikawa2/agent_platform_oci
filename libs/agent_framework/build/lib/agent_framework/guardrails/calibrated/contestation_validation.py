"""Deprecated compatibility shim.

Business-specific contestation validation moved to the Contas agent. New agents
must keep equivalent policy in their own domain package.
"""
from __future__ import annotations
import warnings
warnings.warn("agent_framework.guardrails.calibrated.contestation_validation is deprecated; use the agent-owned domain validator", DeprecationWarning, stacklevel=2)
try:
    from app.domain.contas.contestation_validation import *  # compatibility for migrated Contas only
except ImportError as exc:
    raise ImportError("No domain contestation validator is installed. The generic framework does not provide TIM/Contas contestation policy.") from exc
