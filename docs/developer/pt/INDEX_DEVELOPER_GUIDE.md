
### Índice de Desenvolvimento — Agent Framework OCI

### Como usar esta documentação

A documentação possui três níveis claros:

1. **Tutorial principal:** [`README.md`](../../../README.md) — criação, configuração, execução e teste de um agente do início ao fim.
2. **Arquitetura:** [01 — Arquitetura e Conceitos](./01_architecture_and_concepts.md) — componentes, responsabilidades e onde implementar cada coisa.
3. **Referências especializadas:** manuais `02` a `12` — implementação profunda e troubleshooting por capacidade.

Se você está começando um novo agente, comece pelo `README.md`.

Se algo não está funcionando, use **Buscar pelo problema** abaixo.

### Buscar pelo problema

| Problema / dúvida | O que normalmente está envolvido | Onde procurar |
|---|---|---|
| O framework não encontra o agente/intenção correta | routing, intents, threshold, modo determinístico/LLM | [Routing e Stickiness](./02_routing_stickiness_and_intent_shift.md) |
| O agente fica preso no mesmo assunto e não troca de intent | route stickiness, intent shift, handoff | [Routing e Stickiness](./02_routing_stickiness_and_intent_shift.md) |
| Uma resposta que deveria preencher parâmetro é interpretada como novo intent | precedência transacional, parameter extraction | [Workflows Transacionais](./03_transaction_workflows_and_state.md) |
| A transação fica pedindo o mesmo parâmetro | estado transacional, extractor, schema | [Workflows Transacionais](./03_transaction_workflows_and_state.md) e [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| A confirmação “sim/não” não continua o fluxo | confirmation state, transaction state | [Workflows Transacionais](./03_transaction_workflows_and_state.md) |
| Uma fala inválida durante um `expected_input` vira `CONTINUAR` em vez de pedir esclarecimento | `semantic_classifier.unmatched_value`, `reprompt`, `contextual_reentry`, COER delegado | [Workflows Transacionais](./03_transaction_workflows_and_state.md) e [Feedback de Guardrails de Entrada](./12_input_guardrail_feedback_and_blocked_turns.md) |
| Uma transação encerrada reaparece | checkpoint antigo versus estado transacional ativo | [Workflows Transacionais](./03_transaction_workflows_and_state.md) e [LTM/Checkpoint](./08_long_term_memory_and_checkpoint.md) |
| O sistema diz que executou algo, mas não existe evidência | MCP result, estado `COMPLETED`, judges transacionais | [Workflows Transacionais](./03_transaction_workflows_and_state.md) e [Guardrails/Judges](./06_guardrails_judges_and_transaction_evaluation.md) |
| Uma tool não aparece ou não é encontrada | `tools.yaml`, catálogo MCP, discovery | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| MCP Server não aparece no catálogo | registration, manifest/discovery, MCP Gateway | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) e [Gateways](./05_agent_gateway_mcp_gateway_and_auth.md) |
| Parâmetros enviados à tool estão errados | schema, mapping, BusinessContext, extractor | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| Uma operação transacional executa sem confirmação | tool policy, `require_confirmation` | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| Uma busca por nome exige correspondência exata demais | extração/mapeamento de parâmetros e lógica do agente | [MCP/Tools](./04_mcp_integration_tools_and_policies.md) |
| Recebo 401 entre gateway/backend/MCP | Basic Auth, credenciais por hop | [Gateways e Auth](./05_agent_gateway_mcp_gateway_and_auth.md) |
| Preciso decidir se algo pertence ao framework ou ao agente | boundary core/agente | [Arquitetura e Conceitos](./01_architecture_and_concepts.md) |
| Guardrail específico de um agente está quebrando outro | extensibilidade, imports de domínio no core | [Guardrails e Judges](./06_guardrails_judges_and_transaction_evaluation.md) |
| Uma frase incompleta recebe mensagem genérica de “regra de segurança” | feedback de input guardrail, `COER`, blocked-turn state | [Feedback de Guardrails de Entrada](./12_input_guardrail_feedback_and_blocked_turns.md) |
| `route=blocked` aparece junto com tools/resultados de outro turno | limpeza de estado do turno bloqueado | [Feedback de Guardrails de Entrada](./12_input_guardrail_feedback_and_blocked_turns.md) |
| Workflow conclui e gera protocolo, mas a resposta final vira mensagem de segurança | `expected_protocols`, `CMP`, `DLEX_OUT`, ordem de `output_guardrails` | [Guardrails e Judges](./06_guardrails_judges_and_transaction_evaluation.md) |
| Judge não roda em uma transação | sampling, `always_run_for_transactional`, sinais transacionais | [Guardrails e Judges](./06_guardrails_judges_and_transaction_evaluation.md) |
| Groundedness está avaliando sem contexto correto | RAG context, MCP evidence, judge inputs | [RAG/Grounding](./07_rag_business_context_and_grounding.md) |
| RAG não encontra conteúdo | provider, ingestão, embeddings, configuração | [RAG/Grounding](./07_rag_business_context_and_grounding.md) |
| Não sei se usar RAG, memória ou tool | separação de responsabilidades | [Arquitetura e Conceitos](./01_architecture_and_concepts.md) e [RAG/Grounding](./07_rag_business_context_and_grounding.md) |
| Memória desaparece ao trocar de sessão | LTM versus conversation memory | [LTM e Checkpoint](./08_long_term_memory_and_checkpoint.md) |
| Memória de um cliente/agente aparece em outro | identity key, tenant/agent/customer isolation | [LTM e Checkpoint](./08_long_term_memory_and_checkpoint.md) |
| Preciso recuperar `reasoning_content` | `ainvoke_response()` | [LLM Rich Response](./09_llm_rich_response_reasoning.md) |
| `reasoning_content` vem `None` | provider/model não expõe o campo | [LLM Rich Response](./09_llm_rich_response_reasoning.md) |
| Há chamadas LLM desnecessárias | routing determinístico, concorrência, cache | [Performance](./10_performance_cache_and_async_runtime.md) |
| Há deadlock ou espera entre event loops | cross-loop sequence/runtime | [Performance](./10_performance_cache_and_async_runtime.md) |
| Logs/traces não correlacionam o mesmo agente | labels, IDs e mapeamento de observabilidade | [Observabilidade](./11_observability_persistence_and_operational_readiness.md) |
| Sequence está interferindo no processamento | implementação assíncrona de sequência | [Observabilidade](./11_observability_persistence_and_operational_readiness.md) e [Performance](./10_performance_cache_and_async_runtime.md) |
| Um exemplo antigo não compila | documentação histórica versus API atual | [Validação README x Código](./VALIDATION_README_ALIGNMENT.md) |
| Preciso criar um agente novo do zero | fluxo completo | [`README.md`](../../../README.md) |
| Preciso saber onde colocar uma nova feature | arquitetura e boundaries | [Arquitetura e Conceitos](./01_architecture_and_concepts.md) |

### Buscar pela funcionalidade

### [01 — Arquitetura e Conceitos](./01_architecture_and_concepts.md)

**O que é:** visão dos componentes, contratos e limites de responsabilidade.

**Use quando:** precisar entender a plataforma, decidir onde implementar algo ou evitar acoplamento entre core e agente.

### [02 — Routing, Route Stickiness e Intent Shift](./02_routing_stickiness_and_intent_shift.md)

**O que é:** referência completa de descoberta de agente/intent, stickiness, handoff e mudança de intenção.

**Use quando:** a mensagem cai no agente errado, não troca de intent ou perde continuidade.

### [03 — Workflows Transacionais e Estado](./03_transaction_workflows_and_state.md)

**O que é:** ciclo transacional multi-turno, estados, confirmação, pausa/retomada, `expected_input`, `semantic_classifier`, `unmatched_value`/`reprompt` e evidência operacional.

**Use quando:** há loops, confirmações incorretas, retomadas erradas, `CONTINUAR`/`contextual_reentry` indevido, `reprompt` ausente ou operações críticas.

### [04 — MCP, Tools, Policies e Extração de Parâmetros](./04_mcp_integration_tools_and_policies.md)

**O que é:** referência de tools, MCP Servers, mappings, policies e parameter extraction.

**Use quando:** integração/execução de tool está incorreta ou precisa ser criada.

### [05 — Agent Gateway, MCP Gateway e Autenticação](./05_agent_gateway_mcp_gateway_and_auth.md)

**O que é:** responsabilidades dos gateways, governança e autenticação entre componentes.

**Use quando:** houver problema de entrada, catálogo, autorização, 401 ou deployment dos gateways.

### [06 — Guardrails, Judges e Avaliação Transacional](./06_guardrails_judges_and_transaction_evaluation.md)

**O que é:** validações nativas/externas, judges, grounding e regras para turnos transacionais.

**Use quando:** uma validação bloqueia, não roda ou produz avaliação incorreta.

### [07 — RAG, BusinessContext e Grounding](./07_rag_business_context_and_grounding.md)

**O que é:** providers de RAG, contexto recuperado, BusinessContext e grounding.

**Use quando:** conhecimento recuperado não chega corretamente ao agente/judge.

### [08 — Long-Term Memory e Checkpoint](./08_long_term_memory_and_checkpoint.md)

**O que é:** memória durável, memória conversacional, identidade e snapshots de estado.

**Use quando:** contexto some, vaza ou workflow retoma do lugar errado.

### [09 — LLM Rich Response e reasoning_content](./09_llm_rich_response_reasoning.md)

**O que é:** resposta estruturada de inferência além do `str` retornado por `ainvoke()`.

**Use quando:** consumidores precisam de metadados, usage ou reasoning disponibilizado pelo provider.

### [10 — Performance, Cache e Runtime Assíncrono](./10_performance_cache_and_async_runtime.md)

**O que é:** otimizações de concorrência, cache, LLM e event loops.

**Use quando:** houver latência evitável, processamento serial ou deadlock.

### [11 — Observabilidade, Persistência e Prontidão Operacional](./11_observability_persistence_and_operational_readiness.md)

**O que é:** correlação, eventos, labels, sequence, persistência e diagnóstico.

**Use quando:** for necessário provar o caminho executado ou diagnosticar produção.

### [12 — Feedback de Guardrails de Entrada e Turnos Bloqueados](./12_input_guardrail_feedback_and_blocked_turns.md)

**O que é:** tratamento público de bloqueios de input, limpeza do estado do turno e validação da mensagem gerada pelos guardrails de saída.

**Use quando:** mensagens de bloqueio são genéricas, `COER` deveria pedir esclarecimento ou o metadata de um turno bloqueado contém routing/tools antigos.

### Tutorial principal

[`README.md`](../../../README.md) continua sendo a referência para o passo a passo completo:

`arquitetura → configuração → criação do agente → registro → estado → routing → tools → MCP → identidade → execução → testes → gateways → memória → RAG`.

### Manutenção

Não crie outro tutorial paralelo ao `README.md`.

Ao evoluir uma feature:

- atualize o README somente se o fluxo normal de desenvolvimento mudou;
- atualize o manual especializado com comportamento, configuração, exemplos e troubleshooting;
- atualize SPECs se o contrato mudou;
- mantenha release notes como histórico, não como única documentação atual.
