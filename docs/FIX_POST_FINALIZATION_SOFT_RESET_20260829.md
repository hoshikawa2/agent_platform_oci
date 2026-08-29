# Soft reset operacional após finalização de workflow

Quando um workflow de domínio termina, a sessão conversacional permanece a mesma, mas o próximo turno deve iniciar uma nova interação operacional.

A correção introduz um marcador `operational_context_boundary_pending` no fechamento do workflow. No primeiro turno subsequente, o marcador é consumido e o framework:

- mantém `session_id`, `session_key`, `conversation_key`, identidade e BusinessContext;
- preserva o histórico durável/checkpoint para auditoria;
- mantém Long-Term Memory;
- limpa `pending_domain_workflow`, `pending_tool_clarification`, `active_transaction`, tool calls, parâmetros pendentes, confirmação, pre-validation, route/intent/active_agent e demais latches operacionais;
- não executa route continuity do fluxo encerrado;
- não injeta ConversationSummaryMemory nem mensagens recentes do fluxo encerrado no primeiro turno após a fronteira;
- entrega apenas a nova mensagem ao contexto operacional desse turno.

O marcador de reset é de uso único e é desligado no `persist` do novo turno. A partir do turno seguinte, a nova interação pode novamente acumular seu próprio contexto curto, usando o mesmo identificador de sessão.
