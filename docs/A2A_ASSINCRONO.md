# Agentes do framework com A2A assíncrono

## O que foi implementado

O agente criado a partir de `templates/agent_template_backend` pode expor o
protocolo nativo e A2A no mesmo processo. O Agent Gateway também oferece a
mesma fachada A2A. As duas fachadas usam o SDK oficial e suas operações de
Tasks/SSE, com interoperabilidade A2A 1.0 e 0.3.

```text
Consumidor A2A ── Gateway A2A (Task)
                    ├── agente nativo (/gateway/message)
                    └── agente framework A2A (Task remota)

Consumidor A2A ── agente framework A2A diretamente
```

O envio imediato devolve uma Task antes de terminar a operação de negócio.
A execução continua após a resposta HTTP e também após a desconexão do SSE.
O consumidor pode consultar o resultado ou se reconectar à tarefa em andamento.
Os endpoints nativos conservam seu comportamento; `/gateway/message` continua
aguardando o resultado, e o SSE nativo permanece separado do SSE A2A.

## Habilitar no agente construído com o framework

Na raiz do framework, instale a dependência opcional:

```sh
python -m pip install -e 'libs/agent_framework[a2a]' -r templates/agent_template_backend/requirements.txt
```

No ambiente do backend:

```dotenv
ENABLE_A2A=true
A2A_TASK_MODE=true
A2A_PUBLIC_URL=http://localhost:8000
A2A_TASK_TIMEOUT_SECONDS=240
```

Inicie o backend com suas configurações normais. Por exemplo, após preparar o
`.env` e os arquivos de configuração do agente:

```sh
cd templates/agent_template_backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

O endereço público real deve ser usado em `A2A_PUBLIC_URL`. A configuração de
exemplo está em `.env.a2a.example`. Há também uma imagem opcional, construída
na raiz do framework:

```sh
docker build -f templates/agent_template_backend/Dockerfile.a2a -t framework-agent-a2a .
```

Os perfis de `agents.yaml` são publicados como skills no Agent Card:
`GET /.well-known/agent-card.json`. Use `message.metadata.agent_id` para escolher
um perfil; sem ele, o backend mantém sua seleção padrão.

## Registrar esse agente no Agent Gateway

```yaml
backends:
  pedidos_a2a:
    protocol: a2a
    a2a_version: '1.0'
    url: http://backend-pedidos:8000
    a2a_rpc_path: /a2a
    description: Consulta e acompanhamento de pedidos
    keywords: [pedido, entrega, rastreamento]
    default_agent_id: pedidos
```

No gateway, habilite `ENABLE_A2A=true`, `A2A_TASK_MODE=true` e configure seu próprio
`A2A_PUBLIC_URL`. Para uma execução mais longa, ajuste os limites, por exemplo:
`A2A_TASK_TIMEOUT_SECONDS=300` e `BACKEND_TIMEOUT_SECONDS=270`, com o timeout do
backend em 240 segundos. A duração efetiva é limitada pelo menor prazo aplicável.

O gateway devolve sua própria Task imediatamente e consulta a Task remota até
conclusão ou solicitação de input/autenticação. Eventos de status remoto são
publicados como `a2a.backend.status`. Os IDs local e remoto podem ser distintos.
O resultado nativo inclui `metadata.a2a_task_id` e `metadata.a2a_context_id` para
correlação; o consumidor externo continua acompanhando o ID emitido pelo gateway.

## Envio assíncrono A2A 1.0

Envie um `POST /a2a` com `Content-Type: application/json` e
`A2A-Version: 1.0`:

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
      "parts": [{"text": "Consulte meu pedido"}],
      "metadata": {"agent_id": "pedidos", "tenant_id": "default"}
    }
  }
}
```

A resposta contém `result.task.id`, `contextId` e um estado inicial como
`TASK_STATE_SUBMITTED` ou `TASK_STATE_WORKING`. Guarde esse ID e consulte:

```json
{
  "jsonrpc": "2.0",
  "id": "request-2",
  "method": "GetTask",
  "params": {"id": "ID_DA_TAREFA"}
}
```

O resultado está em `result`. Quando `status.state` for `TASK_STATE_COMPLETED`,
o conteúdo final estará em `artifacts[].parts`. Há uma parte de texto e uma
parte `data` com a resposta original do framework.

Sem `returnImmediately: true`, o envio aguarda o estado final ou interrompido,
retornando uma Task no mesmo formato. Para manter o comportamento da primeira
entrega A2A, que retornava Message, configure `A2A_TASK_MODE=false`; nesse modo,
streaming fica desabilitado e não há Tasks locais.

## Streaming e reconexão

Para enviar e acompanhar, use `SendStreamingMessage` no lugar de `SendMessage`
com os mesmos parâmetros. A resposta tem `Content-Type: text/event-stream`.
Cada campo `data:` contém uma resposta JSON-RPC. Os eventos contêm:

1. A Task inicial.
2. Atualizações de status: submitted/working e eventos de progresso.
3. O artefato de resposta.
4. O estado completed, failed, canceled, input-required ou auth-required.

O backend do framework publica marcos como `flow.start`, `session.upserted`,
`workflow.started`, `workflow.completed` e `message.responded`, quando o fluxo
passa por essas etapas. Eles aparecem em
`result.statusUpdate.metadata.framework_event`, com os dados correspondentes
em `framework_payload`. Isso não implica transmissão de tokens do LLM.

Para se reconectar a uma Task em andamento:

```json
{
  "jsonrpc": "2.0",
  "id": "request-3",
  "method": "SubscribeToTask",
  "params": {"id": "ID_DA_TAREFA"}
}
```

A reconexão entrega o estado atual e os eventos seguintes; não há promessa de
replay de todos os eventos perdidos. Se a tarefa já terminou, consulte `GetTask`.

## Cancelamento, falhas e continuidade

`CancelTask`, com `params.id`, cancela a execução local em andamento. O SDK
interrompe a coroutine e registra `TASK_STATE_CANCELED`. Isso não desfaz efeitos
já confirmados em ferramentas ou sistemas externos. Quando o gateway está
consultando um agente remoto, parar a tarefa local não garante cancelar a
operação que já foi aceita pelo serviço remoto.

Exceções e expiração de `A2A_TASK_TIMEOUT_SECONDS` resultam em
`TASK_STATE_FAILED`, consultável depois, com mensagem genérica. Detalhes internos
permanecem nos logs do servidor.

Para uma interação que exige nova entrada, um handler pode retornar
`metadata.a2a_task_state: "input-required"` ou `"auth-required"`. O consumidor
envia outra mensagem com o mesmo `taskId` e `contextId`. A tarefa é retomada;
uma tarefa concluída não pode ser reexecutada. O adaptador de saída preserva a
continuidade de tarefas remotas nesses estados.

Os workflows nativos que não declaram esse estado concluem uma Task por turno;
a conversa continua com uma nova Task e o mesmo `contextId`, usando as sessões
e memórias já existentes no framework.

## Equivalentes A2A 0.3

Use `A2A-Version: 0.3`, `role: "user"` e os discriminadores `kind` de 0.3.

| A2A 1.0 | A2A 0.3 |
| --- | --- |
| `SendMessage` + `returnImmediately: true` | `message/send` + `blocking: false` |
| `SendStreamingMessage` | `message/stream` |
| `GetTask` | `tasks/get` |
| `SubscribeToTask` | `tasks/resubscribe` |
| `CancelTask` | `tasks/cancel` |

Em 0.3, `result` contém diretamente a Task, sem o envelope `task`. Os estados
usam `submitted`, `working`, `completed`, `failed`, etc.

## Armazenamento e autenticação

O padrão usa o TaskStore em memória do SDK. Tarefas e resultados são perdidos
quando o processo reinicia. Para múltiplos workers/réplicas, use afinidade de
requisições ao mesmo processo durante a execução ou configure armazenamento e
coordenação compartilhados. Um TaskStore persistente, sozinho, não torna a
execução retomável após falha. As funções `install_a2a` e `install_backend_a2a`
aceitam `task_store` para integração com um armazenamento do SDK.

O backend opcional reutiliza `AGENT_AUTH_*`; o gateway usa
`AGENT_GATEWAY_AUTH_*`. A identidade autenticada pelo middleware define o dono
das Tasks, incluindo consultas e cancelamento. Usuários anônimos compartilham
o escopo anônimo. `tenant_id` em metadata continua sendo dado do pedido, não
credencial nem isolamento de autorização. Clientes que compartilham uma mesma
credencial/principal compartilham o escopo de tarefas.

`A2A_SECURITY_SCHEMES` e `A2A_SECURITY` documentam os mecanismos no Agent Card,
como descrito no guia geral. SSE está habilitado no modo de Tasks;
notificações push e gRPC continuam fora desta implementação.

## Validação

A suíte inclui envio imediato enquanto o handler permanece bloqueado, polling,
streaming com progresso e resultado, cancelamento, falhas, timeout, retomada,
separação entre identidades autenticadas e gateway chamando um backend A2A real
em aplicação local. Há também testes HTTP em `127.0.0.1` que verificam a chegada
do primeiro evento antes da conclusão e reconexão após desconexão.

```sh
python -m pip install pytest pytest-asyncio uvicorn
PYTHONPATH=libs/agent_framework/src pytest \
  tests/test_a2a_interoperability.py tests/test_a2a_async_tasks.py \
  tests/test_a2a_http_streaming.py \
  tests/unit/test_sse.py tests/unit/test_sse_replay_dedup.py \
  tests/unit/test_authentication.py tests/unit/test_authentication_policies.py -q
```

Os testes não acessam OCI nem serviços de negócio externos. Em ambientes sem
permissão para abrir portas locais, execute o teste HTTP em um ambiente que
permita bind em loopback.

Especificação oficial: https://a2a-protocol.org/latest/specification/
SDK oficial: https://github.com/a2aproject/a2a-python

## Frontend pronto para A2A

A interface `apps/agent_frontend_a2a` consome este protocolo diretamente, com
Tasks, streaming, consulta e cancelamento. Consulte
[Frontend A2A](../apps/agent_frontend_a2a/README.md) para a demonstração sem OCI
e os comandos de execução com o backend ou Gateway. O frontend nativo continua
em `apps/agent_frontend`.
