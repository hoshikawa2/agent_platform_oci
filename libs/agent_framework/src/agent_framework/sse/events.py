from __future__ import annotations
import asyncio, json, time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

@dataclass
class SSEEvent:
    event: str
    data: dict[str, Any]
    id: int | None = None
    def encode(self) -> str:
        lines=[]
        if self.id is not None: lines.append(f'id: {self.id}')
        lines.append(f'event: {self.event}')
        payload=json.dumps(self.data, ensure_ascii=False, default=str)
        for line in payload.splitlines() or ['{}']:
            lines.append(f'data: {line}')
        return '\n'.join(lines)+'\n\n'

@dataclass
class SessionStream:
    queue: asyncio.Queue[SSEEvent] = field(default_factory=asyncio.Queue)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    connected_at: float = field(default_factory=time.time)

class SessionLockManager:
    def __init__(self): self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    def lock_for(self, session_id: str) -> asyncio.Lock: return self._locks[session_id]

class SSEHub:
    """Hub SSE enterprise no padrão FIRST.

    - lock por sessão para impedir turnos concorrentes;
    - keepalive configurável;
    - replay persistente por Last-Event-ID;
    - eventos rastreados em Langfuse/OTEL/event bus.
    """
    def __init__(self, settings, telemetry=None):
        self.settings=settings
        self.telemetry=telemetry
        self.keepalive=float(getattr(settings,'SSE_KEEPALIVE_SECONDS',15.0))
        self.replay_limit=int(getattr(settings,'SSE_EVENT_REPLAY_LIMIT',100))
        self._streams: dict[str, SessionStream]=defaultdict(SessionStream)
        self.locks=SessionLockManager()
        provider=getattr(settings,'SSE_STORE_PROVIDER', None) or getattr(settings,'SESSION_REPOSITORY_PROVIDER','sqlite')
        if provider in {'autonomous','oracle'}:
            from agent_framework.persistence.oracle_store import OracleStore
            self.store=OracleStore(settings)
            self._async_store=True
        if provider in {'sqlite'}:
            from agent_framework.persistence.sqlite_store import SQLiteStore
            self.store=SQLiteStore(getattr(settings,'SQLITE_DB_PATH','./data/agent_framework.db'))
            self._async_store=False
        if provider in {'mongodb'}:
            from agent_framework.persistence.mongodb_store import MongoDBStore
            self.store = MongoDBStore(settings)
            self._async_store = True

    def stream_for(self, session_id: str) -> SessionStream:
        stream=self._streams[session_id]
        stream.lock=self.locks.lock_for(session_id)
        return stream
    async def _append(self, session_id, event, payload):
        if self._async_store: return await self.store.append_sse_event(session_id,event,payload)
        return self.store.append_sse_event(session_id,event,payload)
    async def _list(self, session_id, after_id, limit):
        if self._async_store: return await self.store.list_sse_events(session_id,after_id,limit)
        return self.store.list_sse_events(session_id,after_id,limit)
    async def emit(self, session_id: str, event: str, payload: dict[str, Any]):
        eid=await self._append(session_id, event, payload)
        await self.stream_for(session_id).queue.put(SSEEvent(event=event, data=payload, id=eid))
        if self.telemetry:
            await self.telemetry.event('sse.event.emitted', {'session_id': session_id, 'event': event, 'event_id': eid}, kind='sse')
        return eid
    async def replay(self, session_id: str, after_id: int=0) -> list[SSEEvent]:
        rows=await self._list(session_id, after_id=after_id, limit=self.replay_limit)
        if self.telemetry:
            await self.telemetry.event('sse.replay', {'session_id': session_id, 'after_id': after_id, 'count': len(rows)}, kind='sse')
        return [SSEEvent(event=r['event_name'], data=r.get('payload') or r.get('data') or {}, id=r['id']) for r in rows]
    async def subscribe(self, session_id: str, last_event_id: int = 0) -> AsyncIterator[str]:
        if self.telemetry:
            await self.telemetry.event(
                "sse.connected",
                {"session_id": session_id, "last_event_id": last_event_id},
                kind="sse",
            )

        replayed = await self.replay(session_id, last_event_id)

        max_replayed_id = last_event_id
        for ev in replayed:
            if ev.id is not None:
                max_replayed_id = max(max_replayed_id, ev.id)
            yield ev.encode()

        stream = self.stream_for(session_id)
        q = stream.queue

        yield SSEEvent(
            event="connected",
            data={"session_id": session_id, "ts": time.time()},
        ).encode()

        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=self.keepalive)

                if ev.id is not None and ev.id <= max_replayed_id:
                    continue

                if ev.id is not None:
                    max_replayed_id = max(max_replayed_id, ev.id)

                yield ev.encode()

            except asyncio.TimeoutError:
                if self.telemetry:
                    await self.telemetry.event(
                        "sse.keepalive",
                        {"session_id": session_id},
                        kind="sse",
                    )
                yield ": keepalive\n\n"

            except asyncio.CancelledError:
                if self.telemetry:
                    await self.telemetry.event(
                        "sse.disconnected",
                        {"session_id": session_id},
                        kind="sse",
                    )
                raise