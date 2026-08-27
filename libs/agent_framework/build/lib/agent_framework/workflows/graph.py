"""LangGraph facade owned by agent_framework.

Applications should import graph primitives from here instead of importing
``langgraph.graph`` directly. This keeps LangGraph as an implementation detail
of the framework and gives us one place to evolve instrumentation/checkpointing.
"""
from __future__ import annotations

from typing import Any

START = "__start__"
END = "__end__"


class FrameworkStateGraph:
    def __new__(cls, state_schema: Any, *args: Any, **kwargs: Any):
        try:
            from langgraph.graph import StateGraph
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "langgraph não está instalado; instale as dependências do agent-framework"
            ) from exc
        return StateGraph(state_schema, *args, **kwargs)
