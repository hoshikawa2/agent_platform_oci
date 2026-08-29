# Confirmação Transacional Semântica

Este template suporta confirmação transacional em duas camadas: primeiro um parser determinístico para `sim`/`não` e equivalentes explícitos; somente quando ele não consegue decidir, o framework usa um classificador semântico configurado em `config/routing.yaml`.

A configuração `router.transaction_confirmation.semantic_fallback` usa três classes: `SIM`, `NAO` e `CONTINUAR`. O prompt pode usar `{{ pending_prompt }}`, `{{ relevant_conversation_context }}`, `{{ user_input }}` e `{{ allowed_values }}`. O histórico injetado é apenas contexto de interpretação; não substitui validação de negócio ou evidência MCP.

Exemplo: após `Você confirma o cancelamento do serviço Tamboro Mensal?`, a frase `isso mesmo, pode confirmar` pode ser classificada como `SIM`. Já `mas qual é o valor?` deve ser `CONTINUAR`, portanto não executa a ação por confirmação.

Entradas explícitas já suportadas continuam no caminho determinístico e não geram custo adicional de LLM. Em observabilidade, o fallback usa `transaction.confirmation.semantic_classifier` e o `route_decision.metadata` informa `transaction_confirmation_source: semantic`.

Consulte `docs/developer/pt/03_transaction_workflows_and_state.md` do framework para o contrato completo e exemplos.
