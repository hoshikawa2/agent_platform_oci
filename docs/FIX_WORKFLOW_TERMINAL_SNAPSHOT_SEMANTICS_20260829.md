# Correção: snapshot terminal não deve virar PAUSED sem interrupt real

## Problema

O `WorkflowRuntime` tratava qualquer `snapshot.next` truthy do LangGraph como evidência de pausa. Em alguns snapshots/checkpointers, o último nó de ação já havia terminado e sua transição ativa apontava para `END`, porém `snapshot.next` ainda continha trabalho estrutural interno. Como não havia `interrupt()`, o runtime fabricava um `pause={"node": current_node}` e devolvia `PAUSED`.

Efeito observado em `contestacao_tool`: `atualizar_status_sr` estava `COMPLETED`, mas o workflow era exposto como `PAUSED`, com `resume_tool=retomar_workflow`, impedindo o fechamento normal da evidência transacional.

## Regra corrigida

A precedência agora é:

1. Se existem payloads reais de `interrupt()` no snapshot: `PAUSED`.
2. Se não há interrupt e o `current_node` possui uma transição ativa para `END`: `COMPLETED`, mesmo que `snapshot.next` esteja truthy.
3. Se não há interrupt, o estado não é estruturalmente terminal e ainda existe `snapshot.next`: fail-closed (`FAILED`) com diagnóstico, em vez de inventar uma pausa.
4. Sem interrupt, sem pending work e sem anomalia: conclusão normal.

A mesma regra foi aplicada em `WorkflowRuntime.arun()` e `WorkflowRuntime.aresume()`.

## Por que não há hardcode

A detecção terminal usa exclusivamente a `WorkflowDefinition`, o `current_node` e as condições das edges. Não conhece `contestacao_tool`, `atualizar_status_sr`, TIM ou qualquer agente específico.

## Testes de regressão

`tests/unit/test_workflow_terminal_snapshot_semantics.py` cobre:

- `arun`: `snapshot.next` truthy + sem interrupt + edge ativa para `END` => `COMPLETED`;
- `aresume`: mesma condição => `COMPLETED`;
- interrupt real tem precedência e continua retornando `PAUSED`;
- pending work não terminal sem interrupt retorna `FAILED`, nunca uma pausa falsa.
