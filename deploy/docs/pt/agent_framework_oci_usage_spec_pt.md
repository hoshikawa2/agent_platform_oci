# Especificação de Utilização do `agent_framework_oci`

## 1. Objetivo

Esta especificação define o padrão para desenvolvimento, empacotamento e deployment de projetos de agentes baseados no `agent_framework_oci`.

O objetivo principal é estabelecer uma separação clara entre:

- o **framework corporativo compartilhado**, responsável pelas capacidades genéricas da plataforma;
- os **projetos de agentes**, responsáveis pelas regras, configurações, workflows e implementações específicas de cada domínio.

O `agent_framework` não deve ser incorporado ou duplicado dentro de cada projeto de agente.

A biblioteca deve ser disponibilizada separadamente e utilizada pelos projetos por meio de imports Python.

---

## 2. Origem do framework

No repositório oficial `agent_framework_oci`, a implementação compartilhada encontra-se em:

```text
agent_framework_oci/
└── libs/
    └── agent_framework/
```

Essa pasta corresponde ao pacote Python distribuível do framework.

Sua estrutura contém, entre outros componentes:

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

O `pyproject.toml` define o pacote:

```toml
[project]
name = "agent-framework"
version = "0.1.0"
```

e utiliza:

```toml
[tool.setuptools.packages.find]
where = ["src"]
```

Portanto, a pasta:

```text
agent_framework_oci/libs/agent_framework
```

deve ser tratada como uma biblioteca Python independente e reutilizável.

---

## 3. Estrutura obrigatória para projetos de agentes

Para utilização do framework fora do repositório principal, a pasta:

```text
agent_framework_oci/libs/agent_framework
```

deve ser disponibilizada juntamente com o projeto de agente.

O projeto de agente e o framework devem ficar **no mesmo nível de diretório**.

Exemplo:

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

Para outro agente:

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

A regra arquitetural é:

```text
<workspace>/
├── agent_framework/
└── <projeto_do_agente>/
```

e não:

```text
<projeto_do_agente>/
└── agent_framework/
```

O projeto do agente não deve possuir uma cópia privada do framework.

---

## 4. Responsabilidades

### 4.1 `agent_framework`

O `agent_framework` contém capacidades genéricas e reutilizáveis da plataforma, como:

- routing;
- supervisor;
- multi-agent;
- workflows;
- estados conversacionais;
- coleta de parâmetros;
- pause/resume;
- pending actions;
- multi-intent;
- intent shift;
- route stickiness;
- transações determinísticas;
- guardrails;
- judges;
- output supervisor;
- RAG;
- memória;
- cache;
- observabilidade;
- telemetria;
- integração MCP;
- persistência;
- analytics;
- integração com provedores OCI;
- mecanismos de resiliência;
- idempotência;
- tratamento de erros.

Esses componentes pertencem ao framework e não devem ser copiados para os projetos consumidores.

### 4.2 Projeto do agente

Cada projeto de agente contém somente a implementação e configuração específicas do domínio.

Exemplo:

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

O projeto pode utilizar qualquer funcionalidade pública do framework por meio de imports.

Exemplo:

```python
from agent_framework.routing import ...
```

ou:

```python
from agent_framework.supervisor import ...
```

ou:

```python
from agent_framework.observability import ...
```

O código do projeto não deve depender de caminhos internos do repositório `agent_framework_oci`.

---

## 5. Instalação local para desenvolvimento

Considerando:

```text
workspace/
├── agent_framework/
└── backoffice/
```

a instalação recomendada é:

```bash
cd workspace

python -m venv .venv

source .venv/bin/activate
```

Em Windows:

```powershell
.venv\Scripts\activate
```

Instalar o framework:

```bash
pip install -e ./agent_framework
```

Instalar as dependências do projeto:

```bash
pip install -r ./backoffice/requirements.txt
```

O modo:

```bash
pip install -e
```

é recomendado para desenvolvimento porque mantém o código do framework referenciado diretamente pelo ambiente Python.

Alterações no framework tornam-se imediatamente disponíveis para o projeto sem reinstalação completa do pacote.

---

## 6. Validação obrigatória

Após instalar o framework, o seguinte comando deve executar sem erro:

```bash
python -c "import agent_framework; print(agent_framework.__file__)"
```

Também deve ser possível testar imports utilizados pelo projeto:

```bash
python -c "from agent_framework import *"
```

ou imports específicos conforme a implementação do agente.

Uma falha como:

```text
ModuleNotFoundError: No module named 'agent_framework'
```

indica que o framework não foi disponibilizado ou instalado corretamente.

---

## 7. Modelo para CI/CD

Em um pipeline de CI/CD, deve ser criado um workspace contendo os dois componentes.

Exemplo:

```text
build/
├── agent_framework/
└── backoffice/
```

O framework pode ser obtido diretamente do repositório `agent_framework_oci`:

```text
agent_framework_oci/libs/agent_framework
```

e copiado para:

```text
build/agent_framework
```

O projeto específico do agente deve ser copiado para:

```text
build/backoffice
```

O build da imagem Docker deve utilizar:

```text
build/
```

como contexto.

Exemplo:

```bash
docker build \
  -f backoffice/Dockerfile \
  -t backoffice:1.0.0 \
  .
```

Esse detalhe é importante.

O contexto deve ser:

```text
.
```

representando o diretório que contém simultaneamente:

```text
agent_framework/
backoffice/
```

---

## 8. Dockerfile padrão

Um projeto de agente deve adotar como base um Dockerfile semelhante ao seguinte:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Framework compartilhado
COPY agent_framework /workspace/agent_framework

# Projeto específico do agente
COPY backoffice /workspace/backoffice

# Instala primeiro o framework corporativo
RUN pip install --upgrade pip \
    && pip install /workspace/agent_framework

# Instala as dependências específicas do agente
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

Para ambiente de desenvolvimento, opcionalmente pode ser utilizado:

```dockerfile
RUN pip install -e /workspace/agent_framework
```

Para imagens imutáveis de produção, recomenda-se:

```dockerfile
RUN pip install /workspace/agent_framework
```

Dessa forma a versão do framework utilizada pela imagem fica congelada no momento do build.

---

## 9. Estrutura dentro do container

O container deve manter conceitualmente a mesma separação utilizada no desenvolvimento:

```text
/workspace/
├── agent_framework/
└── backoffice/
```

A aplicação será executada a partir de:

```text
/workspace/backoffice
```

O framework estará instalado no ambiente Python e poderá ser importado normalmente:

```python
import agent_framework
```

Não deve ser necessário utilizar:

```python
sys.path.append(...)
```

nem alterar dinamicamente o `PYTHONPATH` no código da aplicação.

---

## 10. Versionamento do framework

A versão do framework utilizada pelo agente deve ser determinada durante o build.

É recomendado registrar, no mínimo:

```text
AGENT_FRAMEWORK_VERSION
AGENT_APPLICATION_VERSION
BUILD_ID
GIT_COMMIT
```

Exemplo:

```yaml
env:
  - name: AGENT_FRAMEWORK_VERSION
    value: "1.5.0"

  - name: AGENT_APPLICATION_VERSION
    value: "2.1.4"
```

Isso permite identificar exatamente qual combinação:

```text
Framework + Agente
```

está executando em cada ambiente.

---

## 11. Publicação da imagem

Após o build:

```bash
docker build \
  -f backoffice/Dockerfile \
  -t backoffice:1.0.0 \
  .
```

a imagem deve ser publicada no OCI Container Registry — OCIR.

Exemplo:

```bash
docker tag \
  backoffice:1.0.0 \
  gru.ocir.io/<namespace>/agents/backoffice:1.0.0
```

Depois:

```bash
docker push \
  gru.ocir.io/<namespace>/agents/backoffice:1.0.0
```

---

## 12. Deployment no OCI OKE

Cada projeto de agente deve possuir seu próprio Kubernetes `Deployment`.

O framework não precisa ser executado como Pod independente.

O `agent_framework` é uma biblioteca e estará incorporado à imagem do projeto do agente durante o build.

A arquitetura é:

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
          instalado em cada imagem
```

O código do framework é compartilhado em termos de origem e versionamento, mas estará instalado dentro de cada imagem de agente.

---

## 13. Manifesto YAML base para OKE

O manifesto abaixo pode ser utilizado como base para deployment de um projeto como `backoffice`.

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

## 14. Aplicação do manifesto

O manifesto pode ser armazenado como:

```text
deploy/oke/backoffice.yaml
```

e aplicado com:

```bash
kubectl apply -f deploy/oke/backoffice.yaml
```

Validação:

```bash
kubectl -n agent-platform get pods
kubectl -n agent-platform get deployment
kubectl -n agent-platform get svc
kubectl -n agent-platform get hpa
```

Para acompanhar o rollout:

```bash
kubectl -n agent-platform rollout status deployment/backoffice
```

---

## 15. Health check

Todo projeto de agente destinado ao OKE deve disponibilizar:

```http
GET /health
```

com retorno:

```text
200 OK
```

enquanto estiver apto a receber novas requisições.

Esse endpoint é utilizado pelas probes:

```text
startupProbe
readinessProbe
livenessProbe
```

---

## 16. Persistência e múltiplas réplicas

Aplicações em OKE devem considerar que múltiplos Pods podem executar simultaneamente.

Portanto, dados conversacionais e transacionais que precisem sobreviver entre requisições não devem depender exclusivamente do filesystem do container.

Não é recomendado utilizar SQLite local como repositório definitivo para ambientes OKE com múltiplas réplicas.

Para produção devem ser utilizados providers externos adequados para:

- sessions;
- checkpoints;
- memória;
- cache;
- idempotência;
- locks;
- analytics;
- estado transacional.

Dependendo da configuração do framework, podem ser utilizados, por exemplo:

```text
Oracle Autonomous Database
MongoDB
Redis
OCI Streaming
OCI Object Storage
```

---

## 17. Atualização do framework

Um projeto de agente não deve receber alterações no framework copiando arquivos individualmente para seu código.

A atualização deve acontecer substituindo a versão disponibilizada de:

```text
agent_framework/
```

e reconstruindo a imagem.

Processo:

```text
Nova versão agent_framework
          |
          v
Atualização do workspace CI/CD
          |
          v
Build da imagem do agente
          |
          v
Testes
          |
          v
Push OCIR
          |
          v
Rolling Update OKE
```

Esse modelo mantém clara a separação entre:

```text
produto/framework
```

e:

```text
implementação do agente
```

---

## 18. Regra de compatibilidade

Cada release de projeto deverá declarar explicitamente a versão do framework contra a qual foi testada.

Exemplo:

```text
Backoffice 3.2.0
Agent Framework 1.8.0
```

Uma nova versão do framework não deve ser promovida diretamente para produção sem que sejam executados os testes de regressão do projeto consumidor.

Pipeline recomendado:

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
Homologação
   |
   v
Produção
```

---

## 19. Vários projetos utilizando o mesmo framework

A estrutura pode atender simultaneamente vários projetos:

```text
workspace/
├── agent_framework/
├── backoffice/
├── contas/
├── ofertas/
├── atendimento/
└── suporte/
```

Todos utilizam:

```text
agent_framework/
```

como origem comum da plataforma.

Cada aplicação, entretanto, gera sua própria imagem:

```text
backoffice:3.0.0
contas:5.2.0
ofertas:1.4.0
atendimento:2.6.0
```

Todas podem ter sido construídas com:

```text
agent-framework:1.8.0
```

Isso permite evoluir projetos de forma independente sem realizar forks do framework.

---

## 20. Princípio arquitetural

A relação entre os componentes deve permanecer:

```text
                 agent_framework
                       |
       +---------------+---------------+
       |               |               |
       v               v               v
   Backoffice        Contas          Ofertas
       |               |               |
       v               v               v
   imagem OCI       imagem OCI      imagem OCI
       |               |               |
       +---------------+---------------+
                       |
                       v
                     OKE
```

O `agent_framework` é a plataforma tecnológica comum.

Os projetos de agentes são consumidores dessa plataforma.

Consequentemente:

**o projeto do agente depende do framework; o framework não deve depender do projeto do agente.**

---

## 21. Requisitos obrigatórios

Para que um projeto seja considerado compatível com o `agent_framework_oci`, devem ser atendidos os seguintes requisitos:

1. `agent_framework` deve ser obtido de:

```text
agent_framework_oci/libs/agent_framework
```

2. O framework deve ser disponibilizado separadamente do projeto do agente.

3. A estrutura de distribuição deve ser:

```text
<workspace>/
├── agent_framework/
└── <agent_project>/
```

4. O framework não deve ser duplicado dentro do projeto.

5. A biblioteca deve ser instalada pelo mecanismo padrão do Python:

```bash
pip install ./agent_framework
```

ou, em desenvolvimento:

```bash
pip install -e ./agent_framework
```

6. Imports devem utilizar:

```python
import agent_framework
```

e nunca caminhos físicos do repositório.

7. O contexto Docker deve permitir acesso simultâneo a:

```text
agent_framework/
```

e:

```text
<agent_project>/
```

8. Cada imagem deve conter uma versão conhecida do framework.

9. O deployment OKE deve possuir probes de saúde.

10. Aplicações escaláveis devem externalizar estado compartilhado.

11. Secrets não devem ser mantidos no código nem no manifesto versionado.

12. Cada projeto deve possuir Deployment e Service próprios.

13. A escala horizontal deve acontecer no projeto do agente, e não através de uma instância central executável do `agent_framework`.

---

## 22. Estrutura recomendada final

A estrutura de referência para desenvolvimento e CI/CD é:

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

Para novos projetos, somente a pasta específica muda:

```text
agent-runtime/
│
├── agent_framework/
│
├── novo_agente/
│
└── deploy/
    └── oke/
        └── novo_agente.yaml
```

Esse deve ser o padrão de distribuição e deployment dos projetos construídos sobre o `agent_framework_oci`.
