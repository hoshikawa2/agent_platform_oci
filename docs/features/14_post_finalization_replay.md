# Replay Após Finalização / Post Finalization Replay

> Feature do `agent_framework_oci` — guia bilíngue PT-BR / EN.

**Implementação principal / Main implementation:** `channels/interruption.py + config/settings.py`

---

## Português (PT-BR)

### 1. O que é

Evita que áudio residual ou mensagens tardias reabram uma sessão já finalizada.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
sessão terminal
  ↓
entrada residual
  ↓
policy detecta finalização
  ↓
replay última fala/fallback
  ↓
NÃO reabre LangGraph
```

### 4. Como funciona internamente

A política de interrupção verifica metadata de sessão terminal antes de tratar uma entrada como nova intenção. Quando há texto terminal disponível, usa `last_assistant_text`/`terminal_replay_text`; caso contrário, pode usar a mensagem configurada em `POST_FINALIZE_REPLAY_MESSAGE`.

O objetivo é proteger o fechamento lógico da sessão, especialmente em canais de voz onde pacotes de áudio podem chegar depois do evento de finalização.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```text
Agente: "Atendimento concluído."
→ sessão finalizada

chega fragmento: "ã..."
→ replay "Atendimento concluído."
→ nenhum routing / tool / LLM novo
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

- Se o estado terminal não for persistido, outra réplica pode reabrir a jornada.
- Não use replay técnico/JSON como fala do cliente.
- Essa feature não substitui política de nova sessão intencional.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/channels/interruption.py`
- `libs/agent_framework/src/agent_framework/config/settings.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`

---

## English (EN)

### 1. What it is

Prevents residual audio or late messages from reopening a session that has already been finalized.

### 2. Problem it solves

Production agents should not rely on prompts alone to “do the right thing”. This feature moves a specific responsibility into a controlled framework layer, reducing unpredictable behavior and duplicate domain-agent code.

### 3. Simplified flow

```text
terminal session
  ↓
residual input
  ↓
policy detects finalization
  ↓
replay last utterance/fallback
  ↓
DO NOT reopen LangGraph
```

### 4. How it works internally

The interruption policy checks terminal-session metadata before treating an input as a new intent. When terminal speech is available, it uses `last_assistant_text`/`terminal_replay_text`; otherwise it may use `POST_FINALIZE_REPLAY_MESSAGE`.

The purpose is to protect the logical end of a session, especially on voice channels where audio packets may arrive after the finalization event.

### 5. How to enable/configure

Exact activation depends on the template/agent. Check framework settings, YAML configuration, and the service template. Not every feature requires a global flag: some are activated by the contract returned from a tool/workflow.

### 6. Example

```text
Agent: "The interaction is complete."
→ session finalized

late fragment arrives: "uh..."
→ replay "The interaction is complete."
→ no new routing / tool / LLM call
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

- If terminal state is not persisted, another replica may reopen the journey.
- Do not replay technical/JSON envelopes as user-facing speech.
- This feature does not replace an intentional new-session policy.

### 10. Relationship with other features

Use this feature together with the framework's horizontal capabilities rather than creating a parallel implementation in domain-agent code. For transactional journeys, pay special attention to **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery**, and **Guardrails**.

### 11. Repository references

- `libs/agent_framework/src/agent_framework/channels/interruption.py`
- `libs/agent_framework/src/agent_framework/config/settings.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
