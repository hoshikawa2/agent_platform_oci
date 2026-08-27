from .base import ChannelAdapter, ChannelMessage, ChannelResponse


def _merge_context(payload: dict) -> dict:
    """Preserva todo payload como contexto.

    Antes o WebAdapter só copiava payload["context"]. Com isso, campos como
    business_context, msisdn, invoice_id e ura_call_id eram perdidos antes de
    chegar ao workflow/MCP.
    """
    payload = dict(payload or {})
    ctx = dict(payload.get("context") or {})
    for k, v in payload.items():
        if k != "context" and k not in ctx:
            ctx[k] = v
    return ctx


class WebAdapter(ChannelAdapter):
    name = "web"

    async def normalize(self, payload):
        payload = payload or {}
        text = payload.get("message") or payload.get("text") or payload.get("content") or ""
        return ChannelMessage(
            channel="web",
            text=text,
            session_id=payload.get("session_id"),
            user_id=payload.get("user_id"),
            channel_id=payload.get("channel_id") or payload.get("channelId"),
            context=_merge_context(payload),
        )

    async def render(self, response):
        return response.model_dump()


class WhatsAppAdapter(ChannelAdapter):
    name = "whatsapp"

    async def normalize(self, payload):
        payload = payload or {}
        return ChannelMessage(
            channel="whatsapp",
            channel_id=payload.get("from"),
            text=payload.get("text") or payload.get("message") or "",
            session_id=payload.get("session_id"),
            context=_merge_context(payload),
        )

    async def render(self, response):
        return {"to": response.metadata.get("channel_id"), "text": response.text, "session_id": response.session_id}


class VoiceAdapter(ChannelAdapter):
    name = "voice"

    async def normalize(self, payload):
        payload = payload or {}
        return ChannelMessage(
            channel="voice",
            channel_id=payload.get("ani"),
            text=payload.get("transcript") or payload.get("text") or payload.get("message") or "",
            session_id=payload.get("session_id"),
            context=_merge_context(payload),
        )

    async def render(self, response):
        return {"speak": response.text, "session_id": response.session_id}
