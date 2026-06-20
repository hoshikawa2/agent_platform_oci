from pydantic import BaseModel, Field
from typing import Any

class ChannelMessage(BaseModel):
    channel: str
    channel_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    text: str
    context: dict[str, Any] = Field(default_factory=dict)

class ChannelResponse(BaseModel):
    channel: str
    session_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class ChannelAdapter:
    name = 'base'
    async def normalize(self, payload: dict) -> ChannelMessage: ...
    async def render(self, response: ChannelResponse) -> dict: ...
