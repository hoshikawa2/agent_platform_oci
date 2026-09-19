# Implementação prática — MCP Multi-Item

Este documento mostra o caminho mínimo para adicionar uma operação multi-item a um agente sem criar lógica paralela no código do agente.

## 1. Modele uma única operação lógica

Exemplo de requisito:

```text
quero cancelar Produto A, Produto B e Produto C
```

A operação lógica deve continuar sendo uma só:

```text
cancelar_produtos
```

Não crie `cancelar_produto_1`, `cancelar_produto_2`, loops no agent ou intents artificiais por item.

## 2. Declare a coleção em `tools.yaml`

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
        description: Lista de produtos a cancelar.
        user_prompt: Quais produtos deseja cancelar?
```

Também é aceito `type: list` quando o projeto já usa essa forma.

## 3. Use a policy transacional existente

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

Nenhuma chave específica de multi-item é necessária.

## 4. Canonicalize os itens no MCP validator

Entrada possível:

```json
{
  "items": ["produto a", "produto b", "produto c"]
}
```

Saída recomendada:

```json
{
  "eligible": true,
  "status": "ELIGIBLE",
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

O validator deve ser side-effect-free.

## 5. Não transforme uma falha individual em rejeição global

Caso:

```text
A = válido
B = inválido
C = válido
```

Se A e C ainda podem ser executados, não use simplesmente:

```json
{
  "eligible": false,
  "reason": "B inválido"
}
```

Isso encerraria a transação inteira.

Prefira manter a transação elegível quando houver item acionável e preservar informação suficiente para a tool primária produzir o resultado final por item.

## 6. Execute a coleção no MCP Server ou workflow

### Backend com API batch

```python
async def cancelar_produtos(items):
    response = await backend.cancel_batch(items)
    return normalize_results(response)
```

### Backend com API apenas unitária

```python
async def cancelar_produtos(items):
    results = []
    for item in items:
        try:
            response = await backend.cancel_one(item)
            results.append({
                "name": item["name"],
                "success": True,
                "response": response,
            })
        except Exception as exc:
            results.append({
                "name": item["name"],
                "success": False,
                "error": str(exc),
            })
    return {"results": results}
```

O loop acima pertence ao MCP/workflow, **não ao Agent**.

## 7. Retorne `results[]` por item

Contrato mínimo:

```json
{
  "results": [
    {"name": "Produto A", "success": true},
    {"name": "Produto B", "success": false, "error": "not_found"},
    {"name": "Produto C", "success": true}
  ]
}
```

O framework aceita `success` ou `ok` booleano por item.

## 8. Resultado interpretado pelo framework

No exemplo anterior:

```text
items_count            = 3
items_succeeded_count  = 2
items_failed_count     = 1
multi_item_status      = PARTIAL_SUCCESS
```

O framework preserva os resultados terminais e fornece esse contexto para composição/presentation.

## 9. Workflow com etapa auxiliar

Estrutura recomendada:

```json
{
  "status": "COMPLETED",
  "output": {
    "cancelar_produtos": {
      "results": [
        {"name": "A", "success": true},
        {"name": "B", "success": true}
      ]
    },
    "registrar_analitica": {
      "success": false,
      "error": "analytics unavailable"
    }
  }
}
```

O resultado autoritativo da operação principal deve estar em:

```text
workflow.output[cancelar_produtos].results
```

Assim uma falha auxiliar não converte A e B em falha operacional.

## 10. Checklist do desenvolvedor

Antes de criar código adicional, verifique:

- [ ] existe uma única tool lógica para a operação;
- [ ] a coleção está declarada como `array` ou `list` em `tools.yaml`;
- [ ] confirmação/pre-validation usam `tool_policies.yaml` existente;
- [ ] canonicalização pertence ao MCP validator;
- [ ] fan-out, se necessário, pertence ao MCP Server/workflow;
- [ ] a tool primária devolve `results[]`;
- [ ] cada item contém `success` ou `ok` booleano;
- [ ] sucessos parciais não são apagados por uma falha global posterior;
- [ ] a apresentação comunica sucesso/falha por item;
- [ ] não foi criado um segundo motor multi-item no Agent.

## 11. Testes mínimos recomendados

Cubra ao menos:

```text
1 item / sucesso
N itens / todos sucesso
N itens / sucesso parcial
N itens / todos falha
item não canonicalizado
confirmação única para N itens
falha auxiliar após sucesso primário
replay/idempotência da mesma operação
```

Para detalhes do contrato interno do runtime, consulte `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE.md`.
