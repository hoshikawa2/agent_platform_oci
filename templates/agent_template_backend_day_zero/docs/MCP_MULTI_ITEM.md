# MCP Multi-item — Guia do Desenvolvedor

## Objetivo

Use este guia quando uma única intenção do usuário precisa operar sobre **mais de um item do mesmo tipo** — por exemplo, cancelar vários VAS/produtos, devolver ou consultar vários pedidos, alterar vários ativos ou processar várias faturas/linhas/contratos.

O framework já possui suporte genérico para **resolução/canonicalização de múltiplos itens**, **confirmação transacional**, **execução MCP/workflow**, **preservação de evidência por item** e **normalização de `SUCCESS` / `PARTIAL_SUCCESS` / `FAILED`**. O desenvolvedor não deve criar um segundo motor de multi-item dentro do agente.

> **Regra central:** multi-item é uma característica da resolução, execução e resultado da operação. **Não é definido pelo tipo do parâmetro de entrada.** Uma tool pode receber `subject: string`, `id: string`, `items: array` ou outro contrato natural de domínio e ainda assim processar múltiplos itens.

## Regra principal

**Não faça loop de negócio no agente.** O agente seleciona a intenção/tool e usa o runtime. A expansão para múltiplos itens pode ocorrer no pre-validator, na própria tool MCP ou em um workflow de domínio.

Fluxo recomendado:

```text
Usuário cita N itens
  -> Router/Agent seleciona a tool
  -> Runtime coleta os parâmetros declarados pela tool
  -> Entrada pode ser escalar ou coleção
  -> (opcional) pre-validation resolve/expande/canonicaliza N itens
  -> Runtime pede UMA confirmação coerente para o conjunto efetivo
  -> MCP tool/workflow processa 1 ou N itens
  -> Tool primária devolve results[] com success/ok por item
  -> Framework normaliza SUCCESS / PARTIAL_SUCCESS / FAILED
  -> Composição final relata sucessos e falhas individualmente
```

## 1. Declare o contrato natural da operação em `tools.yaml`

O framework **não exige `array/list`** para que uma operação seja multi-item.

Use o contrato que faz sentido para a tool e para o domínio:

- **parâmetro escalar** (`subject`, `id`, `query`, etc.) quando a operação recebe uma expressão que pode representar uma ou várias entidades;
- **`array/list`** quando a interface MCP é naturalmente batch e recebe explicitamente uma coleção.

### Padrão A — parâmetro escalar que pode representar vários itens

Este é o padrão usado pelo agente de Contas para cancelamento de VAS.

```yaml
tools:
  cancelar_vas_avulso:
    description: Cancela um ou mais serviços VAS.
    mcp_server: contas
    enabled: true
    tool_type: action
    args_schema:
      subject:
        type: string
        label: o serviço ou os serviços
        description: Serviço ou expressão com um ou mais serviços a cancelar.
```

Entrada possível:

```text
subject = "TIM Fashion, Aya Audiobooks, Neymar Jr"
```

O `subject` continua sendo uma `string`. O suporte multi-item aparece posteriormente quando o validator/tool resolve essa expressão em itens independentes.

### Padrão B — coleção explícita

Também é válido quando a API/tool é naturalmente batch:

```yaml
tools:
  cancelar_produtos:
    description: Cancela um ou mais produtos do cliente.
    mcp_server: contas
    enabled: true
    tool_type: action
    args_schema:
      items:
        type: array
        label: os produtos
        description: Lista de produtos que o cliente deseja cancelar.
```

Os dois padrões são suportados. **Não altere uma interface escalar existente para array apenas para “habilitar multi-item”.**

## 2. `tool_policies.yaml` não possui sintaxe especial de multi-item

`tool_policies.yaml` continua definindo tipo de operação, confirmação, parâmetros obrigatórios e pre-validation. Não é necessário criar `multi_item: true`, trocar `subject` por `items` ou introduzir outra configuração.

Exemplo realista do agente de Contas:

```yaml
version: 1
defaults:
  operation_type: read_only
  require_confirmation: false

tool_policies:
  cancelar_vas_avulso:
    operation_type: transactional
    require_confirmation: true
    requires:
      - subject
    pre_validation:
      enabled: true
      tool: validar_vas_subject
      fail_open: false
```

`requires: [subject]` significa apenas que a operação precisa saber **o que** será processado. Esse `subject` pode representar um item ou vários.

## 3. Pre-validation pode transformar um parâmetro escalar em múltiplos itens

Quando necessário, o pre-validator resolve nomes, canonicaliza entidades e pode materializar uma lista estrutural em `transaction_decision.resolved_arguments`.

Exemplo:

```json
{
  "eligible": true,
  "subject": "TIM Fashion, Aya Audiobooks, Neymar Jr",
  "resolved_subject": "TIM Fashion Mensal, Aya Audiobooks Premium, Neymar Jr",
  "resolved_subjects": [
    "TIM Fashion Mensal",
    "Aya Audiobooks Premium",
    "Neymar Jr"
  ],
  "transaction_decision": {
    "resolved_arguments": {
      "subject": "TIM Fashion Mensal, Aya Audiobooks Premium, Neymar Jr",
      "items": [
        {"name": "TIM Fashion Mensal"},
        {"name": "Aya Audiobooks Premium"},
        {"name": "Neymar Jr"}
      ]
    },
    "target_tool": "cancelar_vas_avulso",
    "confirmation_message": "Você confirma o cancelamento de TIM Fashion Mensal, Aya Audiobooks Premium e Neymar Jr?"
  }
}
```

`resolved_arguments.items[]` é uma representação canônica útil para a execução, mas **não obriga** `tools.yaml` a declarar `items` como parâmetro de entrada.

### Validação parcial e `fail_open: false`

`eligible` é global. Com `fail_open: false`, retornar `eligible: false` encerra a transação inteira.

Portanto, quando alguns itens são válidos e outros não:

1. mantenha `eligible: true` se existe pelo menos um item acionável;
2. preserve o estado individual dos itens resolvidos/rejeitados;
3. deixe a tool primária produzir o resultado terminal por item em `results[]`.

Exemplo conceitual:

```json
{
  "eligible": true,
  "status": "PARTIALLY_ELIGIBLE",
  "transaction_decision": {
    "resolved_arguments": {
      "items": [
        {"name": "TIM Fashion Mensal", "eligible": true},
        {"name": "Aya Audiobooks Premium", "eligible": false, "reason": "item_nao_encontrado"},
        {"name": "Neymar Jr", "eligible": true}
      ]
    }
  }
}
```

Se nenhum item puder ser processado, `eligible: false` é apropriado.

## 4. Contrato de entrada do MCP: uma operação lógica, não necessariamente uma coleção explícita

Prefira **uma única operação lógica MCP para o agente**. Ela pode ser implementada de três formas:

1. receber um parâmetro escalar e expandi-lo no validator/workflow;
2. receber uma coleção explícita (`array/list`);
3. receber uma expressão/identificador e descobrir os itens dentro da própria tool/workflow.

O agente não deve fazer fan-out chamando a mesma tool repetidamente por conta própria.

### Exemplo — escalar expandido

```json
{
  "tool_name": "cancelar_vas_avulso",
  "arguments": {
    "subject": "TIM Fashion Mensal, Aya Audiobooks Premium, Neymar Jr"
  }
}
```

### Exemplo — batch explícito

```json
{
  "tool_name": "cancelar_produtos",
  "arguments": {
    "items": [
      {"name": "A", "id": "1001"},
      {"name": "B", "id": "1002"}
    ]
  }
}
```

Se o backend só possui API unitária, o fan-out deve ficar encapsulado no **MCP Server ou workflow de domínio**, preservando uma única operação lógica para o agente.

## 5. Contrato obrigatório de resultado por item

Para o framework reconhecer automaticamente o resultado como multi-item, a **tool primária solicitada** deve expor uma lista `results` com **dois ou mais itens**, e cada item deve possuir `success` ou `ok` booleano.

```json
{
  "results": [
    {"subject": "TIM Fashion Mensal", "success": true},
    {"subject": "Aya Audiobooks Premium", "success": false, "reason": "not_found"},
    {"subject": "Neymar Jr", "success": true}
  ]
}
```

Campos como `id`, `subject`, `name`, `reason`, `error`, `protocol` e outros são de domínio e opcionais. O sinal estrutural do normalizador é `success: true|false` ou `ok: true|false` por item.

### Workflow-backed tool

Se a tool é executada por workflow, o caminho preferencial e autoritativo é:

```text
workflow.output[tool_name].results
```

Uma falha auxiliar posterior não deve apagar itens já concluídos pela tool primária.

## 6. O que o framework produz automaticamente

Com `results[]` válido, o runtime classifica o agregado como:

| Situação | `multi_item_status` |
|---|---|
| todos os itens concluíram | `SUCCESS` |
| parte concluiu e parte falhou | `PARTIAL_SUCCESS` |
| todos falharam | `FAILED` |

Exemplo:

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
      "primary_tool": "cancelar_vas_avulso"
    }
  }
}
```

Se um wrapper/etapa posterior retornar erro depois de existirem resultados terminais válidos, o framework preserva os sucessos individuais e pode registrar o erro como secundário, em vez de converter tudo para falha total.

## 7. O que NÃO fazer

Não crie motor multi-item dentro do agente:

```python
# NÃO
for product in products:
    await tool_router.call("cancelar_produto", {"product": product})
```

Não reduza resultado misto a um único booleano global sem evidência por item:

```json
{
  "approved": false,
  "error": "um item falhou"
}
```

Também não altere uma interface existente apenas para trocar:

```text
subject: string
```

por:

```text
items: array
```

quando o validator/workflow já consegue expandir corretamente o `subject`.

## 8. Exemplo completo — padrão escalar do Contas

### `tools.yaml`

```yaml
tools:
  cancelar_vas_avulso:
    description: Cancela um ou mais VAS.
    mcp_server: contas
    enabled: true
    tool_type: action
    args_schema:
      subject:
        type: string
```

### `tool_policies.yaml`

```yaml
tool_policies:
  cancelar_vas_avulso:
    operation_type: transactional
    require_confirmation: true
    requires:
      - subject
    pre_validation:
      enabled: true
      tool: validar_vas_subject
      fail_open: false
```

### Validator

```json
{
  "eligible": true,
  "transaction_decision": {
    "resolved_arguments": {
      "subject": "TIM Fashion Mensal, Aya Audiobooks Premium, Neymar Jr",
      "items": [
        {"name": "TIM Fashion Mensal"},
        {"name": "Aya Audiobooks Premium"},
        {"name": "Neymar Jr"}
      ]
    }
  }
}
```

### Resultado MCP/workflow

```json
{
  "results": [
    {"subject": "TIM Fashion Mensal", "success": true},
    {"subject": "Aya Audiobooks Premium", "success": false, "reason": "not_found"},
    {"subject": "Neymar Jr", "success": true}
  ]
}
```

Resultado agregado: `PARTIAL_SUCCESS`.

## 9. Exemplo alternativo — API naturalmente batch

Quando o MCP já define coleção como contrato de entrada, `array/list` continua válido:

```yaml
args_schema:
  order_ids:
    type: array
```

```json
{
  "results": [
    {"order_id": "P-100", "success": true},
    {"order_id": "P-101", "success": false, "reason": "already_shipped"},
    {"order_id": "P-102", "success": true}
  ]
}
```

O ponto importante é: **array é uma opção de contrato, não o gatilho do mecanismo multi-item.**

## 10. Read-only, conversational e transactional podem ser multi-item

Multi-item é independente do `operation_type`.

É possível ter:

```text
read_only + multi-item
conversational + multi-item
transactional + multi-item
internal + multi-item
```

O que muda é a política de confirmação e execução, não a capacidade de representar vários itens.

## 11. Idempotência e protocolos

Em operações com efeito colateral:

- use chave de idempotência de requisição e, quando necessário, por item;
- devolva protocolo/operation id no próprio item;
- preserve itens já concluídos em retry;
- não dependa apenas de mensagem textual agregada.

A política específica de idempotência do sistema de destino continua pertencendo ao MCP/workflow de domínio.

## 12. Checklist do desenvolvedor

- [ ] O agente seleciona a operação e **não** implementa fan-out/loop MCP de negócio.
- [ ] `tools.yaml` declara o contrato natural da operação, que pode ser escalar ou coleção.
- [ ] Nenhuma chave especial `multi_item: true` foi criada ou é necessária.
- [ ] `tool_policies.yaml` usa os `requires` reais do domínio; não é necessário trocar `subject` por `items`.
- [ ] Se um escalar representar múltiplas entidades, validator/tool/workflow expande e canonicaliza os itens.
- [ ] A confirmação representa o conjunto efetivo resolvido.
- [ ] Com `fail_open: false`, um item inválido não força `eligible: false` global quando outros ainda são acionáveis.
- [ ] A tool primária retorna `results[]` com `success` ou `ok` por item quando há múltiplos resultados.
- [ ] Workflow usa `output[tool_name].results` como evidência terminal preferencial da tool primária.
- [ ] Resultado parcial não é reduzido a um único `approved=false` ou `success=false` global.
- [ ] Testes cobrem todos-sucesso, parcial, todos-falha e falha auxiliar posterior.
- [ ] A apresentação final menciona sucessos e falhas individualmente quando houver `PARTIAL_SUCCESS`.

## 13. Onde o comportamento existe no framework

```text
libs/agent_framework/src/agent_framework/runtime/transaction_parameters.py
  - suporte existente a coerção de array/list quando esse for o contrato declarado

libs/agent_framework/src/agent_framework/runtime/agent_runtime.py
  - pre-validation e resolved_arguments
  - _primary_multi_item_outcomes()
  - _normalize_multi_item_tool_result()
  - instrução de composição multi-item para o LLM

tests/test_multi_item_result_normalization.py
  - regressões de SUCCESS/PARTIAL_SUCCESS e proteção contra falha auxiliar
```

## 14. Resumo de responsabilidade

| Camada | Responsabilidade |
|---|---|
| Agente | selecionar intenção/tool e usar o runtime; não implementar motor multi-item |
| `tools.yaml` | declarar o contrato natural da operação; pode ser escalar ou coleção |
| `tool_policies.yaml` | confirmação, `requires` e pre-validation; sem sintaxe especial de multi-item |
| Pre-validator MCP | identificar, resolver, canonicalizar e, quando necessário, expandir 1 parâmetro em N itens |
| Tool MCP/workflow | executar 1 ou N itens e produzir resultado por item |
| Framework runtime | manter estado/confirmação, interpretar `results[]`, preservar evidência e calcular `SUCCESS` / `PARTIAL_SUCCESS` / `FAILED` |
| LLM/presentation | transformar evidências em resposta sem apagar sucesso/falha individual |
