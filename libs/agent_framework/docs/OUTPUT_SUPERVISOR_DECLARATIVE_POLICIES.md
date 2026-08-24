# OutputSupervisor sem taxonomia contratual hardcoded

## Objetivo

O `OutputSupervisor` do framework trabalha somente com eventos semânticos e ações de runtime. Códigos contratuais externos/numerados pertencem exclusivamente ao `ObservabilityCodeMapper` configurado pelo agente/deployment.

## Eventos internos

Exemplos de eventos internos:

```text
guardrail.output_supervisor.started
guardrail.result.allow
guardrail.result.block
guardrail.result.retry
guardrail.output.<rail>.completed
guardrail.output_supervisor.completed
```

Se um cliente exigir códigos próprios, configure `config/observability_mapping.yaml`. O supervisor não conhece a taxonomia externa.

## Ação quando um rail nega

O framework não decide mais a ação procurando nomes específicos de rails. A ação pode vir do próprio resultado:

```python
metadata={"terminal_action": "retry"}
```

ou do YAML:

```yaml
output:
  - code: MY_VALIDATION
    enabled: true
    on_deny: retry
```

Valores suportados são os valores de `RailAction`, como `block`, `retry` e `handover`.

## Remediação por rewrite

Rewrite também é uma capacidade genérica. O rail/policy declara a remediação:

```yaml
output:
  - code: MY_WORDING_POLICY
    enabled: true
    on_block:
      type: rewrite
      max_attempts: 1
      prompt_id: FALLBACK
      profile_name: grl
      component_name: guardrail.wording.rewrite
```

O supervisor não verifica se o código é `FRASEOLOGIA` ou qualquer outro nome. Um guardrail externo do agente pode usar exatamente o mesmo contrato.

## Mensagens de UX

Mensagens de fallback/handover pertencem ao agente:

```yaml
output_supervisor:
  max_retries: 3
  fallback_message: "..."
  handover_message: "..."
```

Assim o framework não precisa conhecer idioma, marca ou fraseologia do atendimento.

## Contas

O Contas preserva seu comportamento atual:

- `TIM_REVPREC` declara `terminal_action=retry` no próprio rail externo;
- `CMP` está configurado com `on_deny: retry`;
- `TIM_FRASEOLOGIA`, quando habilitado, declara remediação `rewrite` no agente;
- textos de fallback/handover ficam no `config/guardrails.yaml` do Contas.

## Compatibilidade

Rails que retornam apenas `allowed=false` e não declaram policy continuam em `block`, que é o fail-closed genérico. Não há mais inferência de ação pelo nome do rail.
