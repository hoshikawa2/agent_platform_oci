# Deployment do Agent Platform OCI em OCI OKE

Este pacote adiciona os artefatos necessários para publicar o `agent_platform_oci` em um cluster **OCI OKE / Kubernetes**.

O objetivo é atender a três pontos principais:

1. Publicar o `agent_framework` como biblioteca dentro das imagens Python, permitindo imports como:

   ```python
   from agent_framework import ...
   ```

2. Implantar o `agent_template_backend` com múltiplos pods, `Service` interno e `HorizontalPodAutoscaler`, permitindo escalabilidade horizontal.

3. Implantar os componentes externos da plataforma:

   - `agent_gateway`
   - `channel_gateway`
   - `mcp_gateway`
   - `agent_frontend`

O desenho recomendado em OKE é:

```text
Usuário / Canal
   |
   | HTTP/S
   v
OCI Load Balancer
   |
   +--> agent_frontend        Serviço LoadBalancer
   +--> agent_gateway         Serviço LoadBalancer
   +--> channel_gateway       Serviço LoadBalancer
   +--> mcp_gateway           Serviço LoadBalancer

Dentro do cluster:

agent_gateway  ---> agent_template_backend Service ---> vários pods do agente
agent_backend  ---> mcp_gateway Service
mcp_gateway    ---> MCP servers internos ou externos
```

> Observação: este pacote deixa os gateways como serviços externos `LoadBalancer`, conforme solicitado. Em produção, é comum expor apenas o `channel_gateway`, `agent_gateway` ou um Ingress/API Gateway corporativo, mantendo `mcp_gateway` interno.

---

## Estrutura criada

```text
deploy/oke/
  README_OKE_DEPLOYMENT.md
  .dockerignore
  dockerfiles/
    Dockerfile.agent-template-backend
    Dockerfile.agent-gateway
    Dockerfile.channel-gateway
    Dockerfile.mcp-gateway
    Dockerfile.agent-frontend
  nginx/
    default.conf
  k8s/base/
    00-namespace.yaml
    01-configmap.yaml
    02-secret-template.yaml
    03-agent-template-backend.yaml
    04-agent-gateway.yaml
    05-channel-gateway.yaml
    06-mcp-gateway.yaml
    07-frontend.yaml
    kustomization.yaml
  scripts/
    build_images.sh
    push_images.sh
    create_runtime_secret.sh
    deploy_oke.sh
    status.sh
  examples/
    oke.env.example
```

---

## Por que foram criados novos Dockerfiles

Os Dockerfiles existentes usam caminhos relativos ao diretório da aplicação, por exemplo:

```dockerfile
COPY agent_framework /agent_framework
COPY agent_template_backend /app
```

No repositório atual, o framework está em:

```text
libs/agent_framework
```

E o backend está em:

```text
templates/agent_template_backend
```

Por isso, os Dockerfiles de OKE usam a **raiz do repositório como build context** e fazem:

```dockerfile
COPY libs/agent_framework /opt/agent_framework
RUN pip install -e /opt/agent_framework
```

Assim, o `agent_framework` fica instalado como biblioteca Python dentro das imagens dos componentes que precisam dele.

---

## Pré-requisitos

Na máquina de build/deploy:

- Docker
- `kubectl`
- OCI CLI configurado
- Acesso ao cluster OKE
- Acesso ao OCIR
- Usuário OCI com permissões para push no OCIR
- Token de autenticação OCI para login no Docker Registry

Login no OCIR:

```bash
docker login <region-key>.ocir.io
```

Exemplo para São Paulo:

```bash
docker login gru.ocir.io
```

O usuário normalmente segue o formato:

```text
<tenancy-namespace>/<user>
```

---

## 1. Configurar o arquivo de ambiente

Copie o exemplo:

```bash
cp deploy/oke/examples/oke.env.example deploy/oke/oke.env
```

Edite:

```bash
vi deploy/oke/oke.env
```

Campos principais:

```bash
OCI_REGION=sa-saopaulo-1
OCI_REGION_KEY=gru
OCI_TENANCY_NAMESPACE=your_tenancy_namespace
OCIR_REPOSITORY_PREFIX=agent-platform-oci
IMAGE_TAG=1.0.0
K8S_NAMESPACE=agent-platform
OKE_CLUSTER_OCID=ocid1.cluster.oc1..example
```

Para usar OCI Generative AI em vez de mock:

```bash
LLM_PROVIDER=oci_openai
OCI_GENAI_BASE_URL=https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1
OCI_GENAI_MODEL=<modelo>
OCI_GENAI_API_KEY=<api-key>
OCI_COMPARTMENT_ID=<compartment-ocid>
```

Para primeiro teste sem custo de LLM, deixe:

```bash
LLM_PROVIDER=mock
```

---

## 2. Build das imagens

Execute a partir da raiz do projeto:

```bash
./deploy/oke/scripts/build_images.sh deploy/oke/oke.env
```

Imagens geradas:

```text
agent-template-backend
agent-gateway
channel-gateway
mcp-gateway
agent-frontend
```

Todas serão tagueadas no padrão:

```text
<region-key>.ocir.io/<tenancy-namespace>/<prefix>/<image>:<tag>
```

Exemplo:

```text
gru.ocir.io/mytenancy/agent-platform-oci/agent-template-backend:1.0.0
```

---

## 3. Push para OCIR

```bash
./deploy/oke/scripts/push_images.sh deploy/oke/oke.env
```

---

## 4. Criar secrets de runtime

O script abaixo cria ou atualiza o secret `agent-platform-secrets` no namespace configurado:

```bash
./deploy/oke/scripts/create_runtime_secret.sh deploy/oke/oke.env
```

O arquivo `02-secret-template.yaml` existe apenas como referência. Não coloque credenciais reais no Git.

---

## 5. Fazer deploy no OKE

```bash
./deploy/oke/scripts/deploy_oke.sh deploy/oke/oke.env
```

O script:

1. Opcionalmente atualiza o kubeconfig via OCI CLI, se `OKE_CLUSTER_OCID` estiver preenchido.
2. Cria/atualiza o namespace.
3. Cria/atualiza os secrets.
4. Aplica os manifests com Kustomize.
5. Aguarda o rollout dos deployments.
6. Lista os serviços e IPs externos.

---

## 6. Verificar status

```bash
./deploy/oke/scripts/status.sh
```

Ou manualmente:

```bash
kubectl -n agent-platform get pods -o wide
kubectl -n agent-platform get svc
kubectl -n agent-platform get hpa
```

Quando o Load Balancer estiver provisionado, os serviços externos aparecerão com `EXTERNAL-IP`:

```bash
kubectl -n agent-platform get svc agent-gateway
kubectl -n agent-platform get svc channel-gateway
kubectl -n agent-platform get svc mcp-gateway
kubectl -n agent-platform get svc agent-frontend
```

---

## 7. Testes rápidos

Health do backend interno:

```bash
kubectl -n agent-platform port-forward svc/agent-template-backend 8000:8000
curl http://localhost:8000/health
```

Health do Agent Gateway:

```bash
kubectl -n agent-platform port-forward svc/agent-gateway 8010:8010
curl http://localhost:8010/health
```

Envio de mensagem pelo Agent Gateway:

```bash
curl -X POST http://localhost:8010/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "web",
    "tenant_id": "default",
    "payload": {
      "message": "quero consultar minha fatura",
      "metadata": {
        "customer_key": "11999999999"
      }
    }
  }'
```

---

## Escalabilidade

O `agent_template_backend` foi configurado com:

```yaml
replicas: 3
```

E com HPA:

```yaml
minReplicas: 3
maxReplicas: 10
averageUtilization: 70
```

Ajuste em:

```text
deploy/oke/k8s/base/03-agent-template-backend.yaml
```

O Load Balancer externo fica nos gateways e no frontend. O backend do agente é `ClusterIP`, porque o acesso deve ocorrer via gateway.

---

## Sobre estado, sessão e persistência

O manifesto usa `emptyDir` para `/data`, suficiente para smoke test e validação inicial.

Para produção, substitua SQLite por um provider externo:

- Autonomous Database
- MongoDB
- Redis para cache distribuído
- Object Storage ou banco para artefatos persistentes

Não use SQLite local com múltiplos pods em produção para sessão, memória, checkpoints e usage, porque cada pod teria seu próprio estado.

Configurações relevantes no `ConfigMap`:

```yaml
SESSION_REPOSITORY_PROVIDER: "sqlite"
MEMORY_REPOSITORY_PROVIDER: "sqlite"
CHECKPOINT_REPOSITORY_PROVIDER: "sqlite"
USAGE_REPOSITORY_PROVIDER: "sqlite"
```

Para produção, altere esses providers e injete as credenciais por `Secret`.

---

## Ajuste do Agent Gateway para vários agentes

O arquivo:

```text
deploy/oke/k8s/base/01-configmap.yaml
```

cria o `ConfigMap` `agent-gateway-backends` com:

```yaml
backends:
  contas:
    url: http://agent-template-backend.agent-platform.svc.cluster.local:8000
```

Para adicionar novos agentes, crie novos deployments e serviços, depois adicione novas entradas:

```yaml
backends:
  contas:
    url: http://agent-contas.agent-platform.svc.cluster.local:8000
  ofertas:
    url: http://agent-ofertas.agent-platform.svc.cluster.local:8000
  suporte:
    url: http://agent-suporte.agent-platform.svc.cluster.local:8000
```

---

## Ajuste do MCP Gateway

O `mcp_gateway` é implantado com configuração vazia por padrão:

```yaml
servers: {}
tools: {}
```

Edite o `ConfigMap` `mcp-gateway-config` em:

```text
deploy/oke/k8s/base/01-configmap.yaml
```

Exemplo:

```yaml
servers:
  telecom:
    enabled: true
    discover: true
    protocol: legacy_http
    transport: http
    url: http://telecom-mcp.agent-platform.svc.cluster.local:8100/mcp
    timeout_seconds: 30
```

---

## Frontend

O frontend foi empacotado em Nginx e exposto com `Service LoadBalancer`.

Como o frontend atual é estático, o endereço do gateway pode ser informado na própria interface, caso ela já tenha campo de backend/gateway. Caso você queira fixar o endpoint em build/runtime, o próximo ajuste recomendado é adicionar um arquivo `/config.js` gerado por `ConfigMap` com a URL pública do `agent_gateway`.

---

## Segurança recomendada para produção

Para produção, recomenda-se:

1. Usar `ClusterIP` para `mcp_gateway` e expor apenas via rede privada.
2. Usar OCI API Gateway ou Ingress Controller com TLS.
3. Criar `NetworkPolicy` restringindo tráfego entre namespaces.
4. Usar OCI Vault/External Secrets para credenciais.
5. Usar Workload Identity ou Instance Principal quando aplicável.
6. Usar Autonomous Database ou MongoDB externo para estado.
7. Configurar observabilidade com OTel/Langfuse.
8. Separar namespaces por ambiente: `dev`, `test`, `prod`.
9. Não versionar `.env` nem secrets reais.

---

## Comandos principais

```bash
cp deploy/oke/examples/oke.env.example deploy/oke/oke.env
vi deploy/oke/oke.env

./deploy/oke/scripts/build_images.sh deploy/oke/oke.env
./deploy/oke/scripts/push_images.sh deploy/oke/oke.env
./deploy/oke/scripts/deploy_oke.sh deploy/oke/oke.env
./deploy/oke/scripts/status.sh
```

---

## Próximos passos recomendados

1. Criar manifests separados por ambiente com overlays Kustomize: `dev`, `hml`, `prod`.
2. Criar pipeline OCI DevOps ou GitHub Actions para build/push/deploy.
3. Adicionar Ingress/API Gateway com TLS.
4. Migrar estado de SQLite para Autonomous/MongoDB antes de produção.
5. Criar manifests específicos para cada agente real derivado do `agent_template_backend`.
