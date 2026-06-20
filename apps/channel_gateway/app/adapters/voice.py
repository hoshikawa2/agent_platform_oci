from __future__ import annotations

from app.schemas import BusinessContext, GatewayRequest, VoiceTranscript
from app.settings import settings


class VoiceAdapter:
    name = 'voice'

    async def to_gateway_request(self, payload: VoiceTranscript) -> GatewayRequest:
        session_id = payload.session_id or payload.call_id
        message_id = payload.message_id or (f'{payload.call_id}-turn-1' if payload.call_id else None)
        bc = BusinessContext(
            customer_key=payload.customer_key or payload.caller,
            contract_key=payload.contract_key,
            interaction_key=payload.interaction_key or payload.call_id,
            session_key=session_id,
            metadata={
                'source_channel': 'voice',
                'confidence': payload.confidence,
                'language': payload.language,
                **(payload.metadata or {}),
            },
        )
        data = {
            'message': payload.transcript,
            'session_id': session_id,
            'user_id': payload.caller,
            'message_id': message_id,
            'customer_key': bc.customer_key,
            'contract_key': bc.contract_key,
            'interaction_key': bc.interaction_key,
            'session_key': bc.session_key,
            'business_context': bc.model_dump(exclude_none=True),
            'metadata': {
                **(payload.metadata or {}),
                'external_gateway': settings.APP_NAME,
                'source_channel': 'voice',
                'call_id': payload.call_id,
                'confidence': payload.confidence,
                'language': payload.language,
                'contract_version': 'gateway-request-v1',
            },
        }
        return GatewayRequest(channel='voice', tenant_id=settings.DEFAULT_TENANT_ID, agent_id=settings.DEFAULT_AGENT_ID, payload=data)
