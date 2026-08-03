# Judges obrigatórios em interações transacionais

## Problema

Mesmo com `always_run_for_transactional: true`, os judges podiam ser ignorados
pela amostragem porque o nó `judge` enviava apenas `context`, `route`, `intent` e
`mcp_results`. Os campos transacionais produzidos pelo runtime não chegavam ao
`JudgePipeline`.

## Correção

O nó `judge` agora repassa:

- `transaction_status`
- `confirmation_required`
- `confirmation_received`
- `tool_policy_result`
- `selected_tool_call`
- `pending_tool_call`
- `mcp_results` como evidência

O `JudgePipeline` detecta transações por múltiplos sinais e avalia
`always_run_for_transactional` antes de aplicar `sample_rate`.

Com a configuração abaixo, consultas comuns continuam sendo amostradas em 25%,
mas turnos `AWAITING_CONFIRMATION`, `COMPLETED`, `FAILED` ou `CANCELLED` executam
os judges sempre.

```yaml
enabled: true
sample_rate: 0.25
always_run_for_transactional: true
```
