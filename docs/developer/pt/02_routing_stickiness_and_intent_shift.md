
### Routing, Route Stickiness e Intent Shift

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **routing, stickiness, mudança de intent, roteamento determinístico/LLM e isolamento multiagente**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

Routing, stickiness, mudança de intent, roteamento determinístico/llm e isolamento multiagente.

### Conteúdo técnico consolidado

### Roteamento Multi-Agent, Route Stickiness e Intent Shift

Manual completo de decisão de rota, Enterprise Router, Supervisor, continuidade semântica, ações globais de sessão, mudança explícita de intent e precedência durante transações.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### Manual de roteamento multi-agent

> Conteúdo consolidado a partir de `Documentacao/Manual de Roteamento Multi-Agent.docx`.

Manual de Roteamento Multi-Agent
Agent Gateway (Global Supervisor), Enterprise Router e Supervisor no projeto agent_framework_oci

### Sumário

- 1. Objetivo do manual
- 2. O que é roteamento em um backend multi-agent
- 3. Por que estruturar o roteamento para escala, simplicidade e performance
- 4. Estrutura real de folders do projeto
- 5. Visão geral da arquitetura
- 6. Componentes principais do roteamento
- 7. Tipos de roteamento existentes no projeto
- 8. Caminho 1 - Implementar agentes com Enterprise Router
- 9. Caminho 2 - Implementar agentes com Supervisor
- 10. Como configurar agentes, intents, MCP tools e estado conversacional
- 11. Como o LangGraph executa o roteamento
- 12. Exemplos funcionais de ponta a ponta
- 13. Como testar com curl
- 14. Observabilidade, memória e checkpoint
- 15. Troubleshooting
- 16. Checklist de implementação
- 17. Agent Servers Distintos (Global Supervisor ou Agent Gateway)

### Objetivo do manual

Este manual explica como o roteamento multi-agent está implementado no projeto agent_framework_oci e como evoluir o backend para novos agentes sem perder governança, performance e rastreabilidade.
Os componentes estão distribuídos entre o pacote reutilizável agent_framework e o template FastAPI agent_template_backend.

### O que é roteamento em um backend multi-agent

Roteamento é a etapa que transforma uma mensagem de usuário em uma decisão operacional: qual agente deve responder, com qual intenção, quais ferramentas MCP podem ser usadas, qual domínio está em jogo e qual contexto deve ser preservado.
Em um sistema multi-agent, o roteamento é o equivalente ao controle de tráfego. Sem ele, todos os agentes ficam misturados no mesmo prompt, a memória pode ser contaminada por assuntos diferentes, a latência aumenta e a observabilidade fica confusa.

### Por que estruturar o roteamento para escala, simplicidade e performance

Roteamento não é apenas uma decisão funcional. Ele é uma decisão de arquitetura. A forma como o backend escolhe agentes afeta custo, latência, testes, governança, telemetria e evolução do produto.

### Estrutura real de folders do projeto

A estrutura atual tem três blocos principais: framework reutilizável, template backend e servidores MCP de exemplo.
```
agent_framework_oci/
  agent_framework/
    src/agent_framework/
      routing/
        config_loader.py
        enterprise_router.py
        models.py
      supervisor/
        supervisor.py
      mcp/
        tool_router.py
        registry.py
        client.py
        models.py
      config/
        settings.py
        agent_registry.py
      guardrails/
      judges/
      memory/
      checkpoints/
      observability/
      events/

  agent_template_backend/
    app/
      main.py
      state.py
      workflows/
        agent_graph.py
      agents/
        billing_agent.py
        product_agent.py
        orders_agent.py
        support_agent.py
        runtime.py
        prompting.py
    config/
      agents.yaml
      routing.yaml
      mcp_servers.yaml
      mcp_servers.docker.yaml
      tools.yaml
      guardrails.yaml
      judges.yaml
      prompt_policy.yaml
      agents/
        telecom_contas/
        retail_orders/

  mcp_servers/
    telecom_mcp_server/main.py
    retail_mcp_server/main.py

  agent_frontend/
    index.html
    app.js
    styles.css

  docker-compose.yml
  scripts/
    run_backend.sh
    run_frontend.sh
    run_mcp_servers.sh
    smoke_usage_test.sh
```

### Visão geral da arquitetura

O backend usa FastAPI como camada de entrada, ChannelGateway para normalização de mensagens, LangGraph para orquestração, EnterpriseRouter ou Supervisor para decisão de roteamento, agentes especialistas para execução, MCPToolRouter para tools externas, e camadas de guardrails, judges, memória, checkpoint e observabilidade.
```
Usuário / Frontend / Canal
        |
        v
FastAPI - agent_template_backend/app/main.py
        |
        v
ChannelGateway normaliza payload
        |
        v
SessionRepository + MemoryRepository
        |
        v
AgentWorkflow - app/workflows/agent_graph.py
        |
        +--> input_guardrails
        |
        +--> routing_decision
        |       |-- ROUTING_MODE=router     -> EnterpriseRouter
        |       |-- ROUTING_MODE=supervisor -> Supervisor.route_plan
        |
        +--> agente especialista ou supervisor_agent
        |       |-- billing_agent
        |       |-- product_agent
        |       |-- orders_agent
        |       |-- support_agent
        |       +-- MCPToolRouter -> MCP Servers telecom/retail
        |
        +--> output_guardrails
        +--> judge
        +--> supervisor_review
        +--> persist
        |
        v
Resposta + metadata + trace + checkpoint + eventos
```

### Componentes principais do roteamento


### Settings

O arquivo agent_framework/src/agent_framework/config/settings.py concentra as variáveis que ativam roteamento, MCP, observabilidade, repositórios, LLM e cache.
```
ROUTING_MODE: Literal['router','supervisor'] = 'router'
ROUTING_CONFIG_PATH: str = './config/routing.yaml'
ENABLE_LLM_ROUTER: bool = False
ENABLE_MCP_TOOLS: bool = True
MCP_SERVERS_CONFIG_PATH: str = './config/mcp_servers.yaml'
TOOLS_CONFIG_PATH: str = './config/tools.yaml'
SESSION_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
MEMORY_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
CHECKPOINT_REPOSITORY_PROVIDER: Literal['memory','sqlite','autonomous','oracle','mongodb'] = 'memory'
ENABLE_LANGFUSE: bool = False
```

### RouteDecision

RouteDecision é o contrato de saída do EnterpriseRouter. Ele carrega a decisão funcional e também informações úteis para auditoria e execução de tools.
```
class RouteDecision(BaseModel):
    route: str
    agent: str
    intent: str
    confidence: float = 0.0
    reason: str = ''
    method: Literal['state','keyword','llm','fallback'] = 'fallback'
    next_state: str | None = None
    handoff: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    domain: str | None = None
    mcp_tools: list[str] = Field(default_factory=list)
```

### IntentDefinition

IntentDefinition é carregada a partir de config/routing.yaml e descreve uma intenção roteável.

### SupervisorPlan

SupervisorPlan é o contrato de saída do Supervisor. Em vez de retornar um agente único, ele retorna uma lista de agentes para execução no nó supervisor_agent.
```
@dataclass
class SupervisorPlan:
    agents: list[str]
    intent: str
    confidence: float = 0.0
    reason: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Tipos de roteamento existentes no projeto


### Enterprise Router

O EnterpriseRouter executa uma ordem de decisão clara: estado conversacional, keyword/intents, LLM opcional e fallback. Essa ordem é importante porque evita que mensagens curtas como "sim" sejam classificadas fora do fluxo.
```
Fluxo do EnterpriseRouter:
1. current_state = state.next_state ou session.metadata.workflow_state
2. Se state_policies contém o estado, retorna o agente associado
3. Caso contrário, procura keywords nas intents habilitadas
4. Se ENABLE_LLM_ROUTER=true, pede classificação ao LLM
5. Se nada funcionar, usa router.fallback_agent
```

### Supervisor

O Supervisor implementado é determinístico. Ele procura palavras-chave de billing, product, orders e support. Se detectar mais de um domínio, retorna intent=multi_intent e vários agentes. O workflow então executa supervisor_agent, que chama os agentes indicados e consolida a resposta.
```
Mensagem: "Meu pedido atrasou e minha fatura veio duplicada"
SupervisorPlan:
  agents: ["billing_agent", "orders_agent"]
  intent: "multi_intent"
  reason: "Supervisor detectou múltiplas intenções e acionará mais de um agente."
```

### Caminho 1 - Implementar agentes com Enterprise Router

Este é o caminho recomendado para produção inicial. Cada turno escolhe um agente principal. O desenho é simples, performático e fácil de observar.
```
Usuário
  -> input_guardrails
  -> routing_decision
       -> EnterpriseRouter.route(state)
            -> state_policies
            -> keyword/intents
            -> LLM opcional
            -> fallback
  -> billing_agent | product_agent | orders_agent | support_agent
  -> output_guardrails
  -> judge
  -> supervisor_review
  -> persist
```

### Passo 1 - Definir o modo no .env

```
ROUTING_MODE=router
ROUTING_CONFIG_PATH=./config/routing.yaml
ENABLE_LLM_ROUTER=false
ENABLE_MCP_TOOLS=true
```

### Passo 2 - Cadastrar ou ajustar a intent em config/routing.yaml

Cada intent precisa apontar para o agente especialista e listar as tools MCP autorizadas para aquela intenção.
```
intents:
  - name: billing_invoice_explanation
    domain: telecom
    agent: billing_agent
    description: Dúvidas sobre fatura, cobrança, vencimento, segunda via, contestação e valores.
    priority: 10
    mcp_tools:
      - consultar_fatura
      - consultar_pagamentos
    keywords:
      - fatura
      - conta
      - cobrança
      - boleto
      - vencimento
      - segunda via
      - contestar
      - valor alto
```

### Passo 3 - Garantir que o agente exista no workflow

No projeto atual, os agentes estão instanciados diretamente no AgentWorkflow.__init__ e também foram adicionados como nós no LangGraph.
```
# agent_template_backend/app/workflows/agent_graph.py
self.billing = BillingAgent(llm, **agent_kwargs)
self.product = ProductAgent(llm, **agent_kwargs)
self.orders = OrdersAgent(llm, **agent_kwargs)
self.support = SupportAgent(llm, **agent_kwargs)

builder.add_node("billing_agent", self._node("billing_agent", self.billing_agent))
builder.add_node("product_agent", self._node("product_agent", self.product_agent))
builder.add_node("orders_agent", self._node("orders_agent", self.orders_agent))
builder.add_node("support_agent", self._node("support_agent", self.support_agent))
```

### Passo 4 - Garantir que o condicional do grafo aceite a rota

```
builder.add_conditional_edges(
    "routing_decision",
    lambda s: s.get("route", "billing_agent"),
    {
        "billing_agent": "billing_agent",
        "product_agent": "product_agent",
        "orders_agent": "orders_agent",
        "support_agent": "support_agent",
        "handoff": "handoff",
        "supervisor_agent": "supervisor_agent",
    },
)
```

### Passo 5 - Configurar MCP tools da intent

A intent carrega mcp_tools no RouteDecision. O agente lê state.get("mcp_tools") e chama self.tool_router.call(tool, args).
```
# Exemplo em BillingAgent._collect_tool_context
tools = state.get("mcp_tools") or []
for tool in tools:
    args = {
        "msisdn": ctx.get("msisdn"),
        "invoice_id": ctx.get("invoice_id"),
        "asset_id": ctx.get("asset_id"),
        "session_id": state.get("conversation_key") or state.get("session_id"),
    }
    res = await self.tool_router.call(tool, args)
```

### Caminho 2 - Implementar agentes com Supervisor

Este caminho é indicado quando o usuário pode misturar assuntos em uma única mensagem. O Supervisor não escolhe apenas uma rota; ele cria um plano de execução.
```
Usuário
  -> input_guardrails
  -> routing_decision
       -> Supervisor.route_plan(state)
       -> route = supervisor_agent
  -> supervisor_agent
       -> executa billing_agent opcional
       -> executa product_agent opcional
       -> executa orders_agent opcional
       -> executa support_agent opcional
       -> consolida resposta
  -> output_guardrails
  -> judge
  -> supervisor_review
  -> persist
```

### Passo 1 - Ativar no .env

```
ROUTING_MODE=supervisor
ENABLE_SUPERVISOR=true
ENABLE_MCP_TOOLS=true
```

### Passo 2 - Ajustar regras do Supervisor

No projeto atual, o Supervisor usa a lista ROUTING_RULES no arquivo agent_framework/src/agent_framework/supervisor/supervisor.py. Para incluir um novo agente no modo supervisor, adicione uma regra com intent, agent e keywords.
```
ROUTING_RULES = [
    ("billing", "billing_agent", ["fatura", "conta", "cobrança", "boleto"]),
    ("product", "product_agent", ["produto", "plano", "serviço", "internet"]),
    ("orders", "orders_agent", ["pedido", "entrega", "rastreio", "atraso"]),
    ("support", "support_agent", ["troca", "devolução", "garantia", "defeito"]),
]
```

### Passo 3 - Garantir que supervisor_agent saiba executar o agente

```
handlers = {
    "billing_agent": self.billing.run,
    "product_agent": self.product.run,
    "orders_agent": self.orders.run,
    "support_agent": self.support.run,
}

for agent_name in agents:
    handler = handlers.get(agent_name)
    child_state = {**state, "route": agent_name, "active_agent": agent_name}
    result = await handler(child_state)
```

### Passo 4 - Entender a consolidação

Quando o Supervisor aciona apenas um agente, a resposta final é a resposta desse agente. Quando aciona vários, o projeto atual concatena as respostas parciais com um prefixo de consolidação. Em produção, essa etapa pode evoluir para uma síntese por LLM com prompt próprio e guardrails específicos.
```
if len(partials) == 1:
    answer = partials[0]["answer"]
else:
    joined = "

".join(f"{p['agent']}: {p['answer']}" for p in partials)
    answer = "[Supervisor] Consolidação de múltiplos agentes acionados.
" + joined
```

### Como configurar agentes, intents, MCP tools e estado conversacional


### config/agents.yaml

Este arquivo não cadastra cada nó especialista diretamente. Ele cadastra perfis/templates de agente, como telecom_contas e retail_orders. O agent_id de entrada define o contexto de isolamento, políticas, prompts, guardrails, judges e tools.
```
default_agent_id: telecom_contas
agents:
  - agent_id: telecom_contas
    name: Agente Telecom Contas
    prompt_policy_path: ./config/agents/telecom_contas/prompt_policy.yaml
    routing_config_path: ./config/routing.yaml
    guardrails_config_path: ./config/agents/telecom_contas/guardrails.yaml
    judges_config_path: ./config/agents/telecom_contas/judges.yaml
    mcp_servers_config_path: ./config/mcp_servers.yaml
    tools_config_path: ./config/tools.yaml
    metadata:
      domain: telecom

  - agent_id: retail_orders
    name: Agente Retail Pedidos
    prompt_policy_path: ./config/agents/retail_orders/prompt_policy.yaml
    routing_config_path: ./config/routing.yaml
    guardrails_config_path: ./config/agents/retail_orders/guardrails.yaml
    judges_config_path: ./config/agents/retail_orders/judges.yaml
    mcp_servers_config_path: ./config/mcp_servers.yaml
    tools_config_path: ./config/tools.yaml
    metadata:
      domain: retail
```

### config/routing.yaml

Este arquivo configura o EnterpriseRouter e documenta o modo padrão. A variável ROUTING_MODE do .env é a forma recomendada para ativar router ou supervisor em runtime.

### config/tools.yaml

Define cada tool lógica e o servidor MCP responsável.
```
tools:
  consultar_fatura:
    description: Consulta dados resumidos de fatura por msisdn/invoice_id.
    mcp_server: telecom
    enabled: true
    args_schema:
      msisdn: string
      invoice_id: string

  consultar_pedido:
    description: Consulta pedido de varejo por order_id/customer_id.
    mcp_server: retail
    enabled: true
    args_schema:
      order_id: string
      customer_id: string
```

### config/mcp_servers.yaml

```
servers:
  telecom:
    transport: http
    endpoint: http://localhost:8100/mcp
    enabled: true
    description: MCP Server de exemplo para domínio Telecom.

  retail:
    transport: http
    endpoint: http://localhost:8200/mcp
    enabled: true
    description: MCP Server de exemplo para domínio Retail.
```

### Como o LangGraph executa o roteamento

O grafo é criado em agent_template_backend/app/workflows/agent_graph.py. O ponto central é que existe um nó único de decisão: routing_decision. Isso evita dois backends diferentes para os dois modelos de roteamento.
```
START
  -> input_guardrails
  -> routing_decision
      -> billing_agent
      -> product_agent
      -> orders_agent
      -> support_agent
      -> handoff
      -> supervisor_agent
  -> output_guardrails
  -> judge
  -> supervisor_review
  -> persist
  -> END
```

### Exemplos funcionais de ponta a ponta


### Exemplo router - fatura

```
Entrada:
"Minha fatura veio alta"

EnterpriseRouter:
- Lê sanitized_input
- Encontra keyword "fatura"
- Seleciona intent billing_invoice_explanation
- Retorna route=billing_agent
- Retorna mcp_tools=[consultar_fatura, consultar_pagamentos]

Workflow:
- Vai para billing_agent
- BillingAgent chama MCPToolRouter para consultar_fatura/consultar_pagamentos se houver argumentos no contexto
- Resposta passa por output_guardrails, judges, supervisor_review e persist
```

### Exemplo router - pedido

```
Entrada:
"Onde está meu pedido?"

EnterpriseRouter:
- Keyword "pedido"
- Intent retail_order_tracking
- Route orders_agent
- Tools consultar_pedido e consultar_entrega

Workflow:
- Executa OrdersAgent
- OrdersAgent monta argumentos order_id/customer_id a partir do context
- Chama tools MCP de retail quando disponíveis
```

### Exemplo supervisor - cobrança + pedido

```
Entrada:
"Meu pedido atrasou e minha fatura veio duplicada"

Supervisor:
- Detecta pedido/atraso -> orders_agent
- Detecta fatura/duplicada -> billing_agent
- Retorna agents=[billing_agent, orders_agent] ou ordem conforme regras
- intent=multi_intent

Workflow:
- routing_decision retorna route=supervisor_agent
- supervisor_agent executa cada agente listado
- Consolida resposta final
- Output guardrails e judges avaliam a resposta consolidada
```

### Como testar com curl


### Verificar backend e modo ativo

```
curl http://localhost:8000/health | jq
Campos importantes esperados:
{
  "status": "ok",
  "routing_mode": "router" ou "supervisor",
  "agents": ["telecom_contas", "retail_orders"],
  "session_repository": "memory|sqlite|autonomous|oracle|mongodb",
  "checkpoint_repository": "memory|sqlite|autonomous|oracle|mongodb"
}
```

### Verificar agentes/perfis carregados

```
curl http://localhost:8000/agents | jq
```

### Testar roteamento sem executar conversa completa

```
curl -X POST http://localhost:8000/debug/route   -H 'Content-Type: application/json'   -d '{
    "channel":"web",
    "payload":{
      "text":"Minha fatura veio alta",
      "session_id":"s-router-1",
      "context":{"msisdn":"5511999999999","invoice_id":"INV001"}
    },
    "agent_id":"telecom_contas",
    "tenant_id":"tenant_a"
  }' | jq
Resposta esperada em ROUTING_MODE=router:
{
  "route": "billing_agent",
  "agent": "billing_agent",
  "intent": "billing_invoice_explanation",
  "method": "keyword",
  "mode": "router",
  "mcp_tools": ["consultar_fatura", "consultar_pagamentos"]
}
curl -X POST http://localhost:8000/debug/route   -H 'Content-Type: application/json'   -d '{
    "channel":"web",
    "payload":{
      "text":"Meu pedido atrasou e minha fatura veio duplicada",
      "session_id":"s-supervisor-1",
      "context":{"order_id":"P100","msisdn":"5511999999999"}
    },
    "agent_id":"telecom_contas",
    "tenant_id":"tenant_a"
  }' | jq
Resposta esperada em ROUTING_MODE=supervisor:
{
  "mode": "supervisor",
  "route": "supervisor_agent",
  "agents": ["billing_agent", "orders_agent"],
  "intent": "multi_intent"
}
```

### Testar MCP tools

```
curl http://localhost:8000/debug/mcp/tools | jq

curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura   -H 'Content-Type: application/json'   -d '{"msisdn":"5511999999999","invoice_id":"INV001"}' | jq

curl -X POST http://localhost:8000/debug/mcp/call/consultar_pedido   -H 'Content-Type: application/json'   -d '{"order_id":"P100","customer_id":"C001"}' | jq
```

### Testar conversa completa

```
curl -X POST http://localhost:8000/gateway/message   -H 'Content-Type: application/json'   -d '{
    "channel":"web",
    "agent_id":"telecom_contas",
    "tenant_id":"tenant_a",
    "payload":{
      "text":"Minha fatura veio alta. Pode consultar?",
      "session_id":"web-001",
      "user_id":"u1",
      "channel_id":"browser-1",
      "context":{
        "msisdn":"5511999999999",
        "invoice_id":"INV001"
      }
    }
  }' | jq
Campos úteis na resposta:
metadata.route
metadata.intent
metadata.route_decision
metadata.mcp_tools
metadata.mcp_results
metadata.guardrails
metadata.judges
```

### Observabilidade, memória e checkpoint

O fluxo de entrada cria uma identidade com tenant_id, agent_id e session_id. O método AgentIdentity.conversation_key() é usado como chave operacional da conversa. Essa chave é usada para sessão, memória, checkpoint, SSE e telemetria.
```
tenant_id + agent_id + session_id -> conversation_key
Exemplo:
tenant_a:telecom_contas:web-001
Endpoints úteis:
GET /sessions/{session_id}/messages
GET /sessions/{session_id}/checkpoint
GET /debug/usage
GET /debug/env
```

### Troubleshooting


### Checklist de implementação

- Definir se o caso de uso exige ROUTING_MODE=router ou ROUTING_MODE=supervisor.
- Cadastrar ou ajustar intents em agent_template_backend/config/routing.yaml.
- Garantir que cada intent aponta para o agente especialista correto.
- Configurar mcp_tools na intent apenas quando a tool deve ser permitida naquele contexto.
- Cadastrar tools em config/tools.yaml e servidores em config/mcp_servers.yaml.
- Garantir que o agente especialista exista em agent_template_backend/app/agents/.
- Instanciar o agente em AgentWorkflow.__init__.
- Adicionar nó do agente no LangGraph.
- Adicionar rota no add_conditional_edges de routing_decision.
- No modo supervisor, adicionar regra em Supervisor.ROUTING_RULES e handler em supervisor_agent.
- Testar /health, /agents e /debug/env.
- Testar /debug/route para cada intent.
- Testar /debug/mcp/tools e /debug/mcp/call/{tool_name}.
- Testar /gateway/message com contexto real.
- Verificar metadata.route, metadata.intent, metadata.route_decision, metadata.mcp_results, guardrails e judges.
- Validar memória, checkpoint e traces por conversation_key.

### Arquitetura — Global Supervisor

Usuário / Frontend
        │
        ▼
┌───────────────────────────────┐
│ Agent Gateway                 │
│ Global Supervisor             │
│                               │
│ - Router por regras           │
│ - Supervisor via LLM          │
│ - Híbrido stateful            │
│ - Handoff entre backends      │
└───────────────┬───────────────┘
                │
      ┌─────────┼─────────┬────────────┐
      ▼         ▼         ▼            ▼
Backend      Backend   Backend     Backend
Contas       Ofertas   Suporte     Cobrança
Cada backend continua sendo um projeto independente, com seus próprios agentes, prompts, MCPs e deploy, mas todos usam a mesma biblioteca agent_framework.

### Estado global

O Gateway mantém um active_backend por session_id. No modo hybrid, mensagens curtas como "e esse valor?" continuam no backend ativo sem chamar LLM.

### Memória compartilhada

Para produção, configure os backends para usar o mesmo Session/Memory/Checkpoint Repository, preferencialmente Autonomous DB, Oracle, MongoDB ou Redis + DB.

### Route Stickiness semântica e controle global de sessão

> Conteúdo consolidado a partir de `Documentacao/Route_Stickiness_Semantica_Agent_Framework_OCI.docx`.

Agent Framework OCI
Classificação LLM leve, sem regex, com Human Handoff e Encerramento

### Objetivo

A capacidade usa um perfil LLM leve para decidir o tratamento global do turno sem regex, listas de frases ou regras linguísticas por domínio. Ela evita que cada agente implemente lógica própria de continuidade, transferência humana ou encerramento.
- CONTINUE: mantém o agente ativo.
- ROUTE: executa o Enterprise Router normal.
- HUMAN_HANDOFF: solicita atendimento humano.
- END_SESSION: encerra o atendimento automatizado.

### Princípios arquiteturais

- Nenhuma regra de linguagem natural é codificada no core.
- O classificador não responde ao usuário e não executa ferramentas.
- Handoff e encerramento são tratados por nós globais do grafo.
- Baixa confiança, timeout, erro ou JSON inválido retornam ao Enterprise Router.
- CONTINUE exige agente ativo; sem agente ativo, a decisão vira ROUTE.

### Fluxo

Mensagem -> Classificador LLM leve
  CONTINUE + agente ativo -> agente atual
  ROUTE / baixa confiança / erro -> Enterprise Router
  HUMAN_HANDOFF -> nó human_handoff
  END_SESSION -> nó end_session
As ações globais podem ser reconhecidas no primeiro turno. Isso permite que “quero falar com uma pessoa” ou “pode encerrar” não dependam de um agente de domínio já selecionado.

### Configuração


### .env

ENABLE_ROUTE_STICKINESS=true
ROUTE_STICKINESS_LLM_PROFILE=route_continuity
ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.90
ROUTE_STICKINESS_HISTORY_TURNS=2
ROUTE_STICKINESS_MAX_TOKENS=80
HUMAN_HANDOFF_MESSAGE=Vou encaminhar seu atendimento para uma pessoa.
END_SESSION_MESSAGE=Atendimento encerrado. Obrigado pelo contato.

### llm_profiles.yaml

profiles:
  route_continuity:
    provider: oci_openai
    model: openai.gpt-4.1-mini
    temperature: 0
    max_tokens: 80
    timeout_seconds: 5
O modelo é apenas um exemplo. Deve ser usado o menor modelo aprovado e disponível no ambiente OCI.

### Contratos de saída


### Continuidade

{"decision":"CONTINUE","confidence":0.97,"reason":"Continuação do assunto anterior."}
Com confiança suficiente e agente ativo, o router retorna method=continuity e route_bypassed=true.

### Human handoff

{"route":"human_handoff","intent":"human_handoff","handoff":true,
 "metadata":{"session_control":"HUMAN_HANDOFF","route_bypassed":true}}
- session_control=HUMAN_HANDOFF
- human_handoff_requested=true
- session_ended=false
- next_state=HUMAN_HANDOFF_REQUESTED
- evento session.human_handoff.requested
A integração do cliente continua responsável por selecionar fila, plataforma humana e protocolo de transferência.

### Encerramento

{"route":"end_session","intent":"end_session",
 "metadata":{"session_control":"END_SESSION","route_bypassed":true}}
- session_control=END_SESSION
- session_ended=true
- human_handoff_requested=false
- next_state=SESSION_ENDED
- evento session.end.requested
O fechamento físico da conexão, TTL ou expiração da sessão continua sendo responsabilidade do canal ou backend.

### Exemplos


### Arquivos alterados

- libs/agent_framework/src/agent_framework/routing/continuity.py
- libs/agent_framework/src/agent_framework/config/settings.py
- templates/agent_template_backend/app/workflows/agent_graph.py
- templates/agent_template_backend/app/state.py
- templates/agent_template_backend/.env e .env.example
- tests/unit/test_semantic_route_stickiness.py

### Testes

PYTHONPATH=libs/agent_framework/src pytest -q tests/unit/test_semantic_route_stickiness.py
A suíte cobre CONTINUE, ROUTE, baixa confiança, saída inválida, HUMAN_HANDOFF, END_SESSION, ações globais no primeiro turno e CONTINUE sem agente ativo.

### Limitações e integração

- O classificador não escolhe fila humana.
- O classificador não fecha conexão SSE, HTTP, voz ou WhatsApp.
- O evento global deve ser consumido pelo Channel Gateway ou integração do cliente.
- O nó de encerramento persiste o resultado, mas a política concreta de expiração é externa.
- A qualidade depende do modelo leve e do threshold configurado.

### Enterprise Router versus Supervisor

> Conteúdo consolidado a partir de `Documentacao/README_ROUTING_MODES.md`.

Este projeto suporta dois desenhos arquiteturais para roteamento entre agentes, sem precisar criar dois frameworks diferentes.

### Modos disponíveis

Configure por variável de ambiente:

```bash
ROUTING_MODE=router
```

ou:

```bash
ROUTING_MODE=supervisor
```

Também existe a chave documental em `agent_template_backend/config/routing.yaml`:

```yaml
router:
  mode: router
```

A variável de ambiente `ROUTING_MODE` é a forma recomendada para ativar um modo em runtime, especialmente em Docker, Kubernetes ou OCI.

---

### Opção 1: Enterprise Router

Fluxo:

```text
Usuário
  -> Input Guardrails
  -> EnterpriseRouter
  -> AgentRegistry
  -> 1 agente especialista
  -> Output Guardrails
  -> Judges
  -> Supervisor Review
  -> Persistência/eventos
```

Uso recomendado quando cada mensagem deve ser atendida por um único agente especialista.

Exemplos:

- `Minha fatura veio alta` -> `billing_agent`
- `Onde está meu pedido?` -> `orders_agent`
- `Quero trocar um produto com defeito` -> `support_agent`

Vantagens:

- Menor latência.
- Menor custo de tokens.
- Debug mais simples.
- Mais fácil de operar em produção.

Limitação:

- Uma mensagem com múltiplos assuntos precisa ser roteada para um agente principal ou tratada por handoff.

---

### Opção 2: Supervisor

Fluxo:

```text
Usuário
  -> Input Guardrails
  -> Supervisor.route_plan
  -> supervisor_agent
       -> billing_agent opcional
       -> orders_agent opcional
       -> product_agent opcional
       -> support_agent opcional
  -> Consolidação
  -> Output Guardrails
  -> Judges
  -> Supervisor Review
  -> Persistência/eventos
```

Uso recomendado quando uma única mensagem pode envolver vários agentes.

Exemplo:

```text
Meu pedido não chegou e também fui cobrado duas vezes.
```

Neste caso, o supervisor pode acionar:

- `orders_agent`
- `billing_agent`

Vantagens:

- Suporta múltiplas intenções na mesma mensagem.
- Permite consolidação de respostas.
- Facilita cenários enterprise com vários domínios.

Custos:

- Maior latência.
- Maior consumo de tokens.
- Mais complexidade operacional.

---

### O que foi alterado no código

### 1. Configuração

Arquivo:

```text
agent_framework/src/agent_framework/config/settings.py
```

Foi adicionada a configuração:

```python
ROUTING_MODE: Literal['router','supervisor'] = 'router'
```

### 2. Workflow LangGraph

Arquivo:

```text
agent_template_backend/app/workflows/agent_graph.py
```

O nó `enterprise_route` foi substituído por um nó genérico:

```text
routing_decision
```

Esse nó decide o caminho com base em `ROUTING_MODE`:

- `router` usa `EnterpriseRouter`.
- `supervisor` usa `Supervisor.route_plan`.

Também foi adicionado o nó:

```text
supervisor_agent
```

Ele executa um ou mais agentes e consolida o resultado.

### 3. Supervisor

Arquivo:

```text
agent_framework/src/agent_framework/supervisor/supervisor.py
```

Foi adicionada a estrutura:

```python
SupervisorPlan
```

E o método:

```python
route_plan(state)
```

Esse método retorna uma lista de agentes a executar.

### 4. Debug

Endpoint:

```text
POST /debug/route
```

Agora respeita `ROUTING_MODE` e permite verificar rapidamente como uma mensagem será roteada.

---

### Como testar localmente

### Instalação

```bash
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ../agent_framework
pip install -r requirements.txt
```

### Modo Router

```bash
export ROUTING_MODE=router
uvicorn app.main:app --reload --port 8000
```

Teste:

```bash
curl -X POST http://localhost:8000/debug/route \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"Onde está meu pedido?","session_id":"s1"}}'
```

Resultado esperado:

```json
{
  "mode": "router",
  "route": "orders_agent"
}
```

### Modo Supervisor

```bash
export ROUTING_MODE=supervisor
uvicorn app.main:app --reload --port 8000
```

Teste:

```bash
curl -X POST http://localhost:8000/debug/route \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"Meu pedido atrasou e minha fatura veio duplicada","session_id":"s2"}}'
```

Resultado esperado:

```json
{
  "mode": "supervisor",
  "route": "supervisor_agent",
  "agents": ["billing_agent", "orders_agent"]
}
```

---

### Isolamento

A chave lógica de isolamento permanece:

```text
tenant_id:agent_id:session_id
```

Use essa chave para memória, sessão, checkpoint e telemetria. Em produção, recomenda-se padronizar `agent_id` por agente especialista ou por template, dependendo do nível de isolamento desejado.

---

### Recomendação

Comece em produção com:

```bash
ROUTING_MODE=router
```

Ative:

```bash
ROUTING_MODE=supervisor
```

quando houver necessidade real de múltiplos agentes na mesma mensagem.

### Enterprise Routing e fallback LLM

> Conteúdo consolidado a partir de `Documentacao/README_ENTERPRISE_ROUTING.md`.

Esta versão inclui o projeto completo com:

- `agent_framework`: framework reutilizável.
- `agent_template_backend`: backend FastAPI com LangGraph, OCI Generative AI, Langfuse, guardrails, judges, supervisor e roteamento enterprise.
- `agent_frontend`: frontend web independente.
- `templates/template_telecom_billing_product`: template de exemplo para telecom com agentes de Fatura e Produto.
- `templates/template_retail_orders_support`: template de exemplo para e-commerce com agentes de Pedido e Suporte.

### Roteamento enterprise

O roteamento fica em:

```text
agent_framework/src/agent_framework/routing/
```

Componentes principais:

- `models.py`: modelos `IntentDefinition`, `RouterStatePolicy`, `RouteDecision`.
- `config_loader.py`: carrega o YAML de intents e políticas.
- `enterprise_router.py`: decide o agente de destino por estado, keyword, LLM ou fallback.

O template usa:

```text
agent_template_backend/config/routing.yaml
```

### Ordem de decisão

1. Estado conversacional (`state_policies`).
2. Keywords/intents configuráveis.
3. LLM Router opcional (`ENABLE_LLM_ROUTER=true`).
4. Fallback (`router.fallback_agent`).

### Como testar roteamento sem chamar o agente final

```bash
curl -X POST http://localhost:8000/debug/route \
  -H 'Content-Type: application/json' \
  -d '{
    "channel": "web",
    "payload": {
      "text": "Minha fatura veio alta",
      "user_id": "u1",
      "channel_id": "browser-1",
      "context": {"msisdn": "5511999999999"}
    }
  }'
```

Resposta esperada:

```json
{
  "route": "billing_agent",
  "agent": "billing_agent",
  "intent": "billing_invoice_explanation",
  "method": "keyword"
}
```

### Como habilitar roteamento por LLM

No `.env` do backend:

```env
LLM_PROVIDER=oci_openai
OCI_GENAI_API_KEY=...
OCI_GENAI_BASE_URL=https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1
OCI_GENAI_MODEL=openai.gpt-4.1
ENABLE_LLM_ROUTER=true
ROUTING_CONFIG_PATH=./config/routing.yaml
```

### Como adicionar novo agente

1. Criar classe do agente em `agent_template_backend/app/agents/`.
2. Instanciar o agente em `AgentWorkflow.__init__`.
3. Adicionar node no LangGraph.
4. Adicionar a rota no `add_conditional_edges`.
5. Criar intent no `config/routing.yaml` apontando `agent: nome_do_agente`.

### Templates incluídos

### Template 1 — Telecom

Diretório:

```text
templates/template_telecom_billing_product
```

Agentes:

- BillingAgent
- ProductAgent

### Template 2 — Retail/E-commerce

Diretório:

```text
templates/template_retail_orders_support
```

Agentes:

- OrdersAgent
- SupportAgent

Este segundo template mostra como reutilizar a mesma arquitetura para outro domínio de negócio.

### Intent shift determinístico genérico — comportamento atual

> Conteúdo consolidado a partir de `Documentacao/RELEASE_NOTES_GENERIC_DETERMINISTIC_INTENT_SHIFT_V15.md`.

### Problema corrigido

A Route Stickiness podia preservar a intent anterior quando a nova mensagem correspondia a uma intent configurada no `routing.yaml`, mas a frase do usuário omitia conectores curtos presentes na keyword configurada.

Exemplo real de configuração:

- keyword: `qual é o meu plano`
- mensagem: `qual o meu plano`

A classificação determinística não reconhecia a nova intent e a continuity acabava mantendo a intent anterior.

### Correção

O `EnterpriseRouter` continua usando, nesta ordem:

1. match exato;
2. sequência completa de tokens com palavras inseridas (`ordered_tokens`);
3. sequência de tokens informativos tolerando a omissão de conectores curtos presentes na keyword (`ordered_content_tokens`).

A terceira estratégia ignora, somente no lado da keyword, tokens de até dois caracteres e exige pelo menos dois tokens informativos. Não há nomes de intents, agentes, domínios ou verbos de negócio hardcoded.

Assim, a solução é dirigida integralmente pelas intents carregadas do `routing.yaml` da aplicação.

### Precedência sobre Route Stickiness

Quando o candidato determinístico encontrado é diferente da intent ativa, ele preempta a stickiness e retorna:

- `route_stickiness_preempted: true`
- `previous_agent`
- `previous_intent`
- `keyword_match_strategy`

A continuity LLM não é chamada nesse caminho.

### Casos cobertos

### Mesmo agente, nova intent

`retail_order_tracking` -> `quero cancelar meu pedido` -> `retail_order_cancel`

### Mesmo agente, tools diferentes

`contas_invoice_query` -> `qual o meu plano` -> `contas_plan_information`

Mesmo que ambas as intents usem `faturas_agent`, as tools mudam de `consultar_faturas` para `consultar_plano`.

### Precedência de intent shift sobre stickiness

> Conteúdo consolidado a partir de `Documentacao/RELEASE_NOTES_ROUTE_STICKINESS_DETERMINISTIC_INTENT_SHIFT_V14.md`.

### Problema corrigido

Uma keyword multi-token como `cancelar pedido` não era reconhecida em frases como `quero cancelar meu pedido`. O match legado usava substring literal; assim, a keyword genérica `pedido` podia manter `retail_order_tracking` e a continuidade reutilizava a intent anterior.

### Correção

O `EnterpriseRouter` agora possui um segundo estágio determinístico para keywords multi-token: ordered-token matching com até três tokens intermediários. Não há chamada adicional de LLM.

Exemplos reconhecidos pela keyword configurada `cancelar pedido`:

- `quero cancelar meu pedido`
- `quero cancelar o meu pedido`
- `pode cancelar esse pedido`
- `gostaria de cancelar meu pedido`

Quando esse match identifica uma intent diferente da ativa, ele preempta a route stickiness antes do LLM de continuidade.

Metadados de auditoria esperados:

```json
{
  "method": "keyword",
  "intent": "retail_order_cancel",
  "metadata": {
    "matched_keyword": "cancelar pedido",
    "keyword_match_strategy": "ordered_tokens",
    "route_stickiness_preempted": true,
    "previous_intent": "retail_order_tracking"
  }
}
```

### Custo de LLM

Para mudança explícita reconhecida deterministicamente, o classificador LLM de continuity não é chamado. Para mensagens sem sinal explícito, a Route Stickiness continua com o comportamento configurado.

### Regressão

Testes cobrem mudança `retail_order_tracking -> retail_order_cancel` no mesmo `orders_agent`, inclusive com palavras intermediárias. A suíte relacionada passou com 18 testes.

### Mudança de consulta para ação transacional

> Conteúdo consolidado a partir de `Documentacao/RELEASE_NOTES_ROUTE_STICKINESS_TRANSACTION_SHIFT.md`.

### Problema

Após `consultar pedido 123`, a mensagem `Quero devolver o pedido 123` podia permanecer no `orders_agent` por route stickiness. Como a intent anterior só expunha tools de consulta, o runtime executava novamente `consultar_pedido` e a resposta direta repetia o status do pedido.

### Correções

- Keywords explícitas configuradas no `routing.yaml` podem preemptar a route stickiness quando apontam para outra intent/agente.
- `retail_support_exchange_return` passa a ter prioridade maior que `retail_order_tracking` para mensagens de troca/devolução.
- Tools transacionais declaram `selection_keywords` no `tools.yaml`.
- A resposta direta read-only é bloqueada quando a mensagem contém uma ação transacional registrada, mesmo que a intent anterior ainda esteja ativa.
- A seleção da action tool usa configuração, não aliases de domínio fixos no runtime.

### Fluxo esperado

1. `consultar pedido 123` → `orders_agent` → `consultar_pedido` → resposta direta.
2. `Quero devolver o pedido 123` → preempção da stickiness → `support_agent` / `retail_support_exchange_return`.
3. `consultar_pedido` valida o pedido.
4. `solicitar_devolucao` é selecionada e, com confirmação obrigatória, gera `AWAITING_CONFIRMATION`.
5. `Sim, confirmo` executa a action tool uma única vez.

### Cobertura de testes de route stickiness

> Conteúdo consolidado a partir de `Documentacao/TEST_RESULTS_ROUTE_STICKINESS.md`.

Date: 2026-07-31

### Command

```bash
PYTHONPATH=libs/agent_framework/src pytest -q tests/unit/test_semantic_route_stickiness.py
```

### Result

```text
9 passed
```

### Covered scenarios

1. `CONTINUE` bypasses the Enterprise Router.
2. `ROUTE` falls back to the Enterprise Router.
3. Low-confidence `CONTINUE` falls back safely.
4. Invalid model output falls back safely.
5. With no active agent, the lightweight classifier can still detect global session actions.
6. `HUMAN_HANDOFF` returns the global `human_handoff` route and session-control metadata.
7. `END_SESSION` returns the global `end_session` route and session-control metadata.
8. Global actions work on the first turn.
9. `CONTINUE` without an active agent is normalized to `ROUTE`.

### Additional validation

```bash
python -m compileall -q libs/agent_framework/src templates/agent_template_backend/app
```

Compilation completed successfully.

### Arquivos de origem

Os arquivos abaixo foram consolidados neste manual:

- `Documentacao/Manual de Roteamento Multi-Agent.docx`
- `Documentacao/Route_Stickiness_Semantica_Agent_Framework_OCI.docx`
- `Documentacao/README_ROUTING_MODES.md`
- `Documentacao/README_ENTERPRISE_ROUTING.md`
- `Documentacao/RELEASE_NOTES_GENERIC_DETERMINISTIC_INTENT_SHIFT_V15.md`
- `Documentacao/RELEASE_NOTES_ROUTE_STICKINESS_DETERMINISTIC_INTENT_SHIFT_V14.md`
- `Documentacao/RELEASE_NOTES_ROUTE_STICKINESS_TRANSACTION_SHIFT.md`
- `Documentacao/TEST_RESULTS_ROUTE_STICKINESS.md`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.
