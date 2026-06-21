from __future__ import annotations

from typing import Any


class EvaluationHooks:
    def before_backend_call(self, request_payload: dict[str, Any]) -> dict[str, Any]:
        return request_payload

    def after_backend_call(self, response_payload: dict[str, Any]) -> dict[str, Any]:
        return response_payload
