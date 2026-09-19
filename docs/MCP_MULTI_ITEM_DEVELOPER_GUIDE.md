# MCP Multi-item — Guia do Desenvolvedor

## Objetivo

Use este guia quando uma única intenção do usuário precisa operar sobre **mais de um item do mesmo tipo** em uma chamada MCP, por exemplo:

- cancelar vários VAS/produtos;
- devolver ou consultar vários pedidos;
- alterar vários ativos;
- processar uma lista de faturas, linhas, contratos ou recursos.

O framework já possui contratos genéricos para **coleta de listas**, **pré-validação/canonicalização**, **confirmação transacional**, **execução MCP** e **normalização do resultado por item**. O desenvolvedor não deve criar um segundo motor de multi-item dentro do agente.

## Regra principal

**Não faça loop de negócio no agente.** O agente declara a tool e seus parâmetros; o runtime mantém estado, confirmação e evidência. A operação em lote deve ser exposta como uma tool MCP que aceite uma coleção, ou como uma tool transacional apoiada por um workflow/MCP que processe a coleção.

Fluxo recomendado:

```text
Usuário cita N itens
  -> Router/Agent seleciona a tool
  -> Runtime coleta/reconcilia parâmetro array/list
  -> (opcional) pre-validation canonicaliza itens
  -> Runtime pede UMA confirmação coerente para o conjunto
  -> MCP recebe a coleção
  -> MCP/workflow processa item a item
  -> MCP devolve results[] com success/ok por item
  -> Framework normaliza SUCCESS / PARTIAL_SUCCESS / FAILED
  -> Composição final relata sucessos e falhas individualmente
```

## 1. Declarar um parâmetro de lista em `tools.yaml`

O reconciliador transacional do framework aceita `type: array` ou `type: list`.

```yaml
tools:
  cancelar_produtos:
    description: Cancela um ou mais produtos do cliente.
    mcp_server: contas
    enabled: true
    tool_type: action
    confirmation_required: true
    requires: [items]
    args_schema:
      items:
        type: array
        label: os produtos
        description: Lista de produtos que o cliente deseja cancelar.
        user_prompt: Informe quais produtos deseja cancelar.
```

O runtime pode reconciliar uma frase como:

```text
quero cancelar TIM Fashion, Aya Audiobooks e Neymar Jr
```

para um argumento lógico semelhante a:

```json
{
  "items": ["TIM Fashion", "Aya Audiobooks", "Neymar Jr"]
}
```

A semântica de domínio e a validação dos nomes continuam pertencendo ao MCP/pre-validator, não ao core.

## 2. Quando usar pre-validation

Use `tool_policies.yaml` quando a lista precisa ser resolvida/canonicalizada antes da confirmação.

```yaml
tool_policies:
  cancelar_produtos:
    operation_type: transactional
    require_confirmation: true
    requires: [items]
    pre_validation:
      enabled: true
      tool: validar_produtos_cancelamento
      fail_open: false
```

O pre-validator pode retornar `eligible: true` e substituir argumentos por valores canônicos em `transaction_decision.resolved_arguments`:

```json
{
  "eligible": true,
  "transaction_decision": {
    "resolved_arguments": {
      "items": [
        {"name": "TIM Fashion Mensal", "id": "1001"},
        {"name": "Aya Audiobooks Premium", "id": "1002"},
        {"name": "Neymar Jr", "id": "1003"}
      ]
    },
    "target_tool": "cancelar_produtos",
    "confirmation_message": "Você confirma o cancelamento de TIM Fashion Mensal, Aya Audiobooks Premium e Neymar Jr?"
  }
}
```

### Importante para validação parcial

O contrato `eligible` da pre-validation é global. Portanto, **não retorne `eligible: false` apenas porque um item da lista falhou**, caso os demais ainda possam ser processados. Isso encerraria toda a transação.

Para permitir resultado parcial, a estratégia recomendada é:

1. retornar `eligible: true` quando existe pelo menos um item acionável;
2. preservar/canonicalizar a coleção em `resolved_arguments`;
3. deixar a tool primária devolver o resultado terminal de **cada item** em `results[]`.

Se nenhum item puder ser processado, então `eligible: false` é apropriado.

## 3. Contrato de entrada do MCP

Prefira uma única chamada MCP com uma coleção explícita:

```json
{
  "tool_name": "cancelar_produtos",
  "arguments": {
    "customer_id": "123",
    "items": [
      {"name": "TIM Fashion Mensal", "id": "1001"},
      {"name": "Aya Audiobooks Premium", "id": "1002"},
      {"name": "Neymar Jr", "id": "1003"}
    ]
  }
}
```

O framework **não deve ser usado como um loop improvisado que chama N vezes uma tool escalar a partir do agente**. Se o backend só possui API unitária, o fan-out pode ficar encapsulado no MCP Server ou em um workflow de domínio, mantendo uma única tool lógica para o agente.

## 4. Contrato obrigatório de resultado por item

Para o framework reconhecer multi-item automaticamente, a **tool primária solicitada** deve expor uma lista `results` com **dois ou mais itens**, e cada item deve possuir um booleano `success` ou `ok`.

Exemplo:

```json
{
  "ok": true,
  "result": {
    "results": [
      {"id": "1001", "subject": "TIM Fashion Mensal", "success": true},
      {"id": "1002", "subject": "Aya Audiobooks Premium", "success": false, "reason": "not_found"},
      {"id": "1003", "subject": "Neymar Jr", "success": true}
    ]
  }
}
```

Campos como `id`, `subject`, `name`, `reason`, `error`, `protocol` e outros são de domínio e opcionais. O sinal estrutural exigido pelo normalizador é `success: true|false` ou `ok: true|false` por item.

### Workflow-backed tool

Se a tool é executada por workflow, o caminho preferencial e autoritativo é:

```text
workflow.output[tool_name].results
```

Exemplo:

```json
{
  "ok": false,
  "result": {
    "status": "COMPLETED",
    "output": {
      "cancelar_produtos": {
        "results": [
          {"subject": "A", "success": true},
          {"subject": "B", "success": false, "reason": "not_found"},
          {"subject": "C", "success": true}
        ]
      },
      "etapa_auxiliar": {
        "success": false,
        "error": "falha em pós-processamento"
      }
    }
  },
  "error": "falha em pós-processamento"
}
```

O runtime preserva o resultado da operação primária e não permite que uma falha auxiliar apague itens já concluídos.

## 5. O que o framework produz automaticamente

Com `results[]` válido, o runtime adiciona:

```json
{
  "multi_item_status": "PARTIAL_SUCCESS",
  "partial_success": true,
  "metadata": {
    "multi_item": {
      "status": "PARTIAL_SUCCESS",
      "items_count": 3,
      "items_succeeded_count": 2,
      "items_failed_count": 1,
      "primary_tool": "cancelar_produtos"
    }
  }
}
```

Estados possíveis:

| Situação | `multi_item_status` |
|---|---|
| todos os itens concluíram | `SUCCESS` |
| parte concluiu e parte falhou | `PARTIAL_SUCCESS` |
| todos falharam | `FAILED` |

Se uma etapa posterior fizer o wrapper retornar `ok=false`, mas pelo menos um item primário tiver sucesso, o framework preserva para auditoria:

```json
{
  "ok": true,
  "original_ok": false,
  "secondary_error": "erro da etapa posterior"
}
```

Isso evita transformar sucesso parcial/real em falha total na resposta ao usuário.

## 6. O que NÃO fazer

Evite estes padrões:

```python
# NÃO: motor multi-item paralelo dentro do agente
for product in products:
    await tool_router.call("cancelar_produto", {"product": product})
```

```json
// NÃO: apenas um approved global sem evidência por item
{
  "approved": false,
  "error": "um item falhou"
}
```

```json
// NÃO: um único success agregado quando houve resultados mistos
{
  "success": false,
  "message": "operação bloqueada"
}
```

Esses formatos perdem a evidência terminal individual e podem fazer itens concluídos desaparecerem da composição final.

## 7. Exemplo completo: vários pedidos

### `tools.yaml`

```yaml
tools:
  cancelar_pedidos:
    description: Cancela um ou mais pedidos.
    mcp_server: retail
    enabled: true
    tool_type: action
    confirmation_required: true
    requires: [order_ids]
    args_schema:
      order_ids:
        type: array
        label: os pedidos
        description: Lista de identificadores de pedidos a cancelar.
        user_prompt: Quais pedidos deseja cancelar?
```

### Retorno MCP

```json
{
  "ok": true,
  "result": {
    "results": [
      {"order_id": "P-100", "success": true, "protocol": "ABC1"},
      {"order_id": "P-101", "success": false, "reason": "already_shipped"},
      {"order_id": "P-102", "success": true, "protocol": "ABC3"}
    ]
  }
}
```

O framework classificará automaticamente como `PARTIAL_SUCCESS` e fornecerá ao LLM a instrução de relatar os resultados item a item.

## 8. Read-only multi-item

A mesma estrutura serve para consultas em lote. A diferença é que normalmente não existe confirmação:

```yaml
tool_policies:
  consultar_pedidos:
    operation_type: read_only
    require_confirmation: false
```

A tool ainda pode retornar `results[]` com `success/ok` por item para que uma consulta parcialmente indisponível não esconda as consultas bem-sucedidas.

## 9. Idempotência e protocolos

Em operações com efeito colateral:

- use uma chave de idempotência de requisição e, quando necessário, uma chave por item;
- devolva protocolo/operation id no próprio item;
- não dependa apenas de uma mensagem textual agregada;
- em retry, preserve os itens já concluídos e execute apenas o que a regra de domínio permitir.

O framework preserva evidência; a política de idempotência do sistema de destino continua pertencendo ao MCP/workflow de domínio.

## 10. Checklist para o desenvolvedor

- [ ] A tool aceita `array/list` quando o caso de uso é multi-item.
- [ ] Não existe loop MCP de negócio dentro da classe do agente.
- [ ] Se houver canonicalização, ela está em pre-validation/MCP, não hardcoded no agente.
- [ ] A confirmação mostra o conjunto efetivo de itens.
- [ ] A tool primária retorna `results[]` com `success` ou `ok` por item.
- [ ] Resultado parcial não é reduzido a um único `approved=false` ou `success=false` global.
- [ ] Workflow usa `output[tool_name].results` para a evidência terminal da tool primária.
- [ ] Testes cobrem todos-sucesso, parcial, todos-falha e falha auxiliar posterior.
- [ ] A resposta final menciona sucessos e falhas quando houver `PARTIAL_SUCCESS`.

## 11. Onde o comportamento existe no framework

Referências atuais:

```text
libs/agent_framework/src/agent_framework/runtime/transaction_parameters.py
  - coerção de type=array/list

libs/agent_framework/src/agent_framework/runtime/agent_runtime.py
  - pre-validation e resolved_arguments
  - _primary_multi_item_outcomes()
  - _normalize_multi_item_tool_result()
  - instrução de composição multi-item para o LLM

tests/test_multi_item_result_normalization.py
  - regressões de SUCCESS/PARTIAL_SUCCESS e proteção contra falha auxiliar
```

## 12. Resumo de responsabilidade

| Camada | Responsabilidade |
|---|---|
| Agente | declarar intenção/tool e usar o runtime; não implementar motor multi-item |
| `tools.yaml` | declarar parâmetro `array/list` e schema |
| `tool_policies.yaml` | confirmação e pre-validation |
| Pre-validator MCP | resolver/canonicalizar entidades e argumentos |
| Tool MCP/workflow | executar a coleção e produzir resultado por item |
| Framework runtime | manter estado, confirmação, normalizar resultado multi-item e preservar evidência |
| LLM/presentation | transformar evidências em resposta, sem apagar sucesso/falha individual |
