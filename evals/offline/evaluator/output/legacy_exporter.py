from __future__ import annotations

import gzip
from pathlib import Path
from datetime import datetime
from typing import Any
import json

from evaluator.config.settings import settings
from evaluator.persistence.repository import EvaluationRepository
from evaluator.analytics.vloop import vloop_flag

HEADER = [
    "judgeScore", "accuracyScore", "alucinationScore", "promptLength", "loop",
    "inferredCsiScore", "resolution", "conversationPrecision",
    "uraCallId", "channelId", "sessionId", "messageId"
]


def _q(v) -> str:
    return '"' + str("" if v is None else v).replace('"', '""') + '"'


def export_legacy_txt_gz(repo: EvaluationRepository, run_id: str, agent_id: str) -> Path:
    output_dir = settings.path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"AGENTE_{agent_id}_LLM_JUDGE_{datetime.now().strftime('%Y%m%d')}.TXT.GZ"

    with repo.store.connect() as conn:
        cur = conn.cursor()

        cur.execute(f"""
            select SESSION_ID, INFERRED_CSI_SCORE, RESOLUTION, CONVERSATION_PRECISION
              from {repo.store.t('EVALUATION_RESULT')}
             where RUN_ID = :run_id
               and JUDGE_TYPE = 'SESSION'
        """, {"run_id": run_id})

        session_metrics = {
            sid: {
                "inferredCsiScore": csi,
                "resolution": res,
                "conversationPrecision": prec,
            }
            for sid, csi, res, prec in cur.fetchall()
        }

        cur.execute(f"""
            select r.TRACE_ID, r.SESSION_ID, r.JUDGE_SCORE, r.ACCURACY_SCORE,
                   r.ALUCINATION_SCORE, r.RATIONALE, i.CHANNEL, i.MESSAGE_ID, i.RAW_JSON
              from {repo.store.t('EVALUATION_RESULT')} r
              left join {repo.store.t('EVALUATION_ITEM')} i on i.ITEM_ID = r.ITEM_ID
             where r.RUN_ID = :run_id
               and r.JUDGE_TYPE = 'TRACE'
             order by r.CREATED_AT
        """, {"run_id": run_id})

        rows = cur.fetchall()

    with gzip.open(path, "wt", encoding="utf-8") as f:
        for trace_id, session_id, judge, accuracy, alucination, rationale, channel, message_id, raw_json in rows:
            session = session_metrics.get(session_id, {})

            raw: dict[str, Any] = {}
            ura_call_id = ""
            channel_id = channel or ""
            prompt_length = 0
            loop = 0

            try:
                from evaluator.persistence.oracle_store import _json_loads

                # raw = _json_loads(
                #     raw_json.read() if hasattr(raw_json, "read") else raw_json,
                #     {},
                # )
                raw = normalize_raw(raw_json)

                metadata = raw.get("metadata") or {}

                channel_id = (
                        metadata.get("channel_id")
                        or metadata.get("channelId")
                        or metadata.get("channel")
                        or channel_id
                )

                ura_call_id = extract_ura_call_id(raw, metadata, message_id)
                prompt_length = extract_prompt_length(raw)
                loop = vloop_flag(raw)

                # print(
                #     "[DEBUG promptLength]",
                #     "trace_id=", trace_id,
                #     "type(raw)=", type(raw),
                #     "keys=", list(raw.keys())[:20] if isinstance(raw, dict) else None,
                #     "prompt_length=", prompt_length,
                #     "input_text_len=", len(str(raw.get("input_text") or "")) if isinstance(raw, dict) else None,
                #     "messages=", len(raw.get("messages") or []) if isinstance(raw, dict) else None,
                # )

            except Exception as exc:
                print(f"[legacy_exporter] metadata extraction failed trace_id={trace_id}: {exc}")

            vals = [
                judge,
                accuracy,
                alucination,
                prompt_length,
                loop,
                session.get("inferredCsiScore"),
                session.get("resolution"),
                session.get("conversationPrecision"),
                ura_call_id,
                channel_id,
                session_id,
                message_id or trace_id,
                ]

            f.write("|;".join(_q(v) for v in vals) + "\n")

        f.write("|;".join([_q("TOTAL"), _q(len(rows))]) + "\n")

    return path

def extract_ura_call_id(raw: dict, metadata: dict | None = None, message_id: str | None = None) -> str:
    metadata = metadata or {}

    business_context = (
            metadata.get("business_context")
            or metadata.get("businessContext")
            or raw.get("business_context")
            or raw.get("businessContext")
            or raw.get("metadata", {}).get("business_context")
            or raw.get("metadata", {}).get("businessContext")
            or {}
    )

    if not isinstance(business_context, dict):
        business_context = {}

    trace = raw.get("raw", {}).get("trace", {}) or raw.get("trace", {}) or {}
    detail = raw.get("raw", {}).get("detail", {}) or raw.get("detail", {}) or {}

    trace_input = trace.get("input") or {}
    detail_input = detail.get("input") or {}

    trace_metadata = trace.get("metadata") or {}
    detail_metadata = detail.get("metadata") or {}

    trace_bc = trace_input.get("business_context") or {}
    detail_bc = detail_input.get("business_context") or {}

    return str(
        business_context.get("interaction_key")
        or business_context.get("ura_call_id")
        or metadata.get("ura_call_id")
        or metadata.get("uraCallId")
        or metadata.get("interaction_key")
        or trace_metadata.get("ura_call_id")
        or detail_metadata.get("ura_call_id")
        or trace_bc.get("interaction_key")
        or detail_bc.get("interaction_key")
        or message_id
        or ""
    )

def normalize_raw(raw):
    if hasattr(raw, "read"):
        raw = raw.read()

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        raw = json.loads(raw)

    # caso esteja duplamente serializado
    if isinstance(raw, str):
        raw = json.loads(raw)

    return raw if isinstance(raw, dict) else {}

def extract_prompt_length(raw: dict) -> int:
    # 1. tokens reais do Langfuse/framework
    tokens = find_prompt_tokens(raw)
    if tokens > 0:
        return tokens

    # 2. input_size dos spans
    input_size = find_input_size(raw)
    if input_size > 0:
        return input_size

    # 3. fallback garantido pelo ConversationRecord
    return (
            len(str(raw.get("input_text") or ""))
            + len(str(raw.get("output_text") or ""))
            + sum(
        len(str(m.get("content") or ""))
        for m in raw.get("messages", [])
        if isinstance(m, dict)
    )
    )

def _walk(obj):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)


def _to_positive_int(value) -> int:
    try:
        n = int(value)
        return n if n > 0 else 0
    except Exception:
        return 0


def find_prompt_tokens(raw: dict) -> int:
    candidates = []

    for obj in _walk(raw):
        for key in (
                "prompt_tokens",
                "promptTokens",
                "input_tokens",
                "inputTokens",
        ):
            n = _to_positive_int(obj.get(key))
            if n:
                candidates.append(n)

        usage = obj.get("usage")
        if isinstance(usage, dict):
            for key in ("input", "prompt_tokens", "promptTokens", "input_tokens", "inputTokens"):
                n = _to_positive_int(usage.get(key))
                if n:
                    candidates.append(n)

        usage_details = obj.get("usageDetails") or obj.get("usage_details")
        if isinstance(usage_details, dict):
            for key in ("input", "prompt_tokens", "promptTokens", "input_tokens", "inputTokens"):
                n = _to_positive_int(usage_details.get(key))
                if n:
                    candidates.append(n)

    return max(candidates) if candidates else 0


def find_input_size(raw: dict) -> int:
    candidates = []

    for obj in _walk(raw):
        for key in ("input_size", "inputSize"):
            n = _to_positive_int(obj.get(key))
            if n:
                candidates.append(n)

    return max(candidates) if candidates else 0

def calculate_text_length(raw: dict) -> int:
    return (
            len(str(raw.get("input_text") or ""))
            + len(str(raw.get("output_text") or ""))
            + sum(
        len(str(m.get("content") or ""))
        for m in raw.get("messages", [])
        if isinstance(m, dict)
    )
    )