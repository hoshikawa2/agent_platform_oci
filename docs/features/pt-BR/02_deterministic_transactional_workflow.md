# Workflow Transacional Determinístico

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `workflows/runtime.py + mcp/tool_policy.py`

---

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
