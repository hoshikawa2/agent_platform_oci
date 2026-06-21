from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.governance_middleware import AgentGatewayGovernance

router = APIRouter()
governance = AgentGatewayGovernance()


@router.post("/gateway/message/governed")
async def governed_gateway_message(request: Request):
    """Example governed proxy route.

    Use as reference to patch the existing /gateway/message handler.
    """

    body: dict[str, Any] = await request.json()
    backend_url = os.getenv("DEFAULT_AGENT_BACKEND_URL", "http://localhost:8000")

    governed_body, headers = governance.prepare_backend_request(body)

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{backend_url.rstrip('/')}/gateway/message",
                json=governed_body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            return governance.process_backend_response(data)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
