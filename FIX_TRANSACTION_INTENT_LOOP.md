# Correção: escape de estado transacional / mudança de intenção

Correção aplicada em 2026-08-20 para impedir que uma sessão fique presa em `COLLECTING_PARAMETERS` ou `AWAITING_CONFIRMATION` quando o usuário muda explicitamente de assunto.

## Comportamento corrigido

Antes:

1. uma transação entrava em `COLLECTING_PARAMETERS`;
2. `next_state` forçava o mesmo agente via `state_policies`;
3. toda mensagem seguinte era tratada como tentativa de preencher o parâmetro faltante;
4. uma nova intenção como `quais sao meus servicos` permanecia presa no fluxo anterior.

Agora:

- o `EnterpriseRouter` verifica mudança explícita de intenção antes de aplicar o lock de estado;
- keyword explícita tem prioridade;
- quando necessário, o LLM router pode detectar mudança com confiança >= `router.confidence_threshold`;
- a decisão recebe `metadata.transaction_interruption=intent_shift`;
- o runtime encerra a transação pendente como `CANCELLED`, limpa `next_state`, parâmetros e latches, e prossegue com a nova intent;
- cancelamentos explícitos como `cancele essa operação anterior` funcionam também durante `COLLECTING_PARAMETERS`.

## Testes adicionados

- mudança de intent durante `COLLECTING_PARAMETERS`;
- resposta curta/baixa confiança permanece na transação;
- cancelamento explícito durante coleta de parâmetros;
- limpeza do estado transacional antes de executar a nova intent.

Testes focados: 19 passed.
