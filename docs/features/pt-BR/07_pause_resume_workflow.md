# Pause

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `workflows/runtime.py + workflows/graph.py`

---

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
