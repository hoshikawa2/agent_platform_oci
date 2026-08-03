# Validação — integração transacional Agent Template Backend / MCP

## Correções implementadas

- `mcp_tools` é tratado como allowlist, não como lista de execução automática.
- Tools `read_only` continuam disponíveis para enriquecimento de contexto.
- Somente uma tool transacional compatível com a solicitação é selecionada.
- `require_confirmation: true` cria `pending_tool_call` e `AWAITING_CONFIRMATION`.
- O turno de confirmação executa a chamada pendente com `confirmed: true`.
- O estado expõe `selected_tool_call`, `tool_policy_result`, `confirmation_required`, `confirmation_received` e `transaction_status`.
- `reason` foi padronizado entre catálogo, mapping e FastMCP Retail.
- Pedido `123` e `PED-ENTREGUE` retornam status `ENTREGUE` para testes positivos.
- A keyword genérica `produto` foi removida da intenção Telecom para não capturar devoluções Retail.
- Templates `Normal` e `Route_Stickness` em `Tuning-Performance` foram atualizados.

## Teste recomendado

1. `Quero devolver o pedido 123 porque me arrependi da compra.`
2. Esperado: `transaction_status=AWAITING_CONFIRMATION`, sem execução de `solicitar_devolucao`.
3. `Sim, confirmo a devolução.`
4. Esperado: `transaction_status=COMPLETED` e execução única de `solicitar_devolucao`.

## Resultado automatizado

```text
7 passed
```
