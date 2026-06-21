from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("agent_gateway.governance")


def audit_event(name: str, payload: dict[str, Any]) -> None:
    safe = dict(payload)
    if "message" in safe:
        safe["message_len"] = len(str(safe.pop("message") or ""))
    logger.info("%s %s", name, json.dumps(safe, ensure_ascii=False, default=str))
