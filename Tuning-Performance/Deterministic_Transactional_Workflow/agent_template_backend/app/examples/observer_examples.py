"""Resumo prático do Observer corporativo.

Use este arquivo como cola rápida para IC, NOC e GRL.
"""

from typing import Any


async def emitir_eventos_basicos(observer: Any, state: dict[str, Any]) -> None:
    session_id = state.get("conversation_key") or state.get("session_id")

    await observer.emit_ic(
        "IC.EXEMPLO_NEGOCIO",
        {"session_id": session_id, "agent_id": state.get("agent_id")},
        component="examples.observer",
    )

    await observer.emit_noc(
        "EXEMPLO_OPERACIONAL",
        {"session_id": session_id, "agent_id": state.get("agent_id")},
        component="examples.observer",
    )

    await observer.emit_grl(
        "OBSERVE",
        {"session_id": session_id, "agent_id": state.get("agent_id"), "rail_code": "CUSTOM"},
        component="examples.observer",
    )
