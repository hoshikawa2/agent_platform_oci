# Observability Code Mapping

## Objetivo

O framework separa o **identificador semântico interno** do **identificador contratual externo** usado por observabilidade. Cada agente/deployment pode declarar sua própria tabela sem alterar guardrails, judges ou publishers.

Exemplo:

```yaml
version: "1"
mappings:
  guardrail.dlex_in: GRL.004
  guardrail.tox: GRL.005
```

Nesse exemplo, o componente continua internamente conhecido como `guardrail.dlex_in`, mas Langfuse/OTEL/EventBus recebem `GRL.004` como nome da observation/span/generation.

## Configuração

```dotenv
OBSERVABILITY_CODE_MAPPING_ENABLED=true
OBSERVABILITY_CODE_MAPPING_PATH=./config/observability_mapping.yaml
```

O core não contém mappings de cliente.

## Pontos de aplicação

O mapper atua antes do fan-out nos pontos comuns do framework:

1. `Telemetry.span()` — normaliza o nome antes do span OTEL, observation Langfuse e EventBus.
2. `Telemetry.generation_span()` — normaliza o nome antes da generation Langfuse e EventBus.
3. `Telemetry.event()` — normaliza o nome do evento antes de EventBus/Langfuse.
4. `AgentObserver.emit()` — normaliza `event_type` antes de Analytics, NOC/OTEL e EventBus.

Assim, o mapping não precisa ser duplicado em cada exporter/provider.

## Preservação do identificador interno

Para spans/generations mapeados:

- `observability_name_internal`: nome semântico original;
- `observability_name_mapped`: nome contratual;
- `observability_code_mapped: true`.

Para eventos estruturados:

- `event_code_internal`;
- `event_code_mapped`;
- `observability_code_mapped: true`.

Isso permite que o cliente filtre pelo contrato externo sem eliminar a informação útil para troubleshooting.

## Compatibilidade

- recurso opt-in;
- mapping desconhecido = passthrough;
- YAML ausente/inválido = passthrough com log;
- nenhuma substituição textual em payloads/prompts;
- o código interno de guardrails e judges não é renomeado;
- mappings pertencem ao agente/deployment, nunca ao core.

## Registry v2: ações e aliases

Além da forma escalar histórica, uma entrada pode declarar `label`, `action` e `aliases`.

```yaml
mappings:
  guardrail.revprec:
    action: retry
    aliases: [REVPREC, TIM_REVPREC]
```

`OutputSupervisor` e `ParallelRailExecutor` consultam a mesma instância de `ObservabilityCodeMapper` para resolver a ação de uma negação que não tenha ação mais específica. Precedência: `terminal_action` do rail, `on_deny` do rail, `action` do registry e por fim `BLOCK`.

A ausência de `label` torna a entrada action-only e não renomeia a observabilidade. A sintaxe `guardrail.x: GRL.004` continua suportada.
