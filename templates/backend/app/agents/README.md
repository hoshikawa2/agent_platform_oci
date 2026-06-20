# Agentes do Template Backend Enterprise

Os arquivos desta pasta preservam a estrutura real esperada pelo workflow, mas
não executam lógica de negócio pronta.

Cada agente mostra:

- como emitir IC;
- como emitir NOC;
- como emitir GRL;
- como coletar MCP via `_collect_tool_context()`;
- como recuperar RAG via `_retrieve_rag_context()`;
- onde chamar LLM/cache.

A implementação original do exemplo está comentada no fim de cada arquivo.
