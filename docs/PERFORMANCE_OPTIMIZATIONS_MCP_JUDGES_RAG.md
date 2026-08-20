# Otimizações de execução MCP, RAG e Judges

- `mcp_tools` permanece allowlist; somente a consulta selecionada por `selection_keywords` é executada.
- Extração `strategy: hybrid` tenta `pattern` regex antes do perfil LLM.
- RAG é ignorado quando MCP bem-sucedido é suficiente, salvo perguntas de política/regra.
- `mcp_results` é fornecido como evidência ao groundedness judge.
- `judges.yaml` aceita `sample_rate` e `always_run_for_transactional`.
- Consultas estruturadas simples podem retornar resposta determinística sem LLM do agente.

## Mudança de consulta para ação transacional

A route stickiness é preemptada quando uma keyword explícita configurada em `routing.yaml` identifica outra intent/agente. Assim, uma sessão em `retail_order_tracking` muda para `retail_support_exchange_return` ao receber pedidos como “devolver pedido”. Além disso, respostas diretas de tools read-only são bloqueadas quando a mensagem contém `selection_keywords` de qualquer tool transacional registrada.

As palavras de ação ficam em `config/tools.yaml`; o runtime não mantém aliases de domínio hardcoded.


### Preempção determinística de mudança explícita de intent

A stickiness não chama um segundo LLM quando a mensagem contém uma mudança explícita que pode ser reconhecida deterministicamente. Keywords multi-token configuradas em `routing.yaml` aceitam até três tokens intermediários, preservando a ordem. Assim, `cancelar pedido` reconhece `quero cancelar meu pedido`, `cancelar o meu pedido` e `pode cancelar esse pedido`. Nesse caso a nova intent preempta a stickiness e o metadado `keyword_match_strategy=ordered_tokens` permite auditar a decisão. Mensagens sem sinal explícito continuam usando a route stickiness normalmente.
