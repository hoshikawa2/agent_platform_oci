from __future__ import annotations

import logging
from uuid import uuid4
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_framework.channels.base import ChannelResponse
from agent_framework.channels.gateway import ChannelGateway
from agent_framework.config.agent_registry import AgentProfileRegistry
from agent_framework.config.settings import settings
from agent_framework.analytics.factory import create_analytics_publisher
from agent_framework.observer import configure as configure_global_observer
from agent_framework.llm.providers import create_llm
from agent_framework.memory.message_history import create_memory
from agent_framework.memory.summary_memory import create_conversation_summary_memory
from agent_framework.mcp.tool_router import create_mcp_tool_router
from agent_framework.models.identity import AgentIdentity
from agent_framework.identity import IdentityResolver, BusinessContext
from agent_framework.models.session import ChatMessage, SessionContext
from agent_framework.observability.telemetry import Telemetry
from agent_framework.observability.context import set_observability_context, clear_observability_context
from agent_framework.repositories.session_repository import create_session_repository
from agent_framework.checkpoints.checkpoint_repository import create_checkpoint_repository
from agent_framework.cache.cache import create_cache
from agent_framework.billing.usage_repository import create_usage_repository
from agent_framework.sse.events import SSEHub
from app.workflows.agent_graph import AgentWorkflow
from app.observability.telemetry_observer import TelemetryBackedAgentObserver

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger("agent_template_backend")

app = FastAPI(title="Agent Template Backend FIRST-ready")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

telemetry = Telemetry(settings)
usage_repository = create_usage_repository(settings)
llm = create_llm(settings, telemetry=telemetry, usage_repository=usage_repository)
memory = create_memory(settings)
summary_memory = create_conversation_summary_memory(settings, message_history=memory, llm=llm, telemetry=telemetry)
sessions = create_session_repository(settings)
checkpoints = create_checkpoint_repository(settings)
cache = create_cache(settings, telemetry=telemetry)
gateway = ChannelGateway()
analytics = create_analytics_publisher(settings)
observer = TelemetryBackedAgentObserver(telemetry=telemetry)
configure_global_observer({
    "enabled": getattr(settings, "ENABLE_ANALYTICS", False),
    "providers": getattr(settings, "ANALYTICS_PROVIDERS", "oci_streaming"),
    "topic_path": getattr(settings, "GCP_PUBSUB_TOPIC_PATH", None) or getattr(settings, "AGENT_PUBSUB_TOPIC", None),
})
tool_router = create_mcp_tool_router(settings, telemetry=telemetry)
identity_resolver = IdentityResolver.from_yaml(settings.IDENTITY_CONFIG_PATH)
agent_profiles = AgentProfileRegistry(settings)
sse_hub = SSEHub(settings, telemetry=telemetry)
workflow = AgentWorkflow(llm, memory, telemetry, analytics, settings, observer=observer, tool_router=tool_router, summary_memory=summary_memory)

logger.info("LLM provider carregado: %s", llm.__class__.__name__)
logger.info("Langfuse habilitado: %s host=%s", telemetry.is_enabled(), settings.LANGFUSE_HOST)
logger.info("Analytics habilitado: %s providers=%s", getattr(settings, "ENABLE_ANALYTICS", False), getattr(settings, "ANALYTICS_PROVIDERS", ""))
logger.info("Agentes disponíveis: %s", [p.agent_id for p in agent_profiles.list_profiles()])

@app.middleware("http")
async def observability_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    set_observability_context(
        request_id=request_id,
        channel=request.headers.get("x-channel") or "http",
        ura_call_id=request.headers.get("x-ura-call-id"),
    )
    started = time.time()
    try:
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        await telemetry.event("http.request.completed", {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": int((time.time() - started) * 1000),
        }, kind="http")
        return response
    except Exception as exc:
        await telemetry.event("http.request.failed", {
            "method": request.method,
            "path": request.url.path,
            "error": str(exc),
            "duration_ms": int((time.time() - started) * 1000),
        }, kind="http")
        raise


class GatewayRequest(BaseModel):
    channel: str = "web"
    payload: dict
    agent_id: str | None = None
    tenant_id: str | None = None


def _resolve_identity(req: GatewayRequest, msg) -> tuple[AgentIdentity, dict, BusinessContext, list[str]]:
    payload = req.payload or {}
    context = dict(msg.context or {})
    tenant_id = req.tenant_id or payload.get("tenant_id") or context.get("tenant_id") or "default"
    agent_id = req.agent_id or payload.get("agent_id") or context.get("agent_id") or agent_profiles.default_agent_id
    profile = agent_profiles.get(agent_id)

    # 1) Identidade técnica do framework: isola tenant/agente/sessão.
    context.update({"tenant_id": tenant_id, "agent_id": profile.agent_id, "agent_profile": profile.__dict__})
    identity = AgentIdentity.from_context(context, session_id=msg.session_id)

    # 2) Identidade de negócio: chaves canônicas vindas do front/canal.
    #    Estas chaves são estáveis na sessão e seguem até agentes e MCP Router.
    previous_business_context = context.get("business_context") or context.get("identity") or {}
    business_context = identity_resolver.resolve(
        {**payload, **context},
        session_id=identity.conversation_key(),
        previous=previous_business_context,
    )
    missing_identity_keys = identity_resolver.validate(business_context)
    context.update({
        "business_context": business_context.model_dump(),
        "business_keys": business_context.to_context_dict(),
        "identity_missing": missing_identity_keys,
        "conversation_key": identity.conversation_key(),
        "original_session_id": msg.session_id,
    })
    return identity, context, business_context, missing_identity_keys


async def _process_gateway_message(req: GatewayRequest, emit_sse: bool = False) -> dict:
    msg = await gateway.normalize(req.channel, req.payload)
    identity, normalized_context, business_context, missing_identity_keys = _resolve_identity(req, msg)
    agent_session_id = identity.conversation_key()
    message_id = (req.payload or {}).get("message_id") or str(uuid4())
    set_observability_context(
        session_id=agent_session_id,
        user_id=msg.user_id,
        tenant_id=identity.tenant_id,
        agent_id=identity.agent_id,
        channel=msg.channel,
        message_id=message_id,
        ura_call_id=(req.payload or {}).get("ura_call_id") or normalized_context.get("ura_call_id") or business_context.interaction_key,
    )

    stream = sse_hub.stream_for(agent_session_id)
    async with stream.lock:
        await sse_hub.emit(agent_session_id, "flow.start", {"session_id": agent_session_id, "message_id": message_id, "agent_id": identity.agent_id}) if emit_sse else None

        session = await sessions.get(agent_session_id)
        if not session:
            context_fields = {
                k: v
                for k, v in normalized_context.items()
                if k in SessionContext.model_fields
                and k not in {"tenant_id", "agent_id", "session_id", "user_id", "channel", "channel_id"}
            }
            session = SessionContext(
                tenant_id=identity.tenant_id,
                agent_id=identity.agent_id,
                session_id=agent_session_id,
                user_id=msg.user_id,
                channel=msg.channel,
                channel_id=msg.channel_id,
                **context_fields,
            )

        session.tenant_id = identity.tenant_id
        session.agent_id = identity.agent_id
        session.channel = msg.channel
        session.channel_id = msg.channel_id or session.channel_id
        await sessions.upsert(session)
        session.metadata = {
            **(session.metadata or {}),
            "business_context": business_context.model_dump(),
            "identity_missing": missing_identity_keys,
            "original_context": normalized_context,
        }
        await sse_hub.emit(agent_session_id, "session.upserted", {"session_id": agent_session_id, "business_context": business_context.model_dump()}) if emit_sse else None

        await memory.append(
            agent_session_id,
            ChatMessage(
                role="user",
                content=msg.text,
                metadata={
                    **normalized_context,
                    "agent_id": identity.agent_id,
                    "tenant_id": identity.tenant_id,
                    "message_id": message_id,
                    "business_context": business_context.model_dump(),
                    "identity_missing": missing_identity_keys,
                },
            ),
        )
        await sse_hub.emit(agent_session_id, "message.received", {"session_id": agent_session_id, "role": "user"}) if emit_sse else None
        history = [m.model_dump(mode="json") for m in await memory.list(agent_session_id)]

        trace_input = {
            "text": msg.text,
            "channel": msg.channel,
            "channel_id": msg.channel_id,
            "tenant_id": identity.tenant_id,
            "agent_id": identity.agent_id,
            "conversation_key": agent_session_id,
            "message_id": message_id,
            "business_context": business_context.model_dump(),
            "identity_missing": missing_identity_keys,
        }

        async with telemetry.span(
            "agent.gateway_message",
            session_id=agent_session_id,
            user_id=session.user_id,
            channel=msg.channel,
            input=trace_input,
            tags=["agent-template", msg.channel, f"agent:{identity.agent_id}", f"tenant:{identity.tenant_id}"],
        ):
            await telemetry.event("gateway.message.received", trace_input)
            await sse_hub.emit(agent_session_id, "workflow.started", trace_input) if emit_sse else None
            result = await workflow.ainvoke(
                {
                    "tenant_id": identity.tenant_id,
                    "agent_id": identity.agent_id,
                    "session_id": agent_session_id,
                    "conversation_key": agent_session_id,
                    "agent_profile": normalized_context["agent_profile"],
                    "user_text": msg.text,
                    "history": history,
                    "context": {
                        **normalized_context,
                        "session": session.model_dump(mode="json"),
                        "original_session_id": msg.session_id,
                        "session_id": agent_session_id,
                        "conversation_key": agent_session_id,
                        "user_id": session.user_id,
                        "channel": msg.channel,
                        "message_id": message_id,
                        "business_context": business_context.model_dump(),
                        "business_keys": business_context.to_context_dict(),
                        "identity_missing": missing_identity_keys,
                    },
                }
            )

        await checkpoints.put(agent_session_id, {"state": result, "message_id": message_id})
        await sse_hub.emit(agent_session_id, "workflow.completed", {"session_id": agent_session_id, "route": result.get("route"), "intent": result.get("intent")}) if emit_sse else None

        answer = result.get("final_answer") or result.get("answer") or ""
        await memory.append(
            agent_session_id,
            ChatMessage(
                role="assistant",
                content=answer,
                metadata={
                    "tenant_id": identity.tenant_id,
                    "agent_id": identity.agent_id,
                    "message_id": f"assistant-{message_id}",
                    "route": result.get("route"),
                    "intent": result.get("intent"),
                    "route_decision": result.get("route_decision"),
                    "judges": result.get("judge_results"),
                },
            ),
        )

        await telemetry.event(
            "gateway.message.responded",
            {
                "session_id": agent_session_id,
                "tenant_id": identity.tenant_id,
                "agent_id": identity.agent_id,
                "route": result.get("route"),
                "intent": result.get("intent"),
                "answer_chars": len(answer),
            },
        )

        response = ChannelResponse(
            channel=msg.channel,
            session_id=agent_session_id,
            text=answer,
            metadata={
                "channel_id": msg.channel_id,
                "tenant_id": identity.tenant_id,
                "agent_id": identity.agent_id,
                "original_session_id": msg.session_id,
                "conversation_key": agent_session_id,
                "message_id": message_id,
                "route": result.get("route"),
                "intent": result.get("intent"),
                "route_decision": result.get("route_decision"),
                "domain": result.get("domain"),
                "mcp_tools": result.get("mcp_tools"),
                "mcp_results": result.get("mcp_results"),
                "business_context": business_context.model_dump(),
                "identity_missing": missing_identity_keys,
                "judges": result.get("judge_results"),
                "guardrails": result.get("guardrail_decisions"),
            },
        )
        rendered = await gateway.render(response)
        await sse_hub.emit(agent_session_id, "message.responded", rendered) if emit_sse else None
        await sse_hub.emit(agent_session_id, "flow.end", {"session_id": agent_session_id, "message_id": message_id}) if emit_sse else None
        return rendered


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_class": llm.__class__.__name__,
        "langfuse_enabled": telemetry.is_enabled(),
        "agents": [p.agent_id for p in agent_profiles.list_profiles()],
        "default_agent_id": agent_profiles.default_agent_id,
        "routing_mode": settings.ROUTING_MODE,
        "sse_enabled": settings.ENABLE_SSE,
        "session_repository": settings.SESSION_REPOSITORY_PROVIDER,
        "memory_repository": settings.MEMORY_REPOSITORY_PROVIDER,
        "checkpoint_repository": settings.CHECKPOINT_REPOSITORY_PROVIDER,
        "usage_repository": settings.USAGE_REPOSITORY_PROVIDER,
        "identity_config_path": settings.IDENTITY_CONFIG_PATH,
        "mcp_parameter_mapping_path": settings.MCP_PARAMETER_MAPPING_PATH,
    }


@app.get("/agents")
async def list_agents():
    return {"default_agent_id": agent_profiles.default_agent_id, "agents": [p.__dict__ for p in agent_profiles.list_profiles()]}


@app.get("/debug/env")
async def debug_env():
    return {
        "APP_ENV": settings.APP_ENV,
        "LLM_PROVIDER": settings.LLM_PROVIDER,
        "ENABLE_LANGFUSE": settings.ENABLE_LANGFUSE,
        "LANGFUSE_HOST": settings.LANGFUSE_HOST,
        "TELEMETRY_ENABLED": telemetry.is_enabled(),
        "SQLITE_DB_PATH": settings.SQLITE_DB_PATH,
        "SESSION_REPOSITORY_PROVIDER": settings.SESSION_REPOSITORY_PROVIDER,
        "MEMORY_REPOSITORY_PROVIDER": settings.MEMORY_REPOSITORY_PROVIDER,
        "CHECKPOINT_REPOSITORY_PROVIDER": settings.CHECKPOINT_REPOSITORY_PROVIDER,
        "AGENTS_CONFIG_PATH": settings.AGENTS_CONFIG_PATH,
        "ROUTING_CONFIG_PATH": settings.ROUTING_CONFIG_PATH,
        "ROUTING_MODE": settings.ROUTING_MODE,
    }


@app.get("/test-llm")
async def test_llm():
    async with telemetry.span("debug.test_llm", input={"message": "Diga apenas OK"}):
        answer = await llm.ainvoke([
            {"role": "system", "content": "Responda de forma curta."},
            {"role": "user", "content": "Diga apenas OK"},
        ])
    telemetry.flush()
    return {"provider": llm.__class__.__name__, "answer": answer}


@app.post("/debug/route")
async def debug_route(req: GatewayRequest):
    msg = await gateway.normalize(req.channel, req.payload)
    identity, context, business_context, missing_identity_keys = _resolve_identity(req, msg)
    state = {
        "tenant_id": identity.tenant_id,
        "agent_id": identity.agent_id,
        "session_id": msg.session_id or "debug-session",
        "conversation_key": identity.conversation_key(),
        "agent_profile": context["agent_profile"],
        "user_text": msg.text,
        "sanitized_input": msg.text,
        "history": [],
        "context": {**context, "session": context.get("session", {}), "channel": msg.channel, "business_context": business_context.model_dump()},
    }
    if settings.ROUTING_MODE == "supervisor":
        plan = await workflow.supervisor.route_plan(state)
        return {"mode": "supervisor", "route": "supervisor_agent", "agents": plan.agents, "intent": plan.intent, "confidence": plan.confidence, "reason": plan.reason, "metadata": plan.metadata}
    decision = await workflow.router.route(state)
    data = decision.model_dump(mode="json")
    data["mode"] = "router"
    return data




@app.post("/debug/identity")
async def debug_identity(req: GatewayRequest):
    msg = await gateway.normalize(req.channel, req.payload)
    identity, context, business_context, missing_identity_keys = _resolve_identity(req, msg)
    return {
        "technical_identity": {
            "tenant_id": identity.tenant_id,
            "agent_id": identity.agent_id,
            "conversation_key": identity.conversation_key(),
            "original_session_id": msg.session_id,
        },
        "business_context": business_context.model_dump(),
        "identity_missing": missing_identity_keys,
        "context_keys": sorted(context.keys()),
    }

@app.get("/debug/usage")
async def debug_usage(tenant_id: str | None = None, session_id: str | None = None):
    return await usage_repository.summarize(tenant_id=tenant_id, session_id=session_id)


@app.get("/debug/mcp/tools")
async def debug_mcp_tools():
    return {"enabled": tool_router.enabled, "tools": tool_router.describe_tools()}


@app.post("/debug/mcp/call/{tool_name}")
async def debug_mcp_call(tool_name: str, arguments: dict | None = None):
    arguments = arguments or {}
    ctx = arguments.get("business_context") or arguments.get("identity") or {}
    result = await tool_router.call(
        tool_name,
        arguments,
        business_context=ctx,
        original_context=arguments,
    )
    return result.model_dump(mode="json")


@app.post("/gateway/message")
async def gateway_message(req: GatewayRequest):
    return await _process_gateway_message(req, emit_sse=False)


@app.post("/gateway/message/sse")
async def gateway_message_sse(req: GatewayRequest):
    return await _process_gateway_message(req, emit_sse=True)


@app.get("/gateway/events/{session_id}")
async def gateway_events(session_id: str, request: Request):
    last = request.headers.get("last-event-id") or request.query_params.get("last_event_id") or "0"
    return StreamingResponse(
        sse_hub.subscribe(session_id, int(last)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, limit: int = 50):
    return {"session_id": session_id, "messages": [m.model_dump(mode="json") for m in await memory.list(session_id, limit)]}


@app.get("/sessions/{session_id}/checkpoint")
async def get_session_checkpoint(session_id: str):
    return {"session_id": session_id, "checkpoint": await checkpoints.get_latest(session_id)}


@app.on_event("shutdown")
async def shutdown():
    telemetry.shutdown()
