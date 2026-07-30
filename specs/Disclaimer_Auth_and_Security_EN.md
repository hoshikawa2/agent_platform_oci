### Security, Authentication, and Authorization Recommendations

The components and templates in this framework can be adapted to different architectures and security requirements. For production environments, it is recommended that the solution be assessed in accordance with corporate policies, applicable regulatory requirements, and Oracle Cloud Infrastructure security best practices.

As general guidance, authentication and authorization should be considered for all interfaces accessible by users, channels, external systems, or other services. In OCI, one option is to use OCI API Gateway, or an equivalent layer, together with OAuth 2.0/OpenID Connect, token validation, and authorization policies based on route, scope, role, and tenant.

Methods such as HTTP Basic authentication and API keys may be suitable for certain integration scenarios, particularly in controlled environments or with legacy systems. In such cases, it is recommended that they be used over TLS, that credentials be stored in a secure secrets management service, and that expiration and rotation mechanisms be adopted.

The security assessment should consider, according to the components used by the solution:

- Agent Gateway, Channel Gateway, and MCP Gateway;
- agent backends and communication between gateways and backends;
- frontend applications and APIs consumed by the browser;
- callbacks and webhooks originating from external channels;
- SSE, WebSocket, or other streaming connections;
- history, memory, checkpoints, and session data;
- administrative, debug, documentation, health, and metrics endpoints;
- integrations with LLMs, databases, caches, messaging systems, and observability platforms.

Identifiers received in payloads or headers—such as `tenant_id`, `agent_id`, `user_id`, `customer_id`, and `session_id`—should be treated as contextual information rather than sufficient proof of the requester's identity. When applicable, these identifiers may be derived from validated claims or associated with the authenticated identity before the operation is executed.

In addition to authentication, authorization should be evaluated for each accessed resource. This verification may consider whether the authenticated user or service has permission to access the requested tenant, agent, session, history, checkpoint, backend, or MCP tool.

For service-to-service communication, dedicated workload identities and mechanisms such as OAuth 2.0 client credentials, OCI IAM, OKE Workload Identity, Instance Principals, Resource Principals, or mTLS may be considered. The choice should take into account the execution platform and the trust model defined for the solution.

For callbacks and webhooks, the mechanisms provided by the channel provider should be evaluated, such as digital signatures or HMAC, JWT, timestamps, message identifiers, replay protection, and idempotency.

Operational endpoints should also be evaluated separately:

- liveness endpoints, with a minimal response regarding the process status;
- readiness endpoints, preferably accessible only by the infrastructure;
- metrics endpoints, intended for authorized collectors;
- debug and test endpoints, typically restricted to non-production environments;
- OpenAPI documentation, which may be disabled or protected in production.

It is also recommended to use TLS for communications, restrict service exposure through private networks, subnets, NSGs, and allowlists, and consider rate limiting, auditing, traceability, and monitoring of denied access attempts.

Secrets, tokens, passwords, certificates, and keys may be stored in OCI Secret Management or an equivalent corporate solution, avoiding storage in source code or version-controlled configuration files. Least-privilege access policies, expiration, and rotation practices appropriate to the criticality of each credential should be established.

These recommendations provide an initial reference for best practices. The final definition of authentication, authorization, network protection, and secrets management mechanisms remains the responsibility of the team accountable for the architecture and deployment, taking into consideration the context, risks, and specific requirements of each implementation.
