from __future__ import annotations
import json
import re
from collections import defaultdict
from evaluator.config.settings import settings
from evaluator.core.models import ConversationRecord, TraceJudgeResult, SessionJudgeResult
from evaluator.llm.client import LLMClient, create_llm_client
from evaluator.prompts.loader import load_prompt


def _json_from_text(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def _history(record: ConversationRecord, max_chars: int = 6000) -> str:
    if record.messages:
        text = "\n".join(f"{m.role}: {m.content}" for m in record.messages)
    else:
        text = f"user: {record.input_text}\nagent: {record.output_text}"
    return text[-max_chars:]


class TIMStyleLLMJudge:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or create_llm_client()
        self.trace_prompt = load_prompt(settings.trace_prompt_path, 'trace_metrics')
        self.session_prompt = load_prompt(settings.session_prompt_path, 'session_metrics')

    async def judge_trace(self, record: ConversationRecord) -> TraceJudgeResult:
        prompt = f"""{self.trace_prompt}

HISTÓRICO:
{_history(record)}

MENSAGEM DO USUÁRIO:
{record.input_text}

RESPOSTA DO AGENTE:
{record.output_text}

METADATA:
{json.dumps(record.metadata, ensure_ascii=False, default=str)}
"""
        raw = await self.llm.complete(prompt)
        data = _json_from_text(raw)
        data.setdefault("judge_name", "trace_metrics")
        data.setdefault("judge_type", "trace")
        data.setdefault("judgeScore", data.get("judge_score", 0))
        data.setdefault("accuracyScore", data.get("accuracy_score", 0))
        data.setdefault("alucinationScore", data.get("alucination_score", 1))
        data.setdefault("rationale", data.get("reasoning", ""))
        return TraceJudgeResult(**data)

    async def judge_sessions(self, records: list[ConversationRecord]) -> dict[str, SessionJudgeResult]:
        grouped: dict[str, list[ConversationRecord]] = defaultdict(list)
        for r in records:
            grouped[r.session_id].append(r)
        out = {}
        for session_id, items in grouped.items():
            transcript = "\n".join(_history(r, 3000) for r in items)[-9000:]
            prompt = f"""{self.session_prompt}

TRANSCRIÇÃO DA SESSÃO:
{transcript}
"""
            raw = await self.llm.complete(prompt)
            data = _json_from_text(raw)
            data.setdefault("judge_name", "session_metrics")
            data.setdefault("judge_type", "session")
            data.setdefault("inferredCsiScore", data.get("inferred_csi_score", 0))
            data.setdefault("resolution", data.get("resolution", 0))
            data.setdefault("conversationPrecision", data.get("conversation_precision", 0))
            data.setdefault("rationale", data.get("reasoning", ""))
            out[session_id] = SessionJudgeResult(**data)
        return out
