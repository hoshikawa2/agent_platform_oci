from __future__ import annotations
import json, sqlite3, threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)

def _json_loads(value: str | None, default: Any):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default

class SQLiteStore:
    """Persistência local compatível com o padrão FIRST."""
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def connect(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        ddl = """
        create table if not exists agent_sessions (
            session_id text primary key,
            tenant_id text not null,
            agent_id text not null,
            user_id text,
            channel text,
            channel_id text,
            context_json text,
            metadata_json text,
            created_at text not null,
            updated_at text not null
        );
        create table if not exists agent_messages (
            id integer primary key autoincrement,
            session_id text not null,
            message_id text,
            role text not null,
            content text not null,
            metadata_json text,
            created_at text not null,
            unique(session_id, message_id)
        );
        create index if not exists idx_agent_messages_session_created on agent_messages(session_id, created_at, id);
        create table if not exists agent_memory_summaries (
            session_id text primary key,
            summary text not null,
            last_message_created_at text,
            message_count_summarized integer not null default 0,
            metadata_json text,
            created_at text not null,
            updated_at text not null
        );
        create table if not exists workflow_checkpoints (
            id integer primary key autoincrement,
            thread_id text not null,
            checkpoint_json text not null,
            created_at text not null
        );
        create index if not exists idx_workflow_checkpoints_thread on workflow_checkpoints(thread_id, id desc);
        create table if not exists sse_events (
            id integer primary key autoincrement,
            session_id text not null,
            event_name text not null,
            payload_json text not null,
            created_at text not null
        );
        create index if not exists idx_sse_events_session on sse_events(session_id, id desc);
        create table if not exists rag_documents (
            id text primary key,
            namespace text not null,
            content text not null,
            metadata_json text,
            created_at text not null
        );
        create index if not exists idx_rag_documents_namespace on rag_documents(namespace);
        create table if not exists cache_entries (
            key text primary key,
            value_json text not null,
            expires_at real,
            created_at text not null
        );
        """
        with self._lock, self.connect() as con:
            con.executescript(ddl)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def upsert_session(self, session_id: str, tenant_id: str, agent_id: str, user_id: str | None, channel: str | None, channel_id: str | None, context: dict, metadata: dict):
        now = self.now()
        with self._lock, self.connect() as con:
            existing = con.execute('select created_at from agent_sessions where session_id=?', (session_id,)).fetchone()
            created_at = existing['created_at'] if existing else now
            con.execute('insert or replace into agent_sessions(session_id, tenant_id, agent_id, user_id, channel, channel_id, context_json, metadata_json, created_at, updated_at) values(?,?,?,?,?,?,?,?,?,?)',
                        (session_id, tenant_id, agent_id, user_id, channel, channel_id, _json_dumps(context), _json_dumps(metadata), created_at, now))

    def get_session(self, session_id: str) -> dict | None:
        with self._lock, self.connect() as con:
            row = con.execute('select * from agent_sessions where session_id=?', (session_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d['context'] = _json_loads(d.pop('context_json', None), {})
        d['metadata'] = _json_loads(d.pop('metadata_json', None), {})
        return d

    def insert_message(self, session_id: str, role: str, content: str, metadata: dict | None, message_id: str | None = None):
        now = self.now()
        with self._lock, self.connect() as con:
            try:
                con.execute('insert into agent_messages(session_id, message_id, role, content, metadata_json, created_at) values(?,?,?,?,?,?)',
                            (session_id, message_id, role, content, _json_dumps(metadata or {}), now))
            except sqlite3.IntegrityError:
                return

    def list_messages(self, session_id: str, limit: int = 50) -> list[dict]:
        with self._lock, self.connect() as con:
            rows = con.execute('select * from agent_messages where session_id=? order by id desc limit ?', (session_id, limit)).fetchall()
        out=[]
        for r in reversed(rows):
            d=dict(r)
            d['metadata']=_json_loads(d.pop('metadata_json', None), {})
            out.append(d)
        return out

    def get_memory_summary(self, session_id: str) -> dict | None:
        with self._lock, self.connect() as con:
            row = con.execute('select * from agent_memory_summaries where session_id=?', (session_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d['metadata'] = _json_loads(d.pop('metadata_json', None), {})
        return d

    def upsert_memory_summary(self, session_id: str, summary: str, last_message_created_at: str | None, message_count_summarized: int, metadata: dict | None):
        now = self.now()
        with self._lock, self.connect() as con:
            existing = con.execute('select created_at from agent_memory_summaries where session_id=?', (session_id,)).fetchone()
            created_at = existing['created_at'] if existing else now
            con.execute('''
                insert or replace into agent_memory_summaries(
                    session_id, summary, last_message_created_at, message_count_summarized, metadata_json, created_at, updated_at
                ) values(?,?,?,?,?,?,?)
            ''', (session_id, summary or '', last_message_created_at, int(message_count_summarized or 0), _json_dumps(metadata or {}), created_at, now))

    def delete_memory_summary(self, session_id: str):
        with self._lock, self.connect() as con:
            con.execute('delete from agent_memory_summaries where session_id=?', (session_id,))

    def put_checkpoint(self, thread_id: str, checkpoint: dict):
        with self._lock, self.connect() as con:
            con.execute('insert into workflow_checkpoints(thread_id, checkpoint_json, created_at) values(?,?,?)', (thread_id, _json_dumps(checkpoint), self.now()))

    def get_latest_checkpoint(self, thread_id: str) -> dict | None:
        with self._lock, self.connect() as con:
            row=con.execute('select checkpoint_json from workflow_checkpoints where thread_id=? order by id desc limit 1',(thread_id,)).fetchone()
        return _json_loads(row['checkpoint_json'], None) if row else None

    def append_sse_event(self, session_id: str, event_name: str, payload: dict) -> int:
        with self._lock, self.connect() as con:
            cur=con.execute('insert into sse_events(session_id,event_name,payload_json,created_at) values(?,?,?,?)',(session_id,event_name,_json_dumps(payload),self.now()))
            return int(cur.lastrowid)

    def list_sse_events(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[dict]:
        with self._lock, self.connect() as con:
            rows=con.execute('select * from sse_events where session_id=? and id>? order by id asc limit ?',(session_id,after_id,limit)).fetchall()
        return [{**dict(r), 'payload': _json_loads(r['payload_json'], {})} for r in rows]
