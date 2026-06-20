# Remoção do LEGACY_OUTPUT_GUARDRAIL

`LEGACY_OUTPUT_GUARDRAIL` era um sinal de compatibilidade associado ao guardrail LLM genérico/catch-all do pipeline antigo.

Na arquitetura atual, os rails calibrados já executam suas próprias decisões e emitem GRL com códigos de negócio específicos, por exemplo `PINJ`, `TOX`, `REVPREC`, `AOFERTA`, `DLEX_OUT` e `RAGSEC`.

Por isso, o emit legado foi removido/suprimido para evitar ruído e duplicidade no Langfuse.

## Regra atual

- Mantém `GRL.001` a `GRL.009` para ciclo e resultado do pipeline.
- Mantém eventos nomeados dos rails calibrados, como `GRL.REVPREC` e `guardrail.output.REVPREC.completed`.
- Suprime eventos genéricos/legados: `LEGACY_OUTPUT_GUARDRAIL`, `LLM_GUARDRAIL` e `LLM_GRL`.
- Remove o auto-append do guardrail LLM genérico controlado por `ENABLE_LLM_GUARDRAIL`.

O uso de LLM permanece nos rails calibrados que precisam dele, usando `llm_profiles.yaml` com os profiles `guardrail` e `grl`.
