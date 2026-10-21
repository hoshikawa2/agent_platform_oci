"""A2A JSON-RPC adapter. URLs and credential references are operator configured."""
import asyncio
import json
import os
from uuid import uuid4, uuid5, NAMESPACE_URL

import httpx
from google.protobuf.json_format import ParseDict, MessageToDict
from a2a.types import SendMessageResponse, Task

from .progress import report_progress


def _normalize_legacy(result):
    # Preserve the original wire response separately; normalize only presentation.
    if result.get('kind') == 'message':
        return {'message': result}
    if result.get('kind') == 'task':
        return {'task': result}
    raise ValueError('Expected an A2A Message or Task')


async def call_a2a(backend, request, timeout_seconds):
    payload = request.get('payload') or {}
    session = payload.get('session_id') or str(uuid4())
    tenant = request.get('tenant_id') or 'default'
    context_id = str(uuid5(NAMESPACE_URL, json.dumps([tenant, backend.backend_id, session])))
    legacy = backend.a2a_version == '0.3'
    text = str(payload.get('message') or payload.get('text') or payload.get('transcript') or payload.get('content') or '')
    parts = [{'text': text}, {'data': payload}]
    message = {'role': 'ROLE_USER', 'messageId': str(uuid4()),
               'contextId': payload.get('a2a_context_id') or context_id, 'parts': parts,
               'metadata': {'tenant_id': tenant, 'agent_id': request.get('agent_id') or backend.default_agent_id}}
    if payload.get('a2a_task_id'):
        message['taskId'] = payload['a2a_task_id']
    if legacy:
        message.update(kind='message', role='user')
        for part in parts:
            part['kind'] = 'text' if 'text' in part else 'data'
    headers = {'A2A-Version': backend.a2a_version}
    for header, env_name in backend.a2a_headers_env.items():
        value = os.environ.get(env_name)
        if not value:
            raise ValueError(f'Missing credential environment variable: {env_name}')
        headers[header] = value
    endpoint = backend.base_url + backend.a2a_rpc_path

    async with asyncio.timeout(timeout_seconds):
        async with httpx.AsyncClient(timeout=timeout_seconds, headers=headers) as client:
            async def rpc(method, params):
                request_id = str(uuid4())
                response = await client.post(endpoint, json={
                    'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params,
                })
                response.raise_for_status()
                data = response.json()
                if data.get('jsonrpc') != '2.0' or data.get('id') != request_id:
                    raise ValueError('Invalid A2A JSON-RPC response')
                if 'error' in data:
                    raise RuntimeError(f'A2A error {data["error"].get("code")}')
                result = data.get('result')
                if not isinstance(result, dict):
                    raise ValueError('Missing A2A result')
                return result

            raw = await rpc('message/send' if legacy else 'SendMessage', {
                'message': message,
                'configuration': {'blocking': False} if legacy else {'returnImmediately': True},
            })
            result = _normalize_legacy(raw) if legacy else raw
            if not legacy:
                result = MessageToDict(ParseDict(result, SendMessageResponse()))
            while 'task' in result:
                task = result['task']
                state = task.get('status', {}).get('state', '')
                await report_progress('a2a.backend.status', {
                    'backend_id': backend.backend_id, 'task_id': task.get('id'), 'state': state,
                })
                if state not in {'submitted', 'working', 'TASK_STATE_SUBMITTED', 'TASK_STATE_WORKING'}:
                    break
                await asyncio.sleep(backend.a2a_poll_interval_seconds)
                raw = await rpc('tasks/get' if legacy else 'GetTask', {'id': task['id']})
                result = {'task': raw if legacy else MessageToDict(ParseDict(raw, Task()))}

    task = result.get('task')
    if task:
        state, task_id = task['status']['state'], task['id']
        if state in {'failed', 'canceled', 'rejected', 'unknown', 'TASK_STATE_FAILED', 'TASK_STATE_CANCELED', 'TASK_STATE_REJECTED', 'TASK_STATE_UNSPECIFIED'}:
            raise RuntimeError(f'A2A task ended with state: {state}')
        output_parts = [p for a in task.get('artifacts', []) for p in a.get('parts', [])]
        if not output_parts and task['status'].get('message'):
            output_parts += task['status']['message'].get('parts', [])
        if not output_parts:
            messages = [m for m in task.get('history', []) if m.get('role') in {'agent', 'ROLE_AGENT'}]
            output_parts = messages[-1].get('parts', []) if messages else []
        remote_context = task.get('contextId')
    elif result.get('message'):
        reply = result['message']
        output_parts = reply.get('parts', [])
        state, task_id, remote_context = None, None, reply.get('contextId')
    else:
        raise ValueError('Expected an A2A Message or Task')
    return {
        'channel': request.get('channel', 'web'), 'session_id': session,
        'text': '\n'.join(p['text'] for p in output_parts if 'text' in p),
        'metadata': {'a2a_context_id': remote_context, 'a2a_task_id': task_id,
                     'a2a_state': state, 'a2a_result': raw},
    }
