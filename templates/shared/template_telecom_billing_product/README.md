# Template 1 — Telecom: Faturas + Produtos

Este template demonstra dois agentes especializados:

- `BillingAgent`: dúvidas de fatura, cobrança, vencimento e segunda via.
- `ProductAgent`: dúvidas de plano, pacote, VAS, roaming e benefícios.

O roteamento é definido por `config/routing.yaml` e usa:

1. política por estado;
2. keywords/intents;
3. LLM router opcional;
4. fallback.

Use este template quando o atendimento tiver domínios de negócio separados mas precisar manter uma única sessão conversacional.
