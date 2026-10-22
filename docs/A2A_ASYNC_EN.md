# Framework Agents with Asynchronous A2A

## What was implemented

An agent created from `templates/agent_template_backend` can expose both the native protocol and A2A in the same process. The Agent Gateway also provides the same A2A interface. Both interfaces use the official SDK and its Tasks/SSE operations, with A2A 1.0 and 0.3 interoperability.

```text
A2A consumer ── A2A Gateway (Task)
                 ├── native agent (/gateway/message)
                 └── framework A2A agent (remote Task)

A2A consumer ── framework A2A agent directly
```

Immediate submission returns a Task before the business operation finishes. Execution continues after the HTTP response and even after the SSE connection is closed. The consumer can retrieve the result or reconnect to an in-progress task. Native endpoints retain their behavior: `/gateway/message` still waits for the result, and native SSE remains separate from A2A SSE.

## Enable A2A in an agent built with the framework

From the framework root, install the optional dependency:

```sh
python -m pip install -e 'libs/agent_framework[a2a]' -r templates/agent_template_backend/requirements.txt
```

In the backend environment:

```dotenv
ENABLE_A2A=true
A2A_TASK_MODE=true
A2A_PUBLIC_URL=http://localhost:8000
A2A_TASK_TIMEOUT_SECONDS=240
```

Start the backend with its usual settings. For example, after preparing the `.env` and agent configuration files:

```sh
cd templates/agent_template_backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use the actual public address in `A2A_PUBLIC_URL`. A sample configuration is provided in `.env.a2a.example`. An optional image can also be built from the framework root:

```sh
docker build -f templates/agent_template_backend/Dockerfile.a2a -t framework-agent-a2a .
```

Profiles defined in `agents.yaml` are published as skills in the Agent Card: `GET /.well-known/agent-card.json`. Use `message.metadata.agent_id` to select a profile; otherwise, the backend retains its default selection.

## Register the agent with the Agent Gateway

```yaml
backends:
  pedidos_a2a:
    protocol: a2a
    a2a_version: '1.0'
    url: http://backend-pedidos:8000
    a2a_rpc_path: /a2a
    description: Order inquiry and tracking
    keywords: [pedido, entrega, rastreamento]
    default_agent_id: pedidos
```

On the gateway, enable `ENABLE_A2A=true` and `A2A_TASK_MODE=true`, and configure its own `A2A_PUBLIC_URL`. For longer-running operations, adjust the limits; for example, use `A2A_TASK_TIMEOUT_SECONDS=300` and `BACKEND_TIMEOUT_SECONDS=270`, with the backend timeout set to 240 seconds. The effective duration is limited by the shortest applicable deadline.

The gateway immediately returns its own Task and polls the remote Task until completion or until input/authentication is required. Remote status events are published as `a2a.backend.status`. Local and remote IDs may differ. The native result includes `metadata.a2a_task_id` and `metadata.a2a_context_id` for correlation; external consumers continue tracking the ID issued by the gateway.

## Asynchronous A2A 1.0 submission

Send a `POST /a2a` request with `Content-Type: application/json` and `A2A-Version: 1.0`:

```json
{
  "jsonrpc": "2.0",
  "id": "request-1",
  "method": "SendMessage",
  "params": {
    "configuration": {"returnImmediately": true},
    "message": {
      "messageId": "message-1",
      "contextId": "conversation-123",
      "role": "ROLE_USER",
      "parts": [{"text": "Check my order"}],
      "metadata": {"agent_id": "pedidos", "tenant_id": "default"}
    }
  }
}
```

The response contains `result.task.id`, `contextId`, and an initial state such as `TASK_STATE_SUBMITTED` or `TASK_STATE_WORKING`. Save that ID and query the task:

```json
{
  "jsonrpc": "2.0",
  "id": "request-2",
  "method": "GetTask",
  "params": {"id": "TASK_ID"}
}
```

The result is in `result`. When `status.state` is `TASK_STATE_COMPLETED`, the final content is in `artifacts[].parts`. It includes a text part and a `data` part containing the original framework response.

Without `returnImmediately: true`, submission waits for a final or interrupted state and returns a Task in the same format. To preserve the behavior of the initial A2A release, which returned a Message, set `A2A_TASK_MODE=false`. In that mode, streaming is disabled and there are no local Tasks.

## Streaming and reconnection

To submit and follow a task, use `SendStreamingMessage` instead of `SendMessage`, with the same parameters. The response uses `Content-Type: text/event-stream`. Each `data:` field contains a JSON-RPC response. Events include:

1. The initial Task.
2. Status updates (submitted/working) and progress events.
3. The response artifact.
4. A completed, failed, canceled, input-required, or auth-required state.

The framework backend publishes milestones such as `flow.start`, `session.upserted`, `workflow.started`, `workflow.completed`, and `message.responded` when the flow reaches those stages. They appear in `result.statusUpdate.metadata.framework_event`, with corresponding data in `framework_payload`. This does not imply LLM token streaming.

To reconnect to an in-progress Task:

```json
{
  "jsonrpc": "2.0",
  "id": "request-3",
  "method": "SubscribeToTask",
  "params": {"id": "TASK_ID"}
}
```

Reconnection delivers the current state and subsequent events; replay of all missed events is not guaranteed. If the task has already finished, use `GetTask`.

## Cancellation, failures, and continuity

`CancelTask`, with `params.id`, cancels the ongoing local execution. The SDK interrupts the coroutine and records `TASK_STATE_CANCELED`. This does not undo effects already committed in tools or external systems. When the gateway is polling a remote agent, stopping the local task does not guarantee cancellation of an operation already accepted by the remote service.

Exceptions and expiration of `A2A_TASK_TIMEOUT_SECONDS` result in `TASK_STATE_FAILED`, which can be queried later and carries a generic message. Internal details remain in server logs.

For an interaction requiring further input, a handler can return `metadata.a2a_task_state: "input-required"` or `"auth-required"`. The consumer sends another message with the same `taskId` and `contextId`. The task is resumed; a completed task cannot be re-executed. The output adapter preserves continuity for remote tasks in these states.

Native workflows that do not declare such a state complete one Task per turn. The conversation continues with a new Task and the same `contextId`, using the framework's existing sessions and memories.

## A2A 0.3 equivalents

Use `A2A-Version: 0.3`, `role: "user"`, and the 0.3 `kind` discriminators.

| A2A 1.0 | A2A 0.3 |
| --- | --- |
| `SendMessage` + `returnImmediately: true` | `message/send` + `blocking: false` |
| `SendStreamingMessage` | `message/stream` |
| `GetTask` | `tasks/get` |
| `SubscribeToTask` | `tasks/resubscribe` |
| `CancelTask` | `tasks/cancel` |

In 0.3, `result` directly contains the Task without the `task` envelope. States use `submitted`, `working`, `completed`, `failed`, etc.

## Storage and authentication

By default, the SDK uses an in-memory TaskStore. Tasks and results are lost when the process restarts. With multiple workers/replicas, use request affinity to the same process during execution or configure shared storage and coordination. A persistent TaskStore alone does not make execution resumable after a failure. The `install_a2a` and `install_backend_a2a` functions accept `task_store` for integration with SDK storage.

The optional backend reuses `AGENT_AUTH_*`; the gateway uses `AGENT_GATEWAY_AUTH_*`. The identity authenticated by middleware determines Task ownership, including retrieval and cancellation. Anonymous users share the anonymous scope. `tenant_id` in metadata remains request data, not a credential or authorization isolation mechanism. Clients sharing the same credential/principal also share a task scope.

`A2A_SECURITY_SCHEMES` and `A2A_SECURITY` document mechanisms in the Agent Card, as described in the general guide. SSE is enabled in Task mode; push notifications and gRPC are outside the scope of this implementation.

## Validation

The test suite covers immediate submission while the handler remains blocked, polling, streaming with progress and results, cancellation, failures, timeouts, resumption, isolation between authenticated identities, and a gateway calling a real A2A backend in a local application. HTTP tests on `127.0.0.1` also verify that the first event arrives before completion and that reconnection works after disconnection.

```sh
python -m pip install pytest pytest-asyncio uvicorn
PYTHONPATH=libs/agent_framework/src pytest \
  tests/test_a2a_interoperability.py tests/test_a2a_async_tasks.py \
  tests/test_a2a_http_streaming.py \
  tests/unit/test_sse.py tests/unit/test_sse_replay_dedup.py \
  tests/unit/test_authentication.py tests/unit/test_authentication_policies.py -q
```

The tests do not access OCI or external business services. In environments where binding to local ports is not permitted, run the HTTP test in an environment that allows binding to loopback.

Official specification: https://a2a-protocol.org/latest/specification/  
Official SDK: https://github.com/a2aproject/a2a-python

## A2A-ready frontend

The `apps/agent_frontend_a2a` interface consumes this protocol directly, supporting Tasks, streaming, retrieval, and cancellation. See [A2A Frontend](../apps/agent_frontend_a2a/README.md) for the demonstration without OCI and startup commands using the backend or Gateway. The native frontend remains in `apps/agent_frontend`.
