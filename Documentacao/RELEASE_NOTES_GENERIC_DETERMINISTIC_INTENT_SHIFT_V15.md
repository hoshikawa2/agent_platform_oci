# Release Notes — Generic Deterministic Intent Shift v15

## Problema corrigido

A Route Stickiness podia preservar a intent anterior quando a nova mensagem correspondia a uma intent configurada no `routing.yaml`, mas a frase do usuário omitia conectores curtos presentes na keyword configurada.

Exemplo real de configuração:

- keyword: `qual é o meu plano`
- mensagem: `qual o meu plano`

A classificação determinística não reconhecia a nova intent e a continuity acabava mantendo a intent anterior.

## Correção

O `EnterpriseRouter` continua usando, nesta ordem:

1. match exato;
2. sequência completa de tokens com palavras inseridas (`ordered_tokens`);
3. sequência de tokens informativos tolerando a omissão de conectores curtos presentes na keyword (`ordered_content_tokens`).

A terceira estratégia ignora, somente no lado da keyword, tokens de até dois caracteres e exige pelo menos dois tokens informativos. Não há nomes de intents, agentes, domínios ou verbos de negócio hardcoded.

Assim, a solução é dirigida integralmente pelas intents carregadas do `routing.yaml` da aplicação.

## Precedência sobre Route Stickiness

Quando o candidato determinístico encontrado é diferente da intent ativa, ele preempta a stickiness e retorna:

- `route_stickiness_preempted: true`
- `previous_agent`
- `previous_intent`
- `keyword_match_strategy`

A continuity LLM não é chamada nesse caminho.

## Casos cobertos

### Mesmo agente, nova intent

`retail_order_tracking` -> `quero cancelar meu pedido` -> `retail_order_cancel`

### Mesmo agente, tools diferentes

`contas_invoice_query` -> `qual o meu plano` -> `contas_plan_information`

Mesmo que ambas as intents usem `faturas_agent`, as tools mudam de `consultar_faturas` para `consultar_plano`.
