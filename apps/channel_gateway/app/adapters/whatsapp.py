from __future__ import annotations

from app.schemas import BusinessContext, GatewayRequest, WhatsAppWebhook
from app.settings import settings


class WhatsAppAdapter:
    name = 'whatsapp'

    async def to_gateway_request(self, payload: WhatsAppWebhook) -> GatewayRequest:
        user_id = payload.wa_id or payload.from_
        text = payload.message or payload.text or payload.interactive_title or payload.interactive_id
        if not text:
            raise ValueError('INVALID_WHATSAPP_PAYLOAD: message/text/interactive_title is required')
        session_id = payload.session_id or user_id
        message_id = payload.message_id or payload.interaction_key
        bc = BusinessContext(
            customer_key=payload.customer_key or user_id,
            contract_key=payload.contract_key,
            interaction_key=payload.interaction_key or message_id,
            session_key=session_id,
            metadata={'source_channel': 'whatsapp', **(payload.metadata or {})},
        )
        data = {
            'message': text,
            'session_id': session_id,
            'user_id': user_id,
            'message_id': message_id,
            'customer_key': bc.customer_key,
            'contract_key': bc.contract_key,
            'interaction_key': bc.interaction_key,
            'session_key': bc.session_key,
            'business_context': bc.model_dump(exclude_none=True),
            'metadata': {
                **(payload.metadata or {}),
                'external_gateway': settings.APP_NAME,
                'source_channel': 'whatsapp',
                'interactive_id': payload.interactive_id,
                'contract_version': 'gateway-request-v1',
            },
        }
        return GatewayRequest(channel='whatsapp', tenant_id=settings.DEFAULT_TENANT_ID, agent_id=settings.DEFAULT_AGENT_ID, payload=data)
