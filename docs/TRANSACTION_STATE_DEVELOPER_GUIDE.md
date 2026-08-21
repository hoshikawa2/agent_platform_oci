# Guia do Desenvolvedor — Estado e Transações Multi-turno

Este documento define o contrato operacional para transações multi-turno no Agent Framework OCI. Ele é normativo para hosts e templates que utilizam `AgentRuntime`, checkpoint LangGraph e tools transacionais.

## 1. Objetivo

Uma transação pode atravessar vários turnos. Exemplo:

```text
Usuário: quero cancelar o pedido
Framework: informe o número do pedido
Usuário: PED-1001
Framework: confirma o cancelamento?
Usuário: sim
Framework: executa a tool
```

O framework precisa preservar a transação entre todos esses turnos sem depender de reclassificação por LLM, keyword routing ou reextração de parâmetros já obtidos.

## 2. Fonte canônica do estado transacional

O estado canônico da transação em andamento é `active_transaction`.

```python
active_transaction: dict[str, Any]
last_transaction: dict[str, Any]
```

Todo `AgentState` usado por um host que habilita transações multi-turno **DEVE** declarar os dois campos. Como o LangGraph usa o schema do state para persistência/checkpoint, um campo criado apenas dinamicamente pelo runtime não é um contrato durável seguro.

Exemplo mínimo:

```python
from typing import Any, TypedDict

class AgentState(TypedDict, total=False):
    # ...campos normais...
    selected_tool_call: dict[str, Any]
    pending_tool_call: dict[str, Any]
    active_transaction: dict[str, Any]
    last_transaction: dict[str, Any]
    transaction_status: str
    missing_parameters: list[str]
    confirmation_required: bool
    confirmation_received: bool
```

## 3. Papel de cada campo

| Campo | Papel | Regra |
|---|---|---|
| `active_transaction` | Fonte canônica da transação ativa | Deve sobreviver a checkpoint/resume enquanto a transação estiver ativa. |
| `last_transaction` | Snapshot da última transação terminal | Usado para auditoria, evidência e continuidade controlada; não reativa automaticamente a transação. |
| `transaction_status` | Estado lógico atual | Ex.: `COLLECTING_PARAMETERS`, `AWAITING_CONFIRMATION`, `COMPLETED`, `CANCELLED`, `OUT_OF_SCOPE`. |
| `missing_parameters` | Parâmetros ainda necessários | Deve refletir o estado canônico da transação, não apenas a mensagem corrente. |
| `selected_tool_call` | Estado auxiliar/compatibilidade | Não deve substituir `active_transaction` como fonte canônica. |
| `pending_tool_call` | Estado auxiliar/compatibilidade | Pode ser usado por compatibilidade, mas não como latch principal. |
| `next_state` | Orientação de roteamento do workflow | Ajuda a manter o nó/agente correto durante coleta/confirmação. |
| `transaction_pre_validation` | Evidência de pré-validação | Mantém resultado de validação antes da confirmação/execução. |
| `transaction_evidence` | Evidências da execução | Mantém resultados e trilha de execução da transação. |

## 4. Ciclo de vida recomendado

```text
IDLE
  ↓ intenção transacional
COLLECTING_PARAMETERS
  ↓ parâmetros completos
PRE_VALIDATION (quando configurado)
  ↓ elegível
AWAITING_CONFIRMATION
  ↓ confirmação positiva
EXECUTING
  ↓
COMPLETED
```

Saídas terminais alternativas:

```text
CANCELLED
OUT_OF_SCOPE
FAILED
```

O runtime pode representar algumas fases internamente sem um `transaction_status` público separado. O requisito é preservar o latch e não perder argumentos já coletados.

## 5. Merge incremental de parâmetros

Uma resposta posterior deve complementar a transação existente, nunca recriá-la apenas a partir do texto atual.

```python
existing = dict((state.get("active_transaction") or {}).get("arguments") or {})
new_values = {"valor": "71.99"}
arguments = {**existing, **new_values}
```

Exemplo esperado:

```text
Turno 1: subject = "TIM CTRL Redes Sociais 8.0"
Turno 2: valor = "71.99"
Resultado: subject + valor permanecem disponíveis
```

## 6. Precedência de roteamento durante transação

Quando existe `active_transaction` em `COLLECTING_PARAMETERS`, a mensagem deve primeiro ser avaliada como possível resposta aos parâmetros pendentes.

Precedência normativa:

1. parâmetro pendente claramente preenchido → continuar a transação;
2. cancelamento/abandono explícito → cancelar a transação;
3. nova intenção inequívoca → interromper a transação e rotear;
4. keyword genérica do mesmo domínio/agente → **não** interromper a transação;
5. mensagem ambígua → manter a transação e clarificar.

Exemplos:

| Estado atual | Mensagem | Resultado correto |
|---|---|---|
| `retail_order_cancel`, falta `order_id` | `PED-1001` | Continua cancelamento e preenche `order_id`. |
| `retail_order_cancel`, falta `order_id` | `o pedido é o PED-1001` | Continua cancelamento; `pedido` não deve virar tracking. |
| contestação, falta `valor` | `R$ 71,99` | Continua contestação e preenche `valor`. |
| cancelamento pendente | `esquece, quero ver minha fatura` | Interrupção explícita permitida. |
| cancelamento pendente | `quero rastrear pedido` | Mudança inequívoca para tracking permitida. |

## 7. Checkpoint e retomada

Antes de executar roteamento normal, o host deve restaurar o checkpoint usando a mesma identidade de conversa (`tenant_id`, `agent_id`, `session_id`/`conversation_key` conforme contrato do host).

Após a restauração:

```text
active_transaction existe
       ↓
status ativo?
       ↓ sim
retomar a transação antes de keyword routing / continuity LLM
```

Um estado `COLLECTING_PARAMETERS` sem `active_transaction` deve ser tratado como inconsistência de estado e observado/diagnosticado; não deve silenciosamente reiniciar a tool a partir da mensagem corrente.

## 8. O que pertence ao framework e ao agente

Framework:

- persistência do latch;
- merge de argumentos;
- estados de coleta/confirmação;
- precedência de retomada;
- confirmação determinística;
- idempotência e evidência;
- checkpoint/resume.

Agente:

- definição das tools de domínio;
- parâmetros obrigatórios e mensagens de domínio;
- regras de elegibilidade específicas;
- pre-validation específica, quando houver;
- resposta final ao cliente.

O agente não deve implementar um segundo motor transacional paralelo ao `AgentRuntime`.

## 9. Checklist para novos hosts/templates

- [ ] `AgentState` declara `active_transaction`.
- [ ] `AgentState` declara `last_transaction`.
- [ ] `transaction_status` e `missing_parameters` fazem parte do state quando usados.
- [ ] O host usa checkpoint compatível com o schema do state.
- [ ] A mesma `conversation_key` é usada entre turnos da mesma conversa.
- [ ] Parâmetros já coletados são mesclados com novos valores.
- [ ] Respostas a parâmetros têm precedência sobre keyword routing genérico.
- [ ] Mudança explícita de intenção continua possível.
- [ ] O agente usa `transaction_state_patch(state)` ao retornar respostas transacionais quando o template o exige.
- [ ] Existem testes multi-turno para coleta, confirmação, interrupção e resume.

## 10. Testes regressivos mínimos

```text
A. cancelamento de pedido
1. "quero cancelar pedido"
2. "o pedido é o PED-1001"
Esperado: continua retail_order_cancel; não vira retail_order_tracking.

B. contestação
1. "não contratei TIM CTRL Redes Sociais 8.0"
2. "R$ 71,99"
Esperado: subject e valor chegam juntos à pre-validation.

C. interrupção explícita
1. iniciar transação e deixar parâmetro pendente
2. "esquece, quero ver minha fatura"
Esperado: transação é interrompida e nova intenção é roteada.

D. checkpoint/resume
1. iniciar transação
2. persistir/checkpoint
3. reconstruir execução usando a mesma conversation_key
4. fornecer o parâmetro faltante
Esperado: active_transaction é restaurado e concluído sem reiniciar a tool.
```

## 11. Anti-patterns

- reconstruir a transação somente a partir da última mensagem;
- usar `selected_tool_call` como única fonte do latch;
- remover `active_transaction` do `AgentState` por parecer redundante;
- permitir uma keyword genérica como `pedido` interromper coleta de `order_id`;
- armazenar parâmetros apenas em variáveis locais do nó;
- duplicar confirmação transacional no prompt do agente;
- limpar o latch antes do estado terminal.

## 12. Referências no projeto

- `specs/SPEC-002-Agent-Runtime.md`
- `specs/SPEC-010-Agent-Development.md`
- `templates/agent_template_backend/app/state.py`
- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `libs/agent_framework/src/agent_framework/routing/enterprise_router.py`
- `Tuning-Performance/Deterministic_Transactional_Workflow/`
- `Tuning-Performance/Transaction_Pre_Validation/`
- `Tuning-Performance/Transaction_Evidence/`
