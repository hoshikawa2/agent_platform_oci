from __future__ import annotations

import logging
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent_framework.analytics.factory import create_analytics_publisher
from agent_framework.global_supervisor import (
    BackendClient,
    BackendRegistry,
    GlobalRouteRequest,
    GlobalSupervisorRouter,
    InMemoryGlobalSessionStore,
)
from agent_framework.llm.providers import create_llm
from agent_framework.observability.observer import AgentObserver

from app.settings import settings

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger("agent_gateway")

app = FastAPI(title="Agent Gateway - Global Supervisor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

registry = BackendRegistry.from_yaml(settings.BACKENDS_CONFIG_PATH)
analytics = create_analytics_publisher(settings)
observer = AgentObserver(analytics=analytics)
llm = create_llm(settings)
session_store = InMemoryGlobalSessionStore(ttl_seconds=settings.GLOBAL_SESSION_TTL_SECONDS)
router = GlobalSupervisorRouter(
    registry=registry,
    llm=llm if settings.GLOBAL_ROUTING_MODE in {"supervisor", "hybrid"} else None,
    session_store=session_store,
    mode=settings.GLOBAL_ROUTING_MODE,
    keep_active_backend=settings.GLOBAL_KEEP_ACTIVE_BACKEND,
    use_supervisor_on_conflict=settings.GLOBAL_USE_SUPERVISOR_ON_CONFLICT,
    min_router_confidence=settings.GLOBAL_MIN_ROUTER_CONFIDENCE,
)
backend_client = BackendClient(timeout_seconds=settings.BACKEND_TIMEOUT_SECONDS)


class GatewayRequest(BaseModel):
    channel: str = "web"
    payload: dict = Field(default_factory=dict)
    tenant_id: str | None = None
    agent_id: str | None = None
    backend_id: str | None = None
    session_id: str | None = None
    metadata: dict = Field(default_factory=dict)


def _session_id(req: GatewayRequest) -> str:
    return (
        req.session_id
        or req.payload.get("session_id")
        or req.payload.get("conversation_key")
        or req.payload.get("original_session_id")
        or str(uuid4())
    )


def _as_backend_request(req: GatewayRequest, session_id: str) -> dict:
    # Mantém o contrato do agent_template_backend: {channel, payload, agent_id, tenant_id}
    payload = dict(req.payload or {})
    payload.setdefault("session_id", session_id)
    return {
        "channel": req.channel,
        "payload": payload,
        "agent_id": req.agent_id,
        "tenant_id": req.tenant_id or payload.get("tenant_id") or "default",
    }


@app.middleware("http")
async def noc_middleware(request: Request, call_next):
    started = time.time()
    try:
        response = await call_next(request)
        await observer.emit_noc("006", {"component": "agent_gateway", "path": request.url.path, "status_code": response.status_code, "duration_ms": int((time.time() - started) * 1000)})
        return response
    except Exception as exc:
        await observer.emit_noc("005", {"component": "agent_gateway", "path": request.url.path, "error": str(exc), "duration_ms": int((time.time() - started) * 1000)})
        raise


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "routing_mode": settings.GLOBAL_ROUTING_MODE,
        "backends": [b.backend_id for b in registry.list()],
        "llm_provider": settings.LLM_PROVIDER,
    }


@app.get("/backends")
async def backends():
    return registry.as_dict()


@app.get("/backends/health")
async def backends_health():
    results = []
    for backend in registry.list():
        results.append(await backend_client.health(backend))
    return {"results": results}


@app.post("/debug/route")
async def debug_route(req: GatewayRequest):
    session_id = _session_id(req)
    route_req = GlobalRouteRequest(
        channel=req.channel,
        payload=req.payload,
        tenant_id=req.tenant_id,
        session_id=session_id,
        force_backend=req.backend_id,
        metadata=req.metadata,
    )
    decision = await router.route(route_req)
    return decision.model_dump(mode="json")


@app.get("/debug/sessions")
async def debug_sessions():
    return await session_store.dump()


@app.post("/gateway/message")
async def gateway_message(req: GatewayRequest):
    started = time.time()
    session_id = _session_id(req)
    tenant_id = req.tenant_id or req.payload.get("tenant_id") or "default"
    await observer.emit_ic("GLOBAL_GATEWAY_RECEIVED", {"session_id": session_id, "tenant_id": tenant_id, "channel": req.channel})
    route_req = GlobalRouteRequest(
        channel=req.channel,
        payload=req.payload,
        tenant_id=tenant_id,
        session_id=session_id,
        force_backend=req.backend_id,
        metadata=req.metadata,
    )
    decision = await router.route(route_req)
    backend = registry.get(decision.backend_id)
    await observer.emit_ic("GLOBAL_BACKEND_SELECTED", {"session_id": session_id, "backend_id": backend.backend_id, "confidence": decision.confidence, "reason": decision.reason})
    try:
        result = await backend_client.call_message(backend, _as_backend_request(req, session_id), decision)
    except Exception as exc:
        await observer.emit_noc("005", {"component": "agent_gateway", "backend_id": backend.backend_id, "session_id": session_id, "error": str(exc)})
        raise HTTPException(status_code=502, detail={"message": "Falha ao chamar backend selecionado", "backend_id": backend.backend_id, "error": str(exc)})

    # Handoff opcional: backend pode pedir troca via metadata.handover_backend.
    response = result.response

    backend_session_id = (
            response.get("session_id")
            or response.get("metadata", {}).get("conversation_key")
    )

    if backend_session_id:
        session_data = await session_store.set_active_backend(
            session_id=session_id,
            backend_id=backend.backend_id,
            tenant_id=tenant_id,
            backend_session_id=backend_session_id,
        )

        response["session_id"] = session_id
        metadata = response.get("metadata") or {}
        metadata["backend_session_id"] = backend_session_id
        metadata["global_session_id"] = session_id
        response["metadata"] = metadata
        response["session_id"] = session_id

    metadata = response.get("metadata") or {}
    handover_backend = metadata.get("handover_backend") or metadata.get("handover_to_backend")
    if handover_backend and handover_backend in registry.backends and handover_backend != backend.backend_id:
        await observer.emit_ic("GLOBAL_BACKEND_HANDOVER", {"session_id": session_id, "from_backend": backend.backend_id, "to_backend": handover_backend})
        forced = GatewayRequest(**req.model_dump())
        forced.backend_id = handover_backend
        forced.payload = {**forced.payload, "handover_from_backend": backend.backend_id}
        return await gateway_message(forced)

    await observer.emit_ic("GLOBAL_GATEWAY_COMPLETED", {"session_id": session_id, "backend_id": backend.backend_id, "elapsed_ms": int((time.time() - started) * 1000)})
    metadata = dict(metadata)
    metadata["global_route_decision"] = decision.model_dump(mode="json")
    metadata["selected_backend"] = backend.backend_id
    metadata["backend_elapsed_ms"] = result.elapsed_ms
    response["metadata"] = metadata
    return response


@app.post("/gateway/message/sse")
async def gateway_message_sse(req: GatewayRequest):
    # Para simplificar o contrato, primeiro roteia via gateway e delega ao endpoint SSE do backend.
    # O frontend pode continuar usando /gateway/events/{session_id} diretamente no backend escolhido,
    # ou evoluir para um proxy SSE no gateway.
    return await gateway_message(req)

from fastapi.responses import StreamingResponse
import httpx
import asyncio


@app.get("/gateway/events/{session_id:path}")
async def gateway_events(session_id: str):

    async def stream():
        yield (
            "event: connected\n"
            f'data: {{"session_id":"{session_id}","component":"agent_gateway"}}\n\n'
        )

        session_data = await session_store.get(session_id)

        while not session_data:
            yield (
                "event: waiting\n"
                f'data: {{"session_id":"{session_id}"}}\n\n'
            )

            await asyncio.sleep(1)
            session_data = await session_store.get(session_id)

        logger.error("SESSION_DATA SSE = %s", session_data)

        backend_id = session_data.active_backend
        backend_session_id = session_id

        if not backend_id:
            yield (
                "event: error\n"
                f'data: {{"message":"Sessão encontrada sem active_backend",'
                f'"session_id":"{session_id}"}}\n\n'
            )
            return

        backend = registry.get(backend_id)

        backend_base_url = (
                getattr(backend, "base_url", None)
                or getattr(backend, "url", None)
                or getattr(backend, "endpoint", None)
                or getattr(backend, "base_endpoint", None)
        )

        if not backend_base_url:
            yield (
                "event: error\n"
                f'data: {{"message":"Backend sem URL configurada",'
                f'"backend_id":"{backend_id}"}}\n\n'
            )
            return

        backend_sse_url = (
            f"{backend_base_url.rstrip('/')}/gateway/events/{backend_session_id}"
        )

        yield (
            "event: backend.selected\n"
            f'data: {{"session_id":"{session_id}",'
            f'"backend_id":"{backend_id}",'
            f'"backend_session_id":"{backend_session_id}",'
            f'"backend_sse_url":"{backend_sse_url}"}}\n\n'
        )

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", backend_sse_url) as response:
                    content_type = response.headers.get("content-type", "")

                    if response.status_code != 200:
                        body = await response.aread()
                        yield (
                            "event: error\n"
                            f'data: {{"message":"Backend SSE retornou erro",'
                            f'"status_code":{response.status_code},'
                            f'"content_type":"{content_type}",'
                            f'"body":{body.decode("utf-8", errors="replace")!r}}}\n\n'
                        )
                        return

                    if "text/event-stream" not in content_type:
                        body = await response.aread()
                        yield (
                            "event: error\n"
                            f'data: {{"message":"Backend SSE não retornou text/event-stream",'
                            f'"status_code":{response.status_code},'
                            f'"content_type":"{content_type}",'
                            f'"body":{body.decode("utf-8", errors="replace")!r}}}\n\n'
                        )
                        return

                    async for chunk in response.aiter_text():
                        if chunk:
                            yield chunk

        except Exception as exc:
            logger.exception("Erro no proxy SSE do gateway")
            yield (
                "event: error\n"
                f'data: {{"message":"Erro no proxy SSE do gateway",'
                f'"error":"{str(exc)}"}}\n\n'
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )