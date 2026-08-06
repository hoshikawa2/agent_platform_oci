# Implementação técnica

> [!IMPORTANT]
> **Template de referência — requer adequação antes do uso produtivo.**
> Esta implementação demonstra pontos de extensão, providers, middleware e exemplos de configuração para autenticação. Ela não deve ser considerada uma solução pronta para produção nem substitui o desenho de segurança do projeto. Antes da implantação, a equipe responsável deve revisar, testar e adaptar o código às políticas corporativas, ao modelo de identidade, à topologia de rede, à gestão e rotação de segredos, aos requisitos regulatórios, à observabilidade, à alta disponibilidade e ao processo de resposta a incidentes do ambiente do cliente. Recomenda-se executar security review, threat modeling, testes de integração e testes de segurança antes da homologação e da produção.
## Biblioteca

`libs/agent_framework/src/agent_framework/security` contém:

- contratos e resultados de autenticação;
- Basic, API Key, Bearer estático, JWT, OAuth2 Introspection e Trusted Proxy;
- provider `none` para rotas públicas;
- provider `deny` para default seguro;
- middleware de provider único;
- middleware de políticas por rota;
- factory por ambiente ou mapping;
- instalador reutilizável para qualquer app FastAPI.

## Integrações

- `apps/agent_gateway/app/main.py`: `AGENT_GATEWAY_AUTH_*`
- `apps/mcp_gateway/app/main.py`: `MCP_GATEWAY_AUTH_*`
- `Tuning-Performance/Authentication/agent_template_backend_authentication/app/main.py`: `AGENT_AUTH_*`

Nenhuma integração é obrigatória. A instalação ocorre somente quando `*_AUTH_ENABLED=true`, quando um modo diferente de `none` é configurado ou quando existe `*_AUTH_POLICIES_FILE`.

## Compatibilidade

`AuthenticationMiddleware` e `create_authentication_provider()` foram mantidos para compatibilidade. O caminho recomendado para novos projetos é `install_authentication()`.
