# Validação arquitetural de carga — Agent Framework OCI / OKE

Este pacote executa validação arquitetural e teste de carga do `agent_template_backend` em OCI OKE usando **persistência compartilhada**, **OCI Generative AI**, **Langfuse v3** e um **OCI Load Balancer preexistente**. O pacote não cria um novo OCI Load Balancer: o acesso externo é feito por `NodePort` nos workers e por um listener/backend set criado no LB informado em `EXISTING_LB_OCID`.

## Arquitetura do teste

```text
Cliente / k6 externo
        |
        v
OCI Load Balancer existente :BACKEND_LISTENER_PORT
        |
        v
backend set agent-framework-loadtest
        |
        +--> worker-1:BACKEND_NODE_PORT
        +--> worker-2:BACKEND_NODE_PORT
        +--> worker-N:BACKEND_NODE_PORT
        |
        v
Kubernetes Service NodePort
        |
        v
agent-template-backend (HPA)
        |
        +--> Autonomous Database / wallet
        +--> Mongo-compatible endpoint
        +--> OCI Generative AI
        +--> Langfuse v3
```

O Service `agent-template-backend` continua `ClusterIP` para testes internos. O Service `agent-template-backend-lb` é `NodePort`; ele **não** solicita um novo LB à OCI.

## Estrutura principal

```text
deploy/oke/load-test/
  .env.loadtest.example
  .env.runtime                 # gerado; não commitar
  .env.langfuse                # gerado; não commitar
  README.md
  k8s/
    agent-backend.yaml
    k6-job.yaml
  langfuse/
    langfuse-k8s.yaml
  loadgen/
    loadtest.js
  scripts/
    prepare_env.sh
    configure_kubeconfig.sh
    deploy_langfuse.sh
    sync_langfuse_client_secret.sh
    validate_langfuse_integration.sh
    build_push_backend.sh
    deploy_backend.sh
    configure_existing_lb.sh
    validate_dependencies.sh
    smoke_test.sh
    run_load_test.sh
    run_architecture_suite.sh
    watch_test.sh
    collect_results.sh
```

---

# 1. Preparar `.env.runtime`

Execute da raiz do repositório:

```bash
./deploy/oke/load-test/scripts/prepare_env.sh
```

O script usa `templates/agent_template_backend/.env` como configuração principal, completa somente as chaves ausentes com `deploy/oke/load-test/.env.loadtest.example` e gera:

```text
deploy/oke/load-test/.env.runtime
deploy/oke/load-test/.env.langfuse
```

> **Importante sobre Langfuse:** o script pode gerar valores de inicialização (`LANGFUSE_INIT_*`) para bootstrap headless, mas, para esta validação, o procedimento recomendado é confirmar o ambiente pela UI do Langfuse e criar manualmente o usuário, organização/empresa, projeto e API keys. As chaves criadas na UI devem ser copiadas para os arquivos de configuração antes do deploy do backend.

Preencha no `.env.runtime` os parâmetros reais de OCI/DB/OCIR e o LB existente. Para o LB:

```bash
EXISTING_LB_OCID=ocid1.loadbalancer.oc1.sa-saopaulo-1....
BACKEND_SET_NAME=agent-framework-loadtest
BACKEND_LISTENER_NAME=agent-framework-loadtest
BACKEND_LISTENER_PORT=8000
BACKEND_LISTENER_PROTOCOL=HTTP
BACKEND_HEALTH_PATH=/health
BACKEND_NODE_PORT=32116
LOADTEST_TARGET_MODE=external
```

Opcionalmente, fixe diretamente a URL externa:

```bash
LOADTEST_EXTERNAL_URL=http://<IP_DO_LB>:8000
```

---

# 2. Wallet e acesso ao OKE

Copie a wallet real para:

```text
templates/agent_template_backend/wallet/
```

Ela será criada como Kubernetes Secret e montada em `/app/wallet`.

Configure kubeconfig:

```bash
./deploy/oke/load-test/scripts/configure_kubeconfig.sh
kubectl get nodes -o wide
kubectl top nodes
```

`kubectl top nodes` deve funcionar para o HPA baseado em CPU/memória.

---

# 3. Subir o Langfuse v3 e criar manualmente usuário, organização, projeto e API keys

## 3.1 Subir a infraestrutura do Langfuse

Execute:

```bash
./deploy/oke/load-test/scripts/deploy_langfuse.sh
```

O deploy cria os componentes Kubernetes do Langfuse v3, incluindo web, worker, Postgres, Redis, ClickHouse, MinIO e os Secrets de runtime.

Se a etapa de validação autenticada falhar porque ainda não existem API keys válidas, prossiga com a inicialização manual abaixo. A infraestrutura do Langfuse já pode estar operacional mesmo que a validação das chaves ainda não tenha passado.

Confirme:

```bash
kubectl -n langfuse get pods
kubectl -n langfuse get svc langfuse-web
```

Os pods principais devem estar `Running`/`Ready`.

## 3.2 Abrir a interface do Langfuse

Abra um port-forward em outro terminal:

```bash
kubectl -n langfuse port-forward --address 127.0.0.1 svc/langfuse-web 3005:3000
```

Acesse no navegador:

```text
http://127.0.0.1:3005
```

## 3.3 Criar o usuário

Na primeira abertura do Langfuse:

1. crie o usuário administrador;
2. faça login com esse usuário;
3. confirme que a interface principal do Langfuse foi carregada.

Para ambiente de teste, pode ser utilizado um usuário dedicado ao load test. Não use credenciais pessoais de produção no arquivo do projeto.

## 3.4 Criar a organização/empresa

Dentro do Langfuse, crie ou selecione a organização que será usada pelo teste.

Sugestão de nome:

```text
Agent Framework OCI
```

A UI do Langfuse pode usar o termo **Organization**. Neste manual, organização/empresa representam a mesma entidade de agrupamento do projeto.

## 3.5 Criar o projeto

Dentro dessa organização, crie o projeto que receberá os traces do teste.

Sugestão:

```text
Agent Framework Load Test
```

Não prossiga para o backend enquanto não conseguir abrir esse projeto na UI.

## 3.6 Criar as API keys do projeto

No projeto criado, abra a área de configuração/API Keys e crie um novo par de credenciais.

Você receberá duas chaves:

```text
Public Key: pk-lf-...
Secret Key: sk-lf-...
```

> **Atenção:** copie a `Secret Key` no momento da criação. Dependendo da tela/versão, ela pode não ser exibida novamente.

Essas são as credenciais que o `agent_template_backend` usará para enviar traces ao Langfuse.

## 3.7 Copiar as API keys para `.env.langfuse`

Edite:

```text
deploy/oke/load-test/.env.langfuse
```

Substitua/ajuste estas quatro linhas com o par criado na UI:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-COLE_A_PUBLIC_KEY_AQUI
LANGFUSE_SECRET_KEY=sk-lf-COLE_A_SECRET_KEY_AQUI
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-COLE_A_MESMA_PUBLIC_KEY_AQUI
LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-COLE_A_MESMA_SECRET_KEY_AQUI
```

Para um projeto já criado manualmente na UI, os campos `LANGFUSE_INIT_PROJECT_*` são mantidos com os mesmos valores para que os scripts de sincronização do pacote encontrem um único par de chaves consistente.

Não exiba nem versione a `LANGFUSE_SECRET_KEY`.

## 3.8 Copiar as API keys para `.env.runtime`

Edite também:

```text
deploy/oke/load-test/.env.runtime
```

Garanta:

```bash
ENABLE_LANGFUSE=true
LANGFUSE_HOST=http://langfuse-web.langfuse.svc.cluster.local:3000
LANGFUSE_PUBLIC_KEY=pk-lf-COLE_A_PUBLIC_KEY_AQUI
LANGFUSE_SECRET_KEY=sk-lf-COLE_A_SECRET_KEY_AQUI
```

As chaves em `.env.runtime` devem ser exatamente as mesmas criadas no projeto pela UI.

## 3.9 Atualizar o Secret Kubernetes do Langfuse

Depois de colar as chaves nos arquivos, atualize `Secret/langfuse-runtime` sem imprimir os valores:

```bash
set -a
source deploy/oke/load-test/.env.langfuse
set +a

kubectl -n langfuse create secret generic langfuse-runtime \
  --from-env-file=deploy/oke/load-test/.env.langfuse \
  --dry-run=client -o yaml | kubectl apply -f -
```

Para um projeto criado manualmente, não é necessário recriar o banco do Langfuse. O objetivo desta etapa é manter o Secret usado pelos scripts sincronizado com as credenciais reais do projeto.

## 3.10 Sincronizar as chaves para o namespace do backend

Execute:

```bash
LANGFUSE_NAMESPACE=langfuse \
K8S_NAMESPACE=agent-load-test \
./deploy/oke/load-test/scripts/sync_langfuse_client_secret.sh
```

O script cria/atualiza:

```text
namespace: agent-load-test
Secret: langfuse-client
```

com:

```text
LANGFUSE_PUBLIC_KEY
LANGFUSE_SECRET_KEY
LANGFUSE_HOST
```

Confira apenas a existência do Secret:

```bash
kubectl -n agent-load-test get secret langfuse-client
```

Para conferir somente a Public Key:

```bash
kubectl -n agent-load-test get secret langfuse-client \
  -o jsonpath='{.data.LANGFUSE_PUBLIC_KEY}' | base64 -d

echo
```

Ela deve começar com:

```text
pk-lf-
```

## 3.11 Validar autenticação no Langfuse antes de prosseguir

Execute:

```bash
./deploy/oke/load-test/scripts/validate_langfuse_integration.sh
```

Resultado esperado:

```text
LANGFUSE_AUTH_OK
```

Esse teste chama o Langfuse pela rede interna do OKE e usa `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`. Portanto, `LANGFUSE_AUTH_OK` comprova que o par de chaves é aceito pelo projeto.

Se receber `401`/`403`, não prossiga para o backend. Revise:

```text
.env.langfuse
.env.runtime
Secret/langfuse-runtime no namespace langfuse
Secret/langfuse-client no namespace agent-load-test
```

## 3.12 Ordem obrigatória antes de continuar

A sequência esperada é:

```text
Langfuse Kubernetes operacional
        ↓
criar usuário
        ↓
criar/selecionar organização (empresa)
        ↓
criar projeto
        ↓
criar Public Key + Secret Key
        ↓
colar keys em .env.langfuse
        ↓
colar keys em .env.runtime
        ↓
atualizar Secret/langfuse-runtime
        ↓
sync_langfuse_client_secret.sh
        ↓
validate_langfuse_integration.sh
        ↓
LANGFUSE_AUTH_OK
        ↓
somente então fazer deploy do backend
```

---

# 4. Build e push do backend

Garanta que o repositório OCIR já exista e faça login:

```bash
docker login gru.ocir.io
./deploy/oke/load-test/scripts/build_push_backend.sh
```

A imagem utilizada fica registrada em `deploy/oke/load-test/.backend-image`.

---

# 5. Deploy do backend com NodePort

Execute:

```bash
./deploy/oke/load-test/scripts/deploy_backend.sh
```

O deploy cria/atualiza:

- `agent-backend-runtime`;
- `agent-backend-wallet`;
- `langfuse-client`;
- Deployment do backend;
- `ClusterIP` interno;
- `NodePort` externo (`BACKEND_NODE_PORT`, default `32116`);
- HPA;
- PDB.

Confira:

```bash
kubectl -n agent-load-test get pods -o wide
kubectl -n agent-load-test get svc
kubectl -n agent-load-test get hpa
```

O Service externo deve aparecer como `NodePort`, e não `LoadBalancer`.

---

# 6. Reutilizar o OCI Load Balancer existente

Depois que o NodePort existir:

```bash
./deploy/oke/load-test/scripts/configure_existing_lb.sh
```

O script é idempotente. Ele:

1. valida `EXISTING_LB_OCID`;
2. descobre `BACKEND_NODE_PORT` no Service;
3. verifica o backend set;
4. cria `BACKEND_SET_NAME` se não existir;
5. aguarda a operação OCI concluir;
6. descobre os `InternalIP` dos workers OKE;
7. adiciona os workers ainda não cadastrados como `<worker-ip>:<node-port>`;
8. verifica/cria o listener `BACKEND_LISTENER_NAME`;
9. aponta o listener para o backend set;
10. mostra o health do backend set.

Arquitetura resultante:

```text
OCI LB existente
   -> listener :8000
   -> backend set
   -> worker InternalIP:32116
   -> Service NodePort
   -> pods do backend
```

As Security Lists/NSGs precisam permitir tráfego do LB para os workers na porta NodePort.

---

# 7. Validar dependências antes do smoke/carga

Execute:

```bash
./deploy/oke/load-test/scripts/validate_dependencies.sh
```

Esse teste é executado **de dentro do OKE** usando a mesma imagem, env e wallet do backend. Ele valida:

- conexão real com Oracle/Autonomous usando `/app/wallet`;
- `ping` real no Mongo-compatible endpoint;
- `/api/public/health` do Langfuse;
- presença das API keys Langfuse;
- autenticação real em `/api/public/projects` usando `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`.

Resultado esperado termina com:

```text
dependencies: ALL_DEPENDENCIES_OK
```

Esse passo valida conectividade e autenticação. Ele não faz uma chamada de negócio ao LLM; isso é responsabilidade do smoke test.

---

# 8. Smoke test end-to-end

## Externo — caminho real pelo OCI LB existente

```bash
./deploy/oke/load-test/scripts/smoke_test.sh external
```

Caminho validado:

```text
cliente
 -> OCI LB existente
 -> listener
 -> backend set
 -> NodePort
 -> pod
 -> LangGraph/framework
 -> RAG/memória conforme configuração
 -> OCI Generative AI (quando LLM_PROVIDER=oci_sdk)
 -> persistência
 -> Langfuse
```

O smoke executa `/health`, depois `POST /gateway/message`. Quando Langfuse está habilitado, ele também consulta a Public API autenticada e aguarda o trace da sessão `smoke-*`. O sucesso final inclui:

```text
LANGFUSE_TRACE_OK
```

Assim, um `HTTP 200` sozinho não é mais considerado evidência suficiente de observabilidade.

## Interno — sem OCI LB

```bash
./deploy/oke/load-test/scripts/smoke_test.sh internal
```

Esse modo usa o `ClusterIP` e serve para separar problemas do backend/Kubernetes de problemas do LB externo.

Para provar chamadas reais de OCI Generative AI, mantenha:

```text
LLM_PROVIDER=oci_sdk
OCI_AUTH_MODE=oke_workload_identity
```

Nos logs devem aparecer `OCI SDK GenAI client`, `OnDemandServingMode` e eventos `llm.*` com o modelo configurado.

---

# 9. Teste de carga

## Interno

```bash
./deploy/oke/load-test/scripts/run_load_test.sh internal
```

Alvo:

```text
http://agent-template-backend.agent-load-test.svc.cluster.local:8000
```

## Externo pelo LB preexistente

```bash
./deploy/oke/load-test/scripts/run_load_test.sh external
```

O script resolve o endereço do LB usando `EXISTING_LB_OCID` via OCI CLI, ou usa `LOADTEST_EXTERNAL_URL` se definida.

Acompanhe:

```bash
kubectl -n agent-load-test logs -f job/agent-load-generator
./deploy/oke/load-test/scripts/watch_test.sh
```

Distribuição pelo LB:

```bash
./deploy/oke/load-test/scripts/check_load_balancing.sh
```

---

# 10. Suite arquitetural

Externa:

```bash
./deploy/oke/load-test/scripts/run_architecture_suite.sh external
```

Interna:

```bash
./deploy/oke/load-test/scripts/run_architecture_suite.sh internal
```

Cenários padrão:

```text
warmup         5 rps   2 min  unique_sessions
baseline      25 rps   5 min  unique_sessions
scale        100 rps  10 min  unique_sessions
shared-state  50 rps  10 min  shared_sessions
```

`unique_sessions` estressa criação de estado/checkpoints/DB/Langfuse/LLM. `shared_sessions` reutiliza sessões entre chamadas e é importante para provar que a aplicação não depende de memória local do pod.

---

# 11. Execução completa automatizada

Depois de preencher `.env.runtime` e colocar a wallet:

```bash
./deploy/oke/load-test/scripts/01_deploy_all.sh
```

Ordem:

```text
Langfuse + API keys
 -> build/push backend
 -> deploy backend NodePort
 -> configurar LB existente
 -> validar dependências
 -> smoke externo + confirmação do trace Langfuse
```

Só depois desse fluxo passar execute carga sustentada.

---

# 12. Critérios de aprovação

Antes da carga:

```text
kubectl nodes Ready
metrics-server OK
Langfuse AUTH OK
Oracle connection OK
Mongo ping OK
backend rollout OK
OCI LB backend-set healthy
smoke HTTP 200
OCI GenAI real nos logs (perfil end-to-end)
LANGFUSE_TRACE_OK
```

Durante a carga, procure:

- nenhum `CrashLoopBackOff`/`OOMKilled`;
- ausência de deadlock/cross-event-loop errors;
- sessão consistente entre pods;
- checkpoints recuperáveis por qualquer réplica;
- HPA escalando quando as métricas atingirem os targets;
- 5xx próximos de zero;
- 429/timeouts do LLM separados de erros internos;
- traces chegando ao Langfuse sem criar falha em cascata.

O backend é I/O-bound em chamadas de LLM/DB; CPU/memória não são métricas perfeitas de autoscaling. Para produção, considere métricas de aplicação como `in_flight_requests`, `request_queue_depth` e p95 de latência via KEDA/Prometheus Adapter.

---

# 13. Coletar evidências

```bash
./deploy/oke/load-test/scripts/collect_results.sh
```

Os arquivos ficam em `deploy/oke/load-test/results/`. Use em conjunto com Langfuse para correlacionar request/session/trace.

---

# 14. Resiliência

Com carga ativa:

```bash
kubectl -n agent-load-test delete pod <pod>
kubectl -n agent-load-test rollout restart deployment/agent-template-backend
kubectl -n agent-load-test rollout status deployment/agent-template-backend
```

A perda de uma réplica não deve perder estado compartilhado nem interromper o serviço enquanto houver capacidade saudável.

---

# 15. Troubleshooting de credenciais Langfuse em instalação já existente

O bootstrap headless é idempotente e foi desenhado para criar recursos que ainda não existem. Em um ambiente de teste que já possua PVCs do Langfuse inicializados anteriormente com outro projeto ou outro par de API keys, `validate_langfuse_integration.sh` pode retornar erro de autenticação mesmo que `/api/public/health` esteja `200`.

Primeiro confirme sem revelar a secret key:

```bash
kubectl -n langfuse get secret langfuse-runtime \
  -o jsonpath='{.data.LANGFUSE_INIT_PROJECT_PUBLIC_KEY}' | base64 -d; echo

kubectl -n agent-load-test get secret langfuse-client \
  -o jsonpath='{.data.LANGFUSE_PUBLIC_KEY}' | base64 -d; echo
```

As public keys precisam ser iguais. Depois execute:

```bash
./deploy/oke/load-test/scripts/validate_langfuse_integration.sh
```

Se as keys estiverem sincronizadas no Kubernetes mas a API autenticada falhar, o banco persistente do Langfuse provavelmente já contém credenciais diferentes. Para um ambiente descartável de load test, a opção mais limpa é recriar a stack/PVCs do Langfuse e executar `deploy_langfuse.sh` novamente. Não apague PVCs de um Langfuse que contenha dados que precisem ser preservados.

Depois de qualquer alteração de keys, execute novamente:

```bash
./deploy/oke/load-test/scripts/deploy_backend.sh
```

O checksum de runtime força a criação de pods novos, garantindo que as novas credenciais entrem no environment do processo Python.


## Precedência das variáveis de ambiente

`prepare_env.sh` usa o `.env` real do backend como fonte principal. A ordem é:

```text
templates/agent_template_backend/.env   (fonte principal)
        ↓
.env.loadtest.example                  (somente defaults ausentes)
        ↓
.env.loadtest                          (override explícito opcional)
        ↓
overrides obrigatórios OKE/container   (wallet e Langfuse interno)
        ↓
.env.runtime
```

Portanto, `ENABLE_MCP_TOOLS`, `ENABLE_ANALYTICS`, endpoints, banco, modelos e demais configurações do agente são preservados por padrão. Para substituir deliberadamente alguma delas no teste, copie `.env.loadtest.override.example` para `.env.loadtest` e altere somente as chaves desejadas.

Depois de executar:

```bash
./deploy/oke/load-test/scripts/prepare_env.sh
```

o script informa quantas variáveis do `.env` do backend foram preservadas e lista apenas as que precisaram mudar por compatibilidade com OKE/container.
