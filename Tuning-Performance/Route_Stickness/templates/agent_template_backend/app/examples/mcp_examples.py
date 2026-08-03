"""Exemplos de MCP + IC.

O AgentRuntimeMixin já possui _collect_mcp_context(), mas este arquivo mostra o
padrão para chamadas explícitas ao tool_router quando necessário.
"""

from typing import Any


async def exemplo_chamada_mcp(tool_router: Any, observer: Any, state: dict[str, Any], tool_name: str, payload: dict[str, Any]) -> Any:
    session_id = state.get("conversation_key") or state.get("session_id")

    await observer.emit_ic(
        "IC.MCP_TOOL_CALLED",
        {
            "session_id": session_id,
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "tool_name": tool_name,
        },
        component="examples.mcp",
    )

    result = await tool_router.call(
        tool_name,
        payload,
        business_context=(state.get("context") or {}).get("business_context") or {},
        original_context=state.get("context") or {},
    )

    await observer.emit_ic(
        "IC.TOOL_CALLED",
        {
            "session_id": session_id,
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "tool_name": tool_name,
            "ok": getattr(result, "ok", None),
        },
        component="examples.mcp",
    )

    return result
