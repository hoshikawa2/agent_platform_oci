from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.web import WebAdapter
from app.adapters.whatsapp import WhatsAppAdapter
from app.adapters.voice import VoiceAdapter
from app.client import AgentFrameworkClient
from app.schemas import GatewayRequest, VoiceTranscript, WebMessage, WhatsAppWebhook
from app.settings import settings

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger('external_channel_gateway')

app = FastAPI(title='External Channel Gateway')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(',')],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

client = AgentFrameworkClient()
web_adapter = WebAdapter()
whatsapp_adapter = WhatsAppAdapter()
voice_adapter = VoiceAdapter()


def _require_mode(expected: str, endpoint_type: str):
    if settings.runtime_mode != expected:
        raise HTTPException(
            status_code=409,
            detail={
                'error_code': 'CHANNEL_GATEWAY_MODE_MISMATCH',
                'message': f'{endpoint_type} endpoints require CHANNEL_GATEWAY_RUNTIME_MODE={expected}',
                'current_runtime_mode': settings.runtime_mode,
            },
        )


async def _forward(request: GatewayRequest) -> dict:
    return await client.send(request)


@app.get('/health')
async def health():
    return {
        'status': 'ok',
        'app_name': settings.APP_NAME,
        'runtime_mode': settings.runtime_mode,
        'configured_runtime_mode': settings.CHANNEL_GATEWAY_RUNTIME_MODE,
        'legacy_channel_gateway_mode': settings.CHANNEL_GATEWAY_MODE,
        'backend_url': client.url,
        'default_tenant_id': settings.DEFAULT_TENANT_ID,
        'default_agent_id': settings.DEFAULT_AGENT_ID,
    }


@app.post('/channels/web/message')
async def web_message(payload: WebMessage, request: Request):
    _require_mode('adapter', '/channels/*')
    gateway_request = await web_adapter.to_gateway_request(payload)
    gateway_request.payload.setdefault('metadata', {})
    gateway_request.payload['metadata'].update({
        'channel_gateway_request_id': request.headers.get('x-request-id') or str(uuid4()),
        'channel_gateway_endpoint': '/channels/web/message',
    })
    return await _forward(gateway_request)


@app.post('/channels/whatsapp/webhook')
async def whatsapp_webhook(payload: WhatsAppWebhook, request: Request):
    _require_mode('adapter', '/channels/*')
    try:
        gateway_request = await whatsapp_adapter.to_gateway_request(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    gateway_request.payload.setdefault('metadata', {})
    gateway_request.payload['metadata'].update({
        'channel_gateway_request_id': request.headers.get('x-request-id') or str(uuid4()),
        'channel_gateway_endpoint': '/channels/whatsapp/webhook',
    })
    return await _forward(gateway_request)


@app.post('/channels/voice/transcript')
async def voice_transcript(payload: VoiceTranscript, request: Request):
    _require_mode('adapter', '/channels/*')
    gateway_request = await voice_adapter.to_gateway_request(payload)
    gateway_request.payload.setdefault('metadata', {})
    gateway_request.payload['metadata'].update({
        'channel_gateway_request_id': request.headers.get('x-request-id') or str(uuid4()),
        'channel_gateway_endpoint': '/channels/voice/transcript',
    })
    return await _forward(gateway_request)


@app.post('/gateway/message')
async def proxy_gateway_message(payload: GatewayRequest, request: Request):
    _require_mode('proxy', '/gateway/message')
    payload.payload.setdefault('metadata', {})
    payload.payload['metadata'].update({
        'channel_gateway_request_id': request.headers.get('x-request-id') or str(uuid4()),
        'channel_gateway_endpoint': '/gateway/message',
        'proxied_by': settings.APP_NAME,
    })
    return await _forward(payload)
