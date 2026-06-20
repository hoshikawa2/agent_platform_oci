from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any

@dataclass(frozen=True)
class BusinessContext:
    """Chaves canônicas e estáveis de negócio.

    O framework usa estes nomes. Cada backend decide, por configuração, quais
    campos reais alimentam estas chaves e como elas voltam para as tools MCP.
    """
    customer_key: str | None = None
    contract_key: str | None = None
    interaction_key: str | None = None
    account_key: str | None = None
    resource_key: str | None = None
    session_key: str | None = None
    source_fields: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    def to_context_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v not in (None, "", {})}

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "BusinessContext":
        data = dict(data or {})
        return cls(
            customer_key=_clean(data.get("customer_key")),
            contract_key=_clean(data.get("contract_key")),
            interaction_key=_clean(data.get("interaction_key")),
            account_key=_clean(data.get("account_key")),
            resource_key=_clean(data.get("resource_key")),
            session_key=_clean(data.get("session_key")),
            source_fields=dict(data.get("source_fields") or {}),
            metadata=dict(data.get("metadata") or {}),
        )


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
