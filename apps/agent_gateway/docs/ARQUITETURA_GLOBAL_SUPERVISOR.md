# Arquitetura — Global Supervisor

```text
Usuário / Frontend
        │
        ▼
┌───────────────────────────────┐
│ Agent Gateway                 │
│ Global Supervisor             │
│                               │
│ - Router por regras           │
│ - Supervisor via LLM          │
│ - Híbrido stateful            │
│ - Handoff entre backends      │
└───────────────┬───────────────┘
                │
      ┌─────────┼─────────┬────────────┐
      ▼         ▼         ▼            ▼
Backend      Backend   Backend     Backend
Contas       Ofertas   Suporte     Cobrança
```

Cada backend continua sendo um projeto independente, com seus próprios agentes, prompts, MCPs e deploy, mas todos usam a mesma biblioteca `agent_framework`.

## Estado global

O Gateway mantém um `active_backend` por `session_id`. No modo `hybrid`, mensagens curtas como "e esse valor?" continuam no backend ativo sem chamar LLM.

## Memória compartilhada

Para produção, configure os backends para usar o mesmo Session/Memory/Checkpoint Repository, preferencialmente Autonomous DB, Oracle, MongoDB ou Redis + DB.
