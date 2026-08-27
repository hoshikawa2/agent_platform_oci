
### Arquitetura e Conceitos do Agent Framework OCI

### Propósito deste documento

Este documento **não substitui o `README.md` da raiz** e não repete o tutorial de criação de agente.

Use:

- [`README.md`](../../../README.md) para desenvolver, configurar, executar e testar um agente de ponta a ponta;
- este documento para compreender a arquitetura, os limites de responsabilidade, os componentes e onde cada tipo de implementação deve ficar;
- os demais manuais desta pasta para aprofundar uma capacidade específica ou solucionar um problema.

A separação é intencional: existe **um único tutorial principal** e vários **manuais de referência especializados**.

### Fonte de verdade

Quando existir divergência documental, use esta ordem:

1. código da versão em uso;
2. `README.md` / `README_en.md` da mesma versão;
3. SPECs/SDDs normativas;
4. manuais especializados desta pasta;
5. release notes e `README_old*` apenas como histórico.

### Modelo mental da plataforma

O Agent Framework OCI deve ser entendido como uma plataforma em camadas.

O **framework core** fornece mecanismos reutilizáveis e neutros de domínio: runtime, estado, memória, roteamento, integração de tools, guardrails, judges, persistência, observabilidade e contratos comuns.

O **agente** contém aquilo que é específico do caso de uso: intents, prompts, regras de domínio, policies específicas, workflow de negócio, mapeamentos, integrações e componentes externos pertencentes àquele agente.

Os **gateways** tratam responsabilidades transversais de entrada, governança e integração. Eles não devem absorver a lógica de negócio do agente.

Os **MCP Servers** encapsulam ferramentas e integrações com serviços de domínio ou legados. O **MCP Gateway** fornece catálogo e governança centralizada dessas tools.

### Componentes principais

| Componente | Responsabilidade principal | Não deve conter |
|---|---|---|
| `libs/agent_framework/` | Runtime genérico, contratos, estado, memória, routing, guardrails, judges, integrações comuns | Regra específica de uma empresa ou agente |
| `templates/agent_template_backend/` | Referência executável para criação de agentes | Fork permanente do core |
| `apps/agent_gateway/` | Entrada governada, policies transversais, rate limit, autenticação, metadados | Workflow de negócio |
| `apps/channel_gateway/` | Adaptação dos canais ao contrato canônico | Regra de negócio do agente |
| `apps/mcp_gateway/` | Catálogo, autorização e execução central de tools | Lógica conversacional |
| `mcp/servers/` | Integrações e tools por domínio | Orquestração global do agente |
| `evals/` | Certificação e regressão | Lógica produtiva |
| `deploy/` | Containers e Kubernetes | Regras funcionais |

### Fluxo conceitual de uma requisição

Uma requisição típica percorre as seguintes responsabilidades:

```text
Canal
  |
  v
Channel Gateway
  |
  v
Agent Gateway
  |  governança / autenticação / rate limit / metadata
  v
Backend do agente
  |
  +--> Routing / stickiness / intent
  |
  +--> Estado / memória / checkpoint
  |
  +--> Guardrails / judges
  |
  +--> Workflow / políticas transacionais
  |
  +--> MCP Gateway
          |
          +--> MCP Server A --> sistema legado
          +--> MCP Server B --> serviço externo
          +--> MCP Server C --> API de domínio
```

Nem toda implantação precisa utilizar todos os componentes. A composição deve seguir a necessidade do agente e os contratos da plataforma.

### Runtime do agente

O runtime atual é baseado em `AgentRuntimeMixin` e `RuntimeContext`.

O template importa o runtime através de `app.agents.runtime`, que reexporta a implementação oficial do framework. O objetivo é impedir que cada agente mantenha sua própria cópia divergente do runtime.

Entre as APIs atuais confirmadas no código estão:

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

Essas APIs representam capacidades do runtime. O desenvolvedor deve preferi-las a reconstruir manualmente a mesma lógica dentro de cada agente.

### Configuração versus código

Uma diretriz central do framework é que comportamento configurável permaneça em configuração.

Exemplos:

- agentes e metadados: `config/agents.yaml`;
- roteamento: `config/routing.yaml`;
- tools: `config/tools.yaml`;
- MCP Servers e mappings: configuração MCP correspondente;
- perfis de LLM: `llm_profiles.yaml`;
- policies e extensões: arquivos de configuração específicos da capacidade.

O código deve implementar mecanismos. YAML/config deve escolher comportamento sempre que isso puder ser feito sem comprometer segurança ou contratos.

### Separação entre framework e agente

Uma mudança pertence ao **framework** quando introduz um mecanismo reutilizável por diferentes agentes.

Exemplos:

- nova SPI de guardrail;
- novo contrato de resposta rica de LLM;
- nova capacidade genérica de checkpoint;
- novo mecanismo configurável de tool policy;
- nova estratégia genérica de routing.

Uma mudança pertence ao **agente** quando expressa uma regra de um domínio ou empresa.

Exemplos:

- quais cobranças podem ser contestadas;
- um prompt específico de telecom;
- regras de VAS;
- códigos internos de uma empresa;
- mapeamento de um serviço legado;
- fraseologia específica.

Se o core precisa importar um módulo concreto do agente para funcionar, essa separação provavelmente foi quebrada.

### Estado, memória e checkpoint são conceitos diferentes

**Estado de execução** representa o que está acontecendo no turno e no workflow.

**Memória de conversa** preserva contexto conversacional.

**Long-Term Memory** guarda fatos duráveis associados a uma identidade de negócio.

**Checkpoint** persiste snapshots do estado LangGraph para retomada.

Um checkpoint antigo não deve, sozinho, determinar qual transação está ativa. A decisão funcional deve usar o estado transacional canônico.

### Routing e execução são responsabilidades diferentes

O routing responde: **qual agente/intent deve tratar esta mensagem?**

A execução responde: **o que esse agente deve fazer agora?**

Route stickiness preserva continuidade, mas não deve impedir uma mudança explícita de intenção. Durante uma transação, parâmetros esperados e confirmação válida têm precedência para evitar falsos intent shifts.

Detalhes completos: [Roteamento, Stickiness e Intent Shift](./02_routing_stickiness_and_intent_shift.md).

### Tools e MCP

Uma tool representa uma capacidade invocável.

O MCP Server implementa ou expõe essa capacidade.

O MCP Gateway organiza catálogo, autorização, mapping e execução centralizada.

O agente decide **quando** uma tool deve ser usada dentro do seu fluxo; a tool/MCP decide **como** acessar o serviço correspondente.

Detalhes completos: [MCP, Tools, Policies e Extração de Parâmetros](./04_mcp_integration_tools_and_policies.md).

### Transações

Operações com efeitos colaterais exigem tratamento diferente de consultas.

O framework fornece mecanismos de estado, confirmação, políticas e workflow determinístico. Regras concretas permanecem no agente.

O LLM pode participar da interpretação e composição, mas não deve ser a única fonte de verdade para afirmar que uma operação crítica foi executada.

Detalhes completos: [Workflows Transacionais e Estado](./03_transaction_workflows_and_state.md).

### Guardrails e Judges

Guardrails controlam ou validam comportamento durante o processamento.

Judges avaliam qualidade, grounding e outros critérios.

O core fornece mecanismos nativos e pontos de extensão. Guardrails/judges específicos de um domínio devem ser carregados pelo agente por configuração, evitando imports específicos dentro do framework.

Detalhes completos: [Guardrails, Judges e Avaliação Transacional](./06_guardrails_judges_and_transaction_evaluation.md).

### RAG, memória e ferramentas não são equivalentes

- **RAG** recupera conhecimento.
- **Memory** preserva contexto/fatos.
- **Tool** executa ou consulta uma capacidade externa.

Escolher o mecanismo errado cria bugs difíceis de diagnosticar. Uma informação que precisa ser atualizada em sistema não deve ser resolvida apenas por RAG; um fato durável do cliente não deve depender apenas do histórico do prompt.

### Observabilidade como contrato transversal

Roteamento, agente, transação, tool, guardrail, judge e falha precisam ser correlacionáveis.

Observabilidade deve registrar o que aconteceu, mas não controlar estado de negócio. Sequence, trace IDs e labels são infraestrutura de diagnóstico e auditoria.

Detalhes completos: [Observabilidade, Persistência e Prontidão Operacional](./11_observability_persistence_and_operational_readiness.md).

### Onde colocar uma nova funcionalidade

Antes de implementar, faça estas perguntas:

1. A capacidade é reutilizável por diferentes agentes?
2. Existe regra específica de domínio?
3. Precisa de estado entre turnos?
4. Produz efeito colateral?
5. Depende de sistema externo?
6. Deve ser configurável?
7. Precisa aparecer em observabilidade?
8. Precisa ser avaliada por guardrail/judge?

Uma feature reutilizável normalmente começa no core e é habilitada/configurada pelo agente. Uma regra de negócio normalmente começa no agente e usa interfaces do core.

### Anti-padrões

Evite:

- importar pacote concreto de um agente dentro do core;
- duplicar `AgentRuntimeMixin` em cada agente;
- codificar nomes de agentes, intents, tools ou empresas no runtime;
- usar resposta do LLM como prova de execução de operação;
- confundir checkpoint antigo com transação ativa;
- executar operação transacional sem política/confirmacão quando ela é requerida;
- acoplar agente diretamente a dezenas de serviços quando o MCP Gateway é a camada prevista;
- criar um novo documento funcional para cada bug fix em vez de atualizar o manual da feature.

### Caminho recomendado para um novo desenvolvedor

1. Leia a visão arquitetural neste documento.
2. Siga o [`README.md`](../../../README.md) do início ao fim para criar e executar um agente.
3. Quando chegar a uma capacidade específica, use o manual especializado correspondente.
4. Para falhas, comece pelo [Índice de Desenvolvimento](./INDEX_DEVELOPER_GUIDE.md), na seção **Buscar pelo problema**.
5. Antes de copiar código antigo, confirme API/import no template e no core atuais.

### Documentos relacionados

- [Tutorial principal — README.md](../../../README.md)
- [Roteamento, Stickiness e Intent Shift](./02_routing_stickiness_and_intent_shift.md)
- [Workflows Transacionais e Estado](./03_transaction_workflows_and_state.md)
- [MCP, Tools, Policies e Parâmetros](./04_mcp_integration_tools_and_policies.md)
- [Gateways e Autenticação](./05_agent_gateway_mcp_gateway_and_auth.md)
- [Guardrails e Judges](./06_guardrails_judges_and_transaction_evaluation.md)
- [RAG e BusinessContext](./07_rag_business_context_and_grounding.md)
- [Long-Term Memory e Checkpoint](./08_long_term_memory_and_checkpoint.md)
- [LLM Rich Response](./09_llm_rich_response_reasoning.md)
- [Performance, Cache e Runtime Assíncrono](./10_performance_cache_and_async_runtime.md)
- [Observabilidade e Prontidão Operacional](./11_observability_persistence_and_operational_readiness.md)
