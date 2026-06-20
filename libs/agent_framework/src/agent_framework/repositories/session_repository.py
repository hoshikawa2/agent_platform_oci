from abc import ABC, abstractmethod
from datetime import datetime, timezone
from agent_framework.models.session import SessionContext
from agent_framework.persistence.sqlite_store import SQLiteStore

class SessionRepository(ABC):
    @abstractmethod
    async def get(self, session_id: str) -> SessionContext | None: ...
    @abstractmethod
    async def upsert(self, session: SessionContext) -> SessionContext: ...

class InMemorySessionRepository(SessionRepository):
    def __init__(self): self._data: dict[str, SessionContext] = {}
    async def get(self, session_id: str): return self._data.get(session_id)
    async def upsert(self, session: SessionContext):
        session.updated_at=datetime.now(timezone.utc)
        self._data[session.session_id]=session
        return session

def _session_from_row(d: dict) -> SessionContext:
    ctx=d.get('context') or {}
    metadata=d.get('metadata') or {}
    return SessionContext(
        tenant_id=d.get('tenant_id') or ctx.get('tenant_id') or 'default',
        agent_id=d.get('agent_id') or ctx.get('agent_id') or 'default_agent',
        session_id=d['session_id'], user_id=d.get('user_id'), channel=d.get('channel') or 'web',
        channel_id=d.get('channel_id'), metadata=metadata,
        **{k:v for k,v in ctx.items() if k in SessionContext.model_fields and k not in {'tenant_id','agent_id','session_id','user_id','channel','channel_id','metadata','created_at','updated_at'}}
    )

class SQLiteSessionRepository(SessionRepository):
    def __init__(self, settings): self.store=SQLiteStore(settings.SQLITE_DB_PATH)
    async def get(self, session_id: str):
        d=self.store.get_session(session_id)
        return _session_from_row(d) if d else None
    async def upsert(self, session: SessionContext):
        session.updated_at=datetime.now(timezone.utc)
        data=session.model_dump(mode='json')
        self.store.upsert_session(session.session_id, session.tenant_id, session.agent_id, session.user_id, session.channel, session.channel_id, data, session.metadata)
        return session

class OracleSessionRepository(SessionRepository):
    """SessionRepository real para Oracle Autonomous Database, equivalente ao padrão FIRST."""
    def __init__(self, settings):
        from agent_framework.persistence.oracle_store import OracleStore
        self.store=OracleStore(settings)
    async def get(self, session_id: str):
        d=await self.store.get_session(session_id)
        return _session_from_row(d) if d else None
    async def upsert(self, session: SessionContext):
        session.updated_at=datetime.now(timezone.utc)
        data=session.model_dump(mode='json')
        await self.store.upsert_session(session.session_id, session.tenant_id, session.agent_id, session.user_id, session.channel, session.channel_id, data, session.metadata)
        return session

AutonomousSessionRepository = OracleSessionRepository

class MongoSessionRepository(SessionRepository):
    def __init__(self, settings):
        from pymongo import MongoClient
        self.client = MongoClient(settings.MONGODB_URI)
        self.col = self.client[settings.MONGODB_DATABASE]['sessions']
    async def get(self, session_id: str):
        doc = self.col.find_one({'session_id': session_id})
        return SessionContext.model_validate({k:v for k,v in doc.items() if k!='_id'}) if doc else None
    async def upsert(self, session: SessionContext):
        session.updated_at=datetime.now(timezone.utc)
        self.col.update_one({'session_id': session.session_id}, {'$set': session.model_dump(mode='json')}, upsert=True)
        return session

def create_session_repository(settings) -> SessionRepository:
    provider=getattr(settings,'SESSION_REPOSITORY_PROVIDER','memory')
    if provider == 'mongodb': return MongoSessionRepository(settings)
    if provider == 'sqlite': return SQLiteSessionRepository(settings)
    if provider in {'autonomous','oracle'}: return OracleSessionRepository(settings)
    return InMemorySessionRepository()
