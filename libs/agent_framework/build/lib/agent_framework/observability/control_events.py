from __future__ import annotations

"""API nativa para emissão padronizada de IC/NOC/GRL.

Use este módulo em agentes novos para evitar bridges legados como
`ics_collector.py`. A API preserva contratos TIM/FIRST já existentes:

- AGA.xxx: Item de Controle de domínio/backoffice;
- IC.xxx: Item de Controle genérico do framework;
- NOC.xxx: Evento operacional/NOC;
- GRL.xxx: Evento de guardrail.
"""

from typing import Any

from agent_framework.observer import aevent, aic, anoc, agrl, event, ic, noc, grl


async def emit_control_event(
    code: str,
    *,
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    code = str(code).strip()
    if code.startswith("NOC."):
        return await anoc(code, data=data, metadata=metadata)
    if code.startswith("GRL."):
        return await agrl(code, data=data, metadata=metadata)
    if code.startswith(("IC.", "AGA.")):
        return await aic(code, data=data, metadata=metadata)
    return await aevent(code, data=data, metadata=metadata)


def emit_control_event_sync(
    code: str,
    *,
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    code = str(code).strip()
    if code.startswith("NOC."):
        return noc(code, data=data, metadata=metadata)
    if code.startswith("GRL."):
        return grl(code, data=data, metadata=metadata)
    if code.startswith(("IC.", "AGA.")):
        return ic(code, data=data, metadata=metadata)
    return event(code, data=data, metadata=metadata)


__all__ = [
    "emit_control_event",
    "emit_control_event_sync",
    "aevent",
    "aic",
    "anoc",
    "agrl",
    "event",
    "ic",
    "noc",
    "grl",
]
