# Correção — `max_tokens` por `llm_profiles.yaml` / `.env`

## Objetivo

Remover `max_tokens` efetivos fixados nos pontos de inferência do framework sem perder compatibilidade com os budgets anteriores.

A precedência usada pelos pontos corrigidos passa a ser:

1. `max_tokens` do profile selecionado em `llm_profiles.yaml`;
2. `max_tokens` do profile `default` do mesmo YAML, quando aplicável ao resolver;
3. `LLM_MAX_TOKENS` configurado no ambiente / `.env`;
4. valor legado do ponto de inferência, usado somente como fallback de compatibilidade.

O parâmetro interno `fallback_max_tokens` **não é uma nova configuração do usuário**. Ele apenas preserva o valor histórico quando não existe configuração externa.

## Pontos corrigidos

- Enterprise Router:
  - transaction parameter relevance: fallback legado `256`;
  - transaction intent shift: fallback legado `512`;
  - multi-intent: fallback legado `768`;
  - routing normal: fallback legado `512`.
- MCP parameter extraction: fallback `80`.
- Processing interruption classifier: fallback `8`.
- LLM guardrail: fallback `600`.
- RAG query rewrite: fallback `300`.
- RAG context compression: mantém a fórmula histórica `max(512, max_chars // 3)` apenas como fallback.
- Conversation summary memory: mantém a fórmula histórica `max(256, max_summary_chars // 4)` apenas como fallback.

## Atualização de `llm_profiles.yaml`

Como os quatro pontos do Enterprise Router usam o mesmo profile `router`, o profile foi ajustado para o **maior budget histórico**, conforme solicitado:

```yaml
router:
  max_tokens: 768
```

Também foram garantidos os profiles explícitos:

```yaml
processing_interruption_classifier:
  max_tokens: 8

mcp_parameter_extraction:
  max_tokens: 80
```

Os profiles já existentes foram mantidos:

- `guardrail: 600`
- `rag_rewriter: 300`
- `rag_compressor: 1200`
- `summary_memory: 1200`

## Compatibilidade

Se `llm_profiles.yaml` não estiver disponível e `LLM_MAX_TOKENS` não estiver definido, cada ponto corrigido continua usando seu budget histórico. Portanto a correção não transforma a ausência de configuração em `2048` apenas por causa do default global de `Settings`.
