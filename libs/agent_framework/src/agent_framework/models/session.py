from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

class SessionContext(BaseModel):
    tenant_id: str = 'default'
    agent_id: str = 'default_agent'
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str | None = None
    msisdn: str | None = None
    asset_id: str | None = None
    social_sec_no: str | None = None
    invoice_id: str | None = None
    channel: str = 'web'
    channel_id: str | None = None
    ani: str | None = None
    ura_call_id: str | None = None
    past_invoice_number: str | None = None
    current_invoice_due_date: str | None = None
    past_invoice_due_date: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatMessage(BaseModel):
    role: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
