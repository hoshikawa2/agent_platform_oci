# Memória de Longo Prazo

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `memory/long_term_memory.py + memory/long_term_store.py`

---

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
