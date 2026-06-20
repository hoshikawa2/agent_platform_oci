from __future__ import annotations
from datetime import datetime
from evaluator.collectors.base import ConversationCollector
from evaluator.core.models import ConversationRecord, ConversationMessage
from evaluator.persistence.oracle_store import OracleStore, _json_loads
from evaluator.config.settings import settings

class AgentFrameworkCollector(ConversationCollector):
    def __init__(self):
        self.store = OracleStore(settings, auto_init_schema=False)

    async def collect(self, period_start: datetime, period_end: datetime, agent_aliases: set[str] | None = None, limit: int | None = None):
        return await self.store.to_thread(self._collect, period_start, period_end, agent_aliases or set(), limit or 100)

    def _collect(self, period_start, period_end, aliases, limit):
        records=[]
        with self.store.connect() as conn:
            cur=conn.cursor()
            cur.execute(f"""
                select * from (
                    select SESSION_ID, AGENT_ID, CHANNEL, CONTEXT_JSON, METADATA_JSON, CREATED_AT
                      from {self.store.t('AGENT_SESSION')}
                     where CREATED_AT >= :start_at and CREATED_AT < :end_at
                     order by CREATED_AT desc
                ) where rownum <= :max_rows
            """, dict(start_at=period_start, end_at=period_end, max_rows=limit))
            sessions=cur.fetchall()
            for session_id, agent_id, channel, ctx, meta, created_at in sessions:
                if aliases and agent_id not in aliases: continue
                cur.execute(f"""
                    select ROLE, CONTENT, METADATA_JSON, CREATED_AT, MESSAGE_ID
                      from {self.store.t('AGENT_MESSAGE')}
                     where SESSION_ID=:session_id order by CREATED_AT
                """, dict(session_id=session_id))
                rows=cur.fetchall()
                msgs=[]
                for role, content, msg_meta, msg_created, message_id in rows:
                    msgs.append(ConversationMessage(role=role, content=content or '', created_at=str(msg_created), metadata=_json_loads(msg_meta.read() if hasattr(msg_meta,'read') else msg_meta,{})))
                input_text=next((m.content for m in msgs if m.role in ('user','human')), '')
                output_text=next((m.content for m in reversed(msgs) if m.role in ('assistant','ai','agent')), '')
                records.append(ConversationRecord(session_id=session_id, trace_id=session_id, message_id=rows[-1][4] if rows else None, agent_id=agent_id, channel=channel, input_text=input_text, output_text=output_text, messages=msgs, metadata=_json_loads(meta.read() if hasattr(meta,'read') else meta,{}), raw={}))
        return records
