# Integração A2A no Agent Framework OCI

## Decisão de arquitetura

O Agent Gateway existente passa a ter uma fachada A2A opcional. Não é necessário
manter um segundo roteador, duplicar o supervisor ou migrar os agentes atuais.

```text
Consumidor atual ── /gateway/message ─┐
                                    ├─ Agent Gateway / supervisor ─┬─ backend native
Consumidor A2A ──── /a2a ─────────────┘                             └─ backend a2a
```

O backend nativo continua recebendo `{channel, payload, agent_id, tenant_id}`.
A ausência de `protocol` no catálogo mantém `native`. A2A fica desativado por
padrão; o SDK só é importado ao habilitar a fachada ou selecionar um backend A2A.
Não foi alterado o runtime dos agentes, os workflows, os canais ou os MCPs.

A entrada usa A2A **1.0 / JSON-RPC**, SDK oficial `a2a-sdk==1.2.2`, com adaptação
0.3 disponibilizada pelo próprio SDK. Agentes externos podem ser registrados
com `a2a_version: '1.0'` ou `'0.3'`; não há detecção heurística de versão.

## Ativação local

Na raiz do framework:

```sh
python -m pip install -e 'libs/agent_framework[a2a]' -r apps/agent_gateway/requirements.txt
export ENABLE_A2A=true
export A2A_PUBLIC_URL=https://meu-gateway.example
export BACKENDS_CONFIG_PATH="$PWD/apps/agent_gateway/config/backends.a2a.example.yaml"
python -m uvicorn app.main:app --app-dir apps/agent_gateway --env-file .env --port 8010
```

Edite primeiro as URLs do catálogo de exemplo. Para agentes externos, informe o
endpoint JSON-RPC anunciado no Agent Card como `url` + `a2a_rpc_path`.
Credenciais ficam em variáveis de ambiente referenciadas por `a2a_headers_env`.
Os valores não são publicados em `/backends`.

A imagem opcional pode ser construída a partir da raiz:

```sh
docker build -f apps/agent_gateway/Dockerfile.a2a -t agent-gateway-a2a .
```

Defina `A2A_PUBLIC_URL` no ambiente do container e monte o catálogo de backends.
A imagem e os comandos anteriores de implantação continuam disponíveis.

## Descoberta e chamada

O Agent Card fica em `GET /.well-known/agent-card.json`; as skills são derivadas
dos backends habilitados. As mensagens chegam em `POST /a2a`.

Exemplo A2A 1.0, com cabeçalho `A2A-Version: 1.0`:

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
        {"text": "Quero consultar minha fatura"},
        {"data": {"customer_id": "123"}}
      ],
      "metadata": {"tenant_id": "default"}
    }
  }
}
```

No modo de tarefas (padrão), a resposta fica em `result.task`. O resultado de
negócio está em `artifacts[].parts`, com texto e uma parte `data` contendo a
resposta do framework. Com `A2A_TASK_MODE=false`, permanece em `result.message`. Reutilize `contextId` nos próximos turnos. No modo 0.3,
use o cabeçalho `A2A-Version: 0.3`, método `message/send`, role `user` e os
campos `kind` da especificação 0.3; o resultado é uma Task diretamente
(ou Message com `A2A_TASK_MODE=false`).

Partes `data` devem conter objetos e são incorporadas ao payload de negócio.
A identidade da sessão e o texto do protocolo prevalecem sobre esses dados.
Arquivos recebidos pela fachada são rejeitados explicitamente.

## Conversas, tarefas e limites

- A fachada cria **Tasks A2A** e permite envio imediato, consulta, cancelamento
  e streaming SSE. `A2A_TASK_MODE=false` mantém o modo anterior de Messages.
  Consulte [A2A assíncrono](A2A_ASSINCRONO.md) para os exemplos completos.
- O adaptador de saída aceita Message ou Task; consulta `GetTask`/`tasks/get`
  enquanto o agente está trabalhando, dentro de um prazo total configurável
  por `BACKEND_TIMEOUT_SECONDS`. Não repete automaticamente operações de envio.
- Tarefas que pedem input/autenticação preservam estado e identidade para o
  próximo turno. Tarefas concluídas não são reutilizadas.
- A continuidade remota é guardada no processo, por tenant/backend/sessão,
  com validade de uma hora e limite de 10 mil entradas. Em múltiplas réplicas,
  use afinidade de sessão ou implemente armazenamento compartilhado antes de
  depender dessa continuidade. Reiniciar o processo limpa esse cache.
- `metadata.a2a_result` preserva o resultado remoto, incluindo dados/artefatos;
  `a2a_context_id`, `a2a_task_id` e `a2a_state` permitem inspeção e continuidade
  explícita no payload quando necessário.
- Streaming SSE está disponível no modo de tarefas. Push notifications e gRPC
  não são oferecidos. O proxy de eventos nativo não é utilizado para agentes
  A2A: use `SendStreamingMessage`/`SubscribeToTask` e seus equivalentes 0.3.
- O template `templates/agent_template_backend` também expõe A2A diretamente
  quando `ENABLE_A2A=true`, sem passar pelo gateway global.

## Autenticação

As rotas A2A compartilham o middleware de autenticação já instalado no gateway
(`AGENT_GATEWAY_AUTH_*`). Habilitar A2A não habilita autenticação automaticamente.
O tenant em metadata mantém a semântica atual do framework: é dado do pedido,
não uma autorização concedida pelo protocolo. Políticas de acesso a tenants
continuam sendo responsabilidade da configuração de autenticação/autorização.

Quando houver autenticação, declare-a também no Agent Card, por exemplo:

```sh
export A2A_SECURITY_SCHEMES='{"gatewayBearer":{"httpAuthSecurityScheme":{"scheme":"bearer"}}}'
export A2A_SECURITY='[{"gatewayBearer":[]}]'
```

Essas declarações documentam o mecanismo; quem verifica as credenciais é o
middleware. Se desejar descoberta pública, adicione somente o caminho do Agent
Card à configuração de caminhos públicos; `/a2a` permanece protegido.

## Validação

Testes em `tests/test_a2a_interoperability.py` cobrem os dois formatos de entrada,
o contrato nativo, os dois formatos de saída, polling, erros JSON-RPC,
continuidade de tarefas, separação entre tenants e limite de tempo.

```sh
PYTHONPATH=libs/agent_framework/src pytest tests/test_a2a_interoperability.py -q
```

Validação com transportes HTTP simulados e aplicação FastAPI local; não substitui
um teste de integração com os serviços OCI e agentes externos da implantação.

Referências oficiais:
- https://a2a-protocol.org/latest/specification/
- https://a2a-protocol.org/v0.3.0/specification/
- https://github.com/a2aproject/a2a-python
