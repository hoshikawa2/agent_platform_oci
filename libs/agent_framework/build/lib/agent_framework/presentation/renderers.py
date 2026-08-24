from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Any, Protocol


class ToolResponseRenderer(Protocol):
    def __call__(
        self,
        *,
        tool_name: str,
        result: dict[str, Any],
        state: dict[str, Any],
        agent_label: str,
    ) -> str | None: ...


class ToolResponseRendererRegistry:
    """Thread-safe registry for application/domain response renderers.

    The framework stores only symbolic renderer names. Business-specific
    formatting lives in the application that registers the renderer.
    """

    def __init__(self) -> None:
        self._renderers: dict[str, ToolResponseRenderer] = {}
        self._lock = RLock()

    def register(
        self,
        name: str,
        renderer: ToolResponseRenderer,
        *,
        replace: bool = True,
    ) -> None:
        key = str(name or "").strip()
        if not key:
            raise ValueError("renderer name must not be empty")
        if not callable(renderer):
            raise TypeError("renderer must be callable")
        with self._lock:
            if not replace and key in self._renderers:
                raise KeyError(f"renderer already registered: {key}")
            self._renderers[key] = renderer

    def get(self, name: str | None) -> ToolResponseRenderer | None:
        key = str(name or "").strip()
        if not key:
            return None
        with self._lock:
            return self._renderers.get(key)

    def render(
        self,
        name: str | None,
        *,
        tool_name: str,
        result: dict[str, Any],
        state: dict[str, Any],
        agent_label: str,
    ) -> str | None:
        renderer = self.get(name)
        if renderer is None:
            return None
        value = renderer(
            tool_name=tool_name,
            result=result,
            state=state,
            agent_label=agent_label,
        )
        if value is None:
            return None
        text = str(value).strip()
        return text or None


tool_response_renderers = ToolResponseRendererRegistry()


def register_tool_response_renderer(
    name: str,
    renderer: ToolResponseRenderer,
    *,
    replace: bool = True,
) -> None:
    tool_response_renderers.register(name, renderer, replace=replace)


def render_tool_response(
    name: str | None,
    *,
    tool_name: str,
    result: dict[str, Any],
    state: dict[str, Any],
    agent_label: str,
) -> str | None:
    return tool_response_renderers.render(
        name,
        tool_name=tool_name,
        result=result,
        state=state,
        agent_label=agent_label,
    )
