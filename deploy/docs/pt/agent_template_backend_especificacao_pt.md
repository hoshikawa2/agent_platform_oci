# Especificação de Uso do `agent_template_backend`

## Documento complementar à arquitetura geral do `agent_framework_oci`

> **Escopo deste documento**
>
> Este documento é específico para o `agent_template_backend` distribuído com o `agent_framework_oci`.
>
> Ele **não substitui** a especificação arquitetural geral de utilização do `agent_framework_oci` para projetos de produção. A especificação geral continua sendo a referência normativa para estrutura de projetos produtivos, empacotamento, versionamento, CI/CD, externalização de estado, segurança, escalabilidade e deployment em OKE.
>
> Este documento explica como o `agent_template_backend` existente no repositório deve ser utilizado como **template de referência**, ambiente de desenvolvimento, base para novos agentes e origem para projetos produtivos derivados.

---

## 1. Objetivo

O `agent_template_backend` é o template de backend de agentes fornecido pelo repositório `agent_framework_oci`.

Sua finalidade é oferecer uma implementação inicial funcional que demonstre como um projeto de agente deve consumir o `agent_framework`, organizar configurações, expor APIs, utilizar workflows, integrar MCP, aplicar guardrails e judges e utilizar os demais serviços corporativos do framework.

O template deve ser entendido como:

- referência de implementação;
- ponto de partida para novos projetos;
- ambiente de desenvolvimento e validação;
- exemplo de integração com o `agent_framework`;
- exemplo de deployment;
- base para geração de projetos independentes.

O template **não deve ser interpretado como uma exceção** às regras arquiteturais definidas na especificação geral de produção.

---

## 2. Relação com a especificação arquitetural geral

Existem dois níveis de documentação.

### 2.1. Especificação arquitetural geral

A especificação geral define o padrão para projetos produtivos derivados do framework:

```text
<workspace>/
├── agent_framework/
└── <agent_project>/
```

Ela define, entre outros pontos:

- separação entre framework e projeto;
- instalação do `agent_framework`;
- versionamento;
- contexto de build;
- Docker;
- CI/CD;
- deployment em OKE;
- escalabilidade;
- externalização de estado;
- gerenciamento de secrets;
- compatibilidade entre versão do framework e versão do agente.

### 2.2. Esta especificação

Este documento descreve como o template entregue no repositório se encaixa nesse modelo.

Quando existir diferença entre uma configuração demonstrativa do template e uma regra da especificação arquitetural geral, **a especificação arquitetural geral prevalece para ambientes de produção**.

---

## 3. Localização do template no repositório

No repositório fonte, o template está localizado em:

```text
agent_framework_oci/
└── templates/
    └── agent_template_backend/
```

O framework compartilhado está localizado em:

```text
agent_framework_oci/
└── libs/
    └── agent_framework/
```

Portanto, dentro do repositório de desenvolvimento, a estrutura é:

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

Essa organização é a **estrutura fonte do produto `agent_framework_oci`**.

Ela não altera a regra da especificação arquitetural de produção.

---

## 4. Estrutura de distribuição do template

Quando o `agent_template_backend` for extraído do repositório para uso independente, build isolado ou criação de um projeto derivado, o workspace deve materializar:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

O conteúdo de:

```text
agent_framework_oci/libs/agent_framework/
```

deve ser disponibilizado como:

```text
workspace/agent_framework/
```

e o conteúdo de:

```text
agent_framework_oci/templates/agent_template_backend/
```

como:

```text
workspace/agent_template_backend/
```

Essa estrutura é compatível com o Dockerfile existente no template.

---

## 5. Estrutura atual do `agent_template_backend`

A estrutura principal do template é:

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

O template contém configuração suficiente para demonstrar as capacidades corporativas do framework sem que essas capacidades precisem ser copiadas para o projeto.

---

## 6. Dependência do `agent_framework`

O `agent_template_backend` é um consumidor do framework.

A dependência deve permanecer unidirecional:

```text
agent_template_backend
        |
        v
agent_framework
```

O inverso não deve ocorrer.

O `agent_framework` não deve depender de:

```text
templates/agent_template_backend
```

nem de arquivos específicos do template.

---

## 7. Instalação local no repositório fonte

Para desenvolvimento diretamente dentro do repositório:

```text
agent_framework_oci/
├── libs/agent_framework/
└── templates/agent_template_backend/
```

o framework pode ser instalado em modo editável.

Exemplo, a partir de `templates/agent_template_backend`:

```bash
pip install -e ../../libs/agent_framework
pip install -r requirements.txt
```

Ou, a partir do root:

```bash
pip install -e ./libs/agent_framework
pip install -r ./templates/agent_template_backend/requirements.txt
```

O modo editável é adequado para desenvolvimento do produto, pois alterações realizadas em `libs/agent_framework` são imediatamente utilizadas pelo template.

---

## 8. Instalação em workspace independente

Quando o template for disponibilizado segundo a estrutura arquitetural geral:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

utilize:

```bash
pip install -e ./agent_framework
pip install -r ./agent_template_backend/requirements.txt
```

Para um build de produção:

```bash
pip install ./agent_framework
pip install -r ./agent_template_backend/requirements.txt
```

---

## 9. Validação de instalação

A instalação deve permitir:

```bash
python -c "import agent_framework; print(agent_framework.__file__)"
```

e, a partir do projeto:

```bash
python -c "import app.main"
```

Uma falha:

```text
ModuleNotFoundError: No module named 'agent_framework'
```

indica erro na disponibilização ou instalação da biblioteca.

---

## 10. Execução do backend

O backend do template expõe a aplicação FastAPI em:

```text
8000
```

Execução local:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Outras verificações úteis:

```bash
curl http://localhost:8000/agents
curl http://localhost:8000/debug/mcp/tools
```

A porta `8000` pertence ao backend do agente e não deve ser confundida com as portas dos MCP Servers ou gateways.

---

## 11. Configuração do agente

Os comportamentos específicos do template são definidos principalmente por arquivos externos ao framework.

### `config/agents.yaml`

Define os agentes disponíveis e seus perfis.

### `config/routing.yaml`

Define intents, rotas e comportamento de roteamento.

### `config/tools.yaml`

Define as tools conhecidas pelo projeto e seus vínculos com MCP.

### `config/tool_policies.yaml`

Define políticas de execução, confirmação, controle e requisitos transacionais das tools.

### `config/guardrails.yaml`

Configura guardrails aplicados pelo projeto.

### `config/judges.yaml`

Configura judges.

### `config/identity.yaml`

Define identidade e business keys.

### `config/mcp_parameter_mapping.yaml`

Define mapeamento e extração de parâmetros destinados às tools MCP.

### `config/mcp_servers.yaml`

Define MCP Servers utilizados em execução local.

### `config/mcp_servers.docker.yaml`

Define endpoints adequados ao ambiente Docker.

### `llm_profiles.yaml`

Define perfis e providers LLM utilizados pelo projeto.

Esse modelo preserva a separação entre:

```text
motor genérico = agent_framework
```

e:

```text
regras do domínio = agent_template_backend/config + app
```

---

## 12. MCP Servers de exemplo

O repositório inclui MCP Servers de desenvolvimento em:

```text
agent_framework_oci/mcp/servers/
├── telecom_mcp_server/
├── retail_mcp_server/
└── mock_telecom_mcp/
```

Os exemplos principais utilizam:

```text
Telecom MCP : 8100
Retail MCP  : 8200
```

A configuração local do template referencia:

```yaml
servers:
  telecom:
    endpoint: http://localhost:8100/mcp

  retail:
    endpoint: http://localhost:8200/mcp
```

Esses MCP Servers são componentes separados do backend do agente.

---

## 13. Inicialização dos MCP Servers no ambiente de desenvolvimento

O repositório fornece:

```text
scripts/run_mcp_servers.sh
```

que inicia os MCP Servers de exemplo.

Arquitetura local:

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

Esse script é uma conveniência de desenvolvimento.

Em produção, a implantação dos MCP Servers deve respeitar a arquitetura produtiva do projeto e não depender de processos iniciados por shell dentro do Pod do backend.

---

## 14. MCP Gateway

O `agent_framework_oci` também contém:

```text
apps/mcp_gateway/
```

e configuração OKE para o MCP Gateway.

A porta padrão apresentada no repositório é:

```text
8300
```

O template possui suporte a:

```env
MCP_GATEWAY_ENABLED=true
MCP_GATEWAY_URL=http://localhost:8300
```

ou, em OKE:

```text
http://mcp-gateway.agent-platform.svc.cluster.local:8300
```

O MCP Gateway é um componente da plataforma e não faz parte fisicamente da pasta `agent_template_backend`.

---

## 15. Agent Gateway, Channel Gateway e Frontend

O repositório também contém:

```text
apps/
├── agent_gateway/
├── channel_gateway/
├── mcp_gateway/
└── agent_frontend/
```

Esses componentes devem ser entendidos como componentes de plataforma ou canais adicionais.

O `agent_template_backend` pode operar diretamente na porta `8000` sem que todos esses componentes sejam obrigatórios para um teste local simples.

Em uma topologia corporativa completa, o fluxo pode ser:

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

A composição concreta deve seguir os requisitos do ambiente de destino.

---

## 16. Frontend de desenvolvimento

O frontend de referência está em:

```text
agent_framework_oci/apps/agent_frontend/
```

e aponta, por padrão, para:

```text
http://localhost:8000
```

O frontend não deve ser movido para dentro do `agent_template_backend` apenas para satisfazer uma estrutura de projeto.

Ele é um componente separado.

Um projeto produtivo poderá:

- utilizar esse frontend;
- utilizar outro frontend;
- integrar Web/WhatsApp/Voice;
- utilizar apenas APIs;
- utilizar Agent Gateway/Channel Gateway.

---

## 17. Dockerfile do template

O Dockerfile existente em:

```text
templates/agent_template_backend/Dockerfile
```

pressupõe um contexto que contenha simultaneamente:

```text
agent_framework/
agent_template_backend/
```

Estrutura:

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

Essa forma está alinhada à especificação arquitetural geral.

---

## 18. Dockerfile OKE existente no repositório

O repositório também fornece:

```text
deploy/oke/dockerfiles/Dockerfile.agent-template-backend
```

Esse Dockerfile é executado com o root de `agent_framework_oci` como contexto e copia:

```text
libs/agent_framework        -> /opt/agent_framework
templates/agent_template_backend -> /app
```

Portanto existem dois contextos válidos, para objetivos diferentes.

### Desenvolvimento/distribuição independente

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

### Build a partir do monorepo

```text
agent_framework_oci/
├── libs/agent_framework/
└── templates/agent_template_backend/
```

Ambos materializam a mesma dependência lógica:

```text
agent_template_backend -> agent_framework
```

---

## 19. Derivação de um projeto produtivo

O `agent_template_backend` deve servir como origem para um novo projeto.

Exemplo:

```text
agent_template_backend
        |
        | derivação
        v
agent_backoffice
```

Após a derivação, a estrutura produtiva recomendada é:

```text
workspace/
├── agent_framework/
└── agent_backoffice/
```

Não é necessário manter o nome:

```text
agent_template_backend
```

em produção.

O projeto derivado passa a ter:

- ciclo de versão próprio;
- Docker image própria;
- configuração própria;
- agentes próprios;
- workflows próprios;
- políticas próprias;
- pipeline próprio.

A biblioteca `agent_framework` permanece compartilhada.

---

## 20. O que deve e o que não deve ser copiado

### Deve ser derivado para o projeto

Conforme a necessidade do domínio:

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

### Não deve ser copiado para dentro do projeto

```text
libs/agent_framework
```

O framework deve continuar sendo distribuído e instalado separadamente.

Também não é necessário copiar automaticamente:

```text
apps/agent_gateway
apps/channel_gateway
apps/mcp_gateway
apps/agent_frontend
mcp/servers
```

Esses componentes devem ser incluídos na solução apenas quando fizerem parte da topologia necessária.

---

## 21. OKE: relação com a arquitetura geral

O repositório contém uma implementação OKE de referência em:

```text
deploy/oke/
```

Incluindo:

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

Essa implementação demonstra como os componentes podem ser materializados no Kubernetes.

Para projetos produtivos, devem ser mantidas as regras da especificação arquitetural geral.

---

## 22. Atenção às configurações demonstrativas do OKE

A configuração de referência presente no repositório utiliza, entre outros valores:

```text
SESSION_REPOSITORY_PROVIDER=sqlite
MEMORY_REPOSITORY_PROVIDER=sqlite
CHECKPOINT_REPOSITORY_PROVIDER=sqlite
USAGE_REPOSITORY_PROVIDER=sqlite
VECTOR_STORE_PROVIDER=sqlite
GRAPH_STORE_PROVIDER=sqlite
```

Esses valores são úteis para demonstração e ambientes controlados.

**Eles não devem ser interpretados como recomendação arquitetural para produção com múltiplas réplicas.**

Em produção, a especificação arquitetural geral prevalece: estados compartilhados que precisem sobreviver entre Pods devem utilizar providers externos apropriados.

---

## 23. Deployment base do `agent_template_backend` no OKE

O exemplo abaixo representa especificamente o backend do template.

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

O dimensionamento deve ser ajustado com base nos testes de carga do projeto real.

---

## 24. ConfigMap base específico do template

Exemplo:

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

Providers de persistência, LLM, memória, cache, observabilidade e RAG devem ser configurados de acordo com o ambiente de produção e com a especificação arquitetural geral.

---

## 25. Topologia OKE completa de referência

Uma instalação completa pode utilizar:

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

Essa é uma topologia de referência, não uma obrigação para todos os projetos.

---

## 26. MCP Servers em OKE

Os MCP Servers devem ser implantados como componentes próprios quando utilizados em produção.

Exemplo conceitual:

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

A mesma abordagem pode ser utilizada para outros MCP Servers.

---

## 27. Health, readiness e startup

O backend deve manter:

```text
GET /health
```

como endpoint mínimo para probes.

Recomenda-se utilizar:

- `startupProbe` para inicialização;
- `readinessProbe` para admissão de tráfego;
- `livenessProbe` para detectar processo não saudável.

Uma aplicação não deve depender apenas de `livenessProbe`.

---

## 28. Estado e escalabilidade

Ao utilizar:

```yaml
replicas: 3
```

não existe garantia de que requisições consecutivas sejam atendidas pelo mesmo Pod.

Portanto, em produção:

```text
session
checkpoint
memory
idempotency
transaction state
cache compartilhado
```

devem ser analisados quanto à necessidade de externalização.

Um banco SQLite armazenado em:

```text
/data
```

dentro de `emptyDir` é local ao Pod e não representa armazenamento compartilhado.

---

## 29. Configuração de MCP local versus container

O template separa:

```text
config/mcp_servers.yaml
```

e:

```text
config/mcp_servers.docker.yaml
```

Isso é intencional.

Local:

```yaml
endpoint: http://localhost:8100/mcp
```

Docker/Kubernetes:

```yaml
endpoint: http://telecom-mcp:8100/mcp
```

O endpoint deve refletir o DNS visível a partir do processo do backend.

---

## 30. `.env.example`

O arquivo:

```text
templates/agent_template_backend/.env.example
```

é uma referência de configuração.

Ele não deve ser utilizado como mecanismo para armazenar credenciais reais no repositório.

Em produção:

- configurações não sensíveis podem vir de ConfigMap;
- secrets devem vir de Kubernetes Secret, OCI Vault ou solução corporativa equivalente;
- credenciais não devem ser commitadas.

---

## 31. Uso do template em novos projetos

Fluxo recomendado:

```text
agent_framework_oci
        |
        +--> libs/agent_framework
        |
        +--> templates/agent_template_backend
                          |
                          v
                novo projeto de agente
```

Passos:

1. selecionar a versão do `agent_framework`;
2. derivar o `agent_template_backend`;
3. renomear o projeto;
4. ajustar `agents.yaml`;
5. ajustar `routing.yaml`;
6. ajustar tools e tool policies;
7. criar/ajustar workflows;
8. configurar identidade;
9. configurar MCP;
10. configurar guardrails e judges;
11. configurar persistência e memória;
12. testar localmente;
13. executar regressão;
14. gerar imagem;
15. implantar em ambiente de homologação;
16. promover para produção conforme pipeline corporativo.

---

## 32. O template não deve criar fork do framework

Alterações genéricas e reutilizáveis devem ser avaliadas para implementação em:

```text
libs/agent_framework
```

Alterações específicas de domínio devem permanecer no projeto derivado.

Exemplo:

```text
"nova regra específica de cobrança"
          -> projeto do agente

"novo mecanismo genérico de pause/resume"
          -> agent_framework
```

Esse princípio reduz divergência entre projetos.

---

## 33. Compatibilidade de versões

Um projeto derivado deve registrar:

```text
AGENT_APPLICATION_VERSION
AGENT_FRAMEWORK_VERSION
GIT_COMMIT
BUILD_ID
```

Exemplo:

```text
agent-backoffice: 3.2.0
agent-framework: 1.8.0
```

A atualização do framework deve acionar os testes de regressão do projeto.

---

## 34. Papel da pasta `Tuning-Performance`

O repositório possui cenários e variantes em:

```text
Tuning-Performance/
```

Esses materiais servem como referência para features, cenários de tuning, regressão e exemplos de implementação.

Eles não alteram a estrutura arquitetural básica:

```text
agent project -> agent_framework
```

Um projeto produtivo deve incorporar apenas as configurações ou implementações necessárias e validadas para seu caso.

---

## 35. Papel da documentação interna do template

A pasta:

```text
templates/agent_template_backend/docs/
```

contém documentação detalhada sobre funcionalidades específicas do template, incluindo temas como:

- memória;
- observabilidade;
- guardrails;
- IC/NOC/GRL;
- transações;
- routing;
- channel input;
- output supervisor.

Este documento não substitui esses manuais funcionais.

Ele define o **modelo de utilização, distribuição e deployment do template**.

---

## 36. Requisitos obrigatórios para uso correto

1. O template deve consumir `agent_framework` por import Python.

2. O framework deve continuar em:

```text
agent_framework_oci/libs/agent_framework
```

como origem no monorepo.

3. O template deve continuar em:

```text
agent_framework_oci/templates/agent_template_backend
```

como origem no monorepo.

4. Em uma distribuição independente, ambos devem ser materializados no mesmo nível:

```text
workspace/
├── agent_framework/
└── agent_template_backend/
```

5. Um projeto produtivo derivado deve respeitar a especificação arquitetural geral.

6. O framework não deve ser duplicado dentro do projeto.

7. MCP Servers não devem ser confundidos com o backend.

8. O MCP Gateway não faz parte da pasta do template.

9. O frontend não faz parte da pasta do template.

10. Configurações SQLite existentes nos exemplos não devem ser consideradas padrão produtivo para ambientes multi-Pod.

11. O backend deve expor health check.

12. Secrets reais não devem ser armazenados em `.env.example` ou manifestos versionados.

13. A versão do framework utilizada pelo projeto deve ser rastreável.

14. Mudanças genéricas devem preferencialmente ser implementadas no framework, evitando forks por projeto.

---

## 37. Estrutura de referência final

### Dentro do produto `agent_framework_oci`

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

### Projeto derivado para produção

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

## 38. Regra final

O `agent_template_backend` é uma **implementação de referência do padrão**, não o próprio framework.

A relação correta é:

```text
agent_framework
      ^
      |
agent_template_backend
      |
      v
projetos derivados
```

Para desenvolvimento dentro do monorepo, os caminhos originais em `libs/` e `templates/` podem ser utilizados.

Para distribuição e produção, os projetos derivados devem seguir a **Especificação Geral de Utilização do `agent_framework_oci`**, mantendo o projeto de agente e o `agent_framework` como componentes separados e versionáveis.

