# Guardrails calibrados adaptados ao framework

## Objetivo

Este pacote mantém a arquitetura atual do `agent_framework` e substitui a calibração interna dos rails pela lógica do pacote `guardrails.zip` anexado.

Foram preservados:

- `GuardrailPipeline`
- execução paralela/fail-fast via `ParallelRailExecutor`
- emissão de eventos GRL e eventos nomeados por rail
- `OutputSupervisor`
- perfis dinâmicos de LLM (`guardrail` e `grl`)
- gravação do modelo no Langfuse pelo provider do próprio framework

## O que mudou

A lógica calibrada foi adicionada em:

```text
src/agent_framework/guardrails/calibrated/
```

A ponte com o LLM do framework foi adicionada em:

```text
src/agent_framework/guardrails/framework_llm_client.py
```

As classes públicas foram preservadas em:

```text
src/agent_framework/guardrails/rails.py
```

## Rails calibrados integrados

Input:

- `INPUT_SIZE`
- `MSK`
- `TOX`
- `PINJ`
- `VLOOP`
- `DLEX_IN`
- `OOS` opcional via `GUARDRAIL_OOS_ENABLED=true`

Output:

- `MSK`
- `TOXOUT`
- `CMP`
- `AOFERTA`
- `REVPREC`
- `DLEX_OUT`
- `GND`
- `ALUC_RISK`

Retrieval:

- `RET_REL`
- `RAGSEC`
- `MSK`

## LLM e Langfuse

Os rails LLM não criam outro cliente fora do framework. Eles usam o `llm` passado ao `GuardrailPipeline`, chamando:

```python
llm.ainvoke(..., profile_name="guardrail" ou "grl", component_name="guardrail.<code>")
```

Assim, o modelo usado por `PINJ`, `OOS`, `AOFERTA`, `REVPREC`, `RAGSEC`, etc. continua aparecendo corretamente no Langfuse conforme a instrumentação atual do framework.

## Modo mock

Quando `USE_MOCK_LLM=true`, os rails LLM usam heurísticas locais calibradas para desenvolvimento/teste rápido.

Para validar com LLM real:

```bash
export USE_MOCK_LLM=false
```

