# A2A Integration in Agent Framework OCI

## Architecture decision

The existing Agent Gateway gains an optional A2A interface. There is no need to maintain a second router, duplicate the supervisor, or migrate existing agents.

```text
Existing consumer ── /gateway/message ─┐
                                       ├─ Agent Gateway / supervisor ─┬─ native backend
A2A consumer ─────── /a2a ─────────────┘                              └─ A2A backend
```

The native backend continues receiving `{channel, payload, agent_id, tenant_id}`. Omitting `protocol` from the catalog preserves `native`. A2A is disabled by default; the SDK is imported only when the interface is enabled or an A2A backend is selected. The agent runtime, workflows, channels, and MCPs were not changed.

The inbound interface uses A2A **1.0 / JSON-RPC**, the official `a2a-sdk==1.2.2`, with a 0.3 adapter provided by the SDK itself. External agents can be registered with `a2a_version: '1.0'` or `'0.3'`; there is no heuristic version detection.

## Local setup

From the framework root:

```sh
python -m pip install -e 'libs/agent_framework[a2a]' -r apps/agent_gateway/requirements.txt
export ENABLE_A2A=true
export A2A_PUBLIC_URL=https://meu-gateway.example
export BACKENDS_CONFIG_PATH="$PWD/apps/agent_gateway/config/backends.a2a.example.yaml"
python -m uvicorn app.main:app --app-dir apps/agent_gateway --env-file .env --port 8010
```

First, edit the URLs in the sample catalog. For external agents, specify the JSON-RPC endpoint advertised in the Agent Card as `url` + `a2a_rpc_path`. Credentials are stored in environment variables referenced by `a2a_headers_env`. Their values are not exposed through `/backends`.

An optional image can be built from the framework root:

```sh
docker build -f apps/agent_gateway/Dockerfile.a2a -t agent-gateway-a2a .
```

Set `A2A_PUBLIC_URL` in the container environment and mount the backend catalog. The existing deployment images and commands remain available.

## Discovery and invocation

The Agent Card is available at `GET /.well-known/agent-card.json`; skills are derived from enabled backends. Messages arrive at `POST /a2a`.

A2A 1.0 example, with the `A2A-Version: 1.0` header:

```json
{
  "jsonrpc": "2.0",
  "id": "request-1",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "message-1",
      "contextId": "conversation-123",
      "role": "ROLE_USER",
      "parts": [
        {"text": "I want to check my bill"},
        {"data": {"customer_id": "123"}}
      ],
      "metadata": {"tenant_id": "default"}
    }
  }
}
```

In Task mode (the default), the response is in `result.task`. The business result is in `artifacts[].parts`, with text and a `data` part containing the framework response. With `A2A_TASK_MODE=false`, it remains in `result.message`. Reuse `contextId` on subsequent turns. In 0.3 mode, use the `A2A-Version: 0.3` header, the `message/send` method, the `user` role, and the `kind` fields from the 0.3 specification; the result is a Task directly (or a Message with `A2A_TASK_MODE=false`).

`data` parts must contain objects and are incorporated into the business payload. Session identity and protocol text take precedence over those data. Files received through the interface are explicitly rejected.

## Conversations, tasks, and limits

- The interface creates **A2A Tasks** and supports immediate submission, retrieval, cancellation, and SSE streaming. `A2A_TASK_MODE=false` preserves the previous Message mode. See [Asynchronous A2A](A2A_ASSINCRONO.md) for complete examples.
- The output adapter accepts a Message or a Task; it polls `GetTask`/`tasks/get` while the agent is working, within an overall timeout configured by `BACKEND_TIMEOUT_SECONDS`. It does not automatically retry submission operations.
- Tasks requiring input/authentication preserve state and identity for the next turn. Completed tasks are not reused.
- Remote continuity is stored in-process by tenant/backend/session, with a one-hour lifetime and a limit of 10,000 entries. With multiple replicas, use session affinity or implement shared storage before relying on this continuity. Process restarts clear the cache.
- `metadata.a2a_result` preserves the remote result, including data/artifacts; `a2a_context_id`, `a2a_task_id`, and `a2a_state` allow explicit inspection and continuity in the payload when needed.
- SSE streaming is available in Task mode. Push notifications and gRPC are not provided. The native event proxy is not used for A2A agents: use `SendStreamingMessage`/`SubscribeToTask` and their 0.3 equivalents.
- The `templates/agent_template_backend` template also exposes A2A directly when `ENABLE_A2A=true`, without going through the global gateway.

## Authentication

A2A routes share the authentication middleware already installed in the gateway (`AGENT_GATEWAY_AUTH_*`). Enabling A2A does not automatically enable authentication. The tenant in metadata retains the framework's current semantics: it is request data, not an authorization granted by the protocol. Tenant access policies remain the responsibility of the authentication/authorization configuration.

When authentication is enabled, also declare it in the Agent Card, for example:

```sh
export A2A_SECURITY_SCHEMES='{"gatewayBearer":{"httpAuthSecurityScheme":{"scheme":"bearer"}}}'
export A2A_SECURITY='[{"gatewayBearer":[]}]'
```

These declarations document the mechanism; the middleware validates credentials. If public discovery is desired, add only the Agent Card path to the public-path configuration; `/a2a` remains protected.

## Validation

Tests in `tests/test_a2a_interoperability.py` cover both input formats, the native contract, both output formats, polling, JSON-RPC errors, task continuity, tenant isolation, and timeouts.

```sh
PYTHONPATH=libs/agent_framework/src pytest tests/test_a2a_interoperability.py -q
```

Validation uses simulated HTTP transports and a local FastAPI application; it does not replace integration testing with OCI services and external agents in the deployment environment.

Official references:
- https://a2a-protocol.org/latest/specification/
- https://a2a-protocol.org/v0.3.0/specification/
- https://github.com/a2aproject/a2a-python
