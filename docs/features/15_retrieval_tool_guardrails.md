# Guardrails de Retrieval e Tools / Retrieval / Tool Guardrails

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `guardrails/pipeline.py + guardrails/rails.py`

---

## Português (PT-BR)

### 1. O que é

Aplica proteção não apenas na mensagem do usuário e na resposta final, mas também no conhecimento recuperado por RAG e nos argumentos/resultados de ferramentas.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
Usuário
 ↓
Input Guardrails
 ↓
RAG → Retrieval Guardrails
 ↓
LLM/Tool call → Tool Guardrails
 ↓
API
 ↓
Output Guardrails
```

### 4. Como funciona internamente

O framework possui stages distintos de guardrails. Para retrieval, rails como `RAGSEC` e `RET_REL` podem validar segurança e relevância do conteúdo recuperado. Para tools, `TOOL_VAL` valida o uso/argumentos antes ou ao redor da execução.

As configurações globais incluem `ENABLE_INPUT_GUARDRAILS`, `ENABLE_OUTPUT_GUARDRAILS`, `ENABLE_PARALLEL_GUARDRAILS`, `GUARDRAILS_FAIL_FAST` e `GUARDRAILS_CONFIG_PATH`. O YAML é a fonte de verdade dos rails ativados por agente.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```yaml
retrieval:
  rails:
    - RAGSEC
    - RET_REL

tool:
  rails:
    - TOOL_VAL
```

Exemplo: a pergunta é sobre cancelamento de um serviço, mas o RAG retorna documentação de modem. `RET_REL` pode rejeitar o contexto antes que ele seja usado na resposta.

### 7. Telemetria e observabilidade

Quando a feature participa de uma execução de agente, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id` e demais chaves de correlação no estado/eventos. Isso permite acompanhar a decisão no Langfuse/Observer sem colocar lógica de observabilidade dentro do domínio.

### 8. Como testar

1. Crie um teste unitário do comportamento principal.
2. Crie um teste de integração do runtime quando houver estado entre turns.
3. Verifique o caso feliz e pelo menos um caso de falha/negação.
4. Confirme que não há side effects duplicados em retry/replay quando a feature toca transações.
5. Em produção, valide também telemetria e correlação de IDs.

### 9. Erros comuns

- Ter a implementação do rail não significa que ele está ativo: confira `guardrails.yaml`.
- Fail-fast deve ser escolhido conscientemente para cada stage.
- Tool guardrail não substitui validação de negócio dentro da própria API/action.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/guardrails/pipeline.py`
- `libs/agent_framework/src/agent_framework/guardrails/rails.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Applies safety and validation not only to user input and final output, but also to RAG-retrieved knowledge and tool arguments/results.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
User
 ↓
Input Guardrails
 ↓
RAG → Retrieval Guardrails
 ↓
LLM/Tool call → Tool Guardrails
 ↓
API
 ↓
Output Guardrails
```

### 4. How it works internally

The framework has distinct guardrail stages. For retrieval, rails such as `RAGSEC` and `RET_REL` can validate retrieved-content safety and relevance. For tools, `TOOL_VAL` validates usage/arguments before or around execution.

Global settings include `ENABLE_INPUT_GUARDRAILS`, `ENABLE_OUTPUT_GUARDRAILS`, `ENABLE_PARALLEL_GUARDRAILS`, `GUARDRAILS_FAIL_FAST`, and `GUARDRAILS_CONFIG_PATH`. The agent YAML is the source of truth for enabled rails.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```yaml
retrieval:
  rails:
    - RAGSEC
    - RET_REL

tool:
  rails:
    - TOOL_VAL
```

Example: the question concerns canceling a service, but RAG retrieves modem documentation. `RET_REL` can reject that context before it is used in the answer.

### 7. Telemetry and observability

When the feature participates in an agent execution, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id`, and other correlation keys in state/events. This makes the decision observable through Langfuse/Observer without embedding observability logic in the domain.

### 8. How to test

1. Add a unit test for the core behavior.
2. Add a runtime integration test when state spans multiple turns.
3. Test the happy path and at least one failure/rejection path.
4. Confirm retries/replays do not duplicate side effects for transactional features.
5. In production, also validate telemetry and ID correlation.

### 9. Common mistakes

- Having a rail implementation does not mean it is enabled: check `guardrails.yaml`.
- Fail-fast behavior should be chosen intentionally for each stage.
- Tool guardrails do not replace business validation inside the API/action itself.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/guardrails/pipeline.py`
- `libs/agent_framework/src/agent_framework/guardrails/rails.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
