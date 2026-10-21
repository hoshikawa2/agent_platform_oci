"""A2A 1.0 Tasks and SSE with SDK-managed 0.3 compatibility."""
import asyncio
import logging
from uuid import uuid4

from google.protobuf.json_format import MessageToDict, ParseDict
from a2a.auth.user import User
from a2a.server.agent_execution import AgentExecutor
from a2a.server.routes import (
    DefaultServerCallContextBuilder, add_a2a_routes_to_fastapi,
    create_agent_card_routes, create_jsonrpc_routes,
)
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCard, Message, Part, Role, Task, TaskState, TaskStatus
from a2a.utils.errors import InvalidParamsError, TaskNotCancelableError, UnsupportedOperationError

from .progress import _progress_callback

logger = logging.getLogger(__name__)


class _PrincipalUser(User):
    def __init__(self, principal):
        self.principal = principal

    @property
    def is_authenticated(self):
        return True

    @property
    def user_name(self):
        # Use middleware identity, never client-supplied message metadata.
        return f'{self.principal.scheme}:{self.principal.subject}'


class FrameworkCallContextBuilder(DefaultServerCallContextBuilder):
    def build_user(self, request):
        principal = getattr(request.state, 'auth_principal', None)
        return _PrincipalUser(principal) if principal else super().build_user(request)


def _response_message(response, context_id, task_id=None):
    data = {
        'messageId': str(uuid4()), 'role': 'ROLE_AGENT', 'contextId': context_id,
        'parts': [{'text': str(response.get('text') or response.get('speak') or '')},
                  {'data': response}],
    }
    if task_id:
        data['taskId'] = task_id
    return ParseDict(data, Message())


class GatewayExecutor(AgentExecutor):
    """Wrap any native async handler as an A2A task, without detached worker hacks."""

    def __init__(self, handler, task_mode=True, timeout_seconds=120.0):
        self.handler = handler
        self.task_mode = task_mode
        self.timeout_seconds = timeout_seconds

    async def execute(self, context, event_queue):
        message = context.message
        if message is None or message.role != Role.ROLE_USER:
            raise InvalidParamsError('Expected a user message')
        payload = {}
        for part in MessageToDict(message).get('parts', []):
            if 'data' in part:
                if not isinstance(part['data'], dict):
                    raise InvalidParamsError('Structured data must be an object')
                payload.update(part['data'])
            elif 'text' not in part:
                raise UnsupportedOperationError('Only text and structured data are supported')
        metadata = MessageToDict(message.metadata)
        session_id = context.context_id or str(uuid4())
        payload.update(message=context.get_user_input(), session_id=session_id)
        request = {
            'channel': 'web', 'payload': payload, 'session_id': session_id,
            'tenant_id': metadata.get('tenant_id'), 'agent_id': metadata.get('agent_id'),
            'metadata': metadata, 'backend_id': metadata.get('backend_id'),
        }
        if not self.task_mode:
            async with asyncio.timeout(self.timeout_seconds):
                response = await self.handler(request)
            await event_queue.enqueue_event(_response_message(response, session_id))
            return

        updater = TaskUpdater(event_queue, context.task_id, session_id)
        if context.current_task is None:
            await event_queue.enqueue_event(Task(
                id=context.task_id, context_id=session_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                history=[message],
            ))
        await updater.update_status(TaskState.TASK_STATE_WORKING)

        async def progress(event, data):
            await updater.update_status(TaskState.TASK_STATE_WORKING, metadata={
                'framework_event': event, 'framework_payload': data,
            })

        token = _progress_callback.set(progress)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                response = await self.handler(request)
            reply = _response_message(response, session_id, context.task_id)
            response_metadata = response.get('metadata') or {}
            requested_state = response_metadata.get('a2a_state') or response_metadata.get('a2a_task_state')
            state = {
                'input-required': TaskState.TASK_STATE_INPUT_REQUIRED,
                'auth-required': TaskState.TASK_STATE_AUTH_REQUIRED,
                'TASK_STATE_INPUT_REQUIRED': TaskState.TASK_STATE_INPUT_REQUIRED,
                'TASK_STATE_AUTH_REQUIRED': TaskState.TASK_STATE_AUTH_REQUIRED,
            }.get(requested_state, TaskState.TASK_STATE_COMPLETED)
            await updater.add_artifact(list(reply.parts), artifact_id='response', name='Framework response', last_chunk=True)
            await updater.update_status(state, message=reply)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception('A2A task %s failed', context.task_id)
            text = 'Processing timed out' if isinstance(exc, TimeoutError) else 'Agent processing failed'
            await updater.update_status(TaskState.TASK_STATE_FAILED, message=_response_message({'text': text}, session_id, context.task_id))
        finally:
            _progress_callback.reset(token)

    async def cancel(self, context, event_queue):
        if not self.task_mode:
            raise TaskNotCancelableError()
        # The SDK cancels the running execute coroutine after this callback.
        await TaskUpdater(event_queue, context.task_id, context.context_id).update_status(TaskState.TASK_STATE_CANCELED)


def install_a2a(app, handler, registry, public_url, security_schemes=None, security=None,
                *, task_mode=True, timeout_seconds=120.0, task_store=None,
                name='Agent Framework OCI Gateway', skills=None):
    """Reuse parent middleware. A persistent SDK TaskStore may be injected."""
    if timeout_seconds <= 0:
        raise ValueError('A2A timeout_seconds must be positive')
    if skills is None:
        skills = [{'id': b.backend_id, 'name': b.name or b.backend_id,
                   'description': b.description or b.backend_id,
                   'tags': b.domains or [b.backend_id], 'examples': b.examples}
                  for b in registry.list()]
    card = ParseDict({
        'name': name, 'version': '1.1.0',
        'description': 'Native framework agents and A2A interoperability',
        'supportedInterfaces': [{'url': public_url.rstrip('/') + '/a2a',
                                 'protocolBinding': 'JSONRPC', 'protocolVersion': '1.0'}],
        'capabilities': {'streaming': task_mode, 'pushNotifications': False},
        'defaultInputModes': ['text/plain', 'application/json'],
        'defaultOutputModes': ['text/plain', 'application/json'],
        'securitySchemes': security_schemes or {},
        'securityRequirements': [{'schemes': {k: {'list': v} for k, v in item.items()}}
                                 for item in (security or [])],
        'skills': skills,
    }, AgentCard())
    request_handler = DefaultRequestHandler(
        GatewayExecutor(handler, task_mode=task_mode, timeout_seconds=timeout_seconds),
        task_store if task_store is not None else InMemoryTaskStore(), card,
    )
    add_a2a_routes_to_fastapi(
        app, agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(
            request_handler, rpc_url='/a2a', enable_v0_3_compat=True,
            context_builder=FrameworkCallContextBuilder(),
        ),
    )
    return request_handler


def install_backend_a2a(app, handler, profiles, settings, *, task_store=None):
    """Expose a framework backend directly, with skills built from agent profiles."""
    return install_a2a(
        app, handler, None, settings.A2A_PUBLIC_URL,
        settings.A2A_SECURITY_SCHEMES or None, settings.A2A_SECURITY or None,
        task_mode=settings.A2A_TASK_MODE, timeout_seconds=settings.A2A_TASK_TIMEOUT_SECONDS,
        task_store=task_store, name=settings.APP_NAME,
        skills=[{'id': p.agent_id, 'name': p.name or p.agent_id,
                 'description': p.description or p.agent_id, 'tags': [p.agent_id]}
                for p in profiles.list_profiles()],
    )
