# Replay em Interrupções de Voz / Voice Interruption Replay

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `channels/interruption.py`

---

## Português (PT-BR)

### 1. O que é

Decide se um áudio recebido durante a fala do agente representa uma nova intenção, um ruído/backchannel ou algo que deve apenas repetir/continuar a última fala.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
áudio durante fala
  ↓
InterruptionPolicy
  ├─ process → nova mensagem
  ├─ classify → classificador leve
  └─ replay → última fala
```

### 4. Como funciona internamente

A política fica no framework, não no domínio. Ela diferencia sessão terminal, `idle_nudge`, fala não interrompível e fala potencialmente interrompível. Quando necessário, pode usar um classificador leve baseado no `LLMProvider`; quando a classificação falha, a política é conservadora e pode optar por replay.

O objetivo é evitar que “aham”, ruído, eco ou fragmentos residuais sejam tratados como uma nova intenção completa.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```text
Agente: "Sua fatura possui..."
Cliente: "aham"
→ replay/continua

Agente: "Sua fatura possui..."
Cliente: "espera, quero falar de outra coisa"
→ processa nova intenção
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

- Classificar todo ruído com LLM aumenta latência e custo.
- Permitir interrupção em fala transacional não interrompível pode corromper UX/estado.
- Replay deve usar uma fala real anterior, não um envelope técnico.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/channels/interruption.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Decides whether audio received while the agent is speaking represents a new intent, a backchannel/noise event, or something that should simply replay/continue the previous speech.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
audio during speech
  ↓
InterruptionPolicy
  ├─ process → new message
  ├─ classify → lightweight classifier
  └─ replay → previous speech
```

### 4. How it works internally

The policy lives in the framework rather than domain code. It distinguishes terminal sessions, `idle_nudge`, non-interruptible speech, and potentially interruptible speech. When needed, it may use a lightweight classifier backed by `LLMProvider`; on classification failure, it can fail safely to replay.

The goal is to prevent “uh-huh”, noise, echo, or residual audio fragments from being interpreted as a full new intent.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
Agent: "Your invoice contains..."
User: "uh-huh"
→ replay/continue

Agent: "Your invoice contains..."
User: "wait, I want to ask something else"
→ process new intent
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

- Sending every noise fragment to an LLM increases latency and cost.
- Allowing interruption during non-interruptible transactional speech may corrupt UX/state.
- Replay should use a real previous utterance, not a technical envelope.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/channels/interruption.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
