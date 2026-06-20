import pytest
from types import SimpleNamespace
from agent_framework.sse.events import SSEHub, SSEEvent


class MemorySSEStore:
    def __init__(self):
        self.rows=[]; self.next_id=1
    def append_sse_event(self, session_id, event, payload):
        row={"id": self.next_id, "session_id": session_id, "event_name": event, "payload": payload}
        self.next_id += 1; self.rows.append(row); return row["id"]
    def list_sse_events(self, session_id, after_id, limit):
        return [r for r in self.rows if r["session_id"] == session_id and r["id"] > after_id][:limit]


@pytest.mark.asyncio
async def test_subscribe_skips_live_event_already_replayed():
    hub = SSEHub(SimpleNamespace(SSE_KEEPALIVE_SECONDS=0.01, SSE_EVENT_REPLAY_LIMIT=100, SQLITE_DB_PATH=':memory:', SESSION_REPOSITORY_PROVIDER='sqlite'), telemetry=None)
    hub.store = MemorySSEStore()
    eid = await hub.emit("s1", "message.responded", {"text":"ok"})
    # Same event remains in live queue and is also in replay store.
    gen = hub.subscribe("s1", 0)
    chunks=[]
    chunks.append(await gen.__anext__())  # replay event
    chunks.append(await gen.__anext__())  # connected
    chunks.append(await gen.__anext__())  # keepalive, not duplicated event
    assert chunks[0].startswith(f"id: {eid}")
    assert "message.responded" in chunks[0]
    assert "message.responded" not in chunks[2]
    await gen.aclose()
