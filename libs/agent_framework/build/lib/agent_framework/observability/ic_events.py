from __future__ import annotations

"""Constantes de Itens de Controle (IC) do framework.

ICs representam eventos de negócio/informacionais consumidos pela camada de
curadoria/analytics. Cada agente pode criar seu próprio catálogo, mas estes
códigos servem como contrato mínimo reutilizável.
"""

IC_AGENT_STARTED = "IC.AGENT_STARTED"
IC_AGENT_COMPLETED = "IC.AGENT_COMPLETED"
IC_TOOL_CALLED = "IC.TOOL_CALLED"
IC_MCP_TOOL_CALLED = "IC.MCP_TOOL_CALLED"
IC_ROUTE_SELECTED = "IC.ROUTE_SELECTED"
IC_HANDOFF_REQUESTED = "IC.HANDOFF_REQUESTED"

__all__ = [
    "IC_AGENT_STARTED",
    "IC_AGENT_COMPLETED",
    "IC_TOOL_CALLED",
    "IC_MCP_TOOL_CALLED",
    "IC_ROUTE_SELECTED",
    "IC_HANDOFF_REQUESTED",
]
