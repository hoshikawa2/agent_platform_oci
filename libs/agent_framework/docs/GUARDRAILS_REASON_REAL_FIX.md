# Correção: `reason` real nos guardrails calibrados

Esta versão corrige o fallback local dos guardrails calibrados para não emitir razões genéricas como `mock PINJ calibrado`.

Mesmo quando `USE_MOCK_LLM=true`, os rails agora retornam uma razão operacional baseada no marcador ou padrão que disparou a decisão.

Exemplos:

- `PINJ`: informa o padrão determinístico de prompt injection/jailbreak detectado.
- `REVPREC`: informa o marcador de verbalização prematura encontrado.
- `AOFERTA`: informa o marcador de oferta proativa detectado.
- `TOX`: informa o padrão determinístico de toxicidade detectado.
- `OOS`: informa o marcador fora de escopo encontrado.
- `RAGSEC`, `DLEX_IN` e `DLEX_OUT`: informam o padrão local de risco quando o fallback local estiver ativo.

A arquitetura atual foi preservada:

- `GuardrailPipeline`
- `ParallelRailExecutor`
- emissão GRL
- execução paralela/fail-fast
- uso de `llm_profiles.yaml` via LLM do framework quando `USE_MOCK_LLM=false`
