### Recomendações de segurança, autenticação e autorização

Os componentes e templates deste framework podem ser adaptados a diferentes arquiteturas e requisitos de segurança. Para ambientes produtivos, recomenda-se que a solução seja avaliada de acordo com as políticas corporativas, os requisitos regulatórios aplicáveis e as melhores práticas de segurança da Oracle Cloud Infrastructure.

Como orientação geral, recomenda-se considerar autenticação e autorização em todas as interfaces acessíveis por usuários, canais, sistemas externos ou outros serviços. Na OCI, uma opção é utilizar o OCI API Gateway, ou uma camada equivalente, em conjunto com OAuth 2.0/OpenID Connect, validação de tokens e políticas de autorização por rota, scope, papel e tenant.

Métodos como HTTP Basic e API keys podem ser adequados para determinados cenários de integração, especialmente ambientes controlados ou sistemas legados. Nesses casos, recomenda-se utilizá-los sobre TLS, manter as credenciais em um serviço seguro de gerenciamento de segredos e adotar mecanismos de expiração e rotação.

A avaliação de segurança deve considerar, conforme os componentes utilizados pela solução:

- Agent Gateway, Channel Gateway e MCP Gateway;
- backends de agentes e comunicação entre gateways e backends;
- aplicações frontend e APIs consumidas pelo navegador;
- callbacks e webhooks provenientes de canais externos;
- conexões SSE, WebSocket ou outros mecanismos de streaming;
- histórico, memória, checkpoints e dados de sessão;
- endpoints administrativos, de debug, documentação, health e métricas;
- integrações com LLMs, bancos de dados, caches, mensageria e plataformas de observabilidade.

Recomenda-se tratar identificadores recebidos em payloads ou headers — como `tenant_id`, `agent_id`, `user_id`, `customer_id` e `session_id` — como informações de contexto, e não como evidência suficiente da identidade do solicitante. Quando aplicável, esses identificadores podem ser derivados de claims validadas ou relacionados à identidade autenticada antes da execução da operação.

Além da autenticação, recomenda-se avaliar a autorização sobre cada recurso acessado. Essa verificação pode considerar se o usuário ou serviço autenticado possui permissão para acessar o tenant, agente, sessão, histórico, checkpoint, backend ou ferramenta MCP solicitado.

Para comunicação entre serviços, podem ser consideradas identidades específicas por workload e mecanismos como OAuth 2.0 client credentials, OCI IAM, OKE Workload Identity, Instance Principals, Resource Principals ou mTLS. A escolha deve considerar a plataforma de execução e o modelo de confiança definido para a solução.

Para callbacks e webhooks, recomenda-se avaliar os mecanismos disponibilizados pelo provedor do canal, como assinatura digital ou HMAC, JWT, timestamp, identificador de mensagem, proteção contra replay e idempotência.

Em relação aos endpoints operacionais, é recomendável avaliar separadamente:

- endpoints de liveness, com resposta mínima sobre o estado do processo;
- endpoints de readiness, preferencialmente acessíveis apenas pela infraestrutura;
- endpoints de métricas, destinados aos coletores autorizados;
- endpoints de debug e teste, normalmente restritos a ambientes não produtivos;
- documentação OpenAPI, que pode ser desabilitada ou protegida em produção.

Também é recomendável utilizar TLS nas comunicações, restringir a exposição de serviços por meio de redes privadas, sub-redes, NSGs e allowlists, e considerar rate limiting, auditoria, rastreabilidade e monitoramento de acessos negados.

Segredos, tokens, senhas, certificados e chaves podem ser mantidos no OCI Secret Management ou em solução corporativa equivalente, evitando seu armazenamento em código-fonte ou arquivos de configuração versionados. Recomenda-se estabelecer políticas de acesso de menor privilégio, expiração e rotação compatíveis com a criticidade de cada credencial.

Estas recomendações representam uma referência inicial de melhores práticas. A definição final dos mecanismos de autenticação, autorização, proteção de rede e gestão de segredos permanece sob responsabilidade da equipe responsável pela arquitetura e pelo deployment, considerando o contexto, os riscos e os requisitos específicos de cada implementação.