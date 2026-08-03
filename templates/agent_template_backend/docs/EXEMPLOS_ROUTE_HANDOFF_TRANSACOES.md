# Exemplos implementados no template

Este projeto entrega as capacidades transversais habilitadas como referência:

- route stickiness semântica com o perfil `route_continuity`;
- decisões `CONTINUE`, `ROUTE`, `HUMAN_HANDOFF` e `END_SESSION`;
- nós globais `human_handoff` e `end_session`;
- persistência de `active_agent`, `route_bypassed`, `continuity_signal` e controle de sessão;
- rejeição de novas mensagens depois de `session_ended=true`;
- políticas MCP `read_only` e `transactional` no backend;
- exemplo `solicitar_devolucao` com `require_confirmation: true`.

Para confirmar a transação, envie `confirmed: true` ou `confirmation: true` como booleano. Handoff e encerramento não chamam agentes de domínio nem MCP.

