from __future__ import annotations

from typing import Any


class UsageRecorder:
    def record_gateway_request(self, payload: dict[str, Any]) -> None:
        return None

    def record_model_policy(self, payload: dict[str, Any]) -> None:
        return None

    def record_backend_response(self, payload: dict[str, Any]) -> None:
        return None
