"""Exemplos de NOC.

NOC representa telemetria operacional. O workflow do template já emite NOC.001,
NOC.005 e NOC.006. Estes exemplos mostram eventos adicionais que a squad pode
emitir em pontos críticos.
"""

from typing import Any


async def exemplo_api_invalida(observer: Any, state: dict[str, Any], api_url: str, status_code: int, latency_ms: int) -> None:
    await observer.emit_noc(
        "002",
        {
            "session_id": state.get("conversation_key") or state.get("session_id"),
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "apiUrl": api_url,
            "statusCode": status_code,
            "latencyMs": latency_ms,
        },
        component="examples.noc",
    )


async def exemplo_latencia_banco(observer: Any, state: dict[str, Any], resource_name: str, latency_ms: int) -> None:
    await observer.emit_noc(
        "003",
        {
            "session_id": state.get("conversation_key") or state.get("session_id"),
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "resourceName": resource_name,
            "latencyMs": latency_ms,
        },
        component="examples.noc",
    )
