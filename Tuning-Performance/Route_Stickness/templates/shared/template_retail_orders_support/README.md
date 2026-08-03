# Template 2 — Retail/E-commerce: Pedidos + Suporte

Este template demonstra outro uso do mesmo framework, com dois agentes diferentes:

- `OrdersAgent`: status de pedido, entrega, troca, devolução e rastreamento.
- `SupportAgent`: problemas de acesso, cadastro, pagamento, cupom e atendimento geral.

A ideia é mostrar que o framework não é dependente de telecom. O desenvolvedor troca apenas:

- intents em `routing.yaml`;
- prompts dos agentes;
- tools de negócio;
- estados do workflow.

O core de LangGraph, guardrails, judges, supervisor, Langfuse, OCI Generative AI e sessão permanece igual.
