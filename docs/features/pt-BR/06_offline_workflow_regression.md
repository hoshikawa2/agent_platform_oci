# Regressão Offline de Workflow

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `workflows/runtime.py + Tuning-Performance/Offline_Workflow_Regression`

---

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

O `WorkflowRuntime` possui um caminho determinístico/offline **explicitamente opt-in para testes**. Quando `allow_deterministic_fallback=True`, esse backend é selecionado de forma explícita mesmo que LangGraph esteja instalado, garantindo regressões reproduzíveis entre máquinas e CI. Ele permite validar DSL, condições, pause/resume e proteção contra reexecução sem depender do comportamento interno do LangGraph, banco, OCI ou APIs externas.

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
