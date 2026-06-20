from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class BusinessContext(BaseModel):
    customer_key: str | None = None
    contract_key: str | None = None
    interaction_key: str | None = None
    account_key: str | None = None
    resource_key: str | None = None
    session_key: str | None = None
    protocol_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WebMessage(BaseModel):
    message: str
    session_id: str | None = None
    user_id: str | None = None
    message_id: str | None = None
    customer_key: str | None = None
    contract_key: str | None = None
    interaction_key: str | None = None
    account_key: str | None = None
    resource_key: str | None = None
    session_key: str | None = None
    business_context: BusinessContext | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WhatsAppWebhook(BaseModel):
    wa_id: str | None = None
    from_: str | None = Field(default=None, alias="from")
    message: str | None = None
    text: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    interactive_id: str | None = None
    interactive_title: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    customer_key: str | None = None
    contract_key: str | None = None
    interaction_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VoiceTranscript(BaseModel):
    transcript: str
    call_id: str | None = None
    caller: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    confidence: float | None = None
    language: str | None = None
    customer_key: str | None = None
    contract_key: str | None = None
    interaction_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GatewayRequest(BaseModel):
    channel: str
    payload: dict[str, Any]
    agent_id: str | None = None
    tenant_id: str | None = None


class GatewayResponse(BaseModel):
    channel: str | None = None
    session_id: str | None = None
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
