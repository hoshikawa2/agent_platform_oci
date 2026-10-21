"""Verify SSE flush and disconnect/reconnect over a real local HTTP connection."""
import asyncio
import json
import socket
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
pytest.importorskip("a2a", reason="Install agent-framework[a2a] to run A2A tests")

from agent_framework.a2a.server import install_a2a
from agent_framework.global_supervisor.models import BackendDefinition


@pytest.mark.parametrize('legacy', [False, True])
def test_sse_flush_disconnect_and_resubscribe(legacy):
    release = threading.Event()
    finished = threading.Event()
    async def handler(request):
        while not release.is_set():
            await asyncio.sleep(.005)
        finished.set()
        return {'text': 'stream complete'}
    app = FastAPI()
    registry = SimpleNamespace(list=lambda: [BackendDefinition(backend_id='x', url='http://native')])
    install_a2a(app, handler, registry, 'http://testserver')
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 3
        while not server.started and time.monotonic() < deadline:
            time.sleep(.005)
        assert server.started
        base_url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        with httpx.Client(base_url=base_url, headers={'A2A-Version': '0.3' if legacy else '1.0'}, timeout=2, trust_env=False) as client:
            message = {'messageId': 'm', 'role': 'user' if legacy else 'ROLE_USER',
                       'parts': [{'kind': 'text', 'text': 'run'}] if legacy else [{'text': 'run'}]}
            if legacy: message['kind'] = 'message'
            def envelope(method, params):
                return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}
            with client.stream('POST', '/a2a', json=envelope('message/stream' if legacy else 'SendStreamingMessage', {'message': message})) as response:
                assert response.status_code == 200
                for line in response.iter_lines():
                    if line.startswith('data:'):
                        event = json.loads(line[5:].strip())
                        first = event['result'] if legacy else event['result']['task']
                        task_id = first['id']
                        break
                else:
                    pytest.fail('SSE did not deliver an initial Task')
                assert not release.is_set() and not finished.is_set()
            # Closing the first SSE connection must not cancel the agent task.
            current = client.post('/a2a', json=envelope('tasks/get' if legacy else 'GetTask', {'id': task_id})).json()
            assert current['result']['status']['state'] in ({'submitted', 'working'} if legacy else {'TASK_STATE_SUBMITTED', 'TASK_STATE_WORKING'})
            with client.stream('POST', '/a2a', json=envelope('tasks/resubscribe' if legacy else 'SubscribeToTask', {'id': task_id})) as response:
                events = []
                for line in response.iter_lines():
                    if not line.startswith('data:'):
                        continue
                    event = json.loads(line[5:].strip())
                    assert 'error' not in event, event
                    events.append(event)
                    if len(events) == 1:
                        release.set()
                encoded = json.dumps(events)
                assert 'stream complete' in encoded
                assert ('completed' if legacy else 'TASK_STATE_COMPLETED') in encoded
                assert finished.is_set()
    finally:
        release.set()
        server.should_exit = True
        thread.join(timeout=3)
        sock.close()
        assert not thread.is_alive()
