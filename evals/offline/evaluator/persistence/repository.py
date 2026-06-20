from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from evaluator.config.settings import settings
from evaluator.core.models import ConversationRecord, ItemStatus, RunStatus, TraceJudgeResult, SessionJudgeResult
from evaluator.persistence.oracle_store import OracleStore, _json_dumps, _json_loads


class EvaluationRepository:
    def __init__(self, auto_init_schema: bool = False):
        self.store = OracleStore(settings, auto_init_schema=auto_init_schema)

    def create_run(self, period_start: datetime, period_end: datetime, source: str, agent_id: str | None = None) -> str:
        run_id = str(uuid.uuid4())
        now = self.store.now()
        with self.store.connect() as conn:
            conn.cursor().execute(f"""
                insert into {self.store.t('EVALUATION_RUN')}
                (RUN_ID, AGENT_ID, PERIOD_START, PERIOD_END, SOURCE, STATUS, TOTAL_ITEMS,
                 PROCESSED_ITEMS, FAILED_ITEMS, RETRY_COUNT, LAST_HEARTBEAT_AT, CREATED_AT, UPDATED_AT)
                values (:run_id, :agent_id, :period_start, :period_end, :source, :status,
                        0, 0, 0, 0, :heartbeat_at, :created_at, :updated_at)
            """, {
                "run_id": run_id,
                "agent_id": agent_id,
                "period_start": period_start,
                "period_end": period_end,
                "source": source,
                "status": RunStatus.RUNNING.value,
                "heartbeat_at": now,
                "created_at": now,
                "updated_at": now,
            })
        return run_id

    async def acreate_run(self, *args, **kwargs):
        return await self.store.to_thread(self.create_run, *args, **kwargs)

    def record_progress(self, run_id: str, stage: str, message: str = "", details: dict | None = None):
        with self.store.connect() as conn:
            conn.cursor().execute(f"""
                insert into {self.store.t('EVALUATION_PROGRESS_EVENT')}
                (RUN_ID, STAGE, MESSAGE, DETAILS_JSON, CREATED_AT)
                values (:run_id, :stage, :message, :details_json, :created_at)
            """, {
                "run_id": run_id,
                "stage": stage,
                "message": (message or "")[:1000],
                "details_json": _json_dumps(details or {}),
                "created_at": self.store.now(),
            })

    async def arecord_progress(self, *args, **kwargs):
        return await self.store.to_thread(self.record_progress, *args, **kwargs)

    def insert_items(self, run_id: str, records: list[ConversationRecord]) -> int:
        inserted = 0
        now = self.store.now()
        with self.store.connect() as conn:
            cur = conn.cursor()
            for record in records:
                try:
                    cur.execute(f"""
                        insert into {self.store.t('EVALUATION_ITEM')}
                        (ITEM_ID, RUN_ID, TRACE_ID, SESSION_ID, MESSAGE_ID, AGENT_ID, CHANNEL,
                         STATUS, ATTEMPT_COUNT, RAW_JSON, CREATED_AT, UPDATED_AT)
                        values (:item_id, :run_id, :trace_id, :session_id, :message_id, :agent_id,
                                :channel, :status, 0, :raw_json, :created_at, :updated_at)
                    """, {
                        "item_id": str(uuid.uuid4()),
                        "run_id": run_id,
                        "trace_id": record.trace_id,
                        "session_id": record.session_id,
                        "message_id": record.message_id,
                        "agent_id": record.agent_id,
                        "channel": record.channel,
                        "status": ItemStatus.PENDING.value,
                        "raw_json": record.model_dump_json(),
                        "created_at": now,
                        "updated_at": now,
                    })
                    inserted += 1
                except Exception as exc:
                    if "ORA-00001" not in str(exc):
                        raise
            cur.execute(f"""
                update {self.store.t('EVALUATION_RUN')}
                   set TOTAL_ITEMS = (
                       select count(*) from {self.store.t('EVALUATION_ITEM')} where RUN_ID = :run_id
                   ),
                   UPDATED_AT = :updated_at
                 where RUN_ID = :run_id
            """, {"run_id": run_id, "updated_at": self.store.now()})
        return inserted

    async def ainsert_items(self, *args, **kwargs):
        return await self.store.to_thread(self.insert_items, *args, **kwargs)

    def fetch_next_items(self, run_id: str, batch_size: int) -> list[dict]:
        with self.store.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                select * from (
                    select ITEM_ID, RUN_ID, TRACE_ID, SESSION_ID, MESSAGE_ID, AGENT_ID, CHANNEL,
                           STATUS, ATTEMPT_COUNT, RAW_JSON
                      from {self.store.t('EVALUATION_ITEM')}
                     where RUN_ID = :run_id
                       and STATUS in (:pending, :failed)
                       and ATTEMPT_COUNT < :max_attempts
                     order by CREATED_AT
                ) where rownum <= :batch_size
            """, {
                "run_id": run_id,
                "pending": ItemStatus.PENDING.value,
                "failed": ItemStatus.FAILED.value,
                "max_attempts": settings.max_attempts,
                "batch_size": batch_size,
            })
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    async def afetch_next_items(self, *args, **kwargs):
        return await self.store.to_thread(self.fetch_next_items, *args, **kwargs)

    def mark_item_processing(self, item_id: str):
        with self.store.connect() as conn:
            conn.cursor().execute(f"""
                update {self.store.t('EVALUATION_ITEM')}
                   set STATUS = :status,
                       ATTEMPT_COUNT = ATTEMPT_COUNT + 1,
                       UPDATED_AT = :updated_at
                 where ITEM_ID = :item_id
            """, {
                "status": ItemStatus.PROCESSING.value,
                "updated_at": self.store.now(),
                "item_id": item_id,
            })

    async def amark_item_processing(self, *args, **kwargs):
        return await self.store.to_thread(self.mark_item_processing, *args, **kwargs)

    def mark_item_completed(self, run_id: str, item_id: str):
        now = self.store.now()
        with self.store.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                update {self.store.t('EVALUATION_ITEM')}
                   set STATUS = :status,
                       UPDATED_AT = :updated_at
                 where ITEM_ID = :item_id
            """, {
                "status": ItemStatus.COMPLETED.value,
                "updated_at": now,
                "item_id": item_id,
            })
            self._refresh_run_counters(cur, run_id, now)

    async def amark_item_completed(self, *args, **kwargs):
        return await self.store.to_thread(self.mark_item_completed, *args, **kwargs)

    def mark_item_failed(self, run_id: str, item_id: str, error: str):
        now = self.store.now()
        with self.store.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                update {self.store.t('EVALUATION_ITEM')}
                   set STATUS = :status,
                       ERROR_MESSAGE = :error,
                       UPDATED_AT = :updated_at
                 where ITEM_ID = :item_id
            """, {
                "status": ItemStatus.FAILED.value,
                "error": (error or "")[:4000],
                "updated_at": now,
                "item_id": item_id,
            })
            self._refresh_run_counters(cur, run_id, now)

    async def amark_item_failed(self, *args, **kwargs):
        return await self.store.to_thread(self.mark_item_failed, *args, **kwargs)

    def _refresh_run_counters(self, cur, run_id: str, updated_at):
        cur.execute(f"""
            update {self.store.t('EVALUATION_RUN')}
               set PROCESSED_ITEMS = (
                   select count(*) from {self.store.t('EVALUATION_ITEM')}
                    where RUN_ID = :run_id and STATUS = :completed
               ),
               FAILED_ITEMS = (
                   select count(*) from {self.store.t('EVALUATION_ITEM')}
                    where RUN_ID = :run_id and STATUS = :failed
               ),
               UPDATED_AT = :updated_at
             where RUN_ID = :run_id
        """, {
            "run_id": run_id,
            "completed": ItemStatus.COMPLETED.value,
            "failed": ItemStatus.FAILED.value,
            "updated_at": updated_at,
        })

    def save_trace_result(self, run_id: str, item_id: str, record: ConversationRecord, result: TraceJudgeResult):
        judge_name = getattr(result, "judge_name", None) or "trace_metrics"
        judge_type = (getattr(result, "judge_type", None) or "TRACE").upper()
        score = getattr(result, "judgeScore", None)
        accuracy = getattr(result, "accuracyScore", None)
        alucination = getattr(result, "alucinationScore", None)
        rationale = getattr(result, "rationale", None) or ""
        with self.store.connect() as conn:
            conn.cursor().execute(f"""
                insert into {self.store.t('EVALUATION_RESULT')}
                (RESULT_ID, RUN_ID, ITEM_ID, TRACE_ID, SESSION_ID, AGENT_ID, JUDGE_NAME,
                 JUDGE_TYPE, SCORE, JUDGE_SCORE, ACCURACY_SCORE, ALUCINATION_SCORE,
                 RATIONALE, RESULT_JSON, CREATED_AT)
                values (:result_id, :run_id, :item_id, :trace_id, :session_id, :agent_id,
                        :judge_name, :judge_type, :score, :judge_score, :accuracy_score,
                        :alucination_score, :rationale, :result_json, :created_at)
            """, {
                "result_id": str(uuid.uuid4()),
                "run_id": run_id,
                "item_id": item_id,
                "trace_id": record.trace_id,
                "session_id": record.session_id,
                "agent_id": record.agent_id,
                "judge_name": judge_name,
                "judge_type": judge_type,
                "score": score,
                "judge_score": score,
                "accuracy_score": accuracy,
                "alucination_score": alucination,
                "rationale": rationale,
                "result_json": result.model_dump_json(),
                "created_at": self.store.now(),
            })

    async def asave_trace_result(self, *args, **kwargs):
        return await self.store.to_thread(self.save_trace_result, *args, **kwargs)

    def save_session_result(self, run_id: str, session_id: str, agent_id: str | None, result: SessionJudgeResult):
        judge_name = getattr(result, "judge_name", None) or "session_metrics"
        judge_type = (getattr(result, "judge_type", None) or "SESSION").upper()
        rationale = getattr(result, "rationale", None) or ""
        with self.store.connect() as conn:
            conn.cursor().execute(f"""
                insert into {self.store.t('EVALUATION_RESULT')}
                (RESULT_ID, RUN_ID, SESSION_ID, AGENT_ID, JUDGE_NAME, JUDGE_TYPE,
                 INFERRED_CSI_SCORE, RESOLUTION, CONVERSATION_PRECISION, RATIONALE,
                 RESULT_JSON, CREATED_AT)
                values (:result_id, :run_id, :session_id, :agent_id, :judge_name, :judge_type,
                        :csi, :resolution, :precision, :rationale, :result_json, :created_at)
            """, {
                "result_id": str(uuid.uuid4()),
                "run_id": run_id,
                "session_id": session_id,
                "agent_id": agent_id,
                "judge_name": judge_name,
                "judge_type": judge_type,
                "csi": getattr(result, "inferredCsiScore", None),
                "resolution": getattr(result, "resolution", None),
                "precision": getattr(result, "conversationPrecision", None),
                "rationale": rationale,
                "result_json": result.model_dump_json(),
                "created_at": self.store.now(),
            })

    async def asave_session_result(self, *args, **kwargs):
        return await self.store.to_thread(self.save_session_result, *args, **kwargs)

    def mark_run_status(self, run_id: str, status: RunStatus, error: str | None = None):
        with self.store.connect() as conn:
            conn.cursor().execute(f"""
                update {self.store.t('EVALUATION_RUN')}
                   set STATUS = :status,
                       ERROR_MESSAGE = :error,
                       UPDATED_AT = :updated_at
                 where RUN_ID = :run_id
            """, {
                "status": status.value,
                "error": error,
                "updated_at": self.store.now(),
                "run_id": run_id,
            })

    async def amark_run_status(self, *args, **kwargs):
        return await self.store.to_thread(self.mark_run_status, *args, **kwargs)

    def summarize_run(self, run_id: str) -> dict:
        with self.store.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                select
                    (select count(*) from {self.store.t('EVALUATION_ITEM')} where RUN_ID = :run_id),
                    (select count(*) from {self.store.t('EVALUATION_ITEM')} where RUN_ID = :run_id and STATUS = 'COMPLETED'),
                    (select count(*) from {self.store.t('EVALUATION_ITEM')} where RUN_ID = :run_id and STATUS = 'FAILED'),
                    (select count(*) from {self.store.t('EVALUATION_RESULT')} where RUN_ID = :run_id and JUDGE_TYPE = 'TRACE'),
                    (select avg(JUDGE_SCORE) from {self.store.t('EVALUATION_RESULT')} where RUN_ID = :run_id and JUDGE_TYPE = 'TRACE')
                from dual
            """, {"run_id": run_id})
            r = cur.fetchone()
            return {
                "run_id": run_id,
                "total_items": int(r[0] or 0),
                "completed_items": int(r[1] or 0),
                "failed_items": int(r[2] or 0),
                "evaluations": int(r[3] or 0),
                "avg_score": float(r[4]) if r[4] is not None else None,
            }

    async def asummarize_run(self, *args, **kwargs):
        return await self.store.to_thread(self.summarize_run, *args, **kwargs)

    def get_run_progress(self, run_id: str, event_limit: int = 20) -> dict:
        summary = self.summarize_run(run_id)
        total = summary["total_items"] or 0
        done = summary["completed_items"] + summary["failed_items"]
        with self.store.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                select * from (
                    select STAGE, MESSAGE, DETAILS_JSON, CREATED_AT
                      from {self.store.t('EVALUATION_PROGRESS_EVENT')}
                     where RUN_ID = :run_id
                     order by CREATED_AT desc
                ) where rownum <= :max_rows
            """, {"run_id": run_id, "max_rows": event_limit})
            events = [
                {
                    "stage": s,
                    "message": m,
                    "details": _json_loads(d.read() if hasattr(d, "read") else d, {}),
                    "created_at": str(c),
                }
                for s, m, d, c in cur.fetchall()
            ]
        return {
            **summary,
            "done_items": done,
            "percent_complete": round((done / total) * 100, 2) if total else 0.0,
            "events": events,
        }

    async def aget_run_progress(self, *args, **kwargs):
        return await self.store.to_thread(self.get_run_progress, *args, **kwargs)

    def list_runs(self, limit: int = 20):
        with self.store.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                select * from (
                    select RUN_ID, AGENT_ID, PERIOD_START, PERIOD_END, SOURCE, STATUS,
                           TOTAL_ITEMS, PROCESSED_ITEMS, FAILED_ITEMS, CREATED_AT, UPDATED_AT
                      from {self.store.t('EVALUATION_RUN')}
                     order by CREATED_AT desc
                ) where rownum <= :max_rows
            """, {"max_rows": limit})
            return [
                {
                    "run_id": r[0],
                    "agent_id": r[1],
                    "period_start": str(r[2]),
                    "period_end": str(r[3]),
                    "source": r[4],
                    "status": r[5],
                    "total_items": int(r[6] or 0),
                    "processed_items": int(r[7] or 0),
                    "failed_items": int(r[8] or 0),
                    "created_at": str(r[9]),
                    "updated_at": str(r[10]),
                }
                for r in cur.fetchall()
            ]

    async def alist_runs(self, *args, **kwargs):
        return await self.store.to_thread(self.list_runs, *args, **kwargs)

    def list_results(self, run_id: str, limit: int = 100) -> list[dict]:
        with self.store.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                select JUDGE_NAME, JUDGE_TYPE, SCORE, JUDGE_SCORE, ACCURACY_SCORE,
                       ALUCINATION_SCORE, INFERRED_CSI_SCORE, RESOLUTION,
                       CONVERSATION_PRECISION, RATIONALE, TRACE_ID, SESSION_ID, CREATED_AT
                  from {self.store.t('EVALUATION_RESULT')}
                 where RUN_ID = :run_id
                 order by CREATED_AT desc
            """, {"run_id": run_id})
            return [
                {
                    "judge_name": r[0],
                    "judge_type": r[1],
                    "score": r[2],
                    "judge_score": r[3],
                    "accuracy_score": r[4],
                    "alucination_score": r[5],
                    "inferred_csi_score": r[6],
                    "resolution": r[7],
                    "conversation_precision": r[8],
                    "rationale": r[9],
                    "trace_id": r[10],
                    "session_id": r[11],
                    "created_at": str(r[12]),
                }
                for r in cur.fetchall()[:limit]
            ]

    async def alist_results(self, *args, **kwargs):
        return await self.store.to_thread(self.list_results, *args, **kwargs)
