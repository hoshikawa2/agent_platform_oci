from __future__ import annotations

import time
from typing import Any

import httpx

from .models import BackendCallResult, BackendDefinition, GlobalRouteDecision


class BackendClient:
    def __init__(self, timeout_seconds: float = 120.0):
        self.timeout_seconds = timeout_seconds

    async def call_message(
        self,
        backend: BackendDefinition,
        request_payload: dict[str, Any],
        route_decision: GlobalRouteDecision,
        use_sse: bool = False,
    ) -> BackendCallResult:
        path = backend.sse_message_path if use_sse else backend.message_path
        url = f"{backend.base_url}{path}"
        payload = dict(request_payload)
        # Mantém compatibilidade com agent_template_backend.
        payload.setdefault("agent_id", backend.default_agent_id)
        payload.setdefault("tenant_id", request_payload.get("tenant_id"))
        inner = payload.setdefault("payload", {}) if isinstance(payload.get("payload"), dict) else None
        if inner is not None:
            inner.setdefault("selected_backend", backend.backend_id)
            inner.setdefault("global_route_decision", route_decision.model_dump(mode="json"))
        started = time.time()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(url, json=payload)
        elapsed_ms = int((time.time() - started) * 1000)
        resp.raise_for_status()
        data = resp.json()
        return BackendCallResult(
            backend_id=backend.backend_id,
            backend_url=backend.base_url,
            status_code=resp.status_code,
            response=data,
            route_decision=route_decision,
            elapsed_ms=elapsed_ms,
        )

    async def health(self, backend: BackendDefinition) -> dict[str, Any]:
        url = f"{backend.base_url}{backend.health_path}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url)
                return {"backend_id": backend.backend_id, "status_code": resp.status_code, "ok": resp.is_success, "body": self._safe_json(resp)}
            except Exception as exc:
                return {"backend_id": backend.backend_id, "ok": False, "error": str(exc)}

    def _safe_json(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except Exception:
            return resp.text[:500]
