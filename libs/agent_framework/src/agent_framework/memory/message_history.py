from abc import ABC, abstractmethod
from agent_framework.models.session import ChatMessage
from agent_framework.persistence.sqlite_store import SQLiteStore

class ConversationMemory(ABC):
    @abstractmethod
    async def append(self, session_id: str, message: ChatMessage) -> None: ...
    @abstractmethod
    async def list(self, session_id: str, limit: int = 50) -> list[ChatMessage]: ...

class InMemoryMessageHistory(ConversationMemory):
    def __init__(self): self._data: dict[str, list[ChatMessage]] = {}
    async def append(self, session_id: str, message: ChatMessage): self._data.setdefault(session_id, []).append(message)
    async def list(self, session_id: str, limit: int = 50): return self._data.get(session_id, [])[-limit:]

class SQLiteMessageHistory(ConversationMemory):
    def __init__(self, settings): self.store=SQLiteStore(settings.SQLITE_DB_PATH)
    async def append(self, session_id: str, message: ChatMessage):
        message_id=(message.metadata or {}).get('message_id')
        self.store.insert_message(session_id, message.role, message.content, message.metadata, message_id=message_id)
    async def list(self, session_id: str, limit: int = 50):
        return [ChatMessage(role=r['role'], content=r['content'], metadata=r.get('metadata') or {}, created_at=r['created_at']) for r in self.store.list_messages(session_id, limit)]

class OracleMessageHistory(ConversationMemory):
    """Histórico Oracle com idempotência por message_id, replay e token_usage_json."""
    def __init__(self, settings):
        from agent_framework.persistence.oracle_store import OracleStore
        self.store=OracleStore(settings)
    def normalize_lob(self, value):
        if value is None:
            return ""

        if hasattr(value, "read"):
            return value.read()

        return str(value)
    async def append(self, session_id: str, message: ChatMessage):
        meta=message.metadata or {}
        await self.store.insert_message(session_id, message.role, message.content, meta, message_id=meta.get('message_id'), token_usage=meta.get('token_usage'))
    async def list(self, session_id: str, limit: int = 50):
        rows=await self.store.list_messages(session_id, limit)
        return [ChatMessage(role=r['role'], content=self.normalize_lob(r['content']) or '', metadata=r.get('metadata') or {}, created_at=r['created_at']) for r in rows]

DatabaseMessageHistory = OracleMessageHistory

class MongoMessageHistory(ConversationMemory):
    def __init__(self, settings):
        from pymongo import MongoClient
        self.client=MongoClient(settings.MONGODB_URI)
        self.col=self.client[settings.MONGODB_DATABASE]['messages']
    async def append(self, session_id, message):
        doc=message.model_dump(mode='json'); doc['session_id']=session_id
        mid=(message.metadata or {}).get('message_id')
        if mid:
            self.col.update_one({'session_id':session_id,'metadata.message_id':mid},{'$setOnInsert':doc},upsert=True)
        else:
            self.col.insert_one(doc)
    async def list(self, session_id, limit=50):
        docs=list(self.col.find({'session_id':session_id}).sort('created_at',-1).limit(limit))
        return [ChatMessage.model_validate({k:v for k,v in d.items() if k!='_id' and k!='session_id'}) for d in reversed(docs)]

def create_memory(settings) -> ConversationMemory:
    provider=getattr(settings,'MEMORY_REPOSITORY_PROVIDER','memory')
    if provider == 'mongodb': return MongoMessageHistory(settings)
    if provider == 'sqlite': return SQLiteMessageHistory(settings)
    if provider in {'autonomous','oracle'}: return OracleMessageHistory(settings)
    return InMemoryMessageHistory()
