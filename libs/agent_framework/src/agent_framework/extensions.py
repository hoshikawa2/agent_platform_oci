from __future__ import annotations

"""Extension SPI for agent-owned guardrails and judges.

The framework owns execution, telemetry and lifecycle. Agents may contribute
classes through YAML using ``type: external`` and ``class: module:Class``.
No agent/domain package is imported unless explicitly declared in configuration.
"""

from importlib import import_module
from typing import Any


def load_external_class(path: str) -> type[Any]:
    value = str(path or "").strip()
    if not value:
        raise ValueError("External component requires 'class: module:ClassName'")
    if ':' in value:
        module_name, class_name = value.rsplit(':', 1)
    elif '.' in value:
        module_name, class_name = value.rsplit('.', 1)
    else:
        raise ValueError(f"Invalid external class path: {value}")
    module = import_module(module_name)
    cls = getattr(module, class_name, None)
    if cls is None or not isinstance(cls, type):
        raise ValueError(f"External class not found: {value}")
    return cls


def instantiate_external(path: str, *, kwargs: dict[str, Any] | None = None, injected: dict[str, Any] | None = None) -> Any:
    cls = load_external_class(path)
    params = dict(kwargs or {})
    for key, value in (injected or {}).items():
        params.setdefault(key, value)
    try:
        return cls(**params)
    except TypeError:
        # Backward-friendly path for simple plugins with no constructor args.
        if params:
            obj = cls()
            for key, value in params.items():
                if not hasattr(obj, key):
                    continue
                setattr(obj, key, value)
            return obj
        raise
