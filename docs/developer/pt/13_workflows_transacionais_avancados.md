### Workflows transacionais avançados

### Objetivo

Este capítulo ensina a transformar uma tool sensível em uma transação determinística, com coleta de parâmetros, pré-validação, confirmação, workflow versionado, pausa/retomada, idempotência e recuperação. A regra de negócio e as actions ficam no agente; o motor de execução fica no framework.

### Fluxo real

1. `routing.yaml` escolhe o agente e restringe as tools candidatas.
2. `tools.yaml` descreve argumentos, prompts e resposta.
3. `mcp_parameter_mapping.yaml` resolve identidade, defaults e extrações.
4. `tool_policies.yaml` classifica a operação e exige confirmação.
5. A pré-validação opcional verifica se a operação pode prosseguir sem causar efeito.
6. Após confirmação inequívoca, a execução é direta ou encaminhada ao `WorkflowToolExecutor`.
7. O `WorkflowRuntime` carrega a versão ativa, executa actions, persiste pausa e devolve `COMPLETED`, `PAUSED` ou `FAILED`.
8. A chave idempotente impede a repetição do efeito externo.

### Catálogo e política são contratos diferentes

```yaml
# config/tools.yaml
tools:
  solicitar_devolucao:
    description: Abre uma devolução de pedido.
    mcp_server: retail
    enabled: true
    tool_type: action
    confirmation_required: true
    requires: [order_id, reason]
    args_schema:
      order_id:
        type: string
        label: o número do pedido
        user_prompt: Informe o número do pedido.
      reason:
        type: string
        label: o motivo da devolução
        user_prompt: Qual é o motivo da devolução?
```

```yaml
# config/tool_policies.yaml
version: 1
defaults:
  operation_type: read_only
  require_confirmation: false
tool_policies:
  solicitar_devolucao:
    operation_type: transactional
    require_confirmation: true
    requires: [order_id, reason]
    pre_validation:
      enabled: true
      tool: validar_devolucao
      fail_open: false
    execution:
      mode: workflow
      workflow: devolucao_pedido
      version: active
```

`tools.yaml` é o catálogo público. `tool_policies.yaml` governa efeitos. Não confie somente em `confirmation_required` do catálogo: a política efetiva deve declarar `operation_type` e `require_confirmation`. `pre_validation.tool` deve ser read-only e nunca executar a transação antecipadamente. Para segurança, use `fail_open: false`.

### Definição versionada do workflow

```yaml workflow-definition-example
name: devolucao_pedido
version: 1
start: validar_pedido
nodes:
  - id: validar_pedido
    action: validar_pedido
    input:
      order_id: $.input.order_id
  - id: registrar_devolucao
    action: registrar_devolucao
    retry: 1
    input:
      order_id: $.input.order_id
      reason: $.input.reason
edges:
  - from: validar_pedido
    to: registrar_devolucao
    when:
      path: $.nodes.validar_pedido.valid
      equals: true
  - from: validar_pedido
    to: END
    when:
      path: $.nodes.validar_pedido.valid
      equals: false
  - from: registrar_devolucao
    to: END
```

Salve como `workflows/devolucao_pedido.v1.yaml`. O arquivo `devolucao_pedido.active.yaml` deve apontar para uma definição válida da versão ativa. IDs de nós não podem repetir; `start`, destinos e `resume_from` precisam existir. `retry` aceita de 0 a 10. Paths `$.input.*` leem a entrada e `$.nodes.<id>.*` leem resultados anteriores.

### Actions pertencentes ao agente

```python workflow-actions-example
from agent_framework.workflows import workflow_action


@workflow_action("validar_pedido")
async def validar_pedido(params: dict, state: dict) -> dict:
    return {"valid": bool(params.get("order_id"))}


@workflow_action("registrar_devolucao")
async def registrar_devolucao(params: dict, state: dict) -> dict:
    order_id = str(params["order_id"])
    return {"protocol": f"DEV-{order_id}", "status": "REQUESTED"}
```

O nome do decorator deve ser igual a `node.action`. A assinatura obrigatória é `(params: dict, state: dict) -> dict`. O módulo precisa ser importado no startup para registrar decorators. Actions devem devolver dados serializáveis; não devolva cliente HTTP, conexão, exception ou coroutine.

### Idempotência do efeito externo

```python idempotency-example
async def execute_once(store, customer_key: str, order_id: str, invoke):
    key = store.canonical_key(customer_key, order_id, "solicitar_devolucao", "v1")
    previous = await store.get(key)
    if previous is not None:
        return previous
    result = await invoke()
    await store.set(key, result)
    return result
```

Crie uma única instância no startup com `create_idempotency_store(settings, namespace="return-request", require_durable=True)` e injete-a nas actions. Use componentes de negócio estáveis na chave; nunca use apenas timestamp. `IDEMPOTENCY_PROVIDER` tem precedência sobre checkpoint, session e cache. Em produção transacional, configure `IDEMPOTENCY_REQUIRE_DURABLE=true` e um provider `oracle`, `redis` ou `sqlite` apropriado. `memory` não protege entre pods ou reinícios. Grave o resultado somente depois de o efeito ter sido confirmado pelo sistema externo.

### Pausa, entrada esperada e retomada

Um nó pode declarar `pause.expected_input` com `key`, `allowed_values`, normalização, `reprompt` e classificador semântico. A confirmação explícita continua determinística; o classificador só trata respostas inconclusivas e deve retornar uma das opções permitidas. `contextual_reentry` libera o workflow e devolve a fala ao roteamento normal, sem confirmar fatos automaticamente.

Ao retomar, use o mesmo `execution_id`. Uma nova execução cria outra transação. O checkpoint deve conter somente dados serializáveis e suficientes para reconstruir a pausa. Respostas duplicadas precisam consultar idempotência antes de repetir qualquer efeito.

### Intent shift e limpeza

Quando o usuário abandona a transação, limpe `pending_tool_call`, argumentos coletados, confirmação e estado transacional relacionado. Não reutilize parâmetros de uma transação encerrada. Uma pergunta contextual durante a pausa pode ser respondida e retornar ao workflow; uma mudança real de intenção encerra ou suspende explicitamente o fluxo conforme a política do agente.

### Recuperação e post-finalization replay

- `PAUSED`: persistir `execution_id`, prompt e contrato da entrada esperada.
- `FAILED`: manter detalhes técnicos na telemetria e uma mensagem segura ao usuário.
- timeout após envio: consultar idempotência ou status externo antes de reenviar.
- replay depois de `COMPLETED`: devolver o resultado persistido; nunca executar novamente.
- versão nova: execuções em andamento continuam com sua versão; `active` vale para novas execuções.

### Como testar

Teste grafo inválido, caminho válido/inválido, retry, pause/resume, resposta não reconhecida, intent shift, duplicidade, falha do provider de idempotência e replay após finalização. O contrato copiável deste capítulo é validado por `tests/test_advanced_developer_documentation.py`.
