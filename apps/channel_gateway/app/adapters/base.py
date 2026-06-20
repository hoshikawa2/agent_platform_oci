from __future__ import annotations

from typing import Protocol
from app.schemas import GatewayRequest


class ChannelAdapter(Protocol):
    name: str
    async def to_gateway_request(self, payload) -> GatewayRequest: ...
