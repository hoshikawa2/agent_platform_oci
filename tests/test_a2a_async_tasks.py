"""Real SDK/FastAPI tests: no mock task manager or custom JSON-RPC dispatcher."""
import asyncio
import json
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
pytest.importorskip("a2a", reason="Install agent-framework[a2a] to run A2A tests")

from agent_framework.a2a.server import install_a2a, install_backend_a2a
from agent_framework.a2a.progress import report_progress
from agent_framework.global_supervisor.models import BackendDefinition


HEADERS = {'A2A-Version': '1.0'}


def send(client, method, params, legacy=False):
    return client.post('/a2a', headers={'A2A-Version': '0.3' if legacy else '1.0'}, json={
        'jsonrpc': '2.0', 'id': 'request', 'method': method, 'params': params,
    })


def message_params(legacy=False, immediate=True, task_id=None):
    message = {'messageId': 'm-' + str(time.monotonic_ns()), 'contextId': 'session',
               'role': 'user' if legacy else 'ROLE_USER', 'parts': [{'text': 'Olá'}]}
    if task_id:
        message['taskId'] = task_id
    if legacy:
        message['kind'] = 'message'
        message['parts'][0]['kind'] = 'text'
    return {'message': message,
            'configuration': {'blocking': not immediate} if legacy else {'returnImmediately': immediate}}


def task_result(response, legacy=False):
    data = response.json()
    assert 'error' not in data, data
    return data['result'] if legacy else data['result']['task']


def get_task(client, task_id, legacy=False):
    data = send(client, 'tasks/get' if legacy else 'GetTask', {'id': task_id}, legacy).json()
    assert 'error' not in data, data
    return data['result']


def wait_state(client, task_id, expected, legacy=False):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        task = get_task(client, task_id, legacy)
        if task['status']['state'] == expected:
            return task
        time.sleep(.005)
    pytest.fail(f'Task did not reach {expected}: {task}')


def application(handler, **kwargs):
    app = FastAPI()
    registry = SimpleNamespace(list=lambda: [BackendDefinition(backend_id='native', url='http://native')])
    install_a2a(app, handler, registry, 'http://testserver', **kwargs)
    return app


@pytest.mark.parametrize('legacy', [False, True])
def test_submit_returns_before_processing_and_poll_after_disconnect(legacy):
    release = threading.Event()
    async def handler(request):
        while not release.is_set():
            await asyncio.sleep(.005)
        return {'text': 'done', 'session_id': request['session_id']}
    with TestClient(application(handler)) as client:
        try:
            first = task_result(send(client, 'message/send' if legacy else 'SendMessage', message_params(legacy), legacy), legacy)
            assert not release.is_set()
            assert first['status']['state'] in ({'submitted', 'working'} if legacy else {'TASK_STATE_SUBMITTED', 'TASK_STATE_WORKING'})
            assert get_task(client, first['id'], legacy)['contextId'] == 'session'
            release.set()
            task = wait_state(client, first['id'], 'completed' if legacy else 'TASK_STATE_COMPLETED', legacy)
            assert task['artifacts'][0]['parts'][0]['text'] == 'done'
        finally:
            release.set()


@pytest.mark.parametrize('legacy', [False, True])
def test_stream_contains_task_progress_artifact_and_terminal_state(legacy):
    async def handler(request):
        await report_progress('workflow.started', {'route': 'orders'})
        await asyncio.sleep(.01)
        await report_progress('workflow.completed', {'route': 'orders'})
        return {'text': 'done'}
    with TestClient(application(handler)) as client:
        assert client.get('/.well-known/agent-card.json').json()['capabilities']['streaming']
        response = send(client, 'message/stream' if legacy else 'SendStreamingMessage', message_params(legacy, immediate=False), legacy)
        assert 'text/event-stream' in response.headers['content-type'], response.text
        events = [json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith('data:')]
        assert events and all('error' not in e for e in events), events
        text = json.dumps(events)
        assert 'workflow.started' in text and 'workflow.completed' in text
        assert 'done' in text
        assert ('completed' if legacy else 'TASK_STATE_COMPLETED') in text
        first = events[0]['result']
        assert ('id' in first if legacy else 'task' in first), events


def test_cancel_stops_local_execution():
    started, stopped = threading.Event(), threading.Event()
    async def handler(request):
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            stopped.set()
    with TestClient(application(handler)) as client:
        first = task_result(send(client, 'SendMessage', message_params()))
        assert started.wait(1)
        result = send(client, 'CancelTask', {'id': first['id']}).json()
        assert 'error' not in result, result
        assert result['result']['status']['state'] == 'TASK_STATE_CANCELED'
        assert stopped.wait(1)
        assert get_task(client, first['id'])['status']['state'] == 'TASK_STATE_CANCELED'


@pytest.mark.parametrize('failure', ['exception', 'timeout'])
def test_failure_is_persisted(failure):
    async def handler(request):
        if failure == 'exception':
            raise RuntimeError('internal-sensitive-detail')
        await asyncio.sleep(1)
    with TestClient(application(handler, timeout_seconds=.02)) as client:
        first = task_result(send(client, 'SendMessage', message_params()))
        task = wait_state(client, first['id'], 'TASK_STATE_FAILED')
        assert 'internal-sensitive-detail' not in json.dumps(task)
        assert task['status']['message']['parts'][0]['text'] == ('Processing timed out' if failure == 'timeout' else 'Agent processing failed')


def test_input_required_resumes_same_task():
    turns = []
    async def handler(request):
        turns.append(request)
        return {'text': 'Confirmar?' if len(turns) == 1 else 'Concluído',
                'metadata': {'a2a_task_state': 'input-required'} if len(turns) == 1 else {}}
    with TestClient(application(handler)) as client:
        first = task_result(send(client, 'SendMessage', message_params(immediate=False)))
        assert first['status']['state'] == 'TASK_STATE_INPUT_REQUIRED'
        second = task_result(send(client, 'SendMessage', message_params(immediate=False, task_id=first['id'])))
        assert second['id'] == first['id']
        assert second['status']['state'] == 'TASK_STATE_COMPLETED'
        assert len(turns) == 2
        # A completed task cannot execute a third business operation.
        response = send(client, 'SendMessage', message_params(task_id=first['id'])).json()
        assert 'error' in response
        assert len(turns) == 2


def test_backend_installer_exposes_agent_skills():
    seen = []
    async def handler(request):
        seen.append(request)
        return {'text': 'native agent', 'session_id': request['session_id']}
    profiles = SimpleNamespace(list_profiles=lambda: [SimpleNamespace(agent_id='orders', name='Orders', description='Order status')])
    settings = SimpleNamespace(A2A_PUBLIC_URL='https://backend.example', A2A_SECURITY_SCHEMES={}, A2A_SECURITY=[],
        A2A_TASK_MODE=True, A2A_TASK_TIMEOUT_SECONDS=10, APP_NAME='Framework backend')
    app = FastAPI()
    install_backend_a2a(app, handler, profiles, settings)
    with TestClient(app) as client:
        card = client.get('/.well-known/agent-card.json').json()
        assert card['skills'][0]['id'] == 'orders'
        assert card['supportedInterfaces'][0]['url'] == 'https://backend.example/a2a'
        params = message_params(immediate=False)
        params['message']['metadata'] = {'agent_id': 'orders', 'tenant_id': 't'}
        final = task_result(send(client, 'SendMessage', params))
        assert final['status']['state'] == 'TASK_STATE_COMPLETED'
        assert seen[0]['agent_id'] == 'orders' and seen[0]['tenant_id'] == 't'


def test_tasks_are_scoped_to_authenticated_principal():
    from agent_framework.security.middleware import AuthenticationMiddleware
    from agent_framework.security.authentication import AuthenticationResult, AuthenticatedPrincipal

    class TestProvider:
        async def authenticate(self, request):
            # Test-only identity provider, equivalent to verified middleware output.
            return AuthenticationResult(True, AuthenticatedPrincipal(request.headers['x-test-principal'], 'test'))

    async def handler(request):
        return {'text': 'private result'}
    app = application(handler)
    app.add_middleware(AuthenticationMiddleware, provider=TestProvider())
    with TestClient(app) as client:
        client.headers['x-test-principal'] = 'alice'
        first = task_result(send(client, 'SendMessage', message_params(immediate=False)))
        assert get_task(client, first['id'])['artifacts'][0]['parts'][0]['text'] == 'private result'
        client.headers['x-test-principal'] = 'bob'
        for method in ['GetTask', 'CancelTask']:
            result = send(client, method, {'id': first['id']}).json()
            assert 'error' in result
            assert 'private result' not in json.dumps(result)
        listing = send(client, 'ListTasks', {}).json()
        assert not listing['result'].get('tasks'), listing


@pytest.mark.parametrize('legacy', [False, True])
def test_gateway_to_framework_a2a_backend(monkeypatch, legacy):
    import httpx
    from agent_framework.global_supervisor.client import BackendClient
    from agent_framework.global_supervisor.models import GlobalRouteDecision
    backend_release = threading.Event()
    async def backend_handler(request):
        while not backend_release.is_set():
            await asyncio.sleep(.005)
        return {'text': 'backend complete', 'session_id': request['session_id']}
    backend_app = application(backend_handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.ASGITransport(app=backend_app), **kw))
    backend_client = BackendClient(timeout_seconds=2)
    definition = BackendDefinition(backend_id='x', url='http://backend', protocol='a2a',
        a2a_version='0.3' if legacy else '1.0', a2a_poll_interval_seconds=.005)
    async def gateway_handler(request):
        result = await backend_client.call_message(definition, request, GlobalRouteDecision(backend_id='x'))
        return result.response
    with TestClient(application(gateway_handler)) as client:
        try:
            first = task_result(send(client, 'SendMessage', message_params()))
            assert first['status']['state'] in {'TASK_STATE_SUBMITTED', 'TASK_STATE_WORKING'}
            assert not backend_release.is_set()
            backend_release.set()
            final = wait_state(client, first['id'], 'TASK_STATE_COMPLETED')
            assert final['artifacts'][0]['parts'][0]['text'] == 'backend complete'
        finally:
            backend_release.set()


def test_template_progress_helper_preserves_native_event_contract():
    # Exercise the actual lightweight helper without booting OCI/LLM dependencies.
    import ast
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / 'templates/agent_template_backend/app/main.py'
    module = ast.parse(source.read_text())
    helper = next(n for n in module.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_emit_gateway_event')
    native, a2a = [], []
    async def native_emit(*args):
        native.append(args)
    async def progress(*args):
        a2a.append(args)
    namespace = {'sse_hub': SimpleNamespace(emit=native_emit)}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(source), 'exec'), namespace)
    emit = namespace['_emit_gateway_event']
    async def scenario():
        await emit('session', 'flow.start', {'x': 1}, True, None)
        await emit('session', 'workflow.started', {'x': 2}, False, progress)
        await emit('session', 'message.responded', {'x': 3}, False, None)
    asyncio.run(scenario())
    assert native == [('session', 'flow.start', {'x': 1})]
    assert a2a == [('workflow.started', {'x': 2})]
