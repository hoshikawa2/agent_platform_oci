import pytest
from types import SimpleNamespace
from agent_framework.sse.events import SSEEvent, SSEHub

@pytest.mark.asyncio
async def test_sse_event_encoding():
    encoded = SSEEvent(event='message', data={'text':'ok'}, id=10).encode()
    assert 'id: 10' in encoded
    assert 'event: message' in encoded
    assert 'data: {"text": "ok"}' in encoded

@pytest.mark.asyncio
async def test_sse_hub_emit_and_replay(tmp_path):
    settings = SimpleNamespace(SQLITE_DB_PATH=str(tmp_path/'db.sqlite'), SSE_KEEPALIVE_SECONDS=0.1, SSE_EVENT_REPLAY_LIMIT=10, SESSION_REPOSITORY_PROVIDER='sqlite', SSE_STORE_PROVIDER='sqlite')
    hub = SSEHub(settings)
    eid = await hub.emit('s1', 'flow.start', {'a': 1})
    replayed = await hub.replay('s1', 0)
    assert replayed[0].id == eid
    assert replayed[0].event == 'flow.start'
