# Workflows transacionais determinísticos

## Objetivo

O framework passa a oferecer um executor genérico de transações multi-etapas usando LangGraph como detalhe interno. O LLM permanece responsável por interpretação, roteamento, clarification e preparação da confirmação. Depois da confirmação explícita, passos críticos podem ser executados por um grafo determinístico, auditável e versionado.

## Separação de responsabilidades

O framework fornece carregamento, validação, compilação, cache, execução, retry por nó e integração com `tool_policies.yaml`. O projeto do agente mantém os YAMLs do domínio e as actions que chamam APIs ou MCPs.

```text
LLM/router -> clarification -> transactional confirmation
           -> WorkflowToolExecutor -> WorkflowRuntime/LangGraph
           -> actions de domínio -> APIs/MCP
```

## Política

```yaml
tool_policies:
  solicitar_devolucao:
    operation_type: transactional
    require_confirmation: true
    requires: [order_id, reason]
    execution:
      mode: workflow
      workflow: devolucao_pedido
      version: active
```

`direct_tool` é o padrão e mantém compatibilidade. `workflow` ativa o executor determinístico. `agent` fica reservado para orquestrações não determinísticas explicitamente autorizadas.

## Arquivos e versionamento

```text
workflows/devolucao_pedido.active.yaml   # version: 1
workflows/devolucao_pedido.v1.yaml       # definição imutável
```

Uma execução resolve a versão ativa no início. Para reprodutibilidade, integrações persistentes devem guardar `workflow_name`, `workflow_version` e `execution_id`.

## Actions

```python
from agent_framework.workflows import workflow_action

@workflow_action("registrar_devolucao")
async def registrar_devolucao(params: dict, state: dict) -> dict:
    return {"protocol": "...", "status": "REQUESTED"}
```

As actions devem ser idempotentes quando causarem efeitos externos. O framework aceita `retry` por nó, mas retry seguro depende de chave idempotente no serviço de destino.

## Condições suportadas

Cada edge aceita `path` JSON-like (`$.input...` ou `$.nodes...`) e um operador: `equals`, `not_equals`, `exists` ou `in`. Transições críticas não são escolhidas por LLM.

## Uso programático

```python
from agent_framework.workflows import FileWorkflowRepository, WorkflowRuntime

runtime = WorkflowRuntime(FileWorkflowRepository(settings.WORKFLOWS_PATH))
result = await runtime.arun("devolucao_pedido", payload)
```

Para integração com policy:

```python
from agent_framework.workflows import WorkflowToolExecutor

executor = WorkflowToolExecutor(runtime)
result = await executor.execute_from_policy(
    tool_name=tool_name,
    arguments=arguments,
    policy=resolved_policy,
)
```

Quando o retorno for `None`, a aplicação continua pelo caminho legado `direct_tool`.

## Produção

Antes de habilitar em produção, configure checkpointer persistente, idempotência nas actions, autorização, timeout na camada de integração e telemetria com `transaction_id`, `workflow_execution_id`, versão, nó e tentativa. O runtime não transforma automaticamente uma API não idempotente em uma operação segura.
