from __future__ import annotations

import httpx
from .settings import settings
from .schemas import GatewayRequest


class AgentFrameworkClient:
    def __init__(self):
        self.url = settings.AGENT_FRAMEWORK_BASE_URL.rstrip('/') + settings.AGENT_FRAMEWORK_GATEWAY_PATH

    async def send(self, request: GatewayRequest) -> dict:
        headers = {'Content-Type': 'application/json'}
        if settings.INTERNAL_GATEWAY_TOKEN:
            headers['X-Channel-Gateway-Token'] = settings.INTERNAL_GATEWAY_TOKEN
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(self.url, json=request.model_dump(exclude_none=True), headers=headers)
            try:
                data = resp.json()
            except Exception:
                data = {'text': resp.text}
            if resp.status_code >= 400:
                return {
                    'ok': False,
                    'status_code': resp.status_code,
                    'error': data,
                    'forwarded_to': self.url,
                }
            if isinstance(data, dict):
                data.setdefault('ok', True)
                data.setdefault('forwarded_to', self.url)
                return data
            return {'ok': True, 'data': data, 'forwarded_to': self.url}
