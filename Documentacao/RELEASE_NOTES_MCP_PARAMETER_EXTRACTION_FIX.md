# Correção da extração de parâmetros MCP

## Problema corrigido

O bloco `extract` do `mcp_parameter_mapping.yaml` existia na configuração e na
documentação, mas não era executado pelo runtime. Além disso, valores do
Business Context podiam sobrescrever argumentos explícitos, fazendo
`contract_key` substituir o `order_id` informado pelo usuário.

## Correções

- implementação da extração genérica `strategy: llm` após a escolha da tool;
- suporte preservado para `strategy: month_name_pt`;
- profile dedicado `mcp_parameter_extraction`;
- telemetria `llm.mcp_parameter_extraction`;
- `extract` deixou de ser interpretado como mapeamento simples;
- argumentos explícitos/extraídos têm precedência sobre Business Context;
- remoção de `contract_key: order_id` dos templates;
- `order_id` configurado como `string`;
- atualização das variantes em `Tuning-Performance`.

## Resultado esperado

Para a mensagem `consultar pedido 123`, a chamada MCP deve receber
`order_id=123`, mesmo quando o Business Context contém outro `contract_key`.
