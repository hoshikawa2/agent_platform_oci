# ADR — Motor de workflows transacionais no Agent Framework OCI

## Decisão

Adicionar ao framework uma capacidade opcional de execução determinística baseada em LangGraph. O motor é genérico; definições YAML e actions de domínio permanecem nos agentes.

## Razão

Operações multi-etapas com efeitos colaterais não devem depender do LLM para escolher a sequência crítica. A solução reduz tokens, latência e variação, além de melhorar auditoria, testes e versionamento.

## Compatibilidade

`execution.mode` assume `direct_tool`. Projetos existentes continuam usando MCP diretamente. A adoção de workflow é explícita por tool e pode ser controlada por `ENABLE_TRANSACTIONAL_WORKFLOWS`.

## Limites desta entrega

A base inclui validação, versionamento por arquivo, registry, execução sync/async, condições, retry por nó, cache de grafos e adapter de policy. Persistência corporativa de execution records, compensação/Saga, autorização por escopo e emissão de IC/NOC específica devem ser conectadas às abstrações existentes de cada deployment antes do uso em transações financeiras críticas.
