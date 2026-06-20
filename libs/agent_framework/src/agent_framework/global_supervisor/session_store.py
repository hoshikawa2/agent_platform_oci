from __future__ import annotations

import time
from dataclasses import asdict

from .models import GlobalSessionState


class InMemoryGlobalSessionStore:
    """Store simples para o Agent Gateway.

    Em produção, use o mesmo repositório compartilhado dos backends
    (Autonomous DB/Mongo/Redis) para manter handoff entre serviços.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._data: dict[str, tuple[float, GlobalSessionState]] = {}

    async def get(self, session_id: str) -> GlobalSessionState | None:
        item = self._data.get(session_id)
        if not item:
            return None
        ts, state = item
        if time.time() - ts > self.ttl_seconds:
            self._data.pop(session_id, None)
            return None
        return state

    async def upsert(self, state: GlobalSessionState) -> None:
        state.turn_count += 1
        self._data[state.session_id] = (time.time(), state)

    async def set_active_backend(self, session_id: str, backend_id: str, tenant_id: str = "default", **metadata) -> GlobalSessionState:
        state = await self.get(session_id) or GlobalSessionState(session_id=session_id, tenant_id=tenant_id)
        state.active_backend = backend_id
        state.metadata.update(metadata)
        await self.upsert(state)
        return state

    async def dump(self) -> dict:
        return {k: asdict(v[1]) for k, v in self._data.items()}

    async def rename_session(
            self,
            old_session_id: str,
            new_session_id: str
    ) -> GlobalSessionState | None:

        item = self._data.pop(old_session_id, None)

        if not item:
            return None

        ts, state = item

        state.session_id = new_session_id

        self._data[new_session_id] = (ts, state)

        return state