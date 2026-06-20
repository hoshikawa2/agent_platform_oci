from __future__ import annotations

from app.schemas import BusinessContext, GatewayRequest, WebMessage
from app.settings import settings


class WebAdapter:
    name = 'web'

    async def to_gateway_request(self, payload: WebMessage) -> GatewayRequest:
        bc = payload.business_context or BusinessContext(
            customer_key=payload.customer_key,
            contract_key=payload.contract_key,
            interaction_key=payload.interaction_key,
            account_key=payload.account_key,
            resource_key=payload.resource_key,
            session_key=payload.session_key or payload.session_id,
            metadata={'source_channel': 'web', **(payload.metadata or {})},
        )
        data = payload.model_dump(exclude_none=True)
        data['business_context'] = bc.model_dump(exclude_none=True)
        data.setdefault('session_key', payload.session_key or payload.session_id)
        data.setdefault('metadata', {})
        data['metadata'] = {
            **(data.get('metadata') or {}),
            'external_gateway': settings.APP_NAME,
            'source_channel': 'web',
            'contract_version': 'gateway-request-v1',
        }
        return GatewayRequest(
            channel='web',
            tenant_id=settings.DEFAULT_TENANT_ID,
            agent_id=settings.DEFAULT_AGENT_ID,
            payload=data,
        )
