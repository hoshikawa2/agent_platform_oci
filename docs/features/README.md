# Feature Guide — agent_framework_oci

Guia consolidado e bilíngue das principais capabilities horizontais do framework. Cada página contém **Português (PT-BR)** e **English (EN)** no mesmo arquivo.

Consolidated bilingual guide for the framework's main horizontal capabilities. Each page contains **Portuguese (PT-BR)** and **English (EN)** in the same file.

| # | Feature |
|---:|---|
| 01 | [Autenticação / Authentication](01_authentication.md) |
| 02 | [Workflow Transacional Determinístico / Deterministic Transactional Workflow](02_deterministic_transactional_workflow.md) |
| 03 | [Composição por LLM Solicitada pelo Domínio / Domain Requested LLM Composition](03_domain_requested_llm_composition.md) |
| 04 | [RAG Solicitado pelo Domínio / Domain Requested RAG](04_domain_requested_rag.md) |
| 05 | [Memória de Longo Prazo / Long Term Memory](05_long_term_memory.md) |
| 06 | [Regressão Offline de Workflow / Offline Workflow Regression](06_offline_workflow_regression.md) |
| 07 | [Pause / Resume de Workflow / Pause / Resume Workflow](07_pause_resume_workflow.md) |
| 08 | [Aderência de Rota / Route Stickiness](08_route_stickiness.md) |
| 09 | [Replay em Interrupções de Voz / Voice Interruption Replay](09_voice_interruption_replay.md) |
| 10 | [Recuperação de Erro em Workflow / Workflow Error Recovery](10_workflow_error_recovery.md) |
| 11 | [Clarificação / Clarification](11_clarification.md) |
| 12 | [Idempotência Durável / Durable Idempotency](12_durable_idempotency.md) |
| 13 | [Estados Transacionais Dinâmicos / Dynamic Transaction States](13_dynamic_transaction_states.md) |
| 14 | [Replay Após Finalização / Post Finalization Replay](14_post_finalization_replay.md) |
| 15 | [Guardrails de Retrieval e Tools / Retrieval / Tool Guardrails](15_retrieval_tool_guardrails.md) |

## Mapa conceitual / Conceptual map

```text
LLM
│
├── Conversation
│   ├── Clarification
│   ├── Route Stickiness
│   └── Long Term Memory
│
├── Knowledge
│   ├── Domain Requested RAG
│   └── Retrieval Guardrails
│
├── Transactions
│   ├── Deterministic Transactional Workflow
│   ├── Pause / Resume
│   ├── Dynamic Transaction States
│   ├── Durable Idempotency
│   └── Workflow Error Recovery
│
├── Response
│   └── Domain Requested LLM Composition
│
├── Voice
│   ├── Voice Interruption Replay
│   └── Post Finalization Replay
│
└── Platform
    ├── Authentication
    └── Offline Workflow Regression
```

## Princípio de arquitetura / Architecture principle

**PT-BR:** o LLM entende e redige; o framework controla estado, segurança, memória, roteamento e transações; o domínio contém regras específicas de negócio.

**EN:** the LLM understands and writes; the framework controls state, security, memory, routing, and transactions; the domain contains business-specific rules.
