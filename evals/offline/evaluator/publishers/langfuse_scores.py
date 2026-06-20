from __future__ import annotations
import httpx
from evaluator.config.settings import settings
from evaluator.core.models import ConversationRecord, TraceJudgeResult

class LangfuseScorePublisher:
    async def publish_trace_score(self, record: ConversationRecord, result: TraceJudgeResult):
        if not settings.can_publish_langfuse_scores or not record.trace_id:
            return None
        auth = (settings.langfuse_public_key, settings.langfuse_secret_key)
        payloads = [
            {'traceId': record.trace_id, 'name': 'offline_judge_score', 'value': result.judgeScore, 'comment': result.rationale},
            {'traceId': record.trace_id, 'name': 'offline_accuracy_score', 'value': result.accuracyScore, 'comment': result.rationale},
            {'traceId': record.trace_id, 'name': 'offline_alucination_score', 'value': result.alucinationScore, 'comment': result.rationale},
        ]
        async with httpx.AsyncClient(base_url=settings.langfuse_host, timeout=30) as client:
            for payload in payloads:
                resp = await client.post('/api/public/scores', json=payload, auth=auth)
                if resp.status_code >= 400:
                    # Don't fail the run because score publishing is supplementary.
                    return {'ok': False, 'status': resp.status_code, 'body': resp.text}
        return {'ok': True}
