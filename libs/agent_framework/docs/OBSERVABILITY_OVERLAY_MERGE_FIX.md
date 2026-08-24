# Correção do merge Default + Overlay de Observabilidade

## Problema
O default do framework estava ativo, porém em alguns caminhos o overlay do agente não era carregado. O efeito observado no Langfuse era `GRL.DLEX_IN`/`GRL.TOX` (default) em vez de `GRL.004`/`GRL.005` (Contas).

## Correção
O framework agora monta um único registry efetivo antes de qualquer resolução:

1. carrega `agent_framework/config/observability_mapping.yaml`;
2. localiza o overlay do agente;
3. faz merge por chave canônica, com o agente sobrescrevendo o default;
4. reconstrói os aliases somente depois do merge;
5. usa esse único registry em LLM provider, Telemetry, Analytics, OutputSupervisor e ParallelRailExecutor.

## Descoberta do overlay
Além de `OBSERVABILITY_CODE_MAPPING_PATH`, o framework autodetecta `config/observability_mapping.yaml` no cwd e nos roots de importação Python. O arquivo default empacotado do framework é excluído dessa descoberta.

Assim um agente com arquivo convencional de overlay não depende de alterar seu launcher ou `.env` para que a customização seja aplicada.

## Resultado esperado no Contas
- `guardrail.dlex_in` -> `GRL.004`
- `guardrail.tox` -> `GRL.005`
- componentes não sobrescritos continuam herdando o default do framework.

## Compatibilidade
Agentes antigos sem overlay continuam usando apenas o default do framework e preservam a taxonomia/ações históricas.
