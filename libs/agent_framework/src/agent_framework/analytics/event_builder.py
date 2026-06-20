from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def build_analytics_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    source: str = "agent_framework",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Monta envelope uniforme para IC/NOC/GRL.

    O campo metadata.noc=true é preservado para que o Observer consiga rotear
    eventos também para NOC/OTEL/Elastic quando aplicável.
    """
    body = dict(payload or {})
    meta = dict(metadata or {})
    return {
        "eventType": event_type,
        "source": source,
        "eventDate": datetime.now(timezone.utc).isoformat(),
        "payload": body,
        "metadata": meta,
    }
