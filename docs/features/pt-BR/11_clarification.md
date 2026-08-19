# Clarificação

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `runtime/agent_runtime.py`

---

### 1. O que é

Quando faltam dados ou uma tool encontra múltiplas opções, o framework pergunta ao usuário em vez de adivinhar.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
pedido ambíguo
  ↓
NEEDS_CLARIFICATION
  ↓
pergunta + opções
  ↓
usuário responde
  ↓
framework resolve
  ↓
retoma mesma tool/workflow
```

### 4. Como funciona internamente

O runtime suporta clarificação tanto de parâmetros faltantes quanto de resultados de tools. Para tool-result clarification, um resultado com `status: NEEDS_CLARIFICATION` pode trazer opções; o runtime persiste `pending_tool_clarification`, entra em `TOOL_RESULT_CLARIFICATION` e consegue resolver respostas por ordinal ou nome.

Depois da escolha, o framework reutiliza a mesma tool e injeta os argumentos resolvidos, evitando que o roteador trate a resposta curta como uma intenção nova.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```json
{
  "status": "NEEDS_CLARIFICATION",
  "question": "Qual serviço?",
  "options": [
    {"id": "tim_music", "label": "TIM Music"},
    {"id": "hbo_max", "label": "HBO Max"}
  ]
}
```

Usuário: `o segundo` → `hbo_max`.

### 7. Telemetria e observabilidade

Quando a feature participa de uma execução de agente, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id` e demais chaves de correlação no estado/eventos. Isso permite acompanhar a decisão no Langfuse/Observer sem colocar lógica de observabilidade dentro do domínio.

### 8. Como testar

1. Crie um teste unitário do comportamento principal.
2. Crie um teste de integração do runtime quando houver estado entre turns.
3. Verifique o caso feliz e pelo menos um caso de falha/negação.
4. Confirme que não há side effects duplicados em retry/replay quando a feature toca transações.
5. Em produção, valide também telemetria e correlação de IDs.

### 9. Erros comuns

- Não descarte `pending_tool_clarification` entre turns.
- Uma resposta curta deve ser resolvida contra as opções antes do roteamento normal.
- Opções sem identificador/label consistente pioram a resolução.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/runtime/agent_runtime.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
