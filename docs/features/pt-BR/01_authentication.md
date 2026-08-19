# Autenticação

> Feature do `agent_framework_oci` — guia em Português (PT-BR).

**Implementação principal:** `security/authentication.py`

---

### 1. O que é

Verifica quem pode acessar APIs, gateways e serviços protegidos antes que a requisição chegue ao agente.

### 2. Problema que resolve

Em agentes de produção, não é suficiente pedir ao LLM que “faça a coisa certa”. Esta feature move uma responsabilidade específica para uma camada controlada do framework, reduzindo comportamento imprevisível e código duplicado nos agentes de domínio.

### 3. Fluxo simplificado

```text
Cliente/Sistema
   ↓
Authentication Provider
   ↓
credencial válida?
   ├─ não → 401/nega acesso
   └─ sim → principal autenticado → agente
```

### 4. Como funciona internamente

O framework contém uma abstração `AuthenticationProvider` e implementações para cenários diferentes. Entre as implementações atuais estão `NoAuthenticationProvider`, `DenyAuthenticationProvider`, `BasicAuthenticationProvider`, `ApiKeyAuthenticationProvider`, `StaticBearerAuthenticationProvider`, `JwtAuthenticationProvider`, `OAuth2IntrospectionAuthenticationProvider` e `TrustedProxyAuthenticationProvider`.

A autenticação produz um `AuthenticatedPrincipal` com `subject`, `scheme` e, quando aplicável, `claims`. A regra de negócio do agente não deve validar senha/token diretamente.

### 5. Como ativar/configurar

A ativação exata depende do template/agente. Verifique o arquivo de settings, YAMLs de configuração e o template usado pelo serviço. Nem toda feature precisa de uma flag global: algumas são ativadas pelo contrato retornado por uma tool/workflow.

### 6. Exemplo

```python
from agent_framework.security.authentication import BasicAuthenticationProvider

provider = BasicAuthenticationProvider(
    client_id="client-a",
    secret_hash="pbkdf2_sha256:...",
)
result = await provider.authenticate(request)
if not result.authenticated:
    # negar acesso
    ...
```

Segredos podem ser verificados em formato simples, SHA-256 ou PBKDF2; em produção, prefira hashes fortes e secret stores.

### 7. Telemetria e observabilidade

Quando a feature participa de uma execução de agente, preserve `request_id`, `trace_id`, `session_id`, `agent_id`, `message_id` e demais chaves de correlação no estado/eventos. Isso permite acompanhar a decisão no Langfuse/Observer sem colocar lógica de observabilidade dentro do domínio.

### 8. Como testar

1. Crie um teste unitário do comportamento principal.
2. Crie um teste de integração do runtime quando houver estado entre turns.
3. Verifique o caso feliz e pelo menos um caso de falha/negação.
4. Confirme que não há side effects duplicados em retry/replay quando a feature toca transações.
5. Em produção, valide também telemetria e correlação de IDs.

### 9. Erros comuns

- Basic auth retornando 401: validar `Authorization: Basic ...` e o secret configurado.
- Confundir autenticação do usuário com `OCI_AUTH_MODE`: são problemas diferentes.
- Usar `NoAuthenticationProvider` em produção sem decisão explícita de arquitetura.

### 10. Relação com outras features

Esta feature deve ser usada junto das demais capacidades horizontais do framework, em vez de criar uma implementação paralela no agente de domínio. Em fluxos transacionais, considere especialmente **Clarification**, **Pause/Resume**, **Durable Idempotency**, **Workflow Error Recovery** e **Guardrails**.

### 11. Referências no repositório

- `libs/agent_framework/src/agent_framework/security/authentication.py`
- `Tuning-Performance/`
- `Documentacao/`
- `libs/agent_framework/docs/`
