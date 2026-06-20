from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def _as_list(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _collect_agent_specific_data(metadata: dict[str, Any], body: dict[str, Any]) -> dict[str, Any] | None:
    prefixed: dict[str, Any] = {}
    for source in (metadata, body):
        for key, value in source.items():
            if key.startswith("agentSpecificData."):
                prefixed[key.removeprefix("agentSpecificData.")] = value
    if prefixed:
        return prefixed

    direct = _first(metadata, "agentSpecificData")
    if isinstance(direct, dict):
        return dict(direct)
    direct = _first(body, "agentSpecificData")
    if isinstance(direct, dict):
        return dict(direct)
    return None


def map_analytics_event_to_tim_flat_payload(
    event_type: str,
    event: dict[str, Any],
    *,
    keep_none: bool = False,
) -> dict[str, Any]:
    """Map the framework analytics envelope to TIM's flat Pub/Sub/NOC schema.

    The canonical fields are published at the JSON root. The only intentional
    nested object is ``agentSpecificData``.
    """
    if not isinstance(event, dict):
        event = {}

    body = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    data: dict[str, Any] = {**body, **metadata}

    token_usage = event.get("token_usage") if isinstance(event.get("token_usage"), dict) else {}

    payload: dict[str, Any] = {
        # Tracking
        "eventType": event.get("eventType") or event_type,
        "traceId": _first(data, "traceId", "trace_id"),
        "spanId": _first(data, "spanId", "span_id"),
        "parentSpanId": _first(data, "parentSpanId", "parent_span_id"),
        "eventName": _first(data, "eventName", "name"),
        "version": _first(data, "version") or "1.0",
        "eventDate": _first(data, "eventDate") or event.get("eventDate") or datetime.now(timezone.utc).isoformat(),
        # Session/channel
        "sessionId": _first(data, "sessionId", "session_id"),
        "channelId": _first(data, "channelId", "channel", "channel_id"),
        "agentId": _first(data, "agentId", "agent_id"),
        "customerCode": _first(data, "customerCode", "customer_code"),
        "touchpoint": _first(data, "touchpoint"),
        "protocol": _first(data, "protocol"),
        "tag": _first(data, "tag") or event.get("eventType") or event_type,
        "noc": True if _first(data, "noc") is True else None,
        # Protocol/session
        "agentProtocolId": _first(data, "agentProtocolId", "agent_protocol_id"),
        "adjustedProtocol": _first(data, "adjustedProtocol", "adjusted_protocol"),
        "sessionCreatedAt": _first(data, "sessionCreatedAt", "session_created_at"),
        "sessionEndAt": _first(data, "sessionEndAt", "session_end_at"),
        # URA/voice
        "uraCallId": _first(data, "uraCallId", "ura_call_id"),
        "transcriptionId": _first(data, "transcriptionId", "transcription_id"),
        "gsm": _first(data, "gsm"),
        "ani": _first(data, "ani"),
        "uraProtocolId": _first(data, "uraProtocolId", "ura_protocol_id"),
        "uraLatency": _first(data, "uraLatency", "ura_latency"),
        "uraResolution": _first(data, "uraResolution", "urResolution", "ura_resolution"),
        "customerMessage": _first(data, "customerMessage", "customer_message"),
        # Message/guardrails/analysis
        "messageId": _first(data, "messageId", "message_id"),
        "blockingGuardrailsOutput": _first(data, "blockingGuardrailsOutput", "blocking_guardrails_output"),
        "blockingGuardrailsInput": _first(data, "blockingGuardrailsInput", "blocking_guardrails_input"),
        "llmResponse": _first(data, "llmResponse", "llm_response"),
        "alucinationScore": _first(data, "alucinationScore", "hallucinationScore", "alucination_score"),
        "noMatchRag": _first(data, "noMatchRag", "no_match_rag"),
        "promptLength": _first(data, "promptLength", "prompt_length"),
        "intention": _first(data, "intention", "intent"),
        "loop": _first(data, "loop"),
        "inferredCsiScore": _first(data, "inferredCsiScore", "inferred_csi_score"),
        "supervisorBlockReasons": _first(data, "supervisorBlockReasons", "supervisor_block_reasons"),
        "resolution": _first(data, "resolution"),
        "ConversationPrecision": _first(data, "ConversationPrecision", "conversationPrecision", "conversation_precision"),
        # LLM metrics
        "model": _first(data, "model") or event.get("model"),
        "tokenInput": _first(token_usage, "input_tokens") or _first(data, "tokenInput", "input_tokens"),
        "tokenOutput": _first(token_usage, "output_tokens") or _first(data, "tokenOutput", "output_tokens"),
        "latencyMs": _first(data, "latencyMs", "duration_ms"),
        "toxicityScore": _first(data, "toxicityScore", "toxicity_score"),
        "nps": _first(data, "nps"),
        "judgeScore": _first(data, "judgeScore", "judge_score"),
        "accuracyScore": _first(data, "accuracyScore", "accuracy_score"),
        "guardrails": _first(data, "guardrails"),
        # RAG
        "ragRetrievedDocuments": _as_list(_first(data, "documentsRetrieved", "ragRetrievedDocuments")),
        "ragSelectedDocuments": _as_list(_first(data, "documentsSelected", "ragSelectedDocuments")),
        # API
        "apiUrl": _first(data, "apiUrl", "api_url"),
        "apiStatusCode": _first(data, "httpStatusCode", "apiStatusCode", "http_status_code"),
        "apiResponsePayload": _first(data, "apiResponsePayload", "api_response_payload"),
        # I/O
        "inputData": _first(data, "inputData", "input_data"),
        "outputData": _first(data, "outputData", "output_data"),
        # Business/status/sequence
        "agentSpecificData": _collect_agent_specific_data(metadata, body),
        "status": _first(data, "status"),
        "sequence": _first(data, "sequence"),
    }

    if keep_none:
        return {k: ("" if v is None else v) for k, v in payload.items()}
    return {k: v for k, v in payload.items() if v is not None}
