# Implementação prática — MCP Multi-Item

Este documento mostra como adicionar uma operação multi-item sem criar lógica paralela no agente e sem alterar desnecessariamente contratos já existentes.

## 1. Modele uma única operação lógica

```text
quero cancelar Produto A, Produto B e Produto C
```

A operação lógica continua sendo uma só. Não crie tools/intents por item nem loops no Agent.

## 2. Escolha o contrato natural da operação

### Opção A — parâmetro escalar

Use quando a interface já recebe um `subject`, `id`, `query` ou expressão que pode representar uma ou várias entidades:

```yaml
tools:
  cancelar_vas_avulso:
    args_schema:
      subject:
        type: string
```

Entrada:

```text
subject = "Produto A, Produto B, Produto C"
```

### Opção B — coleção explícita

Use quando a API/tool é naturalmente batch:

```yaml
tools:
  cancelar_produtos:
    args_schema:
      items:
        type: array
```

**Não transforme uma tool escalar em array apenas para obter suporte multi-item.**

## 3. Use a policy existente

Exemplo escalar:

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

Nenhuma chave específica de multi-item é necessária.

## 4. Canonicalize/expanda no validator quando necessário

Entrada:

```json
{"subject": "produto a, produto b, produto c"}
```

Saída possível:

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

O validator deve ser side-effect-free.

## 5. Não transforme uma falha individual em rejeição global

Caso:

```text
A = válido
B = inválido
C = válido
```

Com `fail_open: false`, isto bloquearia tudo:

```json
{"eligible": false, "reason": "B inválido"}
```

Quando A e C ainda podem ser executados, mantenha a transação globalmente elegível e preserve o estado individual dos itens.

## 6. Execute no MCP Server ou workflow

A tool/workflow pode receber `subject` e expandir internamente, ou receber `items[]` já canonicalizado.

### Backend com API unitária

```python
async def cancelar_produtos(items):
    results = []
    for item in items:
        try:
            response = await backend.cancel_one(item)
            results.append({"name": item["name"], "success": True, "response": response})
        except Exception as exc:
            results.append({"name": item["name"], "success": False, "error": str(exc)})
    return {"results": results}
```

O loop pertence ao **MCP Server/workflow**, não ao Agent.

## 7. Retorne `results[]` por item

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

```text
items_count            = 3
items_succeeded_count  = 2
items_failed_count     = 1
multi_item_status      = PARTIAL_SUCCESS
```

## 9. Workflow com etapa auxiliar

O resultado autoritativo da operação principal deve estar em:

```text
workflow.output[tool_name].results
```

Assim uma falha auxiliar posterior não apaga itens já concluídos.

## 10. Checklist do desenvolvedor

- [ ] existe uma única tool lógica para a operação;
- [ ] `tools.yaml` declara o contrato natural, escalar ou coleção;
- [ ] não existe requisito de `type: array` para habilitar multi-item;
- [ ] `tool_policies.yaml` mantém os `requires` reais do domínio;
- [ ] se um escalar representa vários itens, validator/tool/workflow faz a expansão;
- [ ] com `fail_open: false`, falha individual não bloqueia automaticamente todos os itens acionáveis;
- [ ] fan-out, se necessário, pertence ao MCP Server/workflow;
- [ ] a tool primária devolve `results[]`;
- [ ] cada item contém `success` ou `ok` booleano;
- [ ] sucessos parciais não são apagados por uma falha global posterior;
- [ ] a apresentação comunica sucesso/falha por item;
- [ ] não foi criado um segundo motor multi-item no Agent.

## 11. Testes mínimos recomendados

```text
1 item / sucesso
N itens / todos sucesso
N itens / sucesso parcial
N itens / todos falha
entrada escalar expandida para N itens
entrada batch explícita
item não canonicalizado
confirmação única para N itens
falha auxiliar após sucesso primário
replay/idempotência da mesma operação
```

Para detalhes do contrato interno do runtime, consulte `docs/MCP_MULTI_ITEM_DEVELOPER_GUIDE.md`.
