# Disclaimer — template de autenticação

Este conteúdo é um **template de referência técnica** criado para demonstrar como integrar mecanismos genéricos de autenticação ao Agent Framework OCI, ao Agent Gateway, ao MCP Gateway e a aplicações FastAPI independentes.

O código, os arquivos YAML, as variáveis de ambiente, os providers, as políticas por rota e os exemplos de deployment **não constituem uma implementação final ou automaticamente adequada para produção**. Cada projeto deve lapidar e adaptar a solução conforme sua arquitetura, seus fluxos de confiança e suas exigências de segurança.

Antes de usar em homologação ou produção, é responsabilidade da equipe do projeto avaliar e implementar, conforme aplicável:

- integração com o provedor corporativo de identidade;
- definição de autenticação e autorização por sistema, rota, método, tenant, role e scope;
- armazenamento, distribuição e rotação de credenciais e chaves;
- TLS ou mTLS e proteção das comunicações internas e externas;
- bloqueio de acessos que contornem gateways ou proxies de confiança;
- validação de issuer, audience, algoritmo, expiração e revogação de tokens;
- proteção contra replay, brute force, credential stuffing e abuso de endpoints;
- rate limiting, timeout, circuit breaker e controles de disponibilidade;
- mascaramento de dados sensíveis em logs, traces e mensagens de erro;
- auditoria, observabilidade, alertas e resposta a incidentes;
- requisitos legais, regulatórios e políticas corporativas;
- threat modeling, security review, testes de integração, testes de carga e testes de segurança.

Os exemplos de Basic Authentication, API Key, Bearer estático, JWT, OAuth2 Introspection e Trusted Proxy devem ser entendidos como pontos de extensão. A seleção e a configuração finais dependem do cliente, da infraestrutura e do modelo de risco.

A promoção para produção deve ocorrer somente após aprovação formal das equipes responsáveis por arquitetura, segurança, infraestrutura e operação.
