"""Exemplos de IC - Item de Controle.

ICs representam eventos de negócio. Eles alimentam Informacional, Curadoria,
analytics, BigQuery ou qualquer publisher configurado no framework.
"""

from typing import Any


async def exemplo_fatura_consultada(observer: Any, state: dict[str, Any], invoice_id: str) -> None:
    await observer.emit_ic(
        "IC.FATURA_CONSULTADA",
        {
            "session_id": state.get("conversation_key") or state.get("session_id"),
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "invoice_id": invoice_id,
        },
        component="examples.ic",
    )


async def exemplo_acao_concluida(observer: Any, state: dict[str, Any], action_name: str, ok: bool) -> None:
    await observer.emit_ic(
        "IC.ACAO_CONCLUIDA",
        {
            "session_id": state.get("conversation_key") or state.get("session_id"),
            "tenant_id": state.get("tenant_id"),
            "agent_id": state.get("agent_id"),
            "action_name": action_name,
            "ok": ok,
        },
        component="examples.ic",
    )
