from __future__ import annotations

from .adapters import WebAdapter, WhatsAppAdapter, VoiceAdapter, _merge_context
from .base import ChannelMessage, ChannelResponse

try:
    from agent_framework.config.settings import settings
except Exception:  # pragma: no cover
    settings = None


class ChannelGateway:
    """Normalize and render messages at the Agent Framework boundary.

    This class is used by the Agent Framework backend, not by the external
    Channel Gateway service.

    input_mode semantics:
    - embedded: the backend may use internal channel adapters to interpret
      simple/native channel payloads. This is useful for demos, labs and local
      testing.
    - external: the backend expects a GatewayRequest payload that was already
      normalized by an external Channel Gateway. In this mode the backend does
      not parse native WhatsApp, Voice, Teams, or other channel payloads.

    Backward compatibility:
    - The legacy constructor argument ``mode`` and setting
      ``CHANNEL_GATEWAY_MODE`` are still accepted, but the preferred setting is
      ``FRAMEWORK_CHANNEL_INPUT_MODE``.
    """

    def __init__(self, input_mode: str | None = None, mode: str | None = None):
        configured = (
            input_mode
            or mode
            or getattr(settings, "FRAMEWORK_CHANNEL_INPUT_MODE", None)
            or getattr(settings, "CHANNEL_GATEWAY_MODE", None)
            or "embedded"
        )
        self.input_mode = str(configured).strip().lower()
        if self.input_mode not in {"embedded", "external"}:
            raise ValueError(
                "INVALID_FRAMEWORK_CHANNEL_INPUT_MODE: expected 'embedded' or 'external'"
            )
        # Compatibility with previous code that accessed gateway.mode.
        self.mode = self.input_mode
        self.adapters = {a.name: a for a in [WebAdapter(), WhatsAppAdapter(), VoiceAdapter()]}

    def get(self, channel: str):
        return self.adapters.get(channel, self.adapters["web"])

    def _validate_external_payload(self, channel: str, payload: dict):
        """Validate the payload portion of a GatewayRequest.

        In external input mode, the backend is not accepting native channel
        payloads. It expects req.channel plus req.payload.message at minimum.
        Business keys remain optional because some journeys start without all
        identifiers and are completed by IdentityResolver or the agent.
        """
        if not isinstance(channel, str) or not channel.strip():
            raise ValueError("INVALID_GATEWAY_REQUEST: channel is required")
        if not isinstance(payload, dict):
            raise ValueError("INVALID_GATEWAY_REQUEST: payload must be an object")
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError(
                "INVALID_GATEWAY_REQUEST: payload.message is required and must be a non-empty string"
            )

    async def _normalize_external(self, channel: str, payload: dict) -> ChannelMessage:
        self._validate_external_payload(channel, payload)
        return ChannelMessage(
            channel=channel,
            text=payload.get("message"),
            session_id=payload.get("session_id") or payload.get("session_key"),
            user_id=payload.get("user_id"),
            channel_id=payload.get("channel_id") or payload.get("channelId"),
            context=_merge_context(payload),
        )

    async def normalize(self, channel: str, payload: dict) -> ChannelMessage:
        if self.input_mode == "external":
            return await self._normalize_external(channel, payload)
        return await self.get(channel).normalize(payload)

    async def render(self, response: ChannelResponse) -> dict:
        if self.input_mode == "external":
            # The external Channel Gateway owns the final translation back to
            # WhatsApp, Voice, Teams, etc. The backend returns its canonical
            # response shape.
            return response.model_dump()
        return await self.get(response.channel).render(response)
