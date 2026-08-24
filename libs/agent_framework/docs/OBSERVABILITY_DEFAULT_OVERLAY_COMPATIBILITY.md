# Observability default registry + agent overlay

## Objetivo

O `agent_framework_oci` carrega um registry default de observabilidade e políticas de guardrail **sempre por padrão**. Esse registry reproduz o comportamento histórico que antes estava codificado em Python (`GRL.001..GRL.009`, decisões de `REVPREC/CMP/SCO/GND`, handover e rewrite de `FRASEOLOGIA`).

Com isso, um agente legado pode substituir apenas a versão do framework e continuar funcionando sem criar `observability_mapping.yaml` nem declarar novas variáveis.

## Fontes e precedência

1. `agent_framework/config/observability_mapping.yaml` — default interno do framework, carregado por padrão.
2. `OBSERVABILITY_CODE_MAPPING_PATH` — mapping opcional do agente/deployment, aplicado como overlay quando `OBSERVABILITY_CODE_MAPPING_ENABLED=true`.

O overlay é feito por chave canônica. Uma chave declarada pelo agente substitui a entrada default com a mesma chave; todas as demais entradas default continuam disponíveis.

### Exemplo

Default do framework:

```yaml
guardrail.dlex_in:
  label: GRL.DLEX_IN
  aliases: [DLEX_IN]
```

Contas:

```yaml
guardrail.dlex_in:
  label: GRL.004
  aliases: [DLEX_IN]
```

Registry efetivo do Contas:

- `guardrail.dlex_in` / `DLEX_IN` -> `GRL.004` (override do agente)
- `REVPREC` -> `retry` (herdado do framework)
- `CMP` -> `retry` (herdado do framework)
- `guardrail.result.block` -> `GRL.004` (herdado do framework)

## Compatibilidade de agentes antigos

Sem qualquer configuração nova:

```text
agente legado + framework novo
          |
          +-- default registry interno
                +-- GRL.001..GRL.009
                +-- REVPREC/CMP/SCO/GND -> retry
                +-- HANDOVER/ATH/HUMAN -> handover
                +-- FRASEOLOGIA -> remediation rewrite
```

Assim `OBSERVABILITY_CODE_MAPPING_ENABLED` controla apenas o overlay customizado do agente. Ele não desliga o registry base de compatibilidade.

## Escape hatch

Somente deployments que desejarem explicitamente remover a compatibilidade base podem usar:

```env
OBSERVABILITY_DEFAULT_MAPPING_ENABLED=false
```

Também é possível substituir o arquivo default para testes/deployments especiais:

```env
OBSERVABILITY_DEFAULT_MAPPING_PATH=/caminho/default.yaml
```

Essas opções não são necessárias para agentes normais.

## Packaging

O YAML default fica dentro do pacote Python em:

```text
agent_framework/config/observability_mapping.yaml
```

O `pyproject.toml` inclui explicitamente esse arquivo como package data, portanto ele também está presente quando o framework é instalado como wheel.
