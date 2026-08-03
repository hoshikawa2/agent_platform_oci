# Correção — mudança de consulta para ação transacional

## Problema

Após `consultar pedido 123`, a mensagem `Quero devolver o pedido 123` podia permanecer no `orders_agent` por route stickiness. Como a intent anterior só expunha tools de consulta, o runtime executava novamente `consultar_pedido` e a resposta direta repetia o status do pedido.

## Correções

- Keywords explícitas configuradas no `routing.yaml` podem preemptar a route stickiness quando apontam para outra intent/agente.
- `retail_support_exchange_return` passa a ter prioridade maior que `retail_order_tracking` para mensagens de troca/devolução.
- Tools transacionais declaram `selection_keywords` no `tools.yaml`.
- A resposta direta read-only é bloqueada quando a mensagem contém uma ação transacional registrada, mesmo que a intent anterior ainda esteja ativa.
- A seleção da action tool usa configuração, não aliases de domínio fixos no runtime.

## Fluxo esperado

1. `consultar pedido 123` → `orders_agent` → `consultar_pedido` → resposta direta.
2. `Quero devolver o pedido 123` → preempção da stickiness → `support_agent` / `retail_support_exchange_return`.
3. `consultar_pedido` valida o pedido.
4. `solicitar_devolucao` é selecionada e, com confirmação obrigatória, gera `AWAITING_CONFIRMATION`.
5. `Sim, confirmo` executa a action tool uma única vez.
