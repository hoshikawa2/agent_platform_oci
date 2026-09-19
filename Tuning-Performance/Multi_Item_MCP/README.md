# Multi-Item MCP

Capability de referência para operações MCP que precisam processar **mais de um item do mesmo tipo** em uma única intenção: produtos, pedidos, VAS, ativos, faturas, linhas, contratos ou recursos.

> Esta capability é **framework-native**. Ela não exige um motor multi-item dentro do agente e não adiciona novos atributos obrigatórios a `tools.yaml` ou `tool_policies.yaml`.

> **Importante:** multi-item não é definido por `type: array`. O parâmetro de entrada pode ser escalar (`subject`, `id`, `query`) ou uma coleção. O que torna a execução multi-item é a resolução/execução de vários itens e o retorno por item em `results[]`.

## Quando usar

Use quando o usuário puder solicitar, por exemplo:

```text
cancele Produto A, Produto B e Produto C
```

ou:

```text
consulte os pedidos 1001, 1002 e 1003
```

O desenvolvedor deve modelar **uma operação lógica**. O framework cuida de estado, confirmação e interpretação de resultados; validator/MCP Server/workflow cuidam da resolução e execução dos itens.

## Divisão de responsabilidades

```text
Agent
  seleciona a operação
  NÃO cria motor multi-item

      ↓

tools.yaml
  declara o contrato natural da operação
  pode ser escalar OU coleção
  NÃO exige chave multi_item

      ↓

tool_policies.yaml
  confirmação + requires + pre-validation
  NÃO possui sintaxe especial de multi-item

      ↓

MCP validator
  resolve/canonicaliza itens
  pode expandir subject/id/query em items[]
  pode preencher transaction_decision.resolved_arguments

      ↓

MCP tool / workflow
  executa 1 ou N itens
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

## Configuração mínima — padrão escalar

Este padrão é útil quando a interface natural já usa `subject` e o validator expande múltiplas entidades.

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

Nenhuma chave abaixo existe ou é necessária:

```yaml
multi_item: true
multi_item_strategy: partial
fan_out: framework
```

## Configuração alternativa — API batch

Quando a tool MCP recebe naturalmente uma coleção, `array/list` continua válido:

```yaml
args_schema:
  items:
    type: array
```

Isso é **uma opção de contrato**, não um pré-requisito para multi-item.

## Pre-validation e expansão de itens

Um `subject` escalar pode ser transformado em argumentos canônicos:

```json
{
  "eligible": true,
  "transaction_decision": {
    "resolved_arguments": {
      "subject": "Produto A, Produto B, Produto C",
      "items": [
        {"name": "Produto A", "id": "1001"},
        {"name": "Produto B", "id": "1002"},
        {"name": "Produto C", "id": "1003"}
      ]
    },
    "confirmation_message": "Você confirma o cancelamento de Produto A, Produto B e Produto C?"
  }
}
```

### Validação parcial

`eligible` é global. Com `fail_open: false`, não retorne `eligible: false` apenas porque um item falhou se outros ainda são acionáveis.

Padrão recomendado:

1. `eligible: true` enquanto houver pelo menos um item acionável;
2. preservar resolução/eligibilidade individual;
3. executar a operação primária;
4. produzir o resultado terminal individual em `results[]`.

## Resultado MCP esperado

```json
{
  "results": [
    {"name": "Produto A", "success": true},
    {"name": "Produto B", "success": false, "error": "not_found"},
    {"name": "Produto C", "success": true}
  ]
}
```

O framework deriva automaticamente `SUCCESS`, `PARTIAL_SUCCESS` ou `FAILED`.

## Uma operação lógica, sem N chamadas no agente

São válidos:

```text
Agent -> cancelar(subject="A, B, C") -> validator/workflow -> results[]
```

ou:

```text
Agent -> cancelar(items=[A,B,C]) -> MCP/workflow -> results[]
```

Se o backend possui apenas API unitária, o fan-out fica no MCP Server/workflow. Evite loop MCP de negócio dentro do agente.

## Workflow-backed tools

Quando a operação é implementada por workflow, o caminho preferencial do resultado primário é:

```text
workflow.output[tool_name].results
```

Uma falha posterior não deve apagar sucesso terminal de itens já executados.

## Documentação completa

- `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE.md` — guia canônico em português;
- `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE_en.md` — guia canônico em inglês;
- `templates/agent_template_backend/docs/MCP_MULTI_ITEM.md` — referência junto ao template;
- `specs/SPEC-010-Agent-Development.md` — regra arquitetural.

Para o passo a passo prático, leia `IMPLEMENTACAO_MULTI_ITEM_MCP.md`.
