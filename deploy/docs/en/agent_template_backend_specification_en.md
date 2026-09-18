# `agent_template_backend` Usage Specification

## Complementary document to the general `agent_framework_oci` architecture

> **Scope of this document**
>
> This document is specific to the `agent_template_backend` distributed with `agent_framework_oci`.
>
> It **does not replace** the general architectural specification for using `agent_framework_oci` in production projects. The general specification remains the normative reference for production project structure, packaging, versioning, CI/CD, state externalization, security, scalability, and OKE deployment.
>
> This document explains how the existing `agent_template_backend` should be used as a **reference template**, development environment, starting point for new agents, and source for derived production projects.

---

## 1. Purpose

`agent_template_backend` is the agent backend template provided by the `agent_framework_oci` repository.

Its purpose is to provide a functional starting implementation showing how an agent project consumes `agent_framework`, organizes configuration, exposes APIs, uses workflows, integrates MCP, applies guardrails and judges, and consumes the other enterprise capabilities of the framework.

The template should be understood as:

- an implementation reference;
- a starting point for new projects;
- a development and validation environment;
- an integration example for `agent_framework`;
- a deployment example;
- a source for independent derived projects.

The template **must not be interpreted as an exception** to the architectural rules defined by the general production specification.

---

## 2. Relationship with the general architectural specification

There are two documentation levels.

### 2.1. General architectural specification

The general specification defines the standard for production projects derived from the framework:

```text
<workspace>/
├── agent_framework/
└── <agent_project>/
```

It defines, among other items:

- separation between framework and project;
- `agent_framework` installation;
- versioning;
- build context;
- Docker;
- CI/CD;
- OKE deployment;
- scalability;
- state externalization;
- secret management;
- compatibility between framework and agent versions.

### 2.2. This specification

This document describes how the template delivered in the repository fits into that model.

Whenever a demonstration setting in the template differs from a rule in the general architectural specification, **the general architectural specification takes precedence for production environments**.

---

## 3. Template location in the repository

In the source repository, the template is located at:

```text
agent_framework_oci/
└── templates/
    └── agent_template_backend/
```

The shared framework is located at:

```text
agent_framework_oci/
└── libs/
    └── agent_framework/
```

Therefore, inside the development repository, the structure is:

```text
agent_framework_oci/
├── libs/
│   └── agent_framework/
│
├── templates/
│   └── agent_template_backend/
│
├── apps/
├── mcp/
├── deploy/
└── ...
```

This is the **source structure of the `agent_framework_oci` product**.

It does not change the production architecture rule.

---

## 4. Template distribution structure

When `agent_template_backend` is extracted from the repository for independent use, isolated build, or creation of a derived project, the workspace should materialize:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

The content of:

```text
agent_framework_oci/libs/agent_framework/
```

should be made available as:

```text
workspace/agent_framework/
```

and the content of:

```text
agent_framework_oci/templates/agent_template_backend/
```

as:

```text
workspace/agent_template_backend/
```

This structure is compatible with the Dockerfile currently delivered with the template.

---

## 5. Current `agent_template_backend` structure

The main template structure is:

```text
agent_template_backend/
├── app/
│   ├── main.py
│   ├── state.py
│   ├── mcp_gateway_client_factory.py
│   └── ...
│
├── config/
│   ├── agents.yaml
│   ├── routing.yaml
│   ├── tools.yaml
│   ├── tool_policies.yaml
│   ├── guardrails.yaml
│   ├── judges.yaml
│   ├── identity.yaml
│   ├── prompt_policy.yaml
│   ├── mcp_parameter_mapping.yaml
│   ├── mcp_servers.yaml
│   └── mcp_servers.docker.yaml
│
├── workflows/
│   ├── devolucao_pedido.active.yaml
│   └── devolucao_pedido.v1.yaml
│
├── data/
├── docs/
├── scripts/
├── llm_profiles.yaml
├── requirements.txt
├── Dockerfile
├── .env.example
├── README.md
└── README_ENTERPRISE_TEMPLATE.md
```

The template contains enough configuration to demonstrate enterprise framework capabilities without copying those capabilities into the project.

---

## 6. Dependency on `agent_framework`

`agent_template_backend` is a framework consumer.

The dependency must remain one-way:

```text
agent_template_backend
        |
        v
agent_framework
```

The inverse must not occur.

`agent_framework` must not depend on:

```text
templates/agent_template_backend
```

or on template-specific files.

---

## 7. Local installation from the source repository

For development directly inside the repository:

```text
agent_framework_oci/
├── libs/agent_framework/
└── templates/agent_template_backend/
```

the framework may be installed in editable mode.

Example, from `templates/agent_template_backend`:

```bash
pip install -e ../../libs/agent_framework
pip install -r requirements.txt
```

Or, from the repository root:

```bash
pip install -e ./libs/agent_framework
pip install -r ./templates/agent_template_backend/requirements.txt
```

Editable mode is appropriate for product development because changes made under `libs/agent_framework` are immediately consumed by the template.

---

## 8. Installation in an independent workspace

When the template is distributed according to the general architecture:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

use:

```bash
pip install -e ./agent_framework
pip install -r ./agent_template_backend/requirements.txt
```

For a production build:

```bash
pip install ./agent_framework
pip install -r ./agent_template_backend/requirements.txt
```

---

## 9. Installation validation

The installation must allow:

```bash
python -c "import agent_framework; print(agent_framework.__file__)"
```

and, from the project:

```bash
python -c "import app.main"
```

An error such as:

```text
ModuleNotFoundError: No module named 'agent_framework'
```

indicates that the framework was not made available or installed correctly.

---

## 10. Backend execution

The template backend exposes its FastAPI application on:

```text
8000
```

Local execution:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Other useful checks:

```bash
curl http://localhost:8000/agents
curl http://localhost:8000/debug/mcp/tools
```

Port `8000` belongs to the agent backend and must not be confused with MCP Server or gateway ports.

---

## 11. Agent configuration

Template-specific behavior is primarily defined by files external to the framework.

### `config/agents.yaml`

Defines available agents and their profiles.

### `config/routing.yaml`

Defines intents, routes, and routing behavior.

### `config/tools.yaml`

Defines project tools and their MCP bindings.

### `config/tool_policies.yaml`

Defines execution, confirmation, control, and transactional requirements for tools.

### `config/guardrails.yaml`

Configures project guardrails.

### `config/judges.yaml`

Configures judges.

### `config/identity.yaml`

Defines identity and business keys.

### `config/mcp_parameter_mapping.yaml`

Defines parameter mapping and extraction for MCP tools.

### `config/mcp_servers.yaml`

Defines MCP Servers used in local execution.

### `config/mcp_servers.docker.yaml`

Defines endpoints suitable for Docker/container environments.

### `llm_profiles.yaml`

Defines LLM profiles and providers used by the project.

This model preserves the separation between:

```text
generic engine = agent_framework
```

and:

```text
domain rules = agent_template_backend/config + app
```

---

## 12. Example MCP Servers

The repository includes development MCP Servers under:

```text
agent_framework_oci/mcp/servers/
├── telecom_mcp_server/
├── retail_mcp_server/
└── mock_telecom_mcp/
```

The main examples use:

```text
Telecom MCP : 8100
Retail MCP  : 8200
```

The local template configuration references:

```yaml
servers:
  telecom:
    endpoint: http://localhost:8100/mcp

  retail:
    endpoint: http://localhost:8200/mcp
```

These MCP Servers are separate components from the agent backend.

---

## 13. Starting MCP Servers in development

The repository provides:

```text
scripts/run_mcp_servers.sh
```

which starts the example MCP Servers.

Local architecture:

```text
                       +------------------+
                       | Telecom MCP      |
                       | :8100            |
                       +---------+--------+
                                 |
                                 |
+----------------------+         |
| agent_template       |---------+
| backend :8000        |
+----------------------+---------+
                                 |
                                 |
                       +---------v--------+
                       | Retail MCP       |
                       | :8200            |
                       +------------------+
```

This script is a development convenience.

In production, MCP Servers should be deployed according to the target architecture and should not depend on shell processes started inside the backend Pod.

---

## 14. MCP Gateway

`agent_framework_oci` also contains:

```text
apps/mcp_gateway/
```

and OKE configuration for the MCP Gateway.

The default repository example uses:

```text
8300
```

The template supports:

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
```

or, in OKE:

```text
http://mcp-gateway.agent-platform.svc.cluster.local:8300
```

The MCP Gateway is a platform component and is not physically part of the `agent_template_backend` directory.

---

## 15. Agent Gateway, Channel Gateway, and Frontend

The repository also contains:

```text
apps/
├── agent_gateway/
├── channel_gateway/
├── mcp_gateway/
└── agent_frontend/
```

These should be treated as platform or channel components.

`agent_template_backend` can operate directly on port `8000` without all of them being required for a simple local test.

In a complete enterprise topology, the flow may be:

```text
Client / Frontend
       |
       v
Channel Gateway
       |
       v
Agent Gateway
       |
       v
agent_template_backend
       |
       v
MCP Gateway
       |
       v
MCP Servers
```

The actual composition must follow the requirements of the target environment.

---

## 16. Development frontend

The reference frontend is located at:

```text
agent_framework_oci/apps/agent_frontend/
```

and points by default to:

```text
http://localhost:8000
```

The frontend should not be moved into `agent_template_backend` merely to satisfy a project structure.

It is a separate component.

A production project may:

- use this frontend;
- use another frontend;
- integrate Web/WhatsApp/Voice;
- expose APIs only;
- use Agent Gateway/Channel Gateway.

---

## 17. Template Dockerfile

The Dockerfile at:

```text
templates/agent_template_backend/Dockerfile
```

expects a build context containing both:

```text
agent_framework/
agent_template_backend/
```

Structure:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

Build:

```bash
docker build \
  -t agent-template-backend:local \
  -f agent_template_backend/Dockerfile \
  .
```

This is aligned with the general architectural specification.

---

## 18. Existing OKE Dockerfile in the repository

The repository also provides:

```text
deploy/oke/dockerfiles/Dockerfile.agent-template-backend
```

This Dockerfile runs with the `agent_framework_oci` repository root as context and copies:

```text
libs/agent_framework              -> /opt/agent_framework
templates/agent_template_backend  -> /app
```

There are therefore two valid build contexts for different purposes.

### Independent development/distribution

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

### Build directly from the monorepo

```text
agent_framework_oci/
├── libs/agent_framework/
└── templates/agent_template_backend/
```

Both materialize the same logical dependency:

```text
agent_template_backend -> agent_framework
```

---

## 19. Deriving a production project

`agent_template_backend` should be used as the source for a new project.

Example:

```text
agent_template_backend
        |
        | derive
        v
agent_backoffice
```

After derivation, the recommended production structure is:

```text
workspace/
├── agent_framework/
└── agent_backoffice/
```

There is no requirement to preserve the name:

```text
agent_template_backend
```

in production.

The derived project then owns:

- its own version lifecycle;
- its own Docker image;
- its own configuration;
- its own agents;
- its own workflows;
- its own policies;
- its own pipeline.

The `agent_framework` library remains shared.

---

## 20. What should and should not be copied

### Should be derived into the project

As required by the domain:

```text
app/
config/
workflows/
data/
scripts/
requirements.txt
Dockerfile
.env.example
```

### Should not be copied into the project

```text
libs/agent_framework
```

The framework must remain separately distributed and installed.

It is also not necessary to automatically copy:

```text
apps/agent_gateway
apps/channel_gateway
apps/mcp_gateway
apps/agent_frontend
mcp/servers
```

Those components should only be included when required by the target topology.

---

## 21. OKE: relationship with the general architecture

The repository contains a reference OKE implementation under:

```text
deploy/oke/
```

including:

```text
deploy/oke/k8s/base/
├── 00-namespace.yaml
├── 01-configmap.yaml
├── 02-secret-template.yaml
├── 03-agent-template-backend.yaml
├── 04-agent-gateway.yaml
├── 05-channel-gateway.yaml
├── 06-mcp-gateway.yaml
├── 07-frontend.yaml
└── kustomization.yaml
```

This implementation demonstrates how the components can be materialized in Kubernetes.

Production projects must continue to follow the rules defined by the general architectural specification.

---

## 22. Important note about demonstration OKE settings

The reference configuration currently present in the repository uses values such as:

```text
SESSION_REPOSITORY_PROVIDER=sqlite
MEMORY_REPOSITORY_PROVIDER=sqlite
CHECKPOINT_REPOSITORY_PROVIDER=sqlite
USAGE_REPOSITORY_PROVIDER=sqlite
VECTOR_STORE_PROVIDER=sqlite
GRAPH_STORE_PROVIDER=sqlite
```

These values are useful for demonstrations and controlled environments.

**They must not be interpreted as the recommended architecture for multi-replica production environments.**

In production, the general architectural specification takes precedence: shared state that must survive across Pods should use appropriate external providers.

---

## 23. Base OKE deployment for `agent_template_backend`

The following example represents the template backend specifically.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-template-backend
  namespace: agent-platform
spec:
  replicas: 3

  selector:
    matchLabels:
      app: agent-template-backend

  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1

  template:
    metadata:
      labels:
        app: agent-template-backend

    spec:
      containers:
        - name: agent-template-backend
          image: <region>.ocir.io/<namespace>/agents/agent-template-backend:<version>

          ports:
            - name: http
              containerPort: 8000

          envFrom:
            - configMapRef:
                name: agent-template-backend-config
            - secretRef:
                name: agent-template-backend-secrets

          startupProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 5
            failureThreshold: 24

          readinessProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 10
            failureThreshold: 6

          livenessProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 20
            failureThreshold: 3

          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2000m"
              memory: "4Gi"

---
apiVersion: v1
kind: Service
metadata:
  name: agent-template-backend
  namespace: agent-platform
spec:
  type: ClusterIP

  selector:
    app: agent-template-backend

  ports:
    - name: http
      port: 8000
      targetPort: http

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agent-template-backend
  namespace: agent-platform
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agent-template-backend

  minReplicas: 3
  maxReplicas: 10

  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

Sizing must be adjusted using load test results for the actual project.

---

## 24. Template-specific base ConfigMap

Example:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-template-backend-config
  namespace: agent-platform
data:
  APP_ENV: "oke"
  LOG_LEVEL: "INFO"

  AGENTS_CONFIG_PATH: "./config/agents.yaml"
  ROUTING_CONFIG_PATH: "./config/routing.yaml"
  GUARDRAILS_CONFIG_PATH: "./config/guardrails.yaml"
  JUDGES_CONFIG_PATH: "./config/judges.yaml"
  PROMPT_POLICY_PATH: "./config/prompt_policy.yaml"
  IDENTITY_CONFIG_PATH: "./config/identity.yaml"
  MCP_PARAMETER_MAPPING_PATH: "./config/mcp_parameter_mapping.yaml"

  ENABLE_INPUT_GUARDRAILS: "true"
  ENABLE_OUTPUT_GUARDRAILS: "true"
  ENABLE_JUDGES: "true"
  ENABLE_SUPERVISOR: "true"
  ENABLE_OUTPUT_SUPERVISOR: "true"
  ENABLE_PARALLEL_GUARDRAILS: "true"
  ENABLE_MCP_TOOLS: "true"

  MCP_GATEWAY_ENABLED: "true"
  MCP_GATEWAY_URL: "http://mcp-gateway.agent-platform.svc.cluster.local:8300"

  FRAMEWORK_CHANNEL_INPUT_MODE: "embedded"
```

Persistence, LLM, memory, cache, observability, and RAG providers should be configured according to the production environment and the general architectural specification.

---

## 25. Complete reference OKE topology

A complete installation may use:

```text
                       +----------------------+
                       | Agent Frontend       |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | Channel Gateway      |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | Agent Gateway        |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | Agent Backend        |
                       | :8000                |
                       +----------+-----------+
                                  |
                                  v
                       +----------------------+
                       | MCP Gateway          |
                       | :8300                |
                       +----------+-----------+
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
          +------------------+        +------------------+
          | Telecom MCP      |        | Retail MCP       |
          | :8100            |        | :8200            |
          +------------------+        +------------------+
```

This is a reference topology, not a mandatory topology for every project.

---

## 26. MCP Servers on OKE

MCP Servers should be deployed as independent components when used in production.

Conceptual example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: telecom-mcp
  namespace: agent-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: telecom-mcp
  template:
    metadata:
      labels:
        app: telecom-mcp
    spec:
      containers:
        - name: telecom-mcp
          image: <region>.ocir.io/<namespace>/mcp/telecom:<version>
          ports:
            - containerPort: 8100

---
apiVersion: v1
kind: Service
metadata:
  name: telecom-mcp
  namespace: agent-platform
spec:
  selector:
    app: telecom-mcp
  ports:
    - port: 8100
      targetPort: 8100
```

The same approach may be used for other MCP Servers.

---

## 27. Health, readiness, and startup

The backend should maintain:

```text
GET /health
```

as the minimum probe endpoint.

Recommended:

- `startupProbe` for initialization;
- `readinessProbe` for traffic admission;
- `livenessProbe` to detect an unhealthy process.

An application should not rely only on `livenessProbe`.

---

## 28. State and scalability

When using:

```yaml
replicas: 3
```

there is no guarantee that consecutive requests will be handled by the same Pod.

Therefore, in production:

```text
session
checkpoint
memory
idempotency
transaction state
shared cache
```

must be assessed for externalization.

A SQLite database stored under:

```text
/data
```

inside an `emptyDir` volume is local to a Pod and is not shared storage.

---

## 29. Local versus container MCP configuration

The template separates:

```text
config/mcp_servers.yaml
```

from:

```text
config/mcp_servers.docker.yaml
```

This is intentional.

Local:

```yaml
endpoint: http://localhost:8100/mcp
```

Docker/Kubernetes:

```yaml
endpoint: http://telecom-mcp:8100/mcp
```

The endpoint must reflect the DNS visible from the backend process.

---

## 30. `.env.example`

The file:

```text
templates/agent_template_backend/.env.example
```

is a configuration reference.

It must not be used as a place to store real credentials in source control.

In production:

- non-sensitive configuration may come from ConfigMaps;
- secrets should come from Kubernetes Secrets, OCI Vault, or an equivalent enterprise solution;
- credentials must not be committed.

---

## 31. Using the template for new projects

Recommended flow:

```text
agent_framework_oci
        |
        +--> libs/agent_framework
        |
        +--> templates/agent_template_backend
                          |
                          v
                  new agent project
```

Steps:

1. select the `agent_framework` version;
2. derive `agent_template_backend`;
3. rename the project;
4. adjust `agents.yaml`;
5. adjust `routing.yaml`;
6. adjust tools and tool policies;
7. create or modify workflows;
8. configure identity;
9. configure MCP;
10. configure guardrails and judges;
11. configure persistence and memory;
12. test locally;
13. run regression tests;
14. build the image;
15. deploy to staging;
16. promote to production according to the enterprise pipeline.

---

## 32. The template must not create a framework fork

Generic and reusable changes should be evaluated for implementation under:

```text
libs/agent_framework
```

Domain-specific changes should remain in the derived project.

Example:

```text
"new billing-specific rule"
          -> agent project

"new generic pause/resume mechanism"
          -> agent_framework
```

This principle reduces divergence between projects.

---

## 33. Version compatibility

A derived project should record:

```text
AGENT_APPLICATION_VERSION
AGENT_FRAMEWORK_VERSION
GIT_COMMIT
BUILD_ID
```

Example:

```text
agent-backoffice: 3.2.0
agent-framework: 1.8.0
```

A framework upgrade should trigger the project's regression suite.

---

## 34. Role of `Tuning-Performance`

The repository contains scenarios and variants under:

```text
Tuning-Performance/
```

These materials are references for features, tuning scenarios, regression, and implementation examples.

They do not change the basic architectural relationship:

```text
agent project -> agent_framework
```

A production project should incorporate only the configurations or implementations required and validated for its use case.

---

## 35. Role of the template's internal documentation

The directory:

```text
templates/agent_template_backend/docs/
```

contains detailed documentation for template-specific functionality, including topics such as:

- memory;
- observability;
- guardrails;
- IC/NOC/GRL;
- transactions;
- routing;
- channel input;
- output supervisor.

This document does not replace those functional manuals.

It defines the **usage, distribution, and deployment model for the template**.

---

## 36. Mandatory requirements for correct usage

1. The template must consume `agent_framework` through Python imports.

2. The framework must remain under:

```text
agent_framework_oci/libs/agent_framework
```

as its source location in the monorepo.

3. The template must remain under:

```text
agent_framework_oci/templates/agent_template_backend
```

as its source location in the monorepo.

4. In an independent distribution, both should be materialized at the same level:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

5. A derived production project must follow the general architectural specification.

6. The framework must not be duplicated inside the project.

7. MCP Servers must not be confused with the backend.

8. The MCP Gateway is not part of the template directory.

9. The frontend is not part of the template directory.

10. SQLite settings present in examples must not be treated as the production default for multi-Pod environments.

11. The backend must expose a health check.

12. Real secrets must not be stored in `.env.example` or committed manifests.

13. The framework version used by the project must be traceable.

14. Generic changes should preferably be implemented in the framework, avoiding project-specific framework forks.

---

## 37. Final reference structure

### Inside the `agent_framework_oci` product

```text
agent_framework_oci/
├── libs/
│   └── agent_framework/
│
├── templates/
│   └── agent_template_backend/
│
├── apps/
│   ├── agent_gateway/
│   ├── channel_gateway/
│   ├── mcp_gateway/
│   └── agent_frontend/
│
├── mcp/
│   └── servers/
│
└── deploy/
    └── oke/
```

### Derived production project

```text
workspace/
├── agent_framework/
│
└── agent_backoffice/
    ├── app/
    ├── config/
    ├── workflows/
    ├── data/
    ├── scripts/
    ├── requirements.txt
    ├── Dockerfile
    └── .env.example
```

---

## 38. Final rule

`agent_template_backend` is a **reference implementation of the standard**, not the framework itself.

The correct relationship is:

```text
agent_framework
      ^
      |
agent_template_backend
      |
      v
derived projects
```

For development inside the monorepo, the original `libs/` and `templates/` paths may be used.

For distribution and production, derived projects must follow the **General `agent_framework_oci` Usage Specification**, keeping the agent project and `agent_framework` as separate, independently versioned components.
