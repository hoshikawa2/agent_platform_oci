# Correção: precedência de handoff sobre workflow pausado

## Problema

Quando um workflow conversacional estava em `WORKFLOW_PAUSED` com `expected_input`
enumerado e `semantic_classifier`, uma solicitação explícita de atendimento humano podia
ser absorvida pelo classificador local do workflow (por exemplo `SIM/NAO/CONTINUAR`).

Exemplo de regressão:

1. cliente pede explicação de fatura;
2. workflow pausa perguntando se a dúvida foi resolvida;
3. cliente diz `quero falar com um atendente`;
4. a frase era classificada como valor do `expected_input`, em vez de acionar handoff.

## Regra de precedência corrigida

A ordem passa a ser:

1. `expected_input` determinístico continua com precedência absoluta (`sim`, `não`, etc.);
2. se não houver match determinístico, o framework verifica exclusivamente o controle global
   `HUMAN_HANDOFF` usando o classificador semântico de continuidade já existente;
3. se não houver handoff, o `semantic_classifier` declarativo do workflow continua sendo a
   autoridade sobre a mensagem;
4. `CONTINUE`, `ROUTE` e `END_SESSION` encontrados no probe global são ignorados nessa etapa;
5. as regras normais de transação e intent shift permanecem inalteradas.

Assim, `quero falar com um atendente` não é tratado como `intent_shift`: é um comando global
de controle de sessão. A correção não cria lista de palavras nem regex de handoff.

## Observabilidade

Quando o handoff preempta um workflow pausado, a decisão contém:

- `session_control=HUMAN_HANDOFF`;
- `global_control_preempted_workflow=true`;
- `workflow_interruption=human_handoff`;
- `interrupted_workflow_name`;
- `interrupted_workflow_execution_id`.

## Testes

Foram adicionados testes para garantir que:

- pedido explícito de atendente preempta `expected_input.semantic_classifier`;
- resposta determinística `sim` continua retomando o workflow e não é roubada pelo probe global.

Também foram executadas as suítes de regressão de transação/intent shift para confirmar que a
mudança não altera a precedência existente de coleta de parâmetros e confirmação transacional.
