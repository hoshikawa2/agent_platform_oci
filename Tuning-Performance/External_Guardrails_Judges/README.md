# External Guardrails / Judges

Este exemplo parte do `agent_template_backend` e demonstra a composição de componentes nativos com políticas pertencentes ao agente.

- `type: external` ativa import dinâmico somente para o componente declarado.
- Guardrail/judge síncrono roda em worker thread via `asyncio.to_thread`.
- Implementação `async` roda concorrente no event loop.
- O framework não importa `app.extensions.*` por padrão.
- Use códigos/names próprios do domínio; não sobrescreva semanticamente o genérico sem deixar a substituição explícita no YAML.

Veja também `agent_framework_oci/docs/EXTERNAL_GUARDRAILS_JUDGES.md` e `docs/EXTERNAL_GUARDRAILS_JUDGES.md` no Contas.
