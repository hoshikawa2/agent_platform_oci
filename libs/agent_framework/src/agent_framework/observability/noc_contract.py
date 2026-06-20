from __future__ import annotations

"""Contrato NOC.001..NOC.006 da Fundação TIM.

Helpers opcionais para padronizar os payloads NOC operacionais. Eles não
substituem observer.emit_noc(); apenas reduzem erro de campos e nomes.
"""

import time
from typing import Any

BASE_FIELDS = (
    "uraCallId",
    "sessionId",
    "messageId",
    "transcriptionId",
    "gsm",
    "ani",
    "tag",
    "agentId",
    "channelId",
    "eventDate",
    "agentVersion",
)


def epoch_millis() -> int:
    return int(time.time() * 1000)


def base_payload(context: dict[str, Any] | None = None, *, tag: str) -> dict[str, Any]:
    ctx = dict(context or {})
    payload = {
        "uraCallId": ctx.get("uraCallId") or ctx.get("ura_call_id") or "",
        "sessionId": ctx.get("sessionId") or ctx.get("session_id") or "",
        "messageId": ctx.get("messageId") or ctx.get("message_id") or "",
        "transcriptionId": ctx.get("transcriptionId") or ctx.get("transcription_id") or "",
        "gsm": ctx.get("gsm") or ctx.get("msisdn") or "",
        "ani": ctx.get("ani") or ctx.get("ANI") or "",
        "tag": tag,
        "agentId": ctx.get("agentId") or ctx.get("agent_id") or ctx.get("agent") or "",
        "channelId": ctx.get("channelId") or ctx.get("channel_id") or ctx.get("channel") or "",
        "eventDate": ctx.get("eventDate") or epoch_millis(),
        "agentVersion": ctx.get("agentVersion") or ctx.get("agent_version") or "",
    }
    return payload


def noc_001_trace_started(context: dict[str, Any] | None = None) -> dict[str, Any]:
    return base_payload(context, tag="NOC.001")


def noc_002_invalid_api_response(
    context: dict[str, Any] | None = None,
    *,
    retry_count: int = 0,
    latency_ms: int | float = 0,
    api_url: str = "",
    status_code: int | str = "",
) -> dict[str, Any]:
    payload = base_payload(context, tag="NOC.002")
    payload.update({"retryCount": retry_count, "latencyMs": int(latency_ms), "apiUrl": api_url, "statusCode": status_code})
    return payload


def noc_003_database_latency(
    context: dict[str, Any] | None = None,
    *,
    latency_ms: int | float,
    resource_name: str,
) -> dict[str, Any]:
    payload = base_payload(context, tag="NOC.003")
    payload.update({"latencyMs": int(latency_ms), "resourceName": resource_name})
    return payload


def noc_004_inconsistent_llm_response(
    context: dict[str, Any] | None = None,
    *,
    latency_ms: int | float = 0,
    llm_endpoint: str = "",
    model_name: str = "",
) -> dict[str, Any]:
    payload = base_payload(context, tag="NOC.004")
    payload.update({"latencyMs": int(latency_ms), "llmEndpoint": llm_endpoint, "modelName": model_name})
    return payload


def noc_005_fatal_exception(
    context: dict[str, Any] | None = None,
    *,
    exception_type: str = "",
    message: str = "",
) -> dict[str, Any]:
    payload = base_payload(context, tag="NOC.005")
    payload.update({"exceptionType": exception_type, "message": message})
    return payload


def noc_006_flow_latency(
    context: dict[str, Any] | None = None,
    *,
    latency_ms: int | float = 0,
) -> dict[str, Any]:
    payload = base_payload(context, tag="NOC.006")
    payload.update({"latencyMs": int(latency_ms)})
    return payload
