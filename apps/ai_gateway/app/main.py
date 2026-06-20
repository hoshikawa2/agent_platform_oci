from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[Any] | None = None


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[Message]
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelRoute(BaseModel):
    provider: str
    model: str
    base_url: str | None = None


app = FastAPI(title="Agent Framework OCI - AI Gateway", version="0.1.0")


def resolve_route(requested_model: str | None, metadata: dict[str, Any]) -> ModelRoute:
    provider = metadata.get("provider") or os.getenv("AI_GATEWAY_DEFAULT_PROVIDER", "oci_openai")
    model = requested_model or metadata.get("profile_model") or os.getenv("AI_GATEWAY_DEFAULT_MODEL", "openai.gpt-4.1")
    base_url = os.getenv("AI_GATEWAY_OPENAI_COMPAT_BASE_URL")
    return ModelRoute(provider=provider, model=model, base_url=base_url)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "component": "ai_gateway"}


@app.get("/models")
def models() -> dict[str, Any]:
    return {
        "default_provider": os.getenv("AI_GATEWAY_DEFAULT_PROVIDER", "oci_openai"),
        "default_model": os.getenv("AI_GATEWAY_DEFAULT_MODEL", "openai.gpt-4.1"),
        "purpose": "model routing, policy control and LLM abstraction",
    }


@app.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionRequest) -> dict[str, Any]:
    route = resolve_route(payload.model, payload.metadata)
    # Safe default: when no upstream is configured, return route decision only.
    # Production deployments should configure AI_GATEWAY_OPENAI_COMPAT_BASE_URL and credentials.
    if not route.base_url:
        return {
            "gateway": "ai_gateway",
            "mode": "dry_run",
            "route": route.model_dump(),
            "message": "No upstream base URL configured. Set AI_GATEWAY_OPENAI_COMPAT_BASE_URL to proxy requests.",
        }

    api_key = os.getenv("AI_GATEWAY_API_KEY") or os.getenv("OCI_GENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    body = payload.model_dump(exclude_none=True)
    body["model"] = route.model
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("AI_GATEWAY_TIMEOUT_SECONDS", "60"))) as client:
            resp = await client.post(f"{route.base_url.rstrip('/')}/chat/completions", json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                data.setdefault("gateway", "ai_gateway")
                data.setdefault("route", route.model_dump())
            return data
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"AI upstream request failed: {exc}") from exc
