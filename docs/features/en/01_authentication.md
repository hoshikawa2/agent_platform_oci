# Authentication

> `agent_framework_oci` feature — English guide.

**Main implementation:** `security/authentication.py`

---

### 1. What it is

Checks who may access protected APIs, gateways, and services before the request reaches the agent.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Client/System
   ↓
Authentication Provider
   ↓
valid credential?
   ├─ no → 401/deny
   └─ yes → authenticated principal → agent
```

### 4. How it works internally

The framework exposes an `AuthenticationProvider` abstraction with multiple implementations. Current providers include `NoAuthenticationProvider`, `DenyAuthenticationProvider`, `BasicAuthenticationProvider`, `ApiKeyAuthenticationProvider`, `StaticBearerAuthenticationProvider`, `JwtAuthenticationProvider`, `OAuth2IntrospectionAuthenticationProvider`, and `TrustedProxyAuthenticationProvider`.

Authentication produces an `AuthenticatedPrincipal` containing `subject`, `scheme`, and optional `claims`. Domain code should not validate credentials directly.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```python
from agent_framework.security.authentication import BasicAuthenticationProvider

provider = BasicAuthenticationProvider(
    client_id="client-a",
    secret_hash="pbkdf2_sha256:...",
)
result = await provider.authenticate(request)
if not result.authenticated:
    # deny access
    ...
```

Secrets may be verified as plain, SHA-256, or PBKDF2 values; for production, prefer strong hashes and managed secret stores.

### 7. Telemetry and observability

When the feature participates in an agent execution, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id`, and other correlation keys in state/events. This makes the decision observable through Langfuse/Observer without embedding observability logic in the domain.

### 8. How to test

1. Add a unit test for the core behavior.
2. Add a runtime integration test when state spans multiple turns.
3. Test the happy path and at least one failure/rejection path.
4. Confirm retries/replays do not duplicate side effects for transactional features.
5. In production, also validate telemetry and ID correlation.

### 9. Common mistakes

- Basic auth returns 401: validate the `Authorization: Basic ...` header and configured secret.
- Do not confuse API authentication with `OCI_AUTH_MODE`; they solve different problems.
- Avoid `NoAuthenticationProvider` in production unless explicitly accepted by architecture.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/security/authentication.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
