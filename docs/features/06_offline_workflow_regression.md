# Regressão Offline de Workflow / Offline Workflow Regression

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `workflows/runtime.py + Tuning-Performance/Offline_Workflow_Regression`

---

## Português (PT-BR)

### 1. O que é

Permite testar a lógica de workflows sem exigir toda a infraestrutura de produção.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
Teste
  ↓
backend determinístico explicitamente habilitado
  ↓
run → PAUSED
  ↓
resume → COMPLETED
  ↓
asserts de estado/side effects
```

### 4. Como funciona internamente

O `WorkflowRuntime` possui um caminho determinístico/offline **explicitamente opt-in para testes**. Ele permite validar DSL, condições, pause/resume e proteção contra reexecução sem exigir LangGraph, banco, OCI ou APIs externas.

O comportamento de produção continua usando LangGraph. O modo offline não deve virar fallback silencioso quando LangGraph falha ou está ausente em produção.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```text
run(workflow)
  action_a = 1 execução
  status = PAUSED

resume(workflow)
  action_a continua com 1 execução
  action_b = 1 execução
  status = COMPLETED
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

- Usar o backend offline em produção mascara problemas reais.
- Mockar tanto que o teste deixa de validar a DSL real.
- Não verificar side effects anteriores ao pause pode esconder duplicações.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/Tuning-Performance/Offline_Workflow_Regression`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Allows workflow logic to be regression-tested without requiring the full production infrastructure.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Test
  ↓
explicit deterministic test backend
  ↓
run → PAUSED
  ↓
resume → COMPLETED
  ↓
state/side-effect assertions
```

### 4. How it works internally

`WorkflowRuntime` includes an **explicitly opt-in deterministic/offline test backend**. It can validate DSL rules, conditions, pause/resume behavior, and duplicate-execution protection without requiring LangGraph, a database, OCI, or external APIs.

Production behavior still uses LangGraph. Offline mode must never become a silent fallback when LangGraph fails or is unavailable in production.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
run(workflow)
  action_a = executed once
  status = PAUSED

resume(workflow)
  action_a remains executed once
  action_b = executed once
  status = COMPLETED
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

- Using the offline backend in production hides real issues.
- Over-mocking can stop the test from validating real DSL behavior.
- Failing to assert pre-pause side effects may hide duplicate execution.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/Tuning-Performance/Offline_Workflow_Regression`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
