from __future__ import annotations

import json
import logging
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger("agent_framework.oracle_store")


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _json_loads(value: str | bytes | None, default: Any):
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        return json.loads(value)
    except Exception:
        return default


@dataclass
class OracleSettings:
    user: str
    password: str
    dsn: str
    wallet_location: str | None = None
    wallet_password: str | None = None
    table_prefix: str = "AGENTFW"


class OracleStore:
    """Oracle Autonomous Database store no padrão FIRST.

    É síncrono por dentro, mas expõe métodos async usando asyncio.to_thread para
    não bloquear o event loop do FastAPI/LangGraph. O schema é genérico e pode
    ser usado por SessionRepository, MessageHistory, CheckpointRepository,
    cache, RAG e SSE replay.
    """

    def __init__(self, settings):
        self.settings = settings
        self.cfg = OracleSettings(
            user=settings.ADB_USER or "",
            password=settings.ADB_PASSWORD or "",
            dsn=settings.ADB_DSN or "",
            wallet_location=getattr(settings, "ADB_WALLET_LOCATION", None),
            wallet_password=getattr(settings, "ADB_WALLET_PASSWORD", None),
            table_prefix=(getattr(settings, "ADB_TABLE_PREFIX", "AGENTFW") or "AGENTFW").upper(),
        )
        if not self.cfg.user or not self.cfg.password or not self.cfg.dsn:
            raise RuntimeError("ADB_USER, ADB_PASSWORD e ADB_DSN são obrigatórios para provider autonomous/oracle")
        self._init_schema_once = False
        self._init_schema()

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def t(self, name: str) -> str:
        return f"{self.cfg.table_prefix}_{name}".upper()

    @contextmanager
    def connect(self):
        import oracledb
        oracledb.defaults.fetch_lobs = False
        kwargs = {}
        if self.cfg.wallet_location:
            kwargs["config_dir"] = self.cfg.wallet_location
            kwargs["wallet_location"] = self.cfg.wallet_location
        if self.cfg.wallet_password:
            kwargs["wallet_password"] = self.cfg.wallet_password
        conn = oracledb.connect(user=self.cfg.user, password=self.cfg.password, dsn=self.cfg.dsn, **kwargs)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _exec_ddl_ignore_exists(self, cur, ddl: str):
        try:
            cur.execute(ddl)
        except Exception as exc:
            msg = str(exc)
            # ORA-00955 name already used, ORA-01408 index already exists
            if "ORA-00955" in msg or "ORA-01408" in msg:
                return
            raise

    def _init_schema(self):
        with self.connect() as conn:
            cur = conn.cursor()
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('AGENT_SESSION')} (
                    SESSION_ID varchar2(256) primary key,
                    TENANT_ID varchar2(128) not null,
                    AGENT_ID varchar2(128) not null,
                    USER_ID varchar2(256),
                    CHANNEL varchar2(64),
                    CHANNEL_ID varchar2(256),
                    CONTEXT_JSON clob check (CONTEXT_JSON is json),
                    METADATA_JSON clob check (METADATA_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    UPDATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('AGENT_MESSAGE')} (
                    ID number generated always as identity primary key,
                    SESSION_ID varchar2(256) not null,
                    MESSAGE_ID varchar2(256),
                    ROLE varchar2(32) not null,
                    CONTENT clob,
                    METADATA_JSON clob check (METADATA_JSON is json),
                    TOKEN_USAGE_JSON clob check (TOKEN_USAGE_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    constraint {self.t('UQ_MSG')} unique (SESSION_ID, MESSAGE_ID)
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_MSG_SESSION')} on {self.t('AGENT_MESSAGE')}(SESSION_ID, CREATED_AT)")
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('MEMORY_SUMMARY')} (
                    SESSION_ID varchar2(256) primary key,
                    SUMMARY clob,
                    LAST_MESSAGE_CREATED_AT varchar2(128),
                    MESSAGE_COUNT_SUMMARIZED number default 0 not null,
                    METADATA_JSON clob check (METADATA_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    UPDATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('WORKFLOW_CHECKPOINT')} (
                    ID number generated always as identity primary key,
                    THREAD_ID varchar2(256) not null,
                    CHECKPOINT_NS varchar2(128) default 'default',
                    CHECKPOINT_ID varchar2(256),
                    PARENT_CHECKPOINT_ID varchar2(256),
                    CHECKPOINT_JSON clob check (CHECKPOINT_JSON is json),
                    METADATA_JSON clob check (METADATA_JSON is json),
                    CREATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_CHK_THREAD')} on {self.t('WORKFLOW_CHECKPOINT')}(THREAD_ID, ID desc)")
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('WORKFLOW_CHECKPOINT_WRITE')} (
                    ID number generated always as identity primary key,
                    THREAD_ID varchar2(256) not null,
                    CHECKPOINT_ID varchar2(256),
                    TASK_ID varchar2(256),
                    CHANNEL varchar2(256),
                    VALUE_JSON clob check (VALUE_JSON is json),
                    CREATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_EXISTS_BLOB(cur)
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('SSE_EVENT')} (
                    ID number generated always as identity primary key,
                    SESSION_ID varchar2(256) not null,
                    EVENT_NAME varchar2(128) not null,
                    PAYLOAD_JSON clob check (PAYLOAD_JSON is json),
                    CREATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_SSE_SESSION')} on {self.t('SSE_EVENT')}(SESSION_ID, ID)")
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('CACHE_ENTRY')} (
                    CACHE_KEY varchar2(512) primary key,
                    VALUE_JSON clob check (VALUE_JSON is json),
                    EXPIRES_AT timestamp with time zone,
                    CREATED_AT timestamp with time zone not null,
                    UPDATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('RAG_DOCUMENT')} (
                    ID varchar2(256) primary key,
                    NAMESPACE varchar2(256) not null,
                    CONTENT clob,
                    EMBEDDING vector,
                    METADATA_JSON clob check (METADATA_JSON is json),
                    CREATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_RAG_NS')} on {self.t('RAG_DOCUMENT')}(NAMESPACE)")
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('GRAPH_NODE')} (
                    NODE_ID varchar2(512) primary key,
                    LABEL varchar2(256),
                    METADATA_JSON clob check (METADATA_JSON is json),
                    CREATED_AT timestamp with time zone not null,
                    UPDATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"""
                create table {self.t('GRAPH_EDGE')} (
                    ID number generated always as identity primary key,
                    SRC varchar2(512) not null,
                    REL varchar2(256) not null,
                    DST varchar2(512) not null,
                    METADATA_JSON clob check (METADATA_JSON is json),
                    CREATED_AT timestamp with time zone not null
                )
            """)
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_GRAPH_SRC')} on {self.t('GRAPH_EDGE')}(SRC)")
            self._exec_ddl_ignore_exists(cur, f"create index {self.t('IX_GRAPH_DST')} on {self.t('GRAPH_EDGE')}(DST)")

    def _exec_ddl_ignore_EXISTS_BLOB(self, cur):
        self._exec_ddl_ignore_exists(cur, f"""
            create table {self.t('WORKFLOW_CHECKPOINT_BLOB')} (
                ID number generated always as identity primary key,
                THREAD_ID varchar2(256) not null,
                CHECKPOINT_ID varchar2(256),
                BLOB_KEY varchar2(512),
                BLOB_VALUE blob,
                CREATED_AT timestamp with time zone not null
            )
        """)

    async def upsert_session(self, session_id: str, tenant_id: str, agent_id: str, user_id: str | None, channel: str | None, channel_id: str | None, context: dict, metadata: dict):
        return await asyncio.to_thread(self._upsert_session, session_id, tenant_id, agent_id, user_id, channel, channel_id, context, metadata)

    def _upsert_session(self, session_id, tenant_id, agent_id, user_id, channel, channel_id, context, metadata):
        now = self.now()
        sql = f"""
            merge into {self.t('AGENT_SESSION')} t
            using (select :session_id SESSION_ID from dual) s
            on (t.SESSION_ID = s.SESSION_ID)
            when matched then update set
                TENANT_ID=:tenant_id, AGENT_ID=:agent_id, USER_ID=:user_id, CHANNEL=:channel,
                CHANNEL_ID=:channel_id, CONTEXT_JSON=:context_json, METADATA_JSON=:metadata_json, UPDATED_AT=:updated_at
            when not matched then insert
                (SESSION_ID,TENANT_ID,AGENT_ID,USER_ID,CHANNEL,CHANNEL_ID,CONTEXT_JSON,METADATA_JSON,CREATED_AT,UPDATED_AT)
                values (:session_id,:tenant_id,:agent_id,:user_id,:channel,:channel_id,:context_json,:metadata_json,:created_at,:updated_at)
        """
        with self.connect() as conn:
            conn.cursor().execute(sql, dict(session_id=session_id, tenant_id=tenant_id, agent_id=agent_id, user_id=user_id, channel=channel, channel_id=channel_id, context_json=_json_dumps(context), metadata_json=_json_dumps(metadata), created_at=now, updated_at=now))

    async def get_session(self, session_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_session, session_id)

    def _get_session(self, session_id):
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"select SESSION_ID,TENANT_ID,AGENT_ID,USER_ID,CHANNEL,CHANNEL_ID,CONTEXT_JSON,METADATA_JSON,CREATED_AT,UPDATED_AT from {self.t('AGENT_SESSION')} where SESSION_ID=:1", [session_id])
            row = cur.fetchone()
            if not row:
                return None
            cols = [d[0].lower() for d in cur.description]
            d = dict(zip(cols, row))
            ctx_lob = d.pop("context_json", None)
            meta_lob = d.pop("metadata_json", None)
            d["context"] = _json_loads(ctx_lob.read() if hasattr(ctx_lob, "read") else ctx_lob, {})
            d["metadata"] = _json_loads(meta_lob.read() if hasattr(meta_lob, "read") else meta_lob, {})
            return d

    async def insert_message(self, session_id: str, role: str, content: str, metadata: dict | None, message_id: str | None = None, token_usage: dict | None = None):
        return await asyncio.to_thread(self._insert_message, session_id, role, content, metadata, message_id, token_usage)

    def _insert_message(self, session_id, role, content, metadata, message_id=None, token_usage=None):
        with self.connect() as conn:
            try:
                conn.cursor().execute(
                    f"insert into {self.t('AGENT_MESSAGE')}(SESSION_ID,MESSAGE_ID,ROLE,CONTENT,METADATA_JSON,TOKEN_USAGE_JSON,CREATED_AT) values(:1,:2,:3,:4,:5,:6,:7)",
                    [session_id, message_id, role, content, _json_dumps(metadata), _json_dumps(token_usage), self.now()],
                )
            except Exception as exc:
                if "ORA-00001" in str(exc):
                    logger.info("Mensagem duplicada ignorada session_id=%s message_id=%s", session_id, message_id)
                    return
                raise

    async def list_messages(self, session_id: str, limit: int = 50) -> list[dict]:
        return await asyncio.to_thread(self._list_messages, session_id, limit)

    def _list_messages(self, session_id, limit=50):
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"""
                select * from (
                  select ID,SESSION_ID,MESSAGE_ID,ROLE,CONTENT,METADATA_JSON,TOKEN_USAGE_JSON,CREATED_AT
                  from {self.t('AGENT_MESSAGE')}
                  where SESSION_ID=:1
                  order by ID desc
                ) where rownum <= :2
                order by ID asc
            """, [session_id, limit])
            cols = [d[0].lower() for d in cur.description]
            out=[]
            for row in cur.fetchall():
                d=dict(zip(cols,row))
                for key in ("metadata_json", "token_usage_json"):
                    v=d.pop(key, None)
                    d[key.replace("_json", "")] = _json_loads(v.read() if hasattr(v,"read") else v, {})
                out.append(d)
            return out

    async def get_memory_summary(self, session_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_memory_summary, session_id)

    def _get_memory_summary(self, session_id):
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"select SESSION_ID,SUMMARY,LAST_MESSAGE_CREATED_AT,MESSAGE_COUNT_SUMMARIZED,METADATA_JSON,CREATED_AT,UPDATED_AT from {self.t('MEMORY_SUMMARY')} where SESSION_ID=:1",
                [session_id],
            )
            row = cur.fetchone()
            if not row:
                return None
            d = {
                "session_id": row[0],
                "summary": row[1].read() if hasattr(row[1], "read") else (row[1] or ""),
                "last_message_created_at": row[2],
                "message_count_summarized": int(row[3] or 0),
                "metadata": _json_loads(row[4].read() if hasattr(row[4], "read") else row[4], {}),
                "created_at": str(row[5]) if row[5] is not None else None,
                "updated_at": str(row[6]) if row[6] is not None else None,
            }
            return d

    async def upsert_memory_summary(self, session_id: str, summary: str, last_message_created_at: str | None, message_count_summarized: int, metadata: dict | None):
        return await asyncio.to_thread(self._upsert_memory_summary, session_id, summary, last_message_created_at, message_count_summarized, metadata)

    def _upsert_memory_summary(self, session_id, summary, last_message_created_at, message_count_summarized, metadata):
        now = self.now()
        sql = f"""
            merge into {self.t('MEMORY_SUMMARY')} t
            using (select :session_id SESSION_ID from dual) s
            on (t.SESSION_ID = s.SESSION_ID)
            when matched then update set
                SUMMARY=:summary,
                LAST_MESSAGE_CREATED_AT=:last_message_created_at,
                MESSAGE_COUNT_SUMMARIZED=:message_count_summarized,
                METADATA_JSON=:metadata_json,
                UPDATED_AT=:updated_at
            when not matched then insert
                (SESSION_ID,SUMMARY,LAST_MESSAGE_CREATED_AT,MESSAGE_COUNT_SUMMARIZED,METADATA_JSON,CREATED_AT,UPDATED_AT)
                values (:session_id,:summary,:last_message_created_at,:message_count_summarized,:metadata_json,:created_at,:updated_at)
        """
        with self.connect() as conn:
            conn.cursor().execute(sql, dict(
                session_id=session_id,
                summary=summary or "",
                last_message_created_at=last_message_created_at,
                message_count_summarized=int(message_count_summarized or 0),
                metadata_json=_json_dumps(metadata),
                created_at=now,
                updated_at=now,
            ))

    async def delete_memory_summary(self, session_id: str):
        return await asyncio.to_thread(self._delete_memory_summary, session_id)

    def _delete_memory_summary(self, session_id):
        with self.connect() as conn:
            conn.cursor().execute(f"delete from {self.t('MEMORY_SUMMARY')} where SESSION_ID=:1", [session_id])

    async def put_checkpoint(self, thread_id: str, checkpoint: dict, metadata: dict | None = None):
        return await asyncio.to_thread(self._put_checkpoint, thread_id, checkpoint, metadata)

    def _put_checkpoint(self, thread_id, checkpoint, metadata=None):
        with self.connect() as conn:
            conn.cursor().execute(
                f"insert into {self.t('WORKFLOW_CHECKPOINT')}(THREAD_ID,CHECKPOINT_ID,PARENT_CHECKPOINT_ID,CHECKPOINT_JSON,METADATA_JSON,CREATED_AT) values(:1,:2,:3,:4,:5,:6)",
                [thread_id, checkpoint.get("id") or checkpoint.get("checkpoint_id"), checkpoint.get("parent_checkpoint_id"), _json_dumps(checkpoint), _json_dumps(metadata), self.now()],
            )

    async def get_latest_checkpoint(self, thread_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_latest_checkpoint, thread_id)

    def _get_latest_checkpoint(self, thread_id):
        with self.connect() as conn:
            cur=conn.cursor()
            cur.execute(f"select CHECKPOINT_JSON from {self.t('WORKFLOW_CHECKPOINT')} where THREAD_ID=:1 order by ID desc fetch first 1 rows only", [thread_id])
            row=cur.fetchone()
            if not row: return None
            v=row[0]
            return _json_loads(v.read() if hasattr(v,"read") else v, None)

    async def append_sse_event(self, session_id: str, event_name: str, payload: dict) -> int:
        return await asyncio.to_thread(self._append_sse_event, session_id, event_name, payload)

    def _append_sse_event(self, session_id, event_name, payload):
        with self.connect() as conn:
            cur=conn.cursor()
            var=cur.var(int)
            cur.execute(f"insert into {self.t('SSE_EVENT')}(SESSION_ID,EVENT_NAME,PAYLOAD_JSON,CREATED_AT) values(:1,:2,:3,:4) returning ID into :5", [session_id,event_name,_json_dumps(payload),self.now(),var])
            return int(var.getvalue()[0])

    async def list_sse_events(self, session_id: str, after_id: int = 0, limit: int = 100) -> list[dict]:
        return await asyncio.to_thread(self._list_sse_events, session_id, after_id, limit)

    def _list_sse_events(self, session_id, after_id=0, limit=100):
        with self.connect() as conn:
            cur=conn.cursor()
            cur.execute(f"select ID,SESSION_ID,EVENT_NAME,PAYLOAD_JSON,CREATED_AT from {self.t('SSE_EVENT')} where SESSION_ID=:1 and ID>:2 order by ID asc fetch first :3 rows only", [session_id, after_id, limit])
            out=[]
            for row in cur.fetchall():
                v=row[3]
                out.append({"id": row[0], "session_id": row[1], "event_name": row[2], "payload": _json_loads(v.read() if hasattr(v,"read") else v, {}), "created_at": row[4]})
            return out

    async def cache_get(self, key: str):
        return await asyncio.to_thread(self._cache_get, key)

    def _cache_get(self, key):
        with self.connect() as conn:
            cur=conn.cursor()
            cur.execute(f"select VALUE_JSON, EXPIRES_AT from {self.t('CACHE_ENTRY')} where CACHE_KEY=:1", [key])
            row=cur.fetchone()
            if not row: return None
            expires=row[1]
            if expires and expires < self.now():
                cur.execute(f"delete from {self.t('CACHE_ENTRY')} where CACHE_KEY=:1", [key])
                return None
            v=row[0]
            return _json_loads(v.read() if hasattr(v,"read") else v, None)

    async def cache_set(self, key: str, value: Any, expires_at=None):
        return await asyncio.to_thread(self._cache_set, key, value, expires_at)

    def _cache_set(self, key, value, expires_at=None):
        now=self.now()
        with self.connect() as conn:
            conn.cursor().execute(f"""
                merge into {self.t('CACHE_ENTRY')} t using (select :key CACHE_KEY from dual) s on (t.CACHE_KEY=s.CACHE_KEY)
                when matched then update set VALUE_JSON=:value_json, EXPIRES_AT=:expires_at, UPDATED_AT=:updated_at
                when not matched then insert (CACHE_KEY,VALUE_JSON,EXPIRES_AT,CREATED_AT,UPDATED_AT) values (:key,:value_json,:expires_at,:created_at,:updated_at)
            """, dict(key=key, value_json=_json_dumps(value), expires_at=expires_at, created_at=now, updated_at=now))

    async def cache_delete(self, key: str):
        return await asyncio.to_thread(self._cache_delete, key)

    def _cache_delete(self, key):
        with self.connect() as conn:
            conn.cursor().execute(f"delete from {self.t('CACHE_ENTRY')} where CACHE_KEY=:1", [key])

    async def rag_add_text(self, doc_id: str, namespace: str, content: str, metadata: dict, embedding: list[float] | None = None):
        return await asyncio.to_thread(self._rag_add_text, doc_id, namespace, content, metadata, embedding)

    def _rag_add_text(self, doc_id, namespace, content, metadata, embedding=None):
        # Usa TO_VECTOR quando embedding é enviado como JSON. Se a versão do Oracle
        # não suportar VECTOR, a criação da tabela já falhará e o erro será claro.
        emb_json = json.dumps(embedding) if embedding is not None else None
        sql = f"insert into {self.t('RAG_DOCUMENT')}(ID,NAMESPACE,CONTENT,EMBEDDING,METADATA_JSON,CREATED_AT) values(:1,:2,:3,{ 'to_vector(:4)' if emb_json else 'null' },:5,:6)"
        params = [doc_id, namespace, content] + ([emb_json] if emb_json else []) + [_json_dumps(metadata), self.now()]
        with self.connect() as conn:
            conn.cursor().execute(sql, params)

    async def try_create_vector_index(self):
        return await asyncio.to_thread(self._try_create_vector_index)

    def try_create_vector_index(self):
        return self._try_create_vector_index()

    def _try_create_vector_index(self):
        # Oracle 23ai vector index; ignored when version/options are unavailable.
        with self.connect() as conn:
            cur=conn.cursor()
            try:
                cur.execute(f"""
                    create vector index {self.t('IX_RAG_VEC')}
                    on {self.t('RAG_DOCUMENT')}(EMBEDDING)
                    organization inmemory neighbor graph
                    distance COSINE
                    with target accuracy 95
                """)
            except Exception as exc:
                msg=str(exc)
                if "ORA-00955" in msg or "ORA-01408" in msg or "ORA-03001" in msg or "ORA-00904" in msg:
                    return
                logger.debug("Vector index não criado", exc_info=True)

    async def graph_add_edge(self, src: str, rel: str, dst: str, metadata: dict | None = None):
        return await asyncio.to_thread(self._graph_add_edge, src, rel, dst, metadata or {})

    def _upsert_graph_node(self, cur, node_id: str, label: str | None = None, metadata: dict | None = None):
        now=self.now()
        cur.execute(f"""
            merge into {self.t('GRAPH_NODE')} t
            using (select :node_id NODE_ID from dual) s
            on (t.NODE_ID=s.NODE_ID)
            when matched then update set UPDATED_AT=:updated_at
            when not matched then insert (NODE_ID,LABEL,METADATA_JSON,CREATED_AT,UPDATED_AT)
            values (:node_id,:label,:metadata_json,:created_at,:updated_at)
        """, dict(node_id=node_id, label=label, metadata_json=_json_dumps(metadata or {}), created_at=now, updated_at=now))

    def _graph_add_edge(self, src, rel, dst, metadata):
        with self.connect() as conn:
            cur=conn.cursor()
            self._upsert_graph_node(cur, src)
            self._upsert_graph_node(cur, dst)
            cur.execute(f"insert into {self.t('GRAPH_EDGE')}(SRC,REL,DST,METADATA_JSON,CREATED_AT) values(:1,:2,:3,:4,:5)", [src, rel, dst, _json_dumps(metadata), self.now()])

    async def graph_neighbors(self, node: str) -> list[tuple[str,str,str,dict]]:
        return await asyncio.to_thread(self._graph_neighbors, node)

    def _graph_neighbors(self, node):
        with self.connect() as conn:
            cur=conn.cursor()
            cur.execute(f"select SRC,REL,DST,METADATA_JSON from {self.t('GRAPH_EDGE')} where SRC=:1 or DST=:2", [node, node])
            out=[]
            for src,rel,dst,meta in cur.fetchall():
                out.append((src,rel,dst,_json_loads(meta.read() if hasattr(meta,"read") else meta, {})))
            return out

    async def graph_neighbors_pgql(self, graph_name: str, node: str) -> list[dict]:
        return await asyncio.to_thread(self._graph_neighbors_pgql, graph_name, node)

    def _graph_neighbors_pgql(self, graph_name: str, node: str) -> list[dict]:
        # Oracle 23ai SQL property graph query using GRAPH_TABLE.
        with self.connect() as conn:
            cur=conn.cursor()
            cur.execute(f"""
                select SRC, REL, DST, METADATA_JSON
                from graph_table({graph_name}
                    match (a)-[e]->(b)
                    where a.NODE_ID = :node or b.NODE_ID = :node
                    columns (
                        a.NODE_ID as SRC,
                        e.REL as REL,
                        b.NODE_ID as DST,
                        e.METADATA_JSON as METADATA_JSON
                    )
                )
            """, {"node": node})
            out=[]
            for src,rel,dst,meta in cur.fetchall():
                out.append({"src": src, "rel": rel, "dst": dst, "metadata": _json_loads(meta.read() if hasattr(meta,"read") else meta, {})})
            return out

    async def graph_pgql(self, query: str, binds: dict | None = None) -> list[dict]:
        return await asyncio.to_thread(self._graph_pgql, query, binds or {})

    def _graph_pgql(self, query: str, binds: dict | None = None) -> list[dict]:
        with self.connect() as conn:
            cur=conn.cursor()
            cur.execute(query, binds or {})
            cols=[d[0].lower() for d in cur.description] if cur.description else []
            rows=[]
            for row in cur.fetchall():
                item={}
                for k,v in zip(cols,row):
                    item[k]=v.read() if hasattr(v,"read") else v
                rows.append(item)
            return rows

    async def try_create_property_graph(self, graph_name: str):
        return await asyncio.to_thread(self._try_create_property_graph, graph_name)

    def try_create_property_graph(self, graph_name: str):
        return self._try_create_property_graph(graph_name)

    def _try_create_property_graph(self, graph_name: str):
        with self.connect() as conn:
            cur=conn.cursor()
            try:
                cur.execute(f"""
                    create property graph {graph_name}
                    vertex tables (
                        {self.t('GRAPH_NODE')} key (NODE_ID)
                        properties (NODE_ID, LABEL, METADATA_JSON)
                    )
                    edge tables (
                        {self.t('GRAPH_EDGE')} key (ID)
                        source key (SRC) references {self.t('GRAPH_NODE')}(NODE_ID)
                        destination key (DST) references {self.t('GRAPH_NODE')}(NODE_ID)
                        properties (REL, METADATA_JSON)
                    )
                """)
            except Exception as exc:
                msg=str(exc)
                if "ORA-00955" in msg or "already" in msg.lower():
                    return
                logger.debug("Property graph não criado", exc_info=True)
