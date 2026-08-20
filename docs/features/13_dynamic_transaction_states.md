# Estados Transacionais Dinâmicos / Dynamic Transaction States

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `runtime/agent_runtime.py + mcp/tool_policy.py`

---

## Português (PT-BR)

### 1. O que é

Permite criar estados de confirmação baseados no agente/domínio atual sem hardcode de todos os domínios dentro do framework.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
tool transactional
  ↓
agente/domínio atual
  ↓
WAITING_<PREFIX>_CONFIRMATION
  ↓
confirmação/rejeição
  ↓
estado seguinte
```

### 4. Como funciona internamente

Em vez de manter estados fixos como `WAITING_BILLING_CONFIRMATION`, `WAITING_PRODUCT_CONFIRMATION` etc. para cada domínio conhecido, o runtime deriva o prefixo do agente atual e gera o estado dinamicamente. A função interna de estado transacional mantém o framework genérico.

A classificação `operation_type` aceita `read_only`, `transactional`, `conversational` e `internal`; somente `transactional` entra no caminho de confirmação transacional.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```text
VasAgent + cancelar_vas
→ WAITING_VAS_CONFIRMATION

AddressAgent + alterar_endereco
→ WAITING_ADDRESS_CONFIRMATION
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

- Hardcode de estados no domínio reduz reutilização.
- Classificar uma tool como `conversational` não deve ativar confirmação transacional.
- Mudanças no identificador do agente podem mudar o prefixo; mantenha IDs estáveis.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `libs/agent_framework/src/agent_framework/mcp/tool_policy.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Allows confirmation states to be derived from the current agent/domain instead of hardcoding every business domain into the framework.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
transactional tool
  ↓
current agent/domain
  ↓
WAITING_<PREFIX>_CONFIRMATION
  ↓
confirm/reject
  ↓
next state
```

### 4. How it works internally

Instead of maintaining fixed states such as `WAITING_BILLING_CONFIRMATION`, `WAITING_PRODUCT_CONFIRMATION`, and so on for every known domain, the runtime derives a prefix from the current agent and builds the confirmation state dynamically. This keeps the framework generic.

`operation_type` accepts `read_only`, `transactional`, `conversational`, and `internal`; only `transactional` enters the transactional confirmation path.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
VasAgent + cancel_vas
→ WAITING_VAS_CONFIRMATION

AddressAgent + change_address
→ WAITING_ADDRESS_CONFIRMATION
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

- Hardcoding states in domain code reduces reuse.
- Classifying a tool as `conversational` should not trigger transactional confirmation.
- Changing agent identifiers may change state prefixes; keep IDs stable.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `libs/agent_framework/src/agent_framework/mcp/tool_policy.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
