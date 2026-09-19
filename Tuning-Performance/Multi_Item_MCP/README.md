# Multi-Item MCP

Capability de referência para operações MCP que precisam processar **mais de um item do mesmo tipo** em uma única intenção: produtos, pedidos, VAS, ativos, faturas, linhas, contratos ou recursos.

> Esta capability é **framework-native**. Ela não exige um motor multi-item dentro do agente e não adiciona novos atributos obrigatórios a `tools.yaml` ou `tool_policies.yaml`.

## Quando usar

Use quando o usuário puder solicitar, por exemplo:

```text
cancele Produto A, Produto B e Produto C
```

ou:

```text
consulte os pedidos 1001, 1002 e 1003
```

O desenvolvedor deve modelar **uma operação lógica** que receba a coleção. O framework cuida de estado, confirmação e interpretação de resultados; o MCP Server ou workflow de domínio cuida da execução dos itens.

## Divisão de responsabilidades

```text
Agent
  seleciona a operação
  NÃO cria motor multi-item

      ↓

tools.yaml
  declara array/list
  NÃO exige chave multi_item

      ↓

tool_policies.yaml
  confirmação + pre-validation
  usa o mesmo contrato transacional existente

      ↓

MCP validator
  resolve/canonicaliza os itens
  pode preencher transaction_decision.resolved_arguments

      ↓

MCP tool / workflow
  executa os itens
  devolve results[] com success/ok por item

      ↓

Agent Framework
  mantém estado
  controla confirmação
  interpreta results[]
  preserva evidência por item
  calcula SUCCESS / PARTIAL_SUCCESS / FAILED

      ↓

LLM / Presentation
  apresenta cada sucesso/falha
```

## Configuração mínima

### `tools.yaml`

O modo de configuração continua o mesmo. Declare o parâmetro como `array` ou `list`:

```yaml
tools:
  cancelar_produtos:
    description: Cancela um ou mais produtos.
    mcp_server: contas
    enabled: true
    tool_type: action
    confirmation_required: true
    requires: [items]
    args_schema:
      items:
        type: array
        label: os produtos
        description: Produtos solicitados pelo cliente.
        user_prompt: Informe quais produtos deseja cancelar.
```

Não é necessário criar configuração como:

```yaml
# NÃO EXISTE / NÃO É NECESSÁRIO
multi_item: true
multi_item_strategy: partial
fan_out: framework
```

### `tool_policies.yaml`

O contrato também continua o mesmo:

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

## Pre-validation e lista canônica

O validator pode transformar nomes informais em uma coleção canônica antes da confirmação:

```json
{
  "eligible": true,
  "transaction_decision": {
    "resolved_arguments": {
      "items": [
        {"name": "Produto A", "id": "1001"},
        {"name": "Produto B", "id": "1002"},
        {"name": "Produto C", "id": "1003"}
      ]
    },
    "target_tool": "cancelar_produtos",
    "confirmation_message": "Você confirma o cancelamento de Produto A, Produto B e Produto C?"
  }
}
```

### Validação parcial

`eligible` é global para a transação. Portanto, se pelo menos um item puder ser processado, o validator **não deve reprovar o lote inteiro apenas porque outro item falhou**.

Padrão recomendado:

1. `eligible: true` quando existe pelo menos um item acionável;
2. preservar/canonicalizar todos os itens necessários em `resolved_arguments`;
3. executar a operação primária;
4. retornar o resultado terminal individual em `results[]`.

Se nenhum item puder ser processado, `eligible: false` é apropriado.

## Resultado MCP esperado

A tool primária deve retornar `results[]` com `success` ou `ok` booleano por item:

```json
{
  "results": [
    {"name": "Produto A", "success": true},
    {"name": "Produto B", "success": false, "error": "not_found"},
    {"name": "Produto C", "success": true}
  ]
}
```

O framework deriva automaticamente:

```text
PARTIAL_SUCCESS
2 succeeded
1 failed
```

Estados possíveis:

| Resultado dos itens | Status do framework |
|---|---|
| todos concluídos | `SUCCESS` |
| alguns concluídos e alguns falharam | `PARTIAL_SUCCESS` |
| todos falharam | `FAILED` |

## Uma chamada lógica, não N chamadas no agente

Se o backend suporta batch, prefira:

```text
Agent -> cancelar_produtos(items=[A,B,C]) -> MCP
```

Se o backend possui apenas API unitária, o fan-out deve ficar encapsulado no MCP Server ou no workflow de domínio:

```text
Agent -> cancelar_produtos(items=[A,B,C])
                   |
                   v
              MCP/workflow
               /   |   \
              A    B    C
               \   |   /
                results[]
```

Evite:

```python
# NÃO: lógica multi-item dentro do agente
for item in items:
    await tool_router.call("cancelar_produto", {"item": item})
```

## Workflow-backed tools

Quando a operação é implementada por workflow, o caminho preferencial do resultado primário é:

```text
workflow.output[tool_name].results
```

Isso permite distinguir a operação primária de etapas auxiliares. Uma falha posterior não deve apagar o sucesso terminal de itens já executados.

## Documentação completa

Consulte também:

- `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE.md` — guia canônico em português;
- `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE_en.md` — guia canônico em inglês;
- `templates/agent_template_backend/docs/MCP_MULTI_ITEM.md` — referência junto ao template;
- `specs/SPEC-010-Agent-Development.md` — regra arquitetural de desenvolvimento.

Para um passo a passo prático, leia `IMPLEMENTACAO_MULTI_ITEM_MCP.md` nesta pasta.
