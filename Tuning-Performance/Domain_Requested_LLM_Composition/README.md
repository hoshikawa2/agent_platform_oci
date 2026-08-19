# Domain Requested LLM Composition

## Objetivo

Permitir que uma tool/workflow de domínio informe que o resultado operacional não deve ser devolvido diretamente ao usuário e precisa ser redigido pelo LLM oficial do agente, sem criar um gateway LLM dentro do domínio.

## Contrato

A tool pode devolver, em qualquer nível do resultado:

```json
{
  "requires_llm_composition": true,
  "response_instruction": "Explique ao cliente a forma de devolução usando apenas os dados do workflow."
}
```

Também é aceito `response_instructions` como lista.

O `AgentRuntimeMixin` percorre recursivamente o resultado MCP. Quando a flag está ativa, `build_direct_mcp_answer()` retorna `None`; a resposta segue pelo LLM configurado no framework e recebe as evidências MCP no contexto normal do agente.

## Por que isso existe

Algumas operações, como pró-rata, possuem resultado determinístico e efeitos já concluídos, mas precisam de linguagem natural adequada ao canal. Antes, o domínio Contas possuía um gateway LLM próprio. Agora o domínio só declara a necessidade e a instrução; execução, credenciais, profiles, tracing e custos continuam no `agent_framework_oci`.

## Regras

- Não usar para decidir se uma transação deve ocorrer.
- Não usar para inventar valores ou protocolos.
- A instrução deve exigir que o LLM use somente as evidências retornadas pela tool/workflow.
- Pode coexistir com `requires_rag`; nesse caso o framework também executa RAG antes da composição.
