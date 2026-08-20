# Route Stickiness — deterministic intent shift (v14)

## Problema corrigido

Uma keyword multi-token como `cancelar pedido` não era reconhecida em frases como `quero cancelar meu pedido`. O match legado usava substring literal; assim, a keyword genérica `pedido` podia manter `retail_order_tracking` e a continuidade reutilizava a intent anterior.

## Correção

O `EnterpriseRouter` agora possui um segundo estágio determinístico para keywords multi-token: ordered-token matching com até três tokens intermediários. Não há chamada adicional de LLM.

Exemplos reconhecidos pela keyword configurada `cancelar pedido`:

- `quero cancelar meu pedido`
- `quero cancelar o meu pedido`
- `pode cancelar esse pedido`
- `gostaria de cancelar meu pedido`

Quando esse match identifica uma intent diferente da ativa, ele preempta a route stickiness antes do LLM de continuidade.

Metadados de auditoria esperados:

```json
{
  "method": "keyword",
  "intent": "retail_order_cancel",
  "metadata": {
    "matched_keyword": "cancelar pedido",
    "keyword_match_strategy": "ordered_tokens",
    "route_stickiness_preempted": true,
    "previous_intent": "retail_order_tracking"
  }
}
```

## Custo de LLM

Para mudança explícita reconhecida deterministicamente, o classificador LLM de continuity não é chamado. Para mensagens sem sinal explícito, a Route Stickiness continua com o comportamento configurado.

## Regressão

Testes cobrem mudança `retail_order_tracking -> retail_order_cancel` no mesmo `orders_agent`, inclusive com palavras intermediárias. A suíte relacionada passou com 18 testes.
