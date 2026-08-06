# Manual geral de autenticação do Agent Framework OCI

> [!IMPORTANT]
> **Template de referência — requer adequação antes do uso produtivo.**
> Esta implementação demonstra pontos de extensão, providers, middleware e exemplos de configuração para autenticação. Ela não deve ser considerada uma solução pronta para produção nem substitui o desenho de segurança do projeto. Antes da implantação, a equipe responsável deve revisar, testar e adaptar o código às políticas corporativas, ao modelo de identidade, à topologia de rede, à gestão e rotação de segredos, aos requisitos regulatórios, à observabilidade, à alta disponibilidade e ao processo de resposta a incidentes do ambiente do cliente. Recomenda-se executar security review, threat modeling, testes de integração e testes de segurança antes da homologação e da produção.
## 1. Princípio arquitetural

A autenticação é uma capacidade transversal, opcional e reutilizável. Ela não depende da presença do `agent_gateway` ou do `mcp_gateway` e pode ser instalada em qualquer aplicação FastAPI que exponha uma fronteira protegida.

```text
agent_framework.security
  ├── backend independente de agente
  ├── agent_gateway
  ├── mcp_gateway
  ├── channel_gateway
  ├── MCP Server
  └── aplicação customizada
```

O framework fornece providers, middleware, instalação por configuração e políticas por rota. Cada projeto ou deployment decide onde ativar e qual mecanismo usar.

## 2. Onde autenticar

| Arquitetura | Ponto principal de autenticação |
|---|---|
| TIA → Agente Contas diretamente | backend do Agente Contas |
| TIA → Agent Gateway → Agente | Agent Gateway; backend deve ficar inacessível externamente ou usar autenticação interna |
| Agente → MCP Gateway → MCP Servers | MCP Gateway, com autorização adicional por agente e ferramenta |
| Agente → MCP Server diretamente | MCP Server |

Autenticar no gateway só libera o backend de autenticação externa quando o acesso direto ao backend é bloqueado por rede, `ClusterIP`, NetworkPolicy, security group, service mesh ou mTLS.

## 3. Instalação no código

Use a mesma função em qualquer app FastAPI, mudando apenas o prefixo:

```python
from fastapi import FastAPI
from agent_framework.security import install_authentication

app = FastAPI()
install_authentication(app, prefix="AGENT_AUTH")
```

Integrações fornecidas neste pacote:

```python
# Backend independente/template de autenticação
install_authentication(app, prefix="AGENT_AUTH")

# apps/agent_gateway
install_authentication(app, prefix="AGENT_GATEWAY_AUTH")

# apps/mcp_gateway
install_authentication(app, prefix="MCP_GATEWAY_AUTH")
```

A autenticação permanece opcional. Sem ativação, o comportamento original da aplicação é preservado.

## 4. Providers disponíveis

| Modo | Uso típico |
|---|---|
| `none` | rota pública ou desenvolvimento local |
| `deny` | rejeição explícita/default seguro em políticas |
| `basic` | integração system-to-system controlada, como TIA → Contas |
| `api_key` | integração simples entre serviços |
| `bearer_static` | token estático com rotação |
| `jwt` | access token JWT emitido por OAuth2/OIDC |
| `oauth2_introspection` | token opaco validado no authorization server |
| `trusted_proxy` | identidade validada por API Gateway, ingress ou service mesh |

mTLS deve ser terminado no ingress, API Gateway ou service mesh. A identidade resultante pode ser encaminhada com `trusted_proxy`, desde que o acesso direto e os headers internos sejam protegidos.

## 5. Configuração simples com um provider por aplicação

### Agente independente com Basic

```bash
AGENT_AUTH_ENABLED=true
AGENT_AUTH_MODE=basic
AGENT_AUTH_BASIC_CLIENT_ID=tia-contas
AGENT_AUTH_BASIC_SECRET_HASH=pbkdf2_sha256:310000:<salt>:<digest>
AGENT_AUTH_BASIC_REALM=agent-contas
AGENT_AUTH_PUBLIC_PATHS=/health
```

### Agent Gateway com JWT

```bash
AGENT_GATEWAY_AUTH_ENABLED=true
AGENT_GATEWAY_AUTH_MODE=jwt
AGENT_GATEWAY_AUTH_JWT_KEY=<public-key-pem>
AGENT_GATEWAY_AUTH_JWT_ALGORITHMS=RS256
AGENT_GATEWAY_AUTH_JWT_AUDIENCE=agent-gateway
AGENT_GATEWAY_AUTH_JWT_ISSUER=https://identity.example.com/
AGENT_GATEWAY_AUTH_PUBLIC_PATHS=/health,/ready,/live
```

### MCP Gateway com token de serviço

```bash
MCP_GATEWAY_AUTH_ENABLED=true
MCP_GATEWAY_AUTH_MODE=bearer_static
MCP_GATEWAY_AUTH_BEARER_TOKEN_HASH=sha256:<digest>
MCP_GATEWAY_AUTH_BEARER_PRINCIPAL=agent-platform
MCP_GATEWAY_AUTH_PUBLIC_PATHS=/health
```

## 6. Políticas por rota

Use um arquivo YAML quando uma aplicação precisar de providers ou requisitos diferentes por endpoint:

```bash
AGENT_AUTH_ENABLED=true
AGENT_AUTH_POLICIES_FILE=config/authentication.yaml
```

Para gateways, use respectivamente:

```bash
AGENT_GATEWAY_AUTH_POLICIES_FILE=config/authentication.yaml
MCP_GATEWAY_AUTH_POLICIES_FILE=config/authentication.yaml
```

Exemplo:

```yaml
providers:
  public:
    mode: none

  deny:
    mode: deny

  tia_basic:
    mode: basic
    client_id_env: TIA_AGENT_CLIENT_ID
    secret_hash_env: TIA_AGENT_SECRET_HASH
    realm: agent-contas

  platform_jwt:
    mode: jwt
    key_env: PLATFORM_JWT_PUBLIC_KEY
    algorithms: [RS256]
    audience: agent-platform
    issuer: https://identity.example.com/

policies:
  - name: health-public
    provider: public
    paths: [/health, /ready, /live]

  - name: tia-messages
    provider: tia_basic
    paths: [/gateway/message, /gateway/message/sse, /gateway/events/*]

  - name: administration
    provider: platform_jwt
    paths: [/debug/*, /admin/*]
    required_roles: [platform-admin]
    required_scopes: [agent.admin]

default_provider: deny
```

As políticas são avaliadas na ordem declarada; a primeira correspondência vence. Os paths usam padrões glob, como `/gateway/events/*`. Quando `default_provider` é omitido, o comportamento é `deny`.

Secrets nunca devem ser gravados no YAML. Use campos como `secret_hash_env`, `key_env` e `client_secret_env`.

Arquivos de exemplo:

- `Tuning-Performance/Authentication/authentication_policies.example.yaml`
- `apps/agent_gateway/config/authentication.example.yaml`
- `apps/mcp_gateway/config/authentication.example.yaml`
- `agent_template_backend_authentication/config/authentication.example.yaml`

## 7. Roles e scopes

Após autenticar, o middleware extrai roles de `roles`, `role` ou `groups`, e scopes de `scope`, `scp` ou `scopes`. Requisitos ausentes retornam `403 Forbidden`.

```yaml
required_roles: [platform-admin]
required_scopes: [agent.admin]
```

Basic, API Key e tokens estáticos identificam o consumidor, mas não produzem roles/scopes por padrão. Para autorização granular, use JWT/OAuth2, um provider customizado ou uma camada de autorização específica.

No MCP Gateway, autenticação não substitui a autorização por `agent_id`, tenant, ferramenta e tipo de operação.

## 8. Azure DevOps, Azure Key Vault e Kubernetes

O pipeline recupera secrets do Azure Key Vault e os injeta no deployment. O framework não chama Azure DevOps nem Key Vault diretamente.

```yaml
env:
  - name: AGENT_AUTH_ENABLED
    value: "true"
  - name: AGENT_AUTH_MODE
    value: basic
  - name: AGENT_AUTH_BASIC_CLIENT_ID
    valueFrom:
      secretKeyRef:
        name: contas-auth
        key: client-id
  - name: AGENT_AUTH_BASIC_SECRET_HASH
    valueFrom:
      secretKeyRef:
        name: contas-auth
        key: secret-hash
```

No cenário TIA → Contas, o TIA mantém o secret original e o agente pode armazenar somente o hash de validação.

## 9. Provider customizado

Um provider específico implementa somente:

```python
class AuthenticationProvider(Protocol):
    async def authenticate(self, request: Request) -> AuthenticationResult: ...
```

Nomes e regras particulares de TIA, GStreamer, TIM, Azure ou outro cliente devem ficar no projeto do cliente. A biblioteca deve permanecer genérica.

## 10. Testes rápidos

Sem credencial:

```bash
curl -i http://localhost:8000/gateway/message
```

Basic:

```bash
curl -i -u 'tia-contas:secret-original' \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"Olá","session_id":"auth-test","user_id":"tia"}}' \
  http://localhost:8000/gateway/message
```

## 11. Requisitos mínimos

- TLS obrigatório fora de localhost.
- Nunca registrar `Authorization`, API keys, secrets ou tokens.
- Restringir acesso direto aos backends quando a autenticação estiver centralizada no gateway.
- Usar comparação em tempo constante para credenciais estáticas.
- Usar PBKDF2 para secrets humanos e rotação periódica.
- Proteger `/debug`, sessões, métricas e documentação.
- Não confiar em headers de identidade vindos diretamente da internet.
- Separar autenticação, autorização e confirmação transacional.
- Aplicar rate limiting, limites de payload e auditoria no ingress/gateway.
