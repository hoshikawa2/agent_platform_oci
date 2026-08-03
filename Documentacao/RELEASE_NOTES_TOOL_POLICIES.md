# Release notes - políticas read-only/transacionais

## Alterações

- Novo `ToolPolicyRegistry` opcional na biblioteca compartilhada.
- Validação central no `MCPToolRouter`, inclusive para chamadas diretas.
- Tipos mínimos `read_only` e `transactional`.
- Confirmação estrita por `confirmed: true` ou `confirmation: true`.
- Suporte opcional a campos obrigatórios por política.
- Fallback automático para `tool_type`, `requires`, `confirmation_required` e `execution_policy` de `tools.yaml`.
- `config/tool_policies.yaml` e variável `TOOL_POLICIES_PATH` nos templates principais, Day Zero e variantes de `Tuning-Performance/Normal` e `Tuning-Performance/Route_Stickness`.
- Testes unitários de política e compatibilidade adicionados em `tests/unit/test_tool_policies.py`.

## Verificações executadas

- Compilação de `libs`, `templates`, `Tuning-Performance` e `tests`: aprovada.
- Validação estrutural dos seis arquivos YAML: aprovada.
- Casos isolados do loader (política transacional, confirmação, ausência de arquivo e ausência de cadastro): aprovados.
- Renderização dos dois manuais Word atualizados: aprovada, sem cortes ou sobreposição nas páginas adicionadas.

## Limitação do ambiente de validação

A suíte `pytest` foi preparada, mas não pôde ser executada integralmente neste ambiente porque `pytest` e as dependências de runtime do projeto não estavam instalados e o acesso ao índice de pacotes expirou. Para reproduzir em um ambiente do projeto:

```bash
PYTHONPATH=libs/agent_framework/src:templates/agent_template_backend python -m pytest -q
```

## Correção de integração backend/MCP
- `mcp_tools` passou a ser tratado como allowlist.
- Ações não são mais executadas automaticamente junto com consultas.
- Confirmação transacional é persistida e retomada no turno seguinte.
- Corrigida incompatibilidade `reason`/`motivo` no MCP Retail.
- Adicionado pedido entregue determinístico para testes (`123`).
- Removida keyword genérica `produto` da intenção Telecom para evitar colisão com devoluções Retail.
- Templates Normal e Route_Stickness em `Tuning-Performance` foram sincronizados.
