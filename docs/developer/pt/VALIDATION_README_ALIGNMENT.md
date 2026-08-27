
### Validação de Alinhamento da Documentação

### Objetivo

Registrar como a documentação desta versão foi reorganizada e quais fontes devem ser usadas pelo desenvolvedor.

### Decisão estrutural

O `README.md` da raiz é o **único tutorial principal ponta a ponta**.

O antigo `01_architecture_and_agent_development.md` foi removido porque repetia grande parte do README, mas não todo ele. Isso criava ambiguidade: dois documentos aparentavam ensinar a mesma coisa, porém um era parcial.

A nova estrutura substitui esse arquivo por `01_architecture_and_concepts.md`, que contém apenas arquitetura, conceitos, responsabilidades e critérios de extensão.

### Validação de `README_old2.md`

`Documentacao/README_old2.md` permanece útil como histórico, mas não é fonte principal para desenvolvimento.

Foram encontradas evoluções posteriores no README atual e no código, incluindo:

- SPECs/SDDs;
- configuração mais completa de `llm_profiles.yaml`;
- Channel Gateway e contratos canônicos;
- `memory` e `summary_memory` no ciclo atual do agente;
- `prepare_memory_context()` e `build_messages()`;
- `RuntimeContext`;
- `normalize_tools_by_intent()`;
- `build_tool_arguments()`;
- `execute_tools_for_intent()`;
- helpers de estado transacional;
- respostas MCP diretas;
- evolução de gateways, RAG, memória e políticas.

### Correção aplicada ao README principal

Foi corrigido no pacote gerado o typo:

```python
from app.agents.financeiro_agent import FinanceirotAgent
```

para:

```python
from app.agents.financeiro_agent import FinanceiroAgent
```

A classe correta é confirmada pelo código e pelo restante da documentação.

### APIs confirmadas na implementação atual

```python
AgentRuntimeMixin.get_runtime_context()
AgentRuntimeMixin.normalize_tools_by_intent()
AgentRuntimeMixin.build_tool_arguments()
AgentRuntimeMixin.execute_tools_for_intent()
AgentRuntimeMixin.prepare_memory_context()
AgentRuntimeMixin.build_messages()
AgentRuntimeMixin.transaction_state_patch()
AgentRuntimeMixin.transaction_clarification_message()
AgentRuntimeMixin.transaction_confirmation_message()
AgentRuntimeMixin.build_direct_mcp_answer()
```

### Ordem de confiança

1. código da versão;
2. README principal da mesma versão;
3. SPECs/SDDs;
4. manuais especializados;
5. release notes;
6. documentos `README_old*`.

### Regra de manutenção futura

Uma evolução de feature deve atualizar:

1. o README principal, **somente se alterar o caminho normal de desenvolvimento**;
2. o manual especializado da feature, com detalhes técnicos, comportamento, configuração e troubleshooting;
3. a SPEC, quando houver mudança de contrato;
4. release note, quando for necessário registrar a mudança histórica.

Não crie um novo “manual principal” para uma feature. Não mantenha correções funcionais permanentemente apenas em release notes.
