# Idempotência Durável / Durable Idempotency

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `idempotency.py`

---

## Português (PT-BR)

### 1. O que é

Impede que a mesma operação crítica seja executada duas vezes, inclusive quando outra réplica/pod recebe a repetição.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
requisição
  ↓
idempotency key
  ↓
store durável
  ├─ existe → retorna resultado anterior
  └─ não existe → executa → persiste resultado
```

### 4. Como funciona internamente

`create_idempotency_store(settings, ...)` escolhe o backend conforme configuração/plataforma. O framework possui `IdempotencyStore` e `InMemoryIdempotencyStore`, mas produção distribuída deve preferir storage compartilhado. As configurações incluem `IDEMPOTENCY_PROVIDER`, `IDEMPOTENCY_REQUIRE_DURABLE` e `IDEMPOTENCY_TTL_SECONDS`.

Idempotência é diferente de retry: retry repete a tentativa; idempotência garante que a repetição não produza um novo side effect.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```text
Pod A recebe cancelamento
→ key=cliente:servico:operacao
→ executa
→ grava resultado

Pod A cai

Pod B recebe retry
→ mesma key
→ encontra resultado
→ NÃO cancela de novo
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

- Usar store em memória com múltiplos pods não é idempotência durável.
- Chave ampla demais pode bloquear operações legítimas; estreita demais permite duplicidade.
- TTL deve ser compatível com a janela real de retry/replay.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/idempotency.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Prevents the same critical operation from executing twice, including when a retry lands on another replica/pod.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
request
  ↓
idempotency key
  ↓
durable store
  ├─ exists → return previous result
  └─ missing → execute → persist result
```

### 4. How it works internally

`create_idempotency_store(settings, ...)` chooses a backend according to configuration/platform. The framework provides `IdempotencyStore` and `InMemoryIdempotencyStore`, but distributed production should prefer shared storage. Settings include `IDEMPOTENCY_PROVIDER`, `IDEMPOTENCY_REQUIRE_DURABLE`, and `IDEMPOTENCY_TTL_SECONDS`.

Idempotency is different from retry: retry repeats an attempt; idempotency guarantees that repetition does not create another side effect.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
Pod A receives cancellation
→ key=customer:service:operation
→ executes
→ stores result

Pod A crashes

Pod B receives retry
→ same key
→ finds stored result
→ DOES NOT cancel again
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

- An in-memory store across multiple pods is not durable idempotency.
- A key that is too broad may block legitimate operations; too narrow may allow duplicates.
- TTL should match the real retry/replay window.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/idempotency.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
