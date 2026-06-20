from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from evaluator.collectors.base import ConversationCollector
from evaluator.config.settings import settings
from evaluator.core.models import ConversationMessage, ConversationRecord
from evaluator.identity.resolver import IdentityResolver
from evaluator.config.settings import settings

def _iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _metadata(obj: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}
    meta = obj.get("metadata") or {}
    return meta if isinstance(meta, dict) else {}


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _content_to_text(value: Any) -> str:
    """Convert Langfuse/OpenAI-style content payloads to plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = _content_to_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        # OpenAI multimodal content often comes as {"type":"text","text":"..."}
        for key in ("text", "content", "message", "value", "input", "output", "completion"):
            if key in value:
                text = _content_to_text(value.get(key))
                if text:
                    return text
        # Chat completion response variants.
        choices = value.get("choices")
        if isinstance(choices, list) and choices:
            return _content_to_text(choices[0])
        msg = value.get("message")
        if isinstance(msg, dict):
            return _content_to_text(msg.get("content"))
        return ""
    return str(value)


def _messages_from_value(value: Any, default_role: str) -> list[ConversationMessage]:
    """Extract chat messages from strings/lists/dicts returned by Langfuse."""
    if value in (None, "", [], {}):
        return []

    if isinstance(value, str):
        text = value.strip()
        return [ConversationMessage(role=default_role, content=text)] if text else []

    if isinstance(value, dict):
        # Common wrappers: {"messages": [...]}, {"input": ...}, {"output": ...}
        for key in ("messages", "conversation", "chat"):
            if isinstance(value.get(key), list):
                return _messages_from_value(value[key], default_role)

        if "role" in value and "content" in value:
            role = str(value.get("role") or default_role)
            content = _content_to_text(value.get("content")).strip()
            return [ConversationMessage(role=role, content=content, metadata={"source": "langfuse"})] if content else []

        text = _content_to_text(value).strip()
        return [ConversationMessage(role=default_role, content=text, metadata={"source": "langfuse"})] if text else []

    if isinstance(value, list):
        out: list[ConversationMessage] = []
        for item in value:
            out.extend(_messages_from_value(item, default_role))
        return out

    text = _content_to_text(value).strip()
    return [ConversationMessage(role=default_role, content=text, metadata={"source": "langfuse"})] if text else []


def _agent_id(trace: dict[str, Any], detail: dict[str, Any] | None = None) -> str | None:
    detail = detail or {}
    meta = {**_metadata(trace), **_metadata(detail)}
    return (
        meta.get("agent_id")
        or meta.get("agentId")
        or meta.get("agent")
        or detail.get("name")
        or trace.get("name")
    )


def _channel(trace: dict[str, Any], detail: dict[str, Any] | None = None) -> str | None:
    detail = detail or {}
    meta = {**_metadata(trace), **_metadata(detail)}
    return meta.get("channel") or meta.get("channel_id") or meta.get("channelId")


def _observation_sort_key(obs: dict[str, Any]) -> str:
    return str(
        obs.get("startTime")
        or obs.get("start_time")
        or obs.get("createdAt")
        or obs.get("created_at")
        or obs.get("timestamp")
        or ""
    )


class LangfuseCollector(ConversationCollector):
    """Collect traces from Langfuse and hydrate each trace with detail/observations.

    The list endpoint often returns only trace metadata. If we judge that directly,
    prompts reach the LLM as empty conversations and the judge correctly returns
    "Conversa vazia"/"Resposta vazia". This collector therefore fetches each trace
    detail and observations before building ConversationRecord.
    """

    def __init__(self):
        self.identity_resolver = IdentityResolver(settings.identity_config_path)

    async def collect(
        self,
        period_start: datetime,
        period_end: datetime,
        agent_aliases: set[str] | None = None,
        limit: int | None = None,
    ) -> list[ConversationRecord]:
        if not settings.can_use_langfuse:
            raise RuntimeError(
                "Langfuse disabled or credentials missing. Set ENABLE_LANGFUSE=true and LANGFUSE_PUBLIC_KEY/SECRET_KEY."
            )

        params = {
            "fromTimestamp": _iso_z(period_start),
            "toTimestamp": _iso_z(period_end),
            "limit": limit or 100,
        }
        auth = (settings.langfuse_public_key, settings.langfuse_secret_key)
        aliases = {a for a in (agent_aliases or set()) if a}

        async with httpx.AsyncClient(base_url=settings.langfuse_host, timeout=60) as client:
            response = await client.get("/api/public/traces", params=params, auth=auth)
            if response.status_code >= 400:
                raise RuntimeError(f"Langfuse traces API failed {response.status_code}: {response.text}")
            payload = response.json()
            traces = payload.get("data") or payload.get("traces") or []

            records: list[ConversationRecord] = []
            for trace in traces:
                if not isinstance(trace, dict):
                    continue
                trace_id = trace.get("id")
                detail = await self._fetch_trace_detail(client, trace_id, auth) if trace_id else {}
                observations = await self._fetch_observations(client, trace_id, auth) if trace_id else []

                agent_id = _agent_id(trace, detail)
                if aliases and agent_id and agent_id not in aliases:
                    continue

                record = self._to_record(trace, detail, observations, agent_id)
                # Do not send empty traces to the LLM judge. Empty records produce
                # valid but misleading scores such as "Conversa vazia".
                if not (record.input_text or record.output_text or record.messages):
                    continue
                records.append(record)

        return records

    async def _fetch_trace_detail(
        self,
        client: httpx.AsyncClient,
        trace_id: str,
        auth: tuple[str | None, str | None],
    ) -> dict[str, Any]:
        # Langfuse versions differ slightly. This endpoint works in current public API;
        # if unavailable, the collector falls back to the list payload.
        response = await client.get(f"/api/public/traces/{trace_id}", auth=auth)
        if response.status_code >= 400:
            return {}
        payload = response.json()
        if isinstance(payload, dict):
            return payload.get("data") if isinstance(payload.get("data"), dict) else payload
        return {}

    async def _fetch_observations(
        self,
        client: httpx.AsyncClient,
        trace_id: str,
        auth: tuple[str | None, str | None],
    ) -> list[dict[str, Any]]:
        # Try common Langfuse public API shapes. Ignore failures because trace detail
        # may already contain observations in some versions.
        candidates = [
            ("/api/public/observations", {"traceId": trace_id, "limit": 100}),
            ("/api/public/observations", {"trace_id": trace_id, "limit": 100}),
        ]
        for path, params in candidates:
            response = await client.get(path, params=params, auth=auth)
            if response.status_code >= 400:
                continue
            payload = response.json()
            items = payload.get("data") or payload.get("observations") or [] if isinstance(payload, dict) else []
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
        return []

    def _to_record(
        self,
        trace: dict[str, Any],
        detail: dict[str, Any],
        observations: list[dict[str, Any]],
        agent_id: str | None,
    ) -> ConversationRecord:
        meta = {**_metadata(trace), **_metadata(detail)}
        trace_id = trace.get("id") or detail.get("id")
        session_id = (
            detail.get("sessionId")
            or detail.get("session_id")
            or trace.get("sessionId")
            or trace.get("session_id")
            or trace_id
        )

        # Detail payload may already include observations.
        detail_observations = detail.get("observations") or []
        if isinstance(detail_observations, list):
            observations = [*observations, *[x for x in detail_observations if isinstance(x, dict)]]
        observations = sorted(observations, key=_observation_sort_key)

        input_value = _first_value(
            detail.get("input"),
            trace.get("input"),
            meta.get("input"),
            meta.get("user_message"),
            meta.get("message"),
            meta.get("question"),
        )
        output_value = _first_value(
            detail.get("output"),
            trace.get("output"),
            meta.get("output"),
            meta.get("response"),
            meta.get("answer"),
        )

        messages: list[ConversationMessage] = []
        messages.extend(_messages_from_value(input_value, "user"))
        messages.extend(_messages_from_value(output_value, "assistant"))

        for obs in observations:
            obs_meta = _metadata(obs)
            obs_kind = str(obs.get("type") or obs.get("name") or "observation").lower()
            source_meta = {"source": "langfuse_observation", "observation_id": obs.get("id"), "observation_type": obs_kind}
            if obs_meta:
                source_meta["metadata"] = obs_meta

            # Prefer preserving explicit chat roles from observation input.
            before = len(messages)
            messages.extend(_messages_from_value(obs.get("input"), "user"))
            for m in messages[before:]:
                m.metadata.update(source_meta)

            before = len(messages)
            default_output_role = "assistant" if obs_kind in {"generation", "span", "event", "observation"} else "assistant"
            messages.extend(_messages_from_value(obs.get("output"), default_output_role))
            for m in messages[before:]:
                m.metadata.update(source_meta)

        messages = self._deduplicate_messages(messages)

        input_text = _content_to_text(input_value).strip()
        output_text = _content_to_text(output_value).strip()

        if not input_text:
            first_user = next((m.content for m in messages if m.role.lower() in {"user", "human"} and m.content), "")
            input_text = first_user.strip()
        if not output_text:
            last_assistant = next(
                (m.content for m in reversed(messages) if m.role.lower() in {"assistant", "agent", "ai"} and m.content),
                "",
            )
            output_text = last_assistant.strip()

        raw = {"trace": trace, "detail": detail, "observations": observations}

        identity_payload = {
            **(trace.get("metadata") or {}),
            **(trace.get("input") or {}),
            "business_context": (trace.get("input") or {}).get("business_context") or {},
            "session_id": trace.get("sessionId") or trace.get("id"),
            "message_id": (trace.get("input") or {}).get("message_id"),
            "conversation_key": (trace.get("input") or {}).get("conversation_key"),
        }

        business_context = self.identity_resolver.resolve(identity_payload)

        metadata = {
            **(trace.get("metadata") or {}),
            "business_context": business_context,
            "ura_call_id": business_context.get("interaction_key"),
        }
        channel = (
                trace.get("metadata", {}).get("channel")
                or trace.get("input", {}).get("channel")
                or trace.get("input", {}).get("metadata", {}).get("channel")
                or "web"
        )

        return ConversationRecord(
            trace_id=trace_id,
            session_id=business_context.get("session_key") or trace_id,
            message_id=business_context.get("interaction_key") or trace_id,
            agent_id=agent_id,
            channel=channel,
            input_text=input_text,
            output_text=output_text,
            messages=messages,
            metadata=metadata,
            raw=raw,
        )

    def _deduplicate_messages(self, messages: list[ConversationMessage]) -> list[ConversationMessage]:
        out: list[ConversationMessage] = []
        seen: set[tuple[str, str]] = set()
        for msg in messages:
            content = (msg.content or "").strip()
            if not content:
                continue
            key = (msg.role.lower(), content)
            if key in seen:
                continue
            seen.add(key)
            msg.content = content
            out.append(msg)
        return out
