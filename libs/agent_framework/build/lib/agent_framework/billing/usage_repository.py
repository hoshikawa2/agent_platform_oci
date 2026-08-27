from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from agent_framework.observability.context import get_observability_context

@dataclass
class UsageRecord:
    provider: str
    model: str
    operation: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_brl: float = 0.0
    metadata: dict[str, Any] | None = None
    request_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    agent_id: str | None = None
    user_id: str | None = None
    message_id: str | None = None
    created_at: str | None = None

    @classmethod
    def from_usage(cls, provider: str, model: str, operation: str, usage: dict[str, Any], metadata: dict[str, Any] | None = None) -> "UsageRecord":
        ctx = get_observability_context()
        return cls(
            provider=provider, model=model, operation=operation,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cached_tokens=int(usage.get("cached_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            cost_usd=float(usage.get("cost_usd") or 0),
            cost_brl=float(usage.get("cost_brl") or 0),
            metadata=metadata or {}, request_id=ctx.request_id, session_id=ctx.session_id,
            tenant_id=ctx.tenant_id, agent_id=ctx.agent_id, user_id=ctx.user_id,
            message_id=ctx.message_id, created_at=datetime.now(timezone.utc),
        )

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

class UsageRepository:
    async def record(self, usage: UsageRecord) -> None: ...
    async def summarize(self, *, tenant_id: str | None = None, session_id: str | None = None) -> dict[str, Any]: ...

class SQLiteUsageRepository(UsageRepository):
    def __init__(self, settings):
        from agent_framework.persistence.sqlite_store import SQLiteStore
        self.store = SQLiteStore(settings.SQLITE_DB_PATH)
        self._init_schema()

    def _init_schema(self):
        ddl = """
        create table if not exists llm_usage_records (
            id integer primary key autoincrement,
            request_id text, session_id text, tenant_id text, agent_id text, user_id text, message_id text,
            provider text not null, model text not null, operation text not null,
            prompt_tokens integer not null default 0,
            completion_tokens integer not null default 0,
            cached_tokens integer not null default 0,
            total_tokens integer not null default 0,
            cost_usd real not null default 0,
            cost_brl real not null default 0,
            metadata_json text,
            created_at text not null
        );
        create index if not exists idx_usage_tenant_created on llm_usage_records(tenant_id, created_at);
        create index if not exists idx_usage_session_created on llm_usage_records(session_id, created_at);
        """
        with self.store._lock, self.store.connect() as con:
            con.executescript(ddl)

    async def record(self, usage: UsageRecord) -> None:
        with self.store._lock, self.store.connect() as con:
            con.execute("""
                insert into llm_usage_records(
                    request_id,session_id,tenant_id,agent_id,user_id,message_id,
                    provider,model,operation,prompt_tokens,completion_tokens,cached_tokens,total_tokens,
                    cost_usd,cost_brl,metadata_json,created_at
                ) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                usage.request_id, usage.session_id, usage.tenant_id, usage.agent_id, usage.user_id, usage.message_id,
                usage.provider, usage.model, usage.operation, usage.prompt_tokens, usage.completion_tokens,
                usage.cached_tokens, usage.total_tokens, usage.cost_usd, usage.cost_brl,
                json.dumps(usage.metadata or {}, ensure_ascii=False, default=str), usage.created_at,
            ))

    async def summarize(self, *, tenant_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        where=[]; params=[]
        if tenant_id: where.append('tenant_id=?'); params.append(tenant_id)
        if session_id: where.append('session_id=?'); params.append(session_id)
        sql="""select count(*) calls, coalesce(sum(prompt_tokens),0) prompt_tokens,
                      coalesce(sum(completion_tokens),0) completion_tokens,
                      coalesce(sum(total_tokens),0) total_tokens,
                      coalesce(sum(cost_usd),0) cost_usd,
                      coalesce(sum(cost_brl),0) cost_brl
               from llm_usage_records"""
        if where: sql += ' where ' + ' and '.join(where)
        with self.store._lock, self.store.connect() as con:
            row=con.execute(sql, params).fetchone()
        return dict(row) if row else {"calls":0,"prompt_tokens":0,"completion_tokens":0,"total_tokens":0,"cost_usd":0,"cost_brl":0}

class OracleUsageRepository(UsageRepository):
    def __init__(self, settings):
        from agent_framework.persistence.oracle_store import OracleStore
        self.store = OracleStore(settings)
        self._init_schema()

    def _init_schema(self):
        with self.store.connect() as conn:
            cur=conn.cursor()
            self.store._exec_ddl_ignore_exists(cur, f"""
                create table {self.store.t('LLM_USAGE_RECORD')} (
                    ID number generated always as identity primary key,
                    REQUEST_ID varchar2(128), SESSION_ID varchar2(256), TENANT_ID varchar2(128),
                    AGENT_ID varchar2(128), USER_ID varchar2(256), MESSAGE_ID varchar2(256),
                    PROVIDER varchar2(128) not null, MODEL varchar2(256) not null, OPERATION varchar2(128) not null,
                    PROMPT_TOKENS number default 0, COMPLETION_TOKENS number default 0, CACHED_TOKENS number default 0,
                    TOTAL_TOKENS number default 0, COST_USD number default 0, COST_BRL number default 0,
                    METADATA_JSON clob check (METADATA_JSON is json), CREATED_AT timestamp with time zone not null
                )
            """)
            self.store._exec_ddl_ignore_exists(cur, f"create index {self.store.t('IX_USAGE_TENANT')} on {self.store.t('LLM_USAGE_RECORD')}(TENANT_ID, CREATED_AT)")
            self.store._exec_ddl_ignore_exists(cur, f"create index {self.store.t('IX_USAGE_SESSION')} on {self.store.t('LLM_USAGE_RECORD')}(SESSION_ID, CREATED_AT)")

    async def record(self, usage: UsageRecord) -> None:
        await asyncio.to_thread(self._record_sync, usage)

    def _record_sync(self, usage: UsageRecord):
        with self.store.connect() as conn:
            conn.cursor().execute(f"""
                insert into {self.store.t('LLM_USAGE_RECORD')}(
                    REQUEST_ID,SESSION_ID,TENANT_ID,AGENT_ID,USER_ID,MESSAGE_ID,PROVIDER,MODEL,OPERATION,
                    PROMPT_TOKENS,COMPLETION_TOKENS,CACHED_TOKENS,TOTAL_TOKENS,COST_USD,COST_BRL,METADATA_JSON,CREATED_AT
                ) values(:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13,:14,:15,:16,:17)
            """, [
                usage.request_id, usage.session_id, usage.tenant_id, usage.agent_id, usage.user_id, usage.message_id,
                usage.provider, usage.model, usage.operation, usage.prompt_tokens, usage.completion_tokens, usage.cached_tokens,
                usage.total_tokens, usage.cost_usd, usage.cost_brl, json.dumps(usage.metadata or {}, ensure_ascii=False, default=str), usage.created_at,
            ])

    async def summarize(self, *, tenant_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        return await asyncio.to_thread(self._summarize_sync, tenant_id, session_id)

    def _summarize_sync(self, tenant_id, session_id):
        where=[]; params={}
        if tenant_id: where.append('TENANT_ID=:tenant_id'); params['tenant_id']=tenant_id
        if session_id: where.append('SESSION_ID=:session_id'); params['session_id']=session_id
        sql=f"""select count(*) CALLS, coalesce(sum(PROMPT_TOKENS),0) PROMPT_TOKENS,
                       coalesce(sum(COMPLETION_TOKENS),0) COMPLETION_TOKENS,
                       coalesce(sum(TOTAL_TOKENS),0) TOTAL_TOKENS,
                       coalesce(sum(COST_USD),0) COST_USD,
                       coalesce(sum(COST_BRL),0) COST_BRL
                from {self.store.t('LLM_USAGE_RECORD')}"""
        if where: sql += ' where ' + ' and '.join(where)
        with self.store.connect() as conn:
            cur=conn.cursor(); cur.execute(sql, params); row=cur.fetchone()
            cols=[d[0].lower() for d in cur.description]
            return dict(zip(cols,row)) if row else {}

def create_usage_repository(settings) -> UsageRepository:
    provider = getattr(settings, 'USAGE_REPOSITORY_PROVIDER', None) or getattr(settings, 'MEMORY_REPOSITORY_PROVIDER', 'memory')
    if provider in {'autonomous','oracle'}:
        return OracleUsageRepository(settings)
    return SQLiteUsageRepository(settings)
