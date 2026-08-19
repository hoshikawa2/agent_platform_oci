# Composição por LLM Solicitada pelo Domínio

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `runtime/agent_runtime.py`

---

### 1. O que é

Permite que a regra de negócio calcule o resultado e peça ao LLM apenas para redigir a resposta final.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
Regra de negócio calcula
   ↓
requires_llm_composition=true
   ↓
framework impede resposta MCP direta
   ↓
LLMProvider oficial
   ↓
redação natural
```

### 4. Como funciona internamente

O domínio retorna dados confiáveis e uma instrução de composição. O `AgentRuntimeMixin` detecta `requires_llm_composition` de forma recursiva no resultado da tool/workflow e não encerra a resposta pelo caminho direto de MCP. A composição segue pelo LLM oficial do agente, preservando profiles, tracing, usage e políticas do framework.

O LLM deve redigir; ele não deve recalcular valores nem decidir regras de negócio já resolvidas.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```json
{
  "success": true,
  "refund_amount": "38,00",
  "requires_llm_composition": true,
  "response_instruction": "Explique a devolução usando somente os valores calculados."
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

- Instrução muito aberta pode fazer o LLM adicionar conteúdo não autorizado.
- Não envie ao LLM a responsabilidade de recalcular valores determinísticos.
- Se não houver necessidade de redação livre, prefira resposta determinística direta.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
