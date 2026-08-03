# Route Stickiness Semântica e Controle Global de Sessão no Agent Framework OCI

## Objetivo

A route stickiness semântica evita executar novamente o Enterprise Router quando uma nova mensagem continua claramente sob responsabilidade do agente ativo. A implementação usa um perfil LLM leve e não contém regexes, listas de frases, palavras específicas de idioma ou regras conversacionais por domínio.

A funcionalidade é opcional e preserva integralmente o comportamento anterior quando desabilitada, quando não existe agente ativo, quando a confiança é baixa ou quando ocorre erro na inferência.

## Decisão arquitetural

O classificador possui uma responsabilidade transversal e restrita:

- `CONTINUE`: a mensagem continua com o agente ativo;
- `ROUTE`: a mensagem deve seguir para o Enterprise Router normal;
- `HUMAN_HANDOFF`: o usuário solicitou atendimento humano;
- `END_SESSION`: o usuário solicitou ou confirmou o encerramento do atendimento.

Ele não responde ao usuário, não escolhe outro agente, não executa ferramentas e não interpreta regras de negócio. As duas ações globais são encaminhadas para nós próprios do grafo, evitando que cada agente implemente prompts ou regras de sessão.

Fluxo:

```text
Todos os turnos com a funcionalidade habilitada
        -> classificador semântico leve
             CONTINUE + agente ativo             -> agente ativo
             ROUTE/baixa confiança/erro          -> Enterprise Router
             HUMAN_HANDOFF                       -> nó global human_handoff
             END_SESSION                         -> nó global end_session

No primeiro turno, CONTINUE é normalizado para ROUTE porque ainda não existe agente ativo. Handoff e encerramento podem ser reconhecidos mesmo no primeiro turno.
```

## Por que não há regras determinísticas

A interpretação de linguagem natural por regex exige manutenção contínua para novas construções, idiomas e domínios. Além disso, transfere aos times dos agentes a responsabilidade de manter flags e padrões de continuidade.

Esta implementação mantém no código apenas decisões técnicas inevitáveis:

- funcionalidade habilitada ou desabilitada;
- validação de que `CONTINUE` exige agente ativo;
- threshold de confiança;
- fallback em timeout, erro ou JSON inválido.

Não existem `DEFAULT_FOLLOWUP_PATTERNS`, regras de repetição, listas de pronomes ou keywords de continuidade.

## Configuração

### `.env`

```dotenv
ENABLE_ROUTE_STICKINESS=true
ROUTE_STICKINESS_LLM_PROFILE=route_continuity
ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.90
ROUTE_STICKINESS_HISTORY_TURNS=2
ROUTE_STICKINESS_MAX_TOKENS=80
HUMAN_HANDOFF_MESSAGE=Vou encaminhar seu atendimento para uma pessoa.
END_SESSION_MESSAGE=Atendimento encerrado. Obrigado pelo contato.
```

- `ENABLE_ROUTE_STICKINESS`: ativa a capacidade.
- `ROUTE_STICKINESS_LLM_PROFILE`: perfil existente em `llm_profiles.yaml`.
- `ROUTE_STICKINESS_CONFIDENCE_THRESHOLD`: confiança mínima para bypass.
- `ROUTE_STICKINESS_HISTORY_TURNS`: quantidade de turnos recentes enviados ao classificador.
- `ROUTE_STICKINESS_MAX_TOKENS`: limite de saída do classificador.
- `HUMAN_HANDOFF_MESSAGE`: mensagem devolvida pelo nó global de transferência humana.
- `END_SESSION_MESSAGE`: mensagem devolvida pelo nó global de encerramento.

### Perfil leve

```yaml
profiles:
  route_continuity:
    provider: oci_openai
    model: openai.gpt-4.1-mini
    temperature: 0
    max_tokens: 80
    timeout_seconds: 5
```

O modelo acima é apenas um exemplo. Deve ser substituído pelo menor modelo aprovado e disponível no ambiente OCI. O framework reutiliza o mecanismo já existente de `LLM_PROFILES_PATH`; não há uma segunda configuração de provider/model específica para a funcionalidade.

## Contexto enviado ao modelo

O classificador recebe somente:

- agente ativo;
- descrições das capacidades dos agentes derivadas das intents já existentes;
- intent e domínio anteriores;
- histórico recente limitado;
- mensagem atual.

Não são enviados RAG completo, resultados MCP integrais, prompt do agente ou regras de negócio.

## Exemplos

### Continuidade

```text
Usuário: Qual é o meu plano?
Agente: Seu plano é Controle 50GB.
Usuário: O que está incluso?
```

Resultado esperado:

```json
{
  "method": "continuity",
  "route": "product_agent",
  "route_bypassed": true
}
```

### Mudança de domínio

```text
Usuário: Qual é o meu plano?
Agente: Seu plano é Controle 50GB.
Usuário: Agora quero contestar uma cobrança.
```

O classificador retorna `ROUTE` e o Enterprise Router seleciona o agente apropriado.

### Baixa confiança ou falha

Qualquer resultado abaixo do threshold, timeout ou JSON inválido executa o Enterprise Router. A funcionalidade é fail-safe e nunca força continuidade em caso de dúvida.

## Telemetria

Evento `router.continuity`:

```json
{
  "decision": "CONTINUE",
  "confidence": 0.97,
  "active_agent": "product_agent",
  "route_bypassed": true,
  "profile_name": "route_continuity"
}
```

Quando ocorre bypass, `route_decision.method` é `continuity` e o estado final contém:

- `active_agent`;
- `route_bypassed`;
- `continuity_signal`.

## Testes

```bash
pytest -q tests/unit/test_semantic_route_stickiness.py
```

Os testes validam:

- continuidade com bypass;
- mudança de assunto com fallback para o router;
- baixa confiança;
- saída inválida;
- primeiro turno sem chamada ao classificador.

## Benchmark recomendado

Executar a mesma conversação com a funcionalidade desabilitada e habilitada, registrando por turno:

- `route_bypassed`;
- `route_decision.method`;
- latência do `llm.route_continuity`;
- chamadas ao `llm.router`;
- tokens por perfil;
- latência total p50, p95 e p99.

A redução de tempo total somente deve ser atribuída à stickiness quando houver `route_bypassed=true` e ausência da geração `llm.router` no mesmo turno.


## Contratos globais

### Human handoff

Quando a decisão for `HUMAN_HANDOFF`, o router retorna:

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

O nó `human_handoff` produz os campos:

- `session_control=HUMAN_HANDOFF`;
- `human_handoff_requested=true`;
- `session_ended=false`;
- `next_state=HUMAN_HANDOFF_REQUESTED`.

O evento `session.human_handoff.requested` é emitido para que o Channel Gateway ou a integração do cliente encaminhe a conversa à plataforma humana. O framework não presume uma fila, fornecedor ou protocolo específico.

### Encerramento

Quando a decisão for `END_SESSION`, o router retorna:

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

O nó `end_session` produz:

- `session_control=END_SESSION`;
- `session_ended=true`;
- `human_handoff_requested=false`;
- `next_state=SESSION_ENDED`.

O evento `session.end.requested` é emitido antes da persistência. O backend continua responsável por aplicar a política concreta de expiração, fechamento ou limpeza da sessão em cada canal.

## Exemplos

| Mensagem | Contexto | Decisão esperada | Destino |
|---|---|---|---|
| `o que está incluso?` | `product_agent` ativo | `CONTINUE` | `product_agent` |
| `agora quero contestar uma cobrança` | `product_agent` ativo | `ROUTE` | Enterprise Router |
| `quero falar com uma pessoa` | com ou sem agente ativo | `HUMAN_HANDOFF` | nó `human_handoff` |
| `obrigado, pode encerrar` | com ou sem agente ativo | `END_SESSION` | nó `end_session` |

## Segurança e fallback

- Somente decisões acima do threshold são aceitas.
- `CONTINUE` sem agente ativo vira `ROUTE`.
- JSON inválido, timeout ou erro usa o Enterprise Router.
- Handoff e encerramento não executam agentes de domínio nem ferramentas MCP.
- O classificador não encerra fisicamente conexões nem seleciona filas humanas; ele emite um contrato global para integração.
