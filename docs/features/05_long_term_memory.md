# Memória de Longo Prazo / Long Term Memory

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `memory/long_term_memory.py + memory/long_term_store.py`

---

## Português (PT-BR)

### 1. O que é

Permite lembrar informações úteis entre sessões diferentes, sem depender do histórico completo de uma conversa.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
Sessão A
  ↓
extração de memória relevante
  ↓
Long Term Memory Store
  ↓
... dias depois ...
  ↓
Sessão B
  ↓
recupera contexto relevante
  ↓
agente
```

### 4. Como funciona internamente

A memória de longo prazo é diferente de histórico de mensagens e de checkpoint. Ela persiste fatos/preferências úteis e os recupera como contexto de uma nova sessão. O framework oferece providers `memory`, `sqlite`, `autonomous` e `oracle`.

Configurações importantes: `ENABLE_LONG_TERM_MEMORY`, `LONG_TERM_MEMORY_PROVIDER`, `LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS`, `LONG_TERM_MEMORY_MIN_CONFIDENCE`, `LONG_TERM_MEMORY_AUTO_EXTRACT` e `LONG_TERM_MEMORY_INJECT_CONTEXT`.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```env
ENABLE_LONG_TERM_MEMORY=true
LONG_TERM_MEMORY_PROVIDER=oracle
LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS=20
LONG_TERM_MEMORY_MIN_CONFIDENCE=0.70
LONG_TERM_MEMORY_AUTO_EXTRACT=true
LONG_TERM_MEMORY_INJECT_CONTEXT=true
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

- Não confundir LTM com replay de toda conversa.
- Memória irrelevante ou de baixa confiança não deveria ser injetada.
- Em múltiplas réplicas, prefira storage durável compartilhado em vez de memória local.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/memory/long_term_memory.py`
- `libs/agent_framework/src/agent_framework/memory/long_term_store.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Allows useful information to persist across different sessions without depending on the full transcript of a previous conversation.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
Session A
  ↓
extract relevant memory
  ↓
Long Term Memory Store
  ↓
... days later ...
  ↓
Session B
  ↓
retrieve relevant context
  ↓
agent
```

### 4. How it works internally

Long-term memory is different from message history and checkpoints. It persists useful facts/preferences and retrieves them as context for a future session. The framework supports `memory`, `sqlite`, `autonomous`, and `oracle` providers.

Important settings include `ENABLE_LONG_TERM_MEMORY`, `LONG_TERM_MEMORY_PROVIDER`, `LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS`, `LONG_TERM_MEMORY_MIN_CONFIDENCE`, `LONG_TERM_MEMORY_AUTO_EXTRACT`, and `LONG_TERM_MEMORY_INJECT_CONTEXT`.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```env
ENABLE_LONG_TERM_MEMORY=true
LONG_TERM_MEMORY_PROVIDER=oracle
LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS=20
LONG_TERM_MEMORY_MIN_CONFIDENCE=0.70
LONG_TERM_MEMORY_AUTO_EXTRACT=true
LONG_TERM_MEMORY_INJECT_CONTEXT=true
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

- Do not confuse LTM with replaying the entire transcript.
- Irrelevant or low-confidence memories should not be injected.
- For multiple replicas, prefer shared durable storage over local memory.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/memory/long_term_memory.py`
- `libs/agent_framework/src/agent_framework/memory/long_term_store.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
