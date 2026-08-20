# Pause / Resume de Workflow / Pause / Resume Workflow

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `workflows/runtime.py + workflows/graph.py`

---

## Português (PT-BR)

### 1. O que é

Permite interromper um workflow em um ponto seguro, persistir o estado e continuar depois com a resposta do usuário ou outro evento.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
Workflow
  ↓
ações prévias
  ↓
PAUSE
  ↓
checkpoint/estado
  ↓
nova mensagem
  ↓
RESUME
  ↓
ações seguintes
```

### 4. Como funciona internamente

`WorkflowRuntime` expõe `arun(...)` e `aresume(...)`. O nó de pause é separado da action anterior para evitar reexecutar side effects quando o workflow retoma. O mesmo `execution_id/thread_id` identifica a execução pausada e retomada.

O runtime suporta condições declarativas como `all`, `any`, `not`, `eq`, `neq` e `exists`, permitindo definir quando pausar ou continuar sem colocar lógica conversacional no prompt.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```text
status = await runtime.arun(...)
# status == PAUSED

status = await runtime.aresume(execution_id, input={"confirmed": true})
# status == COMPLETED
```

### 7. Telemetria e observabilidade

Quando a feature participa de uma execução de agente, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id` e demais chaves de correlação no estado/eventos. Isso permite acompanhar a decisão no Langfuse/Observer sem colocar lógica de observabilidade dentro do domínio.

### 8. Como testar

1. Crie um teste unitário do comportamento principal.
2. Crie um teste de integração do runtime quando houver estado entre turns.
3. Verifique o caso feliz e pelo menos um caso de falha/negação.
4. Confirme que não há side effects duplicados em retry/replay quando a feature toca transações.
5. Em produção, valide também telemetria e correlação de IDs.

### 9. Erros comuns

- Perder o `execution_id` impede retomar a execução correta.
- Reexecutar o workflow do zero após confirmação pode repetir side effects.
- Pause sem storage/checkpoint compartilhado é frágil em múltiplas réplicas.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/workflows/graph.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Allows a workflow to stop at a safe point, persist state, and continue later using user input or another event.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Workflow
  ↓
pre-pause actions
  ↓
PAUSE
  ↓
checkpoint/state
  ↓
new message
  ↓
RESUME
  ↓
remaining actions
```

### 4. How it works internally

`WorkflowRuntime` exposes `arun(...)` and `aresume(...)`. The pause node is separated from the preceding action so previous side effects are not executed again on resume. The same `execution_id/thread_id` identifies the paused and resumed execution.

The runtime supports declarative conditions such as `all`, `any`, `not`, `eq`, `neq`, and `exists`, so pause/continue decisions do not need to live in the prompt.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
status = await runtime.arun(...)
# status == PAUSED

status = await runtime.aresume(execution_id, input={"confirmed": true})
# status == COMPLETED
```

### 7. Telemetry and observability

When the feature participates in an agent execution, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id`, and other correlation keys in state/events. This makes the decision observable through Langfuse/Observer without embedding observability logic in the domain.

### 8. How to test

1. Add a unit test for the core behavior.
2. Add a runtime integration test when state spans multiple turns.
3. Test the happy path and at least one failure/rejection path.
4. Confirm retries/replays do not duplicate side effects for transactional features.
5. In production, also validate telemetry and ID correlation.

### 9. Common mistakes

- Losing the `execution_id` prevents resuming the right execution.
- Restarting the workflow from scratch after confirmation may duplicate side effects.
- Pause without shared checkpoint/state storage is fragile across multiple replicas.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/workflows/graph.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
