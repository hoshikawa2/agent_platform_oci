from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal


class IntentDefinition(BaseModel):
    """Definição configurável de uma intent roteável para um agente."""

    name: str
    description: str = ""
    agent: str
    keywords: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    priority: int = 100
    enabled: bool = True
    domain: str | None = None
    mcp_tools: list[str] = Field(default_factory=list)


class RouterStatePolicy(BaseModel):
    """Política de roteamento por estado conversacional.

    Exemplo: quando a sessão está aguardando confirmação, frases como "sim"
    não devem ser classificadas por keyword/LLM, pois dependem do estado anterior.
    """

    state: str
    agent: str
    description: str = ""
    terminal: bool = False


class RouteDecision(BaseModel):
    route: str
    agent: str
    intent: str
    confidence: float = 0.0
    reason: str = ""
    method: Literal["state", "keyword", "llm", "fallback"] = "fallback"
    next_state: str | None = None
    handoff: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    domain: str | None = None
    mcp_tools: list[str] = Field(default_factory=list)
