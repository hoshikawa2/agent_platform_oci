from __future__ import annotations

from functools import wraps
from typing import Any, Callable


def traced(name: str | None = None):
    """Decorator para métodos/classes que recebem self.telemetry."""
    def outer(fn: Callable):
        @wraps(fn)
        async def wrapper(self, *args, **kwargs):
            telemetry = getattr(self, "telemetry", None)
            span_name = name or f"{self.__class__.__name__}.{fn.__name__}"
            if telemetry is None:
                return await fn(self, *args, **kwargs)
            async with telemetry.span(span_name, input={"args": len(args), "kwargs": list(kwargs.keys())}):
                return await fn(self, *args, **kwargs)
        return wrapper
    return outer
