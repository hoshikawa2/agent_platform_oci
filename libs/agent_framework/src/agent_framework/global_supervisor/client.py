from __future__ import annotations

import time
import os
from collections import OrderedDict
from typing import Any

import httpx

from .models import BackendCallResult, BackendDefinition, GlobalRouteDecision


class BackendClient:
    def __init__(self, timeout_seconds: float = 120.0):
        self.timeout_seconds = timeout_seconds
        # Bounded, process-local continuation cache; native calls do not use it.
        self._a2a_sessions = OrderedDict()

    async def call_message(
        self,
        backend: BackendDefinition,
        request_payload: dict[str, Any],
        route_decision: GlobalRouteDecision,
        use_sse: bool = False,
    ) -> BackendCallResult:
        if backend.protocol == "a2a":
            from agent_framework.a2a.client import call_a2a
            started = time.monotonic()
            payload = dict(request_payload.get("payload") or {})
            key = (request_payload.get("tenant_id") or "default", backend.backend_id, payload.get("session_id"))
            previous = self._a2a_sessions.get(key) if key[2] else None
            if previous and time.monotonic() - previous[0] < 3600:
                payload.setdefault("a2a_context_id", previous[1].get("a2a_context_id"))
                if previous[1].get("a2a_state") in {"input-required", "auth-required", "TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED"}:
                    payload.setdefault("a2a_task_id", previous[1].get("a2a_task_id"))
            data = await call_a2a(backend, {**request_payload, "payload": payload}, self.timeout_seconds)
            if key[2]:
                self._a2a_sessions[key] = (time.monotonic(), data.get("metadata", {}))
                self._a2a_sessions.move_to_end(key)
                while len(self._a2a_sessions) > 10000:
                    self._a2a_sessions.popitem(last=False)
            return BackendCallResult(
                backend_id=backend.backend_id, backend_url=backend.base_url,
                status_code=200, response=data, route_decision=route_decision,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
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
        path = backend.a2a_agent_card_path if backend.protocol == "a2a" else backend.health_path
        url = f"{backend.base_url}{path}"
        headers = {}
        if backend.protocol == "a2a":
            for header, env_name in backend.a2a_headers_env.items():
                value = os.environ.get(env_name)
                if not value:
                    return {"backend_id": backend.backend_id, "ok": False, "error": f"Missing credential environment variable: {env_name}"}
                headers[header] = value
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
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
