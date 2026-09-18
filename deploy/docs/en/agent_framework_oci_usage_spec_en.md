# `agent_framework_oci` Usage Specification

## 1. Purpose

This specification defines the standard for developing, packaging, and deploying agent projects based on `agent_framework_oci`.

The primary goal is to establish a clear separation between:

- the **shared enterprise framework**, responsible for generic platform capabilities;
- the **agent projects**, responsible for domain-specific rules, configuration, workflows, and implementations.

The `agent_framework` must not be embedded or duplicated inside each agent project.

The library must be made available separately and consumed by agent projects through standard Python imports.

---

## 2. Framework source

In the official `agent_framework_oci` repository, the shared framework implementation is located at:

```text
agent_framework_oci/
└── libs/
    └── agent_framework/
```

This directory is the distributable Python package for the framework.

Its structure includes, among other components:

```text
agent_framework/
├── pyproject.toml
├── src/
│   └── agent_framework/
│       ├── analytics/
│       ├── cache/
│       ├── channels/
│       ├── guardrails/
│       ├── memory/
│       ├── observability/
│       ├── routing/
│       ├── supervisor/
│       ├── workflows/
│       └── ...
```

The `pyproject.toml` defines the package:

```toml
[project]
name = "agent-framework"
version = "0.1.0"
```

and uses:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

Therefore:

```text
agent_framework_oci/libs/agent_framework
```

must be treated as an independent, reusable Python library.

---

## 3. Required directory structure for agent projects

When using the framework outside the main repository, the directory:

```text
agent_framework_oci/libs/agent_framework
```

must be made available together with the agent project.

The agent project and the framework must reside **at the same directory level**.

Example:

```text
workspace/
├── agent_framework/
│   ├── pyproject.toml
│   └── src/
│       └── agent_framework/
│
└── backoffice/
    ├── app/
    ├── config/
    ├── data/
    ├── requirements.txt
    ├── Dockerfile
    └── .env
```

Another example:

```text
workspace/
├── agent_framework/
│
└── agent_contas/
    ├── app/
    ├── config/
    ├── data/
    ├── requirements.txt
    ├── Dockerfile
    └── .env
```

The architectural rule is:

```text
<workspace>/
├── agent_framework/
└── <agent_project>/
```

and not:

```text
<agent_project>/
└── agent_framework/
```

The agent project must not contain a private copy of the framework.

---

## 4. Responsibilities

### 4.1 `agent_framework`

The `agent_framework` contains generic and reusable platform capabilities such as:

- routing;
- supervisor;
- multi-agent;
- workflows;
- conversational states;
- parameter collection;
- pause/resume;
- pending actions;
- multi-intent;
- intent shift;
- route stickiness;
- deterministic transactions;
- guardrails;
- judges;
- output supervisor;
- RAG;
- memory;
- cache;
- observability;
- telemetry;
- MCP integration;
- persistence;
- analytics;
- OCI provider integration;
- resilience mechanisms;
- idempotency;
- error handling.

These components belong to the framework and must not be copied into consumer projects.

### 4.2 Agent project

Each agent project contains only domain-specific implementation and configuration.

Example:

```text
backoffice/
├── app/
│   ├── agents/
│   ├── workflows/
│   ├── observability/
│   ├── workflow_actions/
│   ├── presentation/
│   ├── state.py
│   └── main.py
│
├── config/
│   ├── agents.yaml
│   ├── routing.yaml
│   ├── tools.yaml
│   ├── tool_policies.yaml
│   ├── guardrails.yaml
│   ├── judges.yaml
│   ├── prompt_policy.yaml
│   ├── identity.yaml
│   └── mcp_parameter_mapping.yaml
│
├── data/
├── requirements.txt
├── Dockerfile
└── .env
```

The project may use any public framework capability through standard imports.

Example:

```python
from agent_framework.routing import ...
```

or:

```python
from agent_framework.supervisor import ...
```

or:

```python
from agent_framework.observability import ...
```

The project code must not depend on internal repository paths from `agent_framework_oci`.

---

## 5. Local development installation

Given:

```text
workspace/
├── agent_framework/
└── backoffice/
```

the recommended setup is:

```bash
cd workspace

python -m venv .venv

source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

Install the framework:

```bash
pip install -e ./agent_framework
```

Install project dependencies:

```bash
pip install -r ./backoffice/requirements.txt
```

Editable mode:

```bash
pip install -e
```

is recommended for development because the Python environment references the framework source directly.

Framework changes then become immediately available to the agent project without a complete package reinstall.

---

## 6. Mandatory validation

After installing the framework, the following command must execute successfully:

```bash
python -c "import agent_framework; print(agent_framework.__file__)"
```

Imports used by the application should also be validated:

```bash
python -c "from agent_framework import *"
```

or with specific imports required by the agent implementation.

An error such as:

```text
ModuleNotFoundError: No module named 'agent_framework'
```

indicates that the framework was not made available or installed correctly.

---

## 7. CI/CD model

A CI/CD pipeline should create a workspace containing both components.

Example:

```text
build/
├── agent_framework/
└── backoffice/
```

The framework may be obtained directly from:

```text
agent_framework_oci/libs/agent_framework
```

and copied to:

```text
build/agent_framework
```

The agent project should be copied to:

```text
build/backoffice
```

The Docker build must use:

```text
build/
```

as the build context.

Example:

```bash
docker build \
  -f backoffice/Dockerfile \
  -t backoffice:1.0.0 \
  .
```

This is important.

The build context must be:

```text
.
```

representing the directory that contains both:

```text
agent_framework/
backoffice/
```

---

## 8. Standard Dockerfile

An agent project should use a Dockerfile similar to the following:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Shared framework
COPY agent_framework /workspace/agent_framework

# Agent-specific project
COPY backoffice /workspace/backoffice

# Install enterprise framework first
RUN pip install --upgrade pip \
    && pip install /workspace/agent_framework

# Install agent-specific dependencies
RUN pip install -r /workspace/backoffice/requirements.txt

WORKDIR /workspace/backoffice

EXPOSE 8000

CMD [
    "uvicorn",
    "app.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000"
]
```

For development, the following may optionally be used:

```dockerfile
RUN pip install -e /workspace/agent_framework
```

For immutable production images, the recommended form is:

```dockerfile
RUN pip install /workspace/agent_framework
```

This freezes the framework version used by the image at build time.

---

## 9. Container directory structure

The container should conceptually preserve the same separation used during development:

```text
/workspace/
├── agent_framework/
└── backoffice/
```

The application runs from:

```text
/workspace/backoffice
```

The framework is installed in the Python environment and may be imported normally:

```python
import agent_framework
```

There should be no need to use:

```python
sys.path.append(...)
```

or dynamically modify `PYTHONPATH` inside the application code.

---

## 10. Framework versioning

The framework version used by the agent must be determined at build time.

At minimum, the following should be recorded:

```text
AGENT_FRAMEWORK_VERSION
AGENT_APPLICATION_VERSION
BUILD_ID
GIT_COMMIT
```

Example:

```yaml
env:
  - name: AGENT_FRAMEWORK_VERSION
    value: "1.5.0"

  - name: AGENT_APPLICATION_VERSION
    value: "2.1.4"
```

This makes it possible to identify the exact:

```text
Framework + Agent
```

combination running in each environment.

---

## 11. Image publication

After the build:

```bash
docker build \
  -f backoffice/Dockerfile \
  -t backoffice:1.0.0 \
  .
```

the image should be published to OCI Container Registry — OCIR.

Example:

```bash
docker tag \
  backoffice:1.0.0 \
  gru.ocir.io/<namespace>/agents/backoffice:1.0.0
```

Then:

```bash
docker push \
  gru.ocir.io/<namespace>/agents/backoffice:1.0.0
```

---

## 12. Deployment on OCI OKE

Each agent project should have its own Kubernetes `Deployment`.

The framework does not need to run as an independent Pod.

`agent_framework` is a library and is included in the agent project image during the build process.

Architecture:

```text
                    OCI OKE
                       |
                       v
              Kubernetes Service
                       |
          +------------+------------+
          |            |            |
          v            v            v
       Agent Pod    Agent Pod    Agent Pod
          |            |            |
          +------------+------------+
                       |
              agent_framework
            installed in image
```

The framework code is shared by source and version, but is installed into each agent image.

---

## 13. Base OKE YAML manifest

The following manifest can be used as a base for deploying a project such as `backoffice`.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: agent-platform

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: backoffice-config
  namespace: agent-platform
data:
  APP_ENV: "oke"
  LOG_LEVEL: "INFO"

  AGENT_FRAMEWORK_VERSION: "1.0.0"

  AGENT_ID: "backoffice"
  AGENT_APPLICATION_VERSION: "1.0.0"

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
  ENABLE_MCP_TOOLS: "true"

  MCP_GATEWAY_ENABLED: "true"
  MCP_GATEWAY_URL: "http://mcp-gateway.agent-platform.svc.cluster.local:8300"

  ENABLE_LANGFUSE: "true"
  ENABLE_OTEL: "true"
  ENABLE_ANALYTICS: "true"

---
apiVersion: v1
kind: Secret
metadata:
  name: backoffice-secrets
  namespace: agent-platform
type: Opaque
stringData:
  OCI_COMPARTMENT_ID: "<OCI_COMPARTMENT_ID>"
  OCI_GENAI_API_KEY: "<OCI_GENAI_API_KEY>"
  LANGFUSE_PUBLIC_KEY: "<LANGFUSE_PUBLIC_KEY>"
  LANGFUSE_SECRET_KEY: "<LANGFUSE_SECRET_KEY>"

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backoffice
  namespace: agent-platform
  labels:
    app: backoffice

spec:
  replicas: 3

  selector:
    matchLabels:
      app: backoffice

  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1

  template:
    metadata:
      labels:
        app: backoffice

    spec:
      containers:
        - name: backoffice
          image: gru.ocir.io/<namespace>/agents/backoffice:1.0.0
          imagePullPolicy: IfNotPresent

          ports:
            - name: http
              containerPort: 8000
              protocol: TCP

          envFrom:
            - configMapRef:
                name: backoffice-config
            - secretRef:
                name: backoffice-secrets

          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 15
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 6

          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 30
            periodSeconds: 20
            timeoutSeconds: 5
            failureThreshold: 3

          startupProbe:
            httpGet:
              path: /health
              port: http
            periodSeconds: 5
            failureThreshold: 24

          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2000m"
              memory: "4Gi"

          securityContext:
            allowPrivilegeEscalation: false

---
apiVersion: v1
kind: Service
metadata:
  name: backoffice
  namespace: agent-platform

spec:
  type: ClusterIP

  selector:
    app: backoffice

  ports:
    - name: http
      protocol: TCP
      port: 8000
      targetPort: http

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backoffice
  namespace: agent-platform

spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backoffice

  minReplicas: 3
  maxReplicas: 10

  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0

      policies:
        - type: Percent
          value: 100
          periodSeconds: 60

        - type: Pods
          value: 4
          periodSeconds: 60

      selectPolicy: Max

    scaleDown:
      stabilizationWindowSeconds: 300

      policies:
        - type: Percent
          value: 25
          periodSeconds: 60

  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70

    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 75

---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: backoffice
  namespace: agent-platform

spec:
  minAvailable: 2

  selector:
    matchLabels:
      app: backoffice
```

---

## 14. Applying the manifest

The manifest may be stored as:

```text
deploy/oke/backoffice.yaml
```

and applied with:

```bash
kubectl apply -f deploy/oke/backoffice.yaml
```

Validation:

```bash
kubectl -n agent-platform get pods
kubectl -n agent-platform get deployment
kubectl -n agent-platform get svc
kubectl -n agent-platform get hpa
```

To track rollout status:

```bash
kubectl -n agent-platform rollout status deployment/backoffice
```

---

## 15. Health check

Every agent project deployed to OKE should provide:

```http
GET /health
```

returning:

```text
200 OK
```

while the application is ready to receive requests.

This endpoint is used by:

```text
startupProbe
readinessProbe
livenessProbe
```

---

## 16. Persistence and multiple replicas

OKE applications must assume that multiple Pods may run simultaneously.

Conversational and transactional data that must survive across requests must therefore not depend exclusively on the container filesystem.

Local SQLite is not recommended as the definitive persistence layer for multi-replica OKE environments.

Production environments should use external providers for:

- sessions;
- checkpoints;
- memory;
- cache;
- idempotency;
- locks;
- analytics;
- transactional state.

Depending on the framework configuration, examples include:

```text
Oracle Autonomous Database
MongoDB
Redis
OCI Streaming
OCI Object Storage
```

---

## 17. Framework upgrades

An agent project must not receive framework changes by copying individual framework source files into the project.

Upgrades should be performed by replacing the available version of:

```text
agent_framework/
```

and rebuilding the image.

Process:

```text
New agent_framework version
          |
          v
CI/CD workspace update
          |
          v
Agent image build
          |
          v
Tests
          |
          v
OCIR push
          |
          v
OKE Rolling Update
```

This maintains a clear separation between:

```text
product/framework
```

and:

```text
agent implementation
```

---

## 18. Compatibility rule

Each project release should explicitly declare the framework version against which it was tested.

Example:

```text
Backoffice 3.2.0
Agent Framework 1.8.0
```

A new framework version should not be promoted directly to production without executing regression tests for the consuming agent project.

Recommended pipeline:

```text
Framework
   |
   v
Build Agent
   |
   v
Unit Tests
   |
   v
Integration Tests
   |
   v
Workflow Regression
   |
   v
Smoke Test
   |
   v
Staging
   |
   v
Production
```

---

## 19. Multiple projects using the same framework

The structure may support several projects simultaneously:

```text
workspace/
├── agent_framework/
├── backoffice/
├── contas/
├── ofertas/
├── atendimento/
└── suporte/
```

All of them use:

```text
agent_framework/
```

as the common platform source.

Each application, however, generates its own image:

```text
backoffice:3.0.0
contas:5.2.0
ofertas:1.4.0
atendimento:2.6.0
```

All images may have been built with:

```text
agent-framework:1.8.0
```

This allows projects to evolve independently without forking the framework.

---

## 20. Architectural principle

The relationship between the components should remain:

```text
                 agent_framework
                       |
       +---------------+---------------+
       |               |               |
       v               v               v
   Backoffice        Contas          Ofertas
       |               |               |
       v               v               v
   OCI image        OCI image       OCI image
       |               |               |
       +---------------+---------------+
                       |
                       v
                     OKE
```

`agent_framework` is the common technology platform.

Agent projects are consumers of that platform.

Therefore:

**the agent project depends on the framework; the framework must not depend on the agent project.**

---

## 21. Mandatory requirements

To be considered compatible with `agent_framework_oci`, a project must satisfy the following requirements:

1. `agent_framework` must be obtained from:

```text
agent_framework_oci/libs/agent_framework
```

2. The framework must be made available separately from the agent project.

3. The distribution structure must be:

```text
<workspace>/
├── agent_framework/
└── <agent_project>/
```

4. The framework must not be duplicated inside the agent project.

5. The library must be installed using the standard Python packaging mechanism:

```bash
pip install ./agent_framework
```

or, for development:

```bash
pip install -e ./agent_framework
```

6. Imports must use:

```python
import agent_framework
```

and never physical repository paths.

7. The Docker build context must have access to both:

```text
agent_framework/
```

and:

```text
<agent_project>/
```

8. Each image must contain a known framework version.

9. OKE deployments must expose health probes.

10. Scalable applications must externalize shared state.

11. Secrets must not be stored in source code or committed deployment manifests.

12. Each project must have its own Deployment and Service.

13. Horizontal scaling must occur at the agent application layer, not through a centralized executable `agent_framework` instance.

---

## 22. Recommended final structure

The reference structure for development and CI/CD is:

```text
agent-runtime/
│
├── agent_framework/
│   ├── pyproject.toml
│   └── src/
│       └── agent_framework/
│
├── backoffice/
│   ├── app/
│   ├── config/
│   ├── data/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
└── deploy/
    └── oke/
        └── backoffice.yaml
```

For new projects, only the project-specific directory changes:

```text
agent-runtime/
│
├── agent_framework/
│
├── new_agent/
│
└── deploy/
    └── oke/
        └── new_agent.yaml
```

This should be the standard distribution and deployment model for projects built on `agent_framework_oci`.
