from __future__ import annotations
import inspect, json, random
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable
from evaluator.collectors.base import ConversationCollector
from evaluator.collectors.langfuse import LangfuseCollector
from evaluator.collectors.agent_framework import AgentFrameworkCollector
from evaluator.collectors.mock import MockCollector
from evaluator.config.agents import AgentConfig
from evaluator.config.settings import settings
from evaluator.core.models import ConversationRecord, RunStatus
from evaluator.judges.llm_judge import TIMStyleLLMJudge
from evaluator.output.legacy_exporter import export_legacy_txt_gz
from evaluator.persistence.repository import EvaluationRepository
from evaluator.publishers.langfuse_scores import LangfuseScorePublisher

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

class EvaluationEngine:
    def __init__(self, repository: EvaluationRepository | None=None, progress_callback: ProgressCallback | None=None):
        self.repository = repository or EvaluationRepository(auto_init_schema=False)
        self.progress_callback = progress_callback
        self.judge = TIMStyleLLMJudge()
        self.langfuse_publisher = LangfuseScorePublisher()

    # async def _emit(self, run_id: str, stage: str, message: str='', **details):
    #     details.pop('run_id', None)
    #     await self.repository.arecord_progress(run_id, stage, message, details)
    #     event={'run_id': run_id, 'stage': stage, 'message': message, 'details': details}
    async def _emit(self, progress_run_id: str, stage: str, message: str = "", **details):
        details.pop("run_id", None)

        await self.repository.arecord_progress(
            progress_run_id,
            stage,
            message,
            details,
        )

        event = {
            "run_id": progress_run_id,
            "stage": stage,
            "message": message,
            "details": details,
        }

        if self.progress_callback:
            r = self.progress_callback(event)
            if inspect.isawaitable(r): await r

    def collector_for(self, source: str) -> ConversationCollector:
        if source == 'langfuse': return LangfuseCollector()
        if source == 'agent_framework': return AgentFrameworkCollector()
        if source == 'mock': return MockCollector()
        raise ValueError('source must be langfuse, agent_framework or mock')

    async def run_agent(self, agent: AgentConfig, period_start: datetime, period_end: datetime, source: str='langfuse', limit: int | None=None) -> dict:
        run_id = await self.repository.acreate_run(period_start, period_end, source, agent.agent_id)
        try:
            await self._emit(run_id, 'RUN_CREATED', f'Agent run created: {agent.agent_id}', agent_id=agent.agent_id, source=source)
            collector = self.collector_for(source)
            await self._emit(run_id, 'COLLECTING', 'Collecting conversations')
            records = await collector.collect(period_start, period_end, agent_aliases=agent.aliases, limit=limit)
            await self._emit(run_id, 'COLLECTED', f'Collected {len(records)} records before sampling')
            records = self._sample(records, agent.percentage)
            await self._emit(run_id, 'SAMPLED', f'Kept {len(records)} records', percentage=agent.percentage)
            inserted = await self.repository.ainsert_items(run_id, records)
            await self._emit(run_id, 'ITEMS_INSERTED', f'Inserted {inserted} items')
            summary = await self._process(run_id)
            output_path = export_legacy_txt_gz(self.repository, run_id, agent.agent_id)
            await self._emit(run_id, 'EXPORTED', f'Exported {output_path}', output_file=str(output_path))
            return {**summary, 'agent_id': agent.agent_id, 'output_file': str(output_path), 'uploaded_to': None}
        except Exception as exc:
            await self.repository.amark_run_status(run_id, RunStatus.PARTIAL, str(exc))
            await self._emit(run_id, 'PARTIAL', f'Run failed: {exc}', error=str(exc))
            return {'status':'PARTIAL','run_id':run_id,'agent_id':agent.agent_id,'error':str(exc)}

    async def run(self, period_start: datetime, period_end: datetime, source: str='langfuse', limit: int | None=None) -> dict:
        run_id = await self.repository.acreate_run(period_start, period_end, source, None)
        try:
            collector = self.collector_for(source)
            await self._emit(run_id, 'COLLECTING', 'Collecting conversations')
            records = await collector.collect(period_start, period_end, limit=limit)
            await self._emit(run_id, 'COLLECTED', f'Collected {len(records)} records')
            await self.repository.ainsert_items(run_id, records)
            return await self._process(run_id)
        except Exception as exc:
            await self.repository.amark_run_status(run_id, RunStatus.PARTIAL, str(exc))
            await self._emit(run_id, 'PARTIAL', f'Run failed: {exc}', error=str(exc))
            return {'status':'PARTIAL','run_id':run_id,'error':str(exc)}

    async def _process(self, run_id: str) -> dict:
        processed_records: list[ConversationRecord] = []
        while True:
            items = await self.repository.afetch_next_items(run_id, settings.batch_size)
            if not items: break
            await self._emit(run_id, 'BATCH_STARTED', f'Processing {len(items)} items')
            for item in items:
                item_id=item['item_id']
                await self.repository.amark_item_processing(item_id)
                try:
                    raw=item['raw_json']
                    if hasattr(raw, 'read'): raw = raw.read()
                    record = ConversationRecord.model_validate(json.loads(raw))
                    result = await self.judge.judge_trace(record)
                    await self.repository.asave_trace_result(run_id, item_id, record, result)
                    await self.langfuse_publisher.publish_trace_score(record, result)
                    await self.repository.amark_item_completed(run_id, item_id)
                    processed_records.append(record)

                    #await self._emit(run_id, 'ITEM_COMPLETED', f'Item completed {item_id}', trace_id=record.trace_id)
                    loop_result = getattr(result, "loop_result", None)

                    await self._emit(
                        run_id,
                        "ITEM_COMPLETED",
                        f"Item completed {item_id}",
                        trace_id=record.trace_id,
                        session_id=record.session_id,
                        judgeScore=result.judgeScore,
                        accuracyScore=result.accuracyScore,
                        alucinationScore=result.alucinationScore,
                        rationale=result.rationale,
                        loop=getattr(loop_result, "loop", 0) if loop_result else 0,
                        loop_reason=getattr(loop_result, "reason", "") if loop_result else "",
                    )
                except Exception as exc:
                    await self.repository.amark_item_failed(run_id, item_id, str(exc))
                    await self._emit(run_id, 'ITEM_FAILED', f'Item failed {item_id}', error=str(exc))
        if processed_records:
            sessions = await self.judge.judge_sessions(processed_records)
            for sid, result in sessions.items():
                agent_id = next((r.agent_id for r in processed_records if r.session_id == sid), None)
                await self.repository.asave_session_result(run_id, sid, agent_id, result)
            await self._emit(run_id, 'SESSION_JUDGE_COMPLETED', f'Evaluated {len(sessions)} sessions')
        await self.repository.amark_run_status(run_id, RunStatus.COMPLETED)
        summary = await self.repository.asummarize_run(run_id)
        await self._emit(run_id, 'COMPLETED', 'Run completed', **summary)
        return {'status':'COMPLETED', **summary}

    def _sample(self, records: list[ConversationRecord], percentage: float) -> list[ConversationRecord]:
        if percentage >= 1: return records
        rng = random.Random(42)
        return [r for r in records if rng.random() <= percentage]
