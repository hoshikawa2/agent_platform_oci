### Routing, parâmetros e estado avançados

### Precedência de decisão

O desenvolvedor não deve tratar `routing.yaml` como uma lista de palavras. A decisão combina estado pendente, regras determinísticas e fallback semântico. A ordem segura é:

1. bloqueio ou finalização explícita;
2. transação/coleção pendente por `state_policies`;
3. confirmação determinística;
4. intenção determinística por keywords/examples/priority;
5. fallback LLM, quando habilitado;
6. `fallback_agent` ou handoff.

O estado pendente tem precedência para que “sim”, “não” ou um parâmetro isolado não sejam roteados para outro agente.

### Contrato comentado do `routing.yaml`

```yaml routing-advanced-example
router:
  mode: router
  fallback_agent: billing_agent
  confidence_threshold: 0.65
  allow_handoff: true
  transaction_confirmation:
    semantic_fallback:
      enabled: true
      allowed_values: [SIM, NAO, CONTINUAR]
      confirm_values: [SIM]
      reject_values: [NAO]
      continue_values: [CONTINUAR]
      include_relevant_context: true
      profile_name: router
      prompt: |
        Classifique somente como {{ allowed_values }}.
        Pergunta pendente: {{ pending_prompt }}
        Histórico relevante: {{ relevant_conversation_context }}
        Resposta atual: {{ user_input }}
state_policies:
  - state: COLLECTING_FINANCIAL_PARAMETERS
    agent: financeiro_agent
    description: Mantém respostas curtas na coleta financeira.
  - state: WAITING_FINANCIAL_CONFIRMATION
    agent: financeiro_agent
    description: Mantém a confirmação no fluxo financeiro.
intents:
  - name: financial_analysis
    domain: financial
    agent: financeiro_agent
    description: Consulta saldo, posição e movimentações.
    priority: 10
    mcp_tools: [consultar_saldo, consultar_movimentacoes]
    keywords: [saldo, extrato, movimentação]
    examples:
      - Qual é meu saldo?
      - Mostre minhas movimentações.
```

`priority` desempata intenções; menor valor tem precedência no template atual. `mcp_tools` restringe capacidades candidatas, mas não autoriza efeito sensível. `confidence_threshold` define quando aceitar o resultado semântico. `allow_handoff` permite troca explícita de agente. `domain` é metadado de escopo e não substitui `agent`.

O prompt semântico deve conter `allowed_values` e instruir o modelo a não executar ações nem inventar fatos. `include_relevant_context` inclui somente contexto limitado relacionado à pausa. Se a saída não corresponder a uma opção permitida, mantenha a transação pendente.

### Identidade antes da extração

`identity.yaml` resolve chaves canônicas (`customer_key`, `contract_key`, `interaction_key`, `account_key`, `resource_key`, `session_key`) a partir do payload, do `business_context` ou do contexto anterior. A validação de `required` deve ocorrer antes de chamar MCP. Nunca use `session_id` como identidade de cliente.

### Mapeamento e extração

```yaml parameter-mapping-example
mcp_parameter_mapping:
  defaults:
    use_mock: false
  tools:
    consultar_movimentacoes:
      map:
        customer_key: customer_id
        account_key: account_id
        session_key: session_id
      defaults:
        limit: 20
      extract:
        month:
          from: message
          type: int
          strategy: month_name_pt
          description: Converta o mês mencionado em número de 1 a 12.
        transaction_id:
          from: message
          type: string
          strategy: hybrid
          pattern: '(?i)\\b(?:transação|transaction)\\s*[:#-]?\\s*([A-Z0-9-]+)\\b'
          group: 1
          description: Extraia somente um identificador explicitamente informado.
```

Precedência recomendada para argumentos: valor já confirmado na transação, argumento explícito atual, identidade canônica mapeada, extração determinística, extração LLM/híbrida e default. Um valor novo explícito pode corrigir o anterior; um valor inferido nunca deve sobrescrever um valor confirmado.

`strategy: hybrid` tenta a parte determinística e usa LLM quando necessário. `pattern` e `group` devem ser testados com casos positivos e negativos. `description` é instrução operacional do extrator, não documentação decorativa. `type` deve falhar de forma controlada se a conversão não for segura.

### Reconciliação temporal

A reconciliação temporal é fallback da coleta tradicional. Quando ainda faltarem campos, percorra mensagens relevantes da mais recente para a mais antiga e associe valores somente aos campos descritos no `args_schema`/mapeamento. Ela não deve:

- reabrir transação encerrada;
- misturar agentes, tenants ou sessões;
- recuperar valor invalidado pelo usuário;
- trocar correspondência exata por aproximação perigosa;
- substituir parâmetro já confirmado.

Registre a origem (`current_message`, `business_context`, `history`, `default`), a mensagem correlacionada e a confiança, sem persistir conteúdo sensível desnecessário.

### Estados dinâmicos

Para um agente novo, declare os estados de coleta e confirmação em `AgentState` somente quando eles carregarem campos adicionais; caso contrário, use as chaves transacionais genéricas. Registre ambos em `state_policies`, implemente a limpeza em sucesso/cancelamento/intent shift e inclua os estados nos testes de roteamento. Estado novo sem política correspondente costuma causar perda de stickiness.

### Router versus supervisor

No modo `router`, uma decisão escolhe um agente. No modo `supervisor`, o supervisor pode coordenar vários agentes e consolidar resultados. Não habilite supervisor apenas para melhorar classificação: ele muda custo, latência, estado e observabilidade. Um subagente deve receber contexto mínimo, ferramentas autorizadas e namespace `tenant_id:agent_id:session_id`; nunca compartilhe memória bruta entre agentes.

### Testes obrigatórios

Teste sobreposição de keywords, empate de prioridade, abaixo do threshold, agente fallback, estado pendente, confirmação curta, resposta ambígua, correção de parâmetro, extração regex/LLM, histórico temporal e isolamento entre agentes. Os YAMLs deste capítulo são analisados por `tests/test_advanced_developer_documentation.py`.

