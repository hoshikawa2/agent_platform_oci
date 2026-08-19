# Aderência de Rota

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `routing/enterprise_router.py + runtime/agent_runtime.py`

---

### 1. O que é

Evita que pequenas mensagens de continuação façam a conversa trocar de agente sem necessidade.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
mensagem atual
 + histórico curto
 + rota anterior
   ↓
continuidade semântica
   ↓
manter rota ou handoff
```

### 4. Como funciona internamente

Route Stickiness avalia se a nova mensagem continua semanticamente ligada ao assunto/agente atual. Isso reduz ping-pong de agentes em mensagens como “e esse valor?”, “sim”, “o segundo” ou “e no mês passado?”.

Configurações existentes incluem `ENABLE_ROUTE_STICKINESS`, `ROUTE_STICKINESS_LLM_PROFILE`, `ROUTE_STICKINESS_CONFIDENCE_THRESHOLD`, `ROUTE_STICKINESS_HISTORY_TURNS` e `ROUTE_STICKINESS_MAX_TOKENS`. A decisão pode permitir handoff quando há evidência suficiente de mudança de assunto.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```env
ENABLE_ROUTE_STICKINESS=true
ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.90
ROUTE_STICKINESS_HISTORY_TURNS=2
ROUTE_STICKINESS_MAX_TOKENS=80
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

- Threshold muito baixo pode prender o cliente no agente errado.
- Threshold alto demais perde continuidade em mensagens curtas.
- Stickiness não deve bloquear handoff explícito quando a intenção realmente mudou.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/routing/enterprise_router.py`
- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
