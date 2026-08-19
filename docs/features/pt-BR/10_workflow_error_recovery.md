# Recuperação de Erro em Workflow

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `workflows/runtime.py`

---

### 1. O que é

Preserva o estado parcial de uma execução quando um passo posterior falha, permitindo entender o que já aconteceu e evitar repetir side effects.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
passo A ✅
passo B ✅
passo C ❌
   ↓
FAILED + snapshot parcial
   ↓
recovery decide o que pode continuar/repetir
```

### 4. Como funciona internamente

O runtime preserva o snapshot parcial do LangGraph quando uma etapa posterior falha e produz `error_details` genérico. Quando a exceção externa possui informações estruturadas, podem ser preservados status HTTP, body, número de tentativas, code e metadata.

A feature não significa “tentar tudo de novo”. Recuperação segura depende de conhecer o estado já executado, a idempotência e a natureza do erro.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```json
{
  "status": "FAILED",
  "error_details": {
    "status": 503,
    "attempts": 3,
    "code": "UPSTREAM_UNAVAILABLE"
  },
  "state": {
    "protocol_created": true,
    "operation_completed": true,
    "sms_sent": false
  }
}
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

- Retry indiscriminado pode repetir transações.
- Se a exceção externa perde metadata, a recuperação fica menos precisa.
- Combine sempre com Durable Idempotency em side effects críticos.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/workflows/runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
