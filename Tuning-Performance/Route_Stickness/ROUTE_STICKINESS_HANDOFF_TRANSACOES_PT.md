# Route Stickiness, Handoff, Encerramento e Políticas MCP

## 1. Objetivo

Este material consolida o desenho de continuidade semântica de rota, transferência para atendimento humano, encerramento de sessão e proteção mínima de ferramentas MCP de consulta e transação no Agent Framework OCI.

As capacidades são complementares:

- **Route stickiness** decide se o turno permanece com o agente ativo ou volta ao Enterprise Router.
- **Handoff e encerramento** tratam ações globais de sessão sem delegá-las a agentes de domínio.
- **Políticas MCP** decidem se uma ferramenta já selecionada pode executar, com diferenciação entre `read_only` e `transactional`.

Todas são opcionais e preservam o comportamento anterior quando desabilitadas ou não configuradas.

## 2. Visão arquitetural

```text
Nova mensagem
   |
   +-- sessão já encerrada? -- sim --> rejeitar reutilização da sessão
   |
   +-- route stickiness habilitada --> classificador semântico leve
   |       |
   |       +-- CONTINUE + agente ativo --> agente ativo
   |       +-- ROUTE/baixa confiança/erro --> Enterprise Router
   |       +-- HUMAN_HANDOFF --> nó global human_handoff
   |       +-- END_SESSION --> nó global end_session
   |
   +-- route stickiness desabilitada --> Enterprise Router
                                           |
                                           v
                                     agente de domínio
                                           |
                                           v
                              ferramenta MCP selecionada
                                           |
                                           v
                              política read-only/transacional
                                  |                    |
                              permitida            bloqueada
                                  |                    |
                                  v                    v
                           MCP Gateway/Server     resposta segura
```

O classificador de continuidade não responde ao usuário, não escolhe outro agente, não executa ferramentas e não interpreta regras de negócio. O MCP Server continua sendo a autoridade final para autenticação, autorização, idempotência, validação e atomicidade.

## 3. Decisões de continuidade e sessão

| Decisão | Condição | Destino | Executa agente/MCP? |
|---|---|---|---|
| `CONTINUE` | A mensagem permanece no domínio do agente ativo e supera o threshold | agente ativo | sim, conforme o fluxo do agente |
| `ROUTE` | Mudança de assunto, dúvida, baixa confiança ou falha | Enterprise Router | somente após nova rota |
| `HUMAN_HANDOFF` | Solicitação de atendimento humano | nó global `human_handoff` | não |
| `END_SESSION` | Solicitação ou confirmação de encerramento | nó global `end_session` | não |

No primeiro turno, `CONTINUE` é normalizado para `ROUTE`, pois ainda não existe agente ativo. `HUMAN_HANDOFF` e `END_SESSION` podem ser identificados mesmo no primeiro turno.

### 3.1 Por que a decisão é semântica

Não são usadas regexes, listas de frases, pronomes ou palavras-chave específicas de idioma. O código mantém somente decisões técnicas:

- feature flag;
- existência de agente ativo;
- threshold de confiança;
- validação do contrato de saída;
- fallback em timeout, erro ou JSON inválido.

Isso evita manutenção de padrões linguísticos por domínio e mantém o comportamento multilíngue no perfil LLM.

## 4. Contratos globais de sessão

### 4.1 Handoff humano

O router produz:

```json
{
  "route": "human_handoff",
  "intent": "human_handoff",
  "method": "continuity",
  "handoff": true,
  "metadata": {
    "session_control": "HUMAN_HANDOFF",
    "route_bypassed": true
  }
}
```

O nó global define:

- `session_control=HUMAN_HANDOFF`;
- `human_handoff_requested=true`;
- `session_ended=false`;
- `next_state=HUMAN_HANDOFF_REQUESTED`.

O evento `session.human_handoff.requested` permite que a integração escolha fila, fornecedor e protocolo. O framework não presume uma plataforma humana específica.

### 4.2 Encerramento

O router produz:

```json
{
  "route": "end_session",
  "intent": "end_session",
  "method": "continuity",
  "metadata": {
    "session_control": "END_SESSION",
    "route_bypassed": true
  }
}
```

O nó global define:

- `session_control=END_SESSION`;
- `session_ended=true`;
- `human_handoff_requested=false`;
- `next_state=SESSION_ENDED`.

O evento `session.end.requested` deve ser emitido antes da persistência. Para encerramento definitivo, `session_ended=true` precisa ser persistido e novas mensagens com a mesma `session_id` devem ser bloqueadas antes de guardrails, roteamento, agentes, RAG, judges ou MCP.

## 5. Políticas MCP read-only e transacionais

### 5.1 Responsabilidade

Depois que a rota e o agente selecionam uma ferramenta, o `MCPToolRouter` aplica a política imediatamente antes da chamada externa:

- `read_only`: consulta sem alteração de estado; por padrão não exige confirmação.
- `transactional`: operação que altera estado; pode exigir confirmação explícita e campos obrigatórios.

A classificação não cria outro roteador LLM e não substitui a allowlist atual de ferramentas por agente/intenção.

### 5.2 Configuração no backend

```text
templates/agent_template_backend/config/tool_policies.yaml
```

```dotenv
TOOL_POLICIES_PATH=./config/tool_policies.yaml
```

```yaml
version: 1

defaults:
  operation_type: read_only
  require_confirmation: false

tool_policies:
  consultar_plano:
    operation_type: read_only

  alterar_plano:
    operation_type: transactional
    require_confirmation: true
    requires: [new_plan_id]

  cancelar_servico:
    operation_type: transactional
    require_confirmation: true
```

Uma transação confirmada deve receber um booleano literal:

```json
{
  "new_plan_id": "CONTROLE_100",
  "confirmed": true
}
```

Também é aceito `"confirmation": true`. Strings como `"true"` não confirmam a operação.

### 5.3 Compatibilidade

- Se `tool_policies.yaml` não existir, o framework preserva `tool_type`, `requires`, `confirmation_required` e `execution_policy` de `tools.yaml`.
- Tools antigas sem política executam como antes.
- Uma política explícita no arquivo novo prevalece para tipo e confirmação daquela tool.
- `tools.yaml` continua sendo a fonte de endpoint, schema, habilitação e cache.
- A política fica no backend, e não em `libs/agent_framework`, porque varia por aplicação e domínio.

## 6. Interação entre continuidade e transações

Route stickiness não autoriza transações. Mesmo quando `CONTINUE` mantém o agente ativo, toda ferramenta passa novamente pelo controle MCP.

Exemplo:

```text
Usuário: Quero mudar para o plano Controle 100.
Agente: Confirma a alteração para o Controle 100?
Usuário: Sim.
  -> CONTINUE mantém product_agent
  -> agente recupera a ação pendente
  -> MCPToolRouter valida confirmation=true
  -> alterar_plano executa
```

Em `HUMAN_HANDOFF` ou `END_SESSION`, nenhum agente de domínio ou MCP deve executar. Uma transação pendente deve ser invalidada ou mantida suspensa conforme política explícita da aplicação; nunca deve executar implicitamente após handoff ou encerramento.

## 7. Configuração da continuidade

```dotenv
ENABLE_ROUTE_STICKINESS=true
ROUTE_STICKINESS_LLM_PROFILE=route_continuity
ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.90
ROUTE_STICKINESS_HISTORY_TURNS=2
ROUTE_STICKINESS_MAX_TOKENS=80
HUMAN_HANDOFF_MESSAGE=Vou encaminhar seu atendimento para uma pessoa.
END_SESSION_MESSAGE=Atendimento encerrado. Obrigado pelo contato.
```

```yaml
profiles:
  route_continuity:
    provider: oci_openai
    model: openai.gpt-4.1-mini
    temperature: 0
    max_tokens: 80
    timeout_seconds: 5
```

Use o menor modelo aprovado no ambiente OCI. O classificador recebe apenas agente ativo, capacidades derivadas das intents, intent/domínio anteriores, histórico recente limitado e mensagem atual. Não recebe RAG completo, resultados MCP integrais, prompt do agente ou regras de negócio.

## 8. Segurança e fallback

- Apenas decisões acima do threshold são aceitas.
- `CONTINUE` sem agente ativo vira `ROUTE`.
- Baixa confiança, timeout, erro ou JSON inválido voltam ao Enterprise Router.
- Handoff e encerramento não executam tools.
- Confirmação transacional exige booleano literal.
- A validação conversacional não substitui controles do MCP Server.
- Sessões encerradas devem ser bloqueadas na entrada.
- Retries de transações devem usar idempotência no serviço de destino.

## 9. Telemetria

Evento de continuidade:

```json
{
  "decision": "CONTINUE",
  "confidence": 0.97,
  "active_agent": "product_agent",
  "route_bypassed": true,
  "profile_name": "route_continuity"
}
```

Campos recomendados:

- `route_decision.method`;
- `active_agent`;
- `route_bypassed`;
- `continuity_signal`;
- `session_control`;
- `human_handoff_requested`;
- `session_ended`;
- `tool_name`;
- `operation_type`;
- `policy_source`;
- `blocked_by_policy`.

## 10. Testes e benchmark

Casos mínimos:

1. continuidade com bypass;
2. mudança de domínio com retorno ao router;
3. baixa confiança, timeout e JSON inválido;
4. `CONTINUE` sem agente ativo;
5. handoff e encerramento no primeiro turno e em turnos posteriores;
6. bloqueio de mensagem após sessão encerrada;
7. consulta sem confirmação;
8. transação sem confirmação, com string e com booleano válido;
9. campo obrigatório ausente;
10. ausência de `tool_policies.yaml` usando comportamento legado.

```bash
PYTHONPATH=libs/agent_framework/src:templates/agent_template_backend python -m pytest -q
```

Para benchmark, compare a mesma conversa com a funcionalidade habilitada e desabilitada. Registre `route_bypassed`, chamadas ao `llm.router`, latência de `llm.route_continuity`, tokens por perfil e latência total p50/p95/p99. Só atribua ganho à stickiness quando houver `route_bypassed=true` e nenhuma geração do Enterprise Router no mesmo turno.

## 11. Critério de adoção

Adote route stickiness quando houver conversas multi-turno com retornos frequentes ao mesmo agente. Cadastre políticas apenas para ferramentas que precisem de comportamento adicional, começando pelas transações que exigem confirmação. Mantenha autorização, idempotência e regras de negócio no MCP Server para evitar duas fontes de verdade.

