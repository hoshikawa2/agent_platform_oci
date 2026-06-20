"""Exemplos de GRL.

GRL representa eventos de guardrails. Em regra, GRL.001..GRL.009 são emitidos
pelo pipeline de guardrails e pelo OutputSupervisor do framework. Use emissão
manual apenas para validações customizadas do agente.
"""

from typing import Any


async def exemplo_guardrail_observado(observer: Any, state: dict[str, Any], rail_code: str, reason: str) -> None:
    await observer.emit_grl(
        "OBSERVE",
        {
            "session_id": state.get("conversation_key") or state.get("session_id"),
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "rail_code": rail_code,
            "reason": reason,
        },
        component="examples.grl",
    )


async def exemplo_guardrail_block(observer: Any, state: dict[str, Any], rail_code: str, reason: str) -> None:
    await observer.emit_grl(
        "004",
        {
            "session_id": state.get("conversation_key") or state.get("session_id"),
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "rail_code": rail_code,
            "reason": reason,
            "action": "block",
        },
        component="examples.grl",
    )
