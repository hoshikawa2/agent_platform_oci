# Tuning-Performance

Variantes e documentos de referência para comparar funcionalidades e impacto de performance.

- `Normal`: baseline do template.
- `Route_Stickness`: continuidade de rota, handoff e políticas transacionais conversacionais.
- `Long_Term_Memory`: memória de longo prazo.
- `Deterministic_Transactional_Workflow`: transações multi-etapas executadas por workflow LangGraph determinístico após clarification e confirmação.
- `Transaction_Evidence`: persistência e correlação de resultados transacionais como evidência operacional para turnos posteriores e groundedness.
- `Transaction_Pre_Validation`: pré-validação MCP side-effect-free antes da confirmação transacional; regras de elegibilidade permanecem no domínio.
- `Multi_Item_MCP`: operações MCP sobre listas de produtos/pedidos/serviços/ativos com confirmação única, canonicalização e resultado por item (`SUCCESS` / `PARTIAL_SUCCESS` / `FAILED`), sem criar motor multi-item no agente.
