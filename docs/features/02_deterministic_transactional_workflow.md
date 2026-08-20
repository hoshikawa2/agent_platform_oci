# Workflow Transacional Determinístico / Deterministic Transactional Workflow

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `workflows/runtime.py + mcp/tool_policy.py`

---

## Português (PT-BR)

### 1. O que é

Garante que operações que alteram estado sigam passos previsíveis, com confirmação e controle de execução, em vez de depender da criatividade do LLM.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
Mensagem do cliente
   ↓
LLM entende intenção
   ↓
Tool policy = transactional
   ↓
Workflow determinístico
   ↓
confirmação
   ↓
execução controlada
   ↓
resultado
```

### 4. Como funciona internamente

O LLM pode ajudar a interpretar a intenção e extrair parâmetros, mas não deve decidir a sequência crítica de uma transação. O `ToolPolicyRegistry` classifica tools, e `operation_type: transactional` ativa a política transacional. O `WorkflowRuntime` executa o workflow, mantém estado e integra pause/resume e recuperação de erro.

A configuração `ENABLE_TRANSACTIONAL_WORKFLOWS` controla a capability global, e `WORKFLOWS_PATH` aponta para os YAMLs.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```yaml
tools:
  cancelar_servico:
    operation_type: transactional
    requires_confirmation: true
```

```text
1. localizar serviço
2. validar elegibilidade
3. pedir confirmação
4. PAUSE
5. receber confirmação
6. RESUME
7. executar side effect
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

- Marcar uma tool de escrita como `read_only` elimina proteções transacionais.
- Reexecutar steps anteriores ao pause pode duplicar side effects; use o runtime oficial.
- Não use prompt como única garantia de confirmação.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/mcp/tool_policy.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Ensures state-changing operations follow predictable steps with confirmation and execution control instead of depending on LLM creativity.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Customer message
   ↓
LLM understands intent
   ↓
Tool policy = transactional
   ↓
Deterministic workflow
   ↓
confirmation
   ↓
controlled execution
   ↓
result
```

### 4. How it works internally

The LLM may help interpret intent and extract parameters, but it should not decide the critical sequence of a transaction. `ToolPolicyRegistry` classifies tools, and `operation_type: transactional` activates transactional behavior. `WorkflowRuntime` executes the workflow, preserves state, and integrates pause/resume and error recovery.

`ENABLE_TRANSACTIONAL_WORKFLOWS` controls the capability globally, while `WORKFLOWS_PATH` points to workflow YAML files.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```yaml
tools:
  cancel_service:
    operation_type: transactional
    requires_confirmation: true
```

```text
1. locate service
2. validate eligibility
3. ask for confirmation
4. PAUSE
5. receive confirmation
6. RESUME
7. execute side effect
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

- Marking a write tool as `read_only` bypasses transactional protections.
- Re-running steps before a pause can duplicate side effects; use the official runtime.
- Do not use prompts as the only confirmation guarantee.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `libs/agent_framework/src/agent_framework/mcp/tool_policy.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
