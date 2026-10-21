import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
pytest.importorskip("a2a", reason="Install agent-framework[a2a] to run A2A tests")

from agent_framework.a2a.server import install_a2a
from agent_framework.global_supervisor.models import BackendDefinition, GlobalRouteDecision
from agent_framework.global_supervisor.client import BackendClient


@pytest.fixture
def facade():
    seen = []
    async def handler(request):
        seen.append(request)
        return {'channel': 'web', 'session_id': request['session_id'], 'text': 'Olá', 'metadata': {}}
    app = FastAPI()
    registry = SimpleNamespace(list=lambda: [BackendDefinition(backend_id='native', url='http://native')])
    install_a2a(app, handler, registry, 'https://agents.example', task_mode=False)
    with TestClient(app) as client:
        yield client, seen


@pytest.mark.parametrize('legacy', [False, True])
def test_discovery_and_send(facade, legacy):
    client, seen = facade
    card = client.get('/.well-known/agent-card.json').json()
    assert card['supportedInterfaces'][0]['protocolVersion'] == '1.0'
    message = {'messageId': 'm', 'role': 'ROLE_USER', 'contextId': 'conversation',
               'parts': [{'text': 'Oi'}, {'data': {'invoice_id': 42, 'session_id': 'override'}}]}
    if legacy:
        message.update(kind='message', role='user')
        for part in message['parts']: part['kind'] = 'text' if 'text' in part else 'data'
    response = client.post('/a2a', headers={'A2A-Version': '0.3' if legacy else '1.0'}, json={
        'jsonrpc': '2.0', 'id': 'x', 'method': 'message/send' if legacy else 'SendMessage',
        'params': {'message': message},
    }).json()
    reply = response['result'] if legacy else response['result']['message']
    assert reply['parts'][0]['text'] == 'Olá', response
    assert reply['contextId'] == 'conversation'
    assert seen[0]['payload']['invoice_id'] == 42
    assert seen[0]['payload']['session_id'] == 'conversation'


def test_errors(facade):
    client, _ = facade
    for method, params in [('Unknown', {}), ('GetTask', {'id': 'missing'})]:
        response = client.post('/a2a', headers={'A2A-Version': '1.0'}, json={
            'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params,
        }).json()
        assert 'error' in response


def mock_http(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))


@pytest.mark.parametrize('protocol', ['native', '1.0', '0.3'])
def test_backend_adapter(monkeypatch, protocol):
    seen = []
    def transport(request):
        body = json.loads(request.content)
        seen.append((request, body))
        if protocol == 'native': return httpx.Response(200, json={'text': 'OK', 'session_id': 's'})
        reply = {'messageId': 'r', 'role': 'ROLE_AGENT', 'contextId': 'remote', 'parts': [{'text': 'OK'}]}
        if protocol == '0.3':
            reply.update(kind='message', role='agent'); reply['parts'][0]['kind'] = 'text'
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body['id'], 'result': reply if protocol == '0.3' else {'message': reply}})
    mock_http(monkeypatch, transport)
    backend = BackendDefinition(backend_id='x', url='http://backend', protocol='native' if protocol == 'native' else 'a2a', a2a_version='0.3' if protocol == '0.3' else '1.0')
    response = asyncio.run(BackendClient().call_message(backend, {'payload': {'session_id': 's', 'message': 'Oi'}}, GlobalRouteDecision(backend_id='x')))
    assert response.response['text'] == 'OK'
    assert response.response['session_id'] == 's'
    if protocol == 'native':
        assert str(seen[0][0].url) == 'http://backend/gateway/message'
        assert seen[0][1]['payload']['selected_backend'] == 'x'
    else:
        assert seen[0][1]['method'] == ('message/send' if protocol == '0.3' else 'SendMessage')


def test_task_polling(monkeypatch):
    methods = []
    def transport(request):
        body = json.loads(request.content); methods.append(body['method'])
        task = {'id': 'task', 'contextId': 'remote', 'status': {'state': 'TASK_STATE_WORKING' if len(methods) == 1 else 'TASK_STATE_COMPLETED'}}
        if len(methods) == 2: task['artifacts'] = [{'artifactId': 'a', 'parts': [{'text': 'done'}]}]
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body['id'], 'result': {'task': task} if len(methods) == 1 else task})
    mock_http(monkeypatch, transport)
    backend = BackendDefinition(backend_id='x', url='http://backend', protocol='a2a', a2a_poll_interval_seconds=.001)
    response = asyncio.run(BackendClient().call_message(backend, {'payload': {'message': 'Oi'}}, GlobalRouteDecision(backend_id='x')))
    assert response.response['text'] == 'done'
    assert methods == ['SendMessage', 'GetTask']


def test_rpc_failure(monkeypatch):
    def transport(request):
        body = json.loads(request.content)
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body['id'], 'error': {'code': -32603, 'message': 'private'}})
    mock_http(monkeypatch, transport)
    backend = BackendDefinition(backend_id='x', url='http://backend', protocol='a2a')
    with pytest.raises(RuntimeError, match='-32603'):
        asyncio.run(BackendClient().call_message(backend, {'payload': {}}, GlobalRouteDecision(backend_id='x')))


def test_continuation_and_tenant_isolation(monkeypatch):
    seen = []
    def transport(request):
        body = json.loads(request.content); seen.append(body['params']['message'])
        return httpx.Response(200, json={'jsonrpc': '2.0', 'id': body['id'], 'result': {'task': {
            'id': 'remote-task', 'contextId': 'remote-context', 'status': {'state': 'TASK_STATE_INPUT_REQUIRED',
            'message': {'messageId': 'a', 'role': 'ROLE_AGENT', 'parts': [{'text': 'Confirmar?'}]}}
        }}})
    mock_http(monkeypatch, transport)
    backend = BackendDefinition(backend_id='x', url='http://backend', protocol='a2a')
    async def scenario():
        client = BackendClient()
        for tenant in ['first', 'first', 'second']:
            await client.call_message(backend, {'tenant_id': tenant, 'payload': {'session_id': 'same', 'message': 'sim'}}, GlobalRouteDecision(backend_id='x'))
    asyncio.run(scenario())
    assert seen[1]['taskId'] == 'remote-task'
    assert seen[1]['contextId'] == 'remote-context'
    assert 'taskId' not in seen[2]
    assert seen[0]['contextId'] != seen[2]['contextId']


def test_credentials_and_deadline(monkeypatch):
    monkeypatch.delenv('MISSING_A2A_TOKEN', raising=False)
    backend = BackendDefinition(backend_id='x', url='http://backend', protocol='a2a', a2a_headers_env={'Authorization': 'MISSING_A2A_TOKEN'})
    with pytest.raises(ValueError, match='MISSING_A2A_TOKEN'):
        asyncio.run(BackendClient().call_message(backend, {'payload': {}}, GlobalRouteDecision(backend_id='x')))
    async def transport(request):
        await asyncio.sleep(1)
        return httpx.Response(200)
    mock_http(monkeypatch, transport)
    backend.a2a_headers_env = {}
    with pytest.raises(TimeoutError):
        asyncio.run(BackendClient(timeout_seconds=.01).call_message(backend, {'payload': {}}, GlobalRouteDecision(backend_id='x')))


def test_native_does_not_import_sdk():
    import subprocess
    import sys
    code = '''
import sys
class BlockA2A:
    def find_spec(self, fullname, *args):
        if fullname == 'a2a' or fullname.startswith('a2a.'):
            raise ImportError('A2A unavailable')
sys.meta_path.insert(0, BlockA2A())
from agent_framework.global_supervisor.client import BackendClient
from agent_framework.global_supervisor.models import BackendDefinition
assert BackendDefinition(backend_id='x', url='http://x').protocol == 'native'
BackendClient()
'''
    subprocess.run([sys.executable, '-c', code], check=True)


def test_health_uses_card_and_credentials(monkeypatch):
    seen = []
    def transport(request):
        seen.append(request)
        return httpx.Response(200, json={'name': 'external'})
    mock_http(monkeypatch, transport)
    monkeypatch.setenv('A2A_TEST_AUTH', 'Bearer test')
    backend = BackendDefinition(backend_id='x', url='http://backend', protocol='a2a', a2a_headers_env={'Authorization':'A2A_TEST_AUTH'})
    result = asyncio.run(BackendClient().health(backend))
    assert result['ok']
    assert seen[0].url.path == '/.well-known/agent-card.json'
    assert seen[0].headers['Authorization'] == 'Bearer test'


def test_a2a_backend_selection_is_forwarded_to_gateway(facade):
    client, seen = facade
    response = client.post('/a2a', headers={'A2A-Version': '1.0'}, json={
        'jsonrpc': '2.0', 'id': 'select', 'method': 'SendMessage', 'params': {
            'message': {'messageId': 'm', 'role': 'ROLE_USER', 'parts': [{'text': 'Olá'}],
                        'metadata': {'backend_id': 'billing', 'agent_id': 'billing_agent'}},
        },
    }).json()
    assert 'result' in response, response
    assert seen[0]['backend_id'] == 'billing'
    assert seen[0]['agent_id'] == 'billing_agent'
