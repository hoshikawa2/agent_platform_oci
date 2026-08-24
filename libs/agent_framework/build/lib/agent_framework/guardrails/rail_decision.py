from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rail_action import RailAction
from .rail_result import RailResult


@dataclass(slots=True)
class RailDecisionV2:
    action: RailAction
    results: list[RailResult]
    candidate: str
    guidance: str = ""
    fallback_message: str = "Não consegui validar essa resposta com segurança. Posso reformular ou encaminhar para continuidade do atendimento."
    handover_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.action in {RailAction.ALLOW, RailAction.SANITIZE, RailAction.OBSERVE}
