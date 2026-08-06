# Authentication

> [!IMPORTANT]
> **Template de referência — requer adequação antes do uso produtivo.**
> Esta implementação demonstra pontos de extensão, providers, middleware e exemplos de configuração para autenticação. Ela não deve ser considerada uma solução pronta para produção nem substitui o desenho de segurança do projeto. Antes da implantação, a equipe responsável deve revisar, testar e adaptar o código às políticas corporativas, ao modelo de identidade, à topologia de rede, à gestão e rotação de segredos, aos requisitos regulatórios, à observabilidade, à alta disponibilidade e ao processo de resposta a incidentes do ambiente do cliente. Recomenda-se executar security review, threat modeling, testes de integração e testes de segurança antes da homologação e da produção.
Implementação de referência para autenticação transversal no Agent Framework OCI.

Inclui:

- providers genéricos em `libs/agent_framework/security`;
- instalação opcional por `install_authentication()`;
- políticas por rota, método, roles e scopes;
- integração opcional em `apps/agent_gateway`;
- integração opcional em `apps/mcp_gateway`;
- backend independente autenticado em `agent_template_backend_authentication`;
- exemplos YAML sem secrets embutidos;
- manual completo no diretório `docs` do agente.

A implementação não pressupõe o uso de gateways. Cada fronteira HTTP pode ativar autenticação com um prefixo de ambiente isolado.
