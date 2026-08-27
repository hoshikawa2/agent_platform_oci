### Routing, Route Stickiness and Intent Shift

### How to use this manual

This is a **specialized reference manual**. It does not replace the main tutorial.

- To create an agent from start to finish, use [`README_en.md`](../../../README_en.md).
- Use this document when you need to implement, deepen, or diagnose **routing, stickiness, intent changes, deterministic/LLM routing, and multi-agent isolation**.
- The historical examples consolidated here should be read in light of the framework's current API.
- In case of divergence, the code for the version and the current `README_en.md` take precedence.

### Relationship with the main tutorial

The `README_en.md` presents this capability in the normal development flow. This manual brings together details that were distributed across `docs/`, `Documentacao/`, release notes, validations, and specialized guides.

The goal here is to answer **“how does this feature work in depth and how do I solve problems with it?”**, without turning this file into a second copy of the main tutorial.

### Scope

Routing, stickiness, intent changes, deterministic/LLM routing, and multi-agent isolation.

### Consolidated technical content

### Multi-Agent Routing, Route Stickiness, and Intent Shift

Complete manual for route decision, Enterprise Router, Supervisor, semantic continuity, global session actions, explicit intent changes, and precedence during transactions.

### How to use this document

This is the consolidated development document for this subject. It brings together architecture, configuration, examples, runtime behavior, compatibility, tests, and troubleshooting that were previously distributed across several files. Source sections were preserved when they provided distinct technical details; release notes were incorporated as current behavior or correction history.

### Multi-agent routing manual

> Content consolidated from `Documentacao/Manual de Roteamento Multi-Agent.docx`.

Multi-Agent Routing Manual  
Agent Gateway (Global Supervisor), Enterprise Router, and Supervisor in the `agent_framework_oci` project

### Table of contents

- 1. Purpose of the manual
- 2. What routing means in a multi-agent backend
- 3. Why routing should be structured for scale, simplicity, and performance
- 4. Actual project folder structure
- 5. Architecture overview
- 6. Main routing components
- 7. Routing types available in the project
- 8. Path 1 - Implement agents with Enterprise Router
- 9. Path 2 - Implement agents with Supervisor
- 10. How to configure agents, intents, MCP tools, and conversational state
- 11. How LangGraph executes routing
- 12. End-to-end functional examples
- 13. How to test with curl
- 14. Observability, memory, and checkpointing
- 15. Troubleshooting
- 16. Implementation checklist
- 17. Separate Agent Servers (Global Supervisor or Agent Gateway)

### Purpose of the manual

This manual explains how multi-agent routing is implemented in the `agent_framework_oci` project and how to evolve the backend with new agents without losing governance, performance, and traceability.  
The components are distributed between the reusable `agent_framework` package and the FastAPI `agent_template_backend` template.

### What routing means in a multi-agent backend

Routing is the step that transforms a user message into an operational decision: which agent should answer, with which intent, which MCP tools may be used, which domain is involved, and which context must be preserved.  
In a multi-agent system, routing is equivalent to traffic control. Without it, all agents become mixed into the same prompt, memory can be contaminated by different subjects, latency increases, and observability becomes confusing.

### Why routing should be structured for scale, simplicity, and performance

Routing is not only a functional decision. It is an architectural decision. The way the backend selects agents affects cost, latency, testing, governance, telemetry, and product evolution.

### Actual project folder structure

The current structure has three main blocks: reusable framework, backend template, and example MCP servers.
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

### Architecture overview

The backend uses FastAPI as the entry layer, ChannelGateway for message normalization, LangGraph for orchestration, EnterpriseRouter or Supervisor for routing decisions, specialist agents for execution, MCPToolRouter for external tools, and guardrail, judge, memory, checkpoint, and observability layers.
```
User / Frontend / Canal
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

### Main routing components


### Settings

The file `agent_framework/src/agent_framework/config/settings.py` centralizes the variables that enable routing, MCP, observability, repositories, LLM, and cache.
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

`RouteDecision` is the EnterpriseRouter output contract. It carries the functional decision as well as information useful for audit and tool execution.
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

`IntentDefinition` is loaded from `config/routing.yaml` and describes a routable intent.

### SupervisorPlan

`SupervisorPlan` is the Supervisor output contract. Instead of returning a single agent, it returns a list of agents to execute in the `supervisor_agent` node.
```
@dataclass
class SupervisorPlan:
    agents: list[str]
    intent: str
    confidence: float = 0.0
    reason: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Routing types available in the project


### Enterprise Router

The EnterpriseRouter executes a clear decision order: conversational state, keyword/intents, optional LLM, and fallback. This order is important because it prevents short messages such as "yes" from being classified outside the active flow.
```
Fluxo do EnterpriseRouter:
1. current_state = state.next_state ou session.metadata.workflow_state
2. Se state_policies contém o estado, retorna o agente associado
3. Caso contrário, procura keywords nas intents habilitadas
4. Se ENABLE_LLM_ROUTER=true, pede classificação ao LLM
5. Se nada funcionar, usa router.fallback_agent
```

### Supervisor

The implemented Supervisor is deterministic. It looks for billing, product, orders, and support keywords. If it detects more than one domain, it returns `intent=multi_intent` and multiple agents. The workflow then executes `supervisor_agent`, which calls the specified agents and consolidates the response.
```
Mensagem: "Meu pedido atrasou e minha fatura veio duplicada"
SupervisorPlan:
  agents: ["billing_agent", "orders_agent"]
  intent: "multi_intent"
  reason: "Supervisor detectou múltiplas intenções e acionará mais de um agente."
```

### Path 1 - Implement agents with Enterprise Router

This is the recommended path for initial production. Each turn selects one primary agent. The design is simple, performant, and easy to observe.
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

### Step 1 - Define the mode in `.env`

```
ROUTING_MODE=router
ROUTING_CONFIG_PATH=./config/routing.yaml
ENABLE_LLM_ROUTER=false
ENABLE_MCP_TOOLS=true
```

### Step 2 - Register or adjust the intent in `config/routing.yaml`

Each intent must point to the specialist agent and list the MCP tools authorized for that intent.
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

### Step 3 - Ensure that the agent exists in the workflow

In the current project, agents are instantiated directly in `AgentWorkflow.__init__` and have also been added as LangGraph nodes.
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

### Step 4 - Ensure that the graph conditional accepts the route

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

### Step 5 - Configure the intent's MCP tools

The intent carries `mcp_tools` in the `RouteDecision`. The agent reads `state.get("mcp_tools")` and calls `self.tool_router.call(tool, args)`.
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

### Path 2 - Implement agents with Supervisor

This path is appropriate when the user may mix subjects in a single message. The Supervisor does not choose only one route; it creates an execution plan.
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

### Step 1 - Enable it in `.env`

```
ROUTING_MODE=supervisor
ENABLE_SUPERVISOR=true
ENABLE_MCP_TOOLS=true
```

### Step 2 - Adjust Supervisor rules

In the current project, the Supervisor uses the `ROUTING_RULES` list in `agent_framework/src/agent_framework/supervisor/supervisor.py`. To include a new agent in supervisor mode, add a rule with intent, agent, and keywords.
```
ROUTING_RULES = [
    ("billing", "billing_agent", ["fatura", "conta", "cobrança", "boleto"]),
    ("product", "product_agent", ["produto", "plano", "serviço", "internet"]),
    ("orders", "orders_agent", ["pedido", "entrega", "rastreio", "atraso"]),
    ("support", "support_agent", ["troca", "devolução", "garantia", "defeito"]),
]
```

### Step 3 - Ensure that `supervisor_agent` knows how to execute the agent

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

### Step 4 - Understand consolidation

When the Supervisor activates only one agent, the final response is that agent's response. When it activates several, the current project concatenates partial responses with a consolidation prefix. In production, this step can evolve into an LLM synthesis with its own prompt and specific guardrails.
```
if len(partials) == 1:
    answer = partials[0]["answer"]
else:
    joined = "

".join(f"{p['agent']}: {p['answer']}" for p in partials)
    answer = "[Supervisor] Consolidação de múltiplos agentes acionados.
" + joined
```

### How to configure agents, intents, MCP tools, and conversational state


### `config/agents.yaml`

This file does not directly register each specialist node. It registers agent profiles/templates, such as `telecom_contas` and `retail_orders`. The input `agent_id` defines the isolation context, policies, prompts, guardrails, judges, and tools.
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

### `config/routing.yaml`

This file configures the EnterpriseRouter and documents the default mode. The `.env` variable `ROUTING_MODE` is the recommended way to enable router or supervisor at runtime.

### `config/tools.yaml`

Defines each logical tool and the responsible MCP server.
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

### `config/mcp_servers.yaml`

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

### How LangGraph executes routing

The graph is created in `agent_template_backend/app/workflows/agent_graph.py`. The key point is that there is a single decision node: `routing_decision`. This avoids having two different backends for the two routing models.
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

### End-to-end functional examples


### Router example - invoice

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

### Router example - order

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

### Supervisor example - billing + order

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

### How to test with curl


### Check backend and active mode

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

### Check loaded agents/profiles

```
curl http://localhost:8000/agents | jq
```

### Test routing without executing the full conversation

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

### Test MCP tools

```
curl http://localhost:8000/debug/mcp/tools | jq

curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura   -H 'Content-Type: application/json'   -d '{"msisdn":"5511999999999","invoice_id":"INV001"}' | jq

curl -X POST http://localhost:8000/debug/mcp/call/consultar_pedido   -H 'Content-Type: application/json'   -d '{"order_id":"P100","customer_id":"C001"}' | jq
```

### Test the full conversation

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

### Observability, memory, and checkpointing

The input flow creates an identity with `tenant_id`, `agent_id`, and `session_id`. The `AgentIdentity.conversation_key()` method is used as the operational conversation key. This key is used for session, memory, checkpoint, SSE, and telemetry.
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


### Implementation checklist

- Decide whether the use case requires `ROUTING_MODE=router` or `ROUTING_MODE=supervisor`.
- Register or adjust intents in `agent_template_backend/config/routing.yaml`.
- Ensure each intent points to the correct specialist agent.
- Configure `mcp_tools` on the intent only when the tool should be allowed in that context.
- Register tools in `config/tools.yaml` and servers in `config/mcp_servers.yaml`.
- Ensure the specialist agent exists in `agent_template_backend/app/agents/`.
- Instantiate the agent in `AgentWorkflow.__init__`.
- Add the agent node to LangGraph.
- Add the route to `routing_decision`'s `add_conditional_edges`.
- In supervisor mode, add a rule to `Supervisor.ROUTING_RULES` and a handler to `supervisor_agent`.
- Test `/health`, `/agents`, and `/debug/env`.
- Test `/debug/route` for each intent.
- Test `/debug/mcp/tools` and `/debug/mcp/call/{tool_name}`.
- Test `/gateway/message` with real context.
- Check `metadata.route`, `metadata.intent`, `metadata.route_decision`, `metadata.mcp_results`, guardrails, and judges.
- Validate memory, checkpoint, and traces by `conversation_key`.

### Architecture — Global Supervisor

```text
User / Frontend
        │
        ▼
┌───────────────────────────────┐
│ Agent Gateway                 │
│ Global Supervisor             │
│                               │
│ - Rule-based router           │
│ - LLM-based supervisor        │
│ - Stateful hybrid             │
│ - Handoff between backends    │
└───────────────┬───────────────┘
                │
      ┌─────────┼─────────┬────────────┐
      ▼         ▼         ▼            ▼
Backend      Backend   Backend     Backend
Billing      Offers    Support     Collections
```
Each backend remains an independent project, with its own agents, prompts, MCPs, and deployment, but all of them use the same `agent_framework` library.

### Global state

The Gateway maintains an `active_backend` for each `session_id`. In `hybrid` mode, short messages such as `"and this amount?"` remain on the active backend without calling the LLM.

### Shared memory

For production, configure the backends to use the same Session/Memory/Checkpoint Repository, preferably Autonomous DB, Oracle, MongoDB, or Redis + DB.

### Semantic Route Stickiness and global session control

> Content consolidated from `Documentacao/Route_Stickiness_Semantica_Agent_Framework_OCI.docx`.

Agent Framework OCI  
Lightweight LLM classification, without regex, with Human Handoff and Session End

### Goal

The capability uses a lightweight LLM profile to decide global turn handling without regex, phrase lists, or domain-specific linguistic rules. It prevents each agent from implementing its own continuity, human transfer, or termination logic.
- CONTINUE: keeps the active agent.
- ROUTE: executes the normal Enterprise Router.
- HUMAN_HANDOFF: requests human assistance.
- END_SESSION: ends automated service.

### Architectural principles

- No natural-language rule is coded in the core.
- The classifier does not answer the user and does not execute tools.
- Handoff and session ending are handled by global graph nodes.
- Low confidence, timeout, error, or invalid JSON fall back to the Enterprise Router.
- CONTINUE requires an active agent; without an active agent, the decision becomes ROUTE.

### Flow

Message -> Lightweight LLM classifier  
  CONTINUE + active agent -> current agent  
  ROUTE / low confidence / error -> Enterprise Router  
  HUMAN_HANDOFF -> `human_handoff` node  
  END_SESSION -> `end_session` node  
Global actions can be recognized on the first turn. This allows “I want to talk to a person” or “you can end the session” not to depend on a domain agent having already been selected.

### Configuration


### `.env`

```env
ENABLE_ROUTE_STICKINESS=true
ROUTE_STICKINESS_LLM_PROFILE=route_continuity
ROUTE_STICKINESS_CONFIDENCE_THRESHOLD=0.90
ROUTE_STICKINESS_HISTORY_TURNS=2
ROUTE_STICKINESS_MAX_TOKENS=80
HUMAN_HANDOFF_MESSAGE=I will transfer your service to a person.
END_SESSION_MESSAGE=Service ended. Thank you for contacting us.
```

### `llm_profiles.yaml`

```yaml
profiles:
  route_continuity:
    provider: oci_openai
    model: openai.gpt-4.1-mini
    temperature: 0
    max_tokens: 80
    timeout_seconds: 5
```
The model is only an example. Use the smallest approved model available in the OCI environment.

### Output contracts


### Continuity

{"decision":"CONTINUE","confidence":0.97,"reason":"Continuação do assunto anterior."}
With sufficient confidence and an active agent, the router returns `method=continuity` and `route_bypassed=true`.

### Human handoff

{"route":"human_handoff","intent":"human_handoff","handoff":true,
 "metadata":{"session_control":"HUMAN_HANDOFF","route_bypassed":true}}
- `session_control=HUMAN_HANDOFF`
- `human_handoff_requested=true`
- `session_ended=false`
- `next_state=HUMAN_HANDOFF_REQUESTED`
- event `session.human_handoff.requested`
The client integration remains responsible for selecting the queue, human-assistance platform, and transfer protocol.

### Session end

{"route":"end_session","intent":"end_session",
 "metadata":{"session_control":"END_SESSION","route_bypassed":true}}
- `session_control=END_SESSION`
- `session_ended=true`
- `human_handoff_requested=false`
- `next_state=SESSION_ENDED`
- event `session.end.requested`
Physical connection closing, TTL, or session expiration remains the responsibility of the channel or backend.

### Examples


### Files changed

- libs/agent_framework/src/agent_framework/routing/continuity.py
- libs/agent_framework/src/agent_framework/config/settings.py
- templates/agent_template_backend/app/workflows/agent_graph.py
- templates/agent_template_backend/app/state.py
- templates/agent_template_backend/.env and .env.example
- tests/unit/test_semantic_route_stickiness.py

### Tests

PYTHONPATH=libs/agent_framework/src pytest -q tests/unit/test_semantic_route_stickiness.py  
The suite covers CONTINUE, ROUTE, low confidence, invalid output, HUMAN_HANDOFF, END_SESSION, global actions on the first turn, and CONTINUE without an active agent.

### Limitations and integration

- The classifier does not select the human queue.
- The classifier does not close the SSE, HTTP, voice, or WhatsApp connection.
- The global event must be consumed by the Channel Gateway or client integration.
- The session-end node persists the result, but the concrete expiration policy is external.
- Quality depends on the lightweight model and configured threshold.

### Enterprise Router versus Supervisor

> Content consolidated from `Documentacao/README_ROUTING_MODES.md`.

This project supports two architectural designs for routing among agents without requiring two different frameworks.

### Available modes

Configure through an environment variable:

```bash
ROUTING_MODE=router
```

or:

```bash
ROUTING_MODE=supervisor
```

There is also the documentation key in `agent_template_backend/config/routing.yaml`:

```yaml
router:
  mode: router
```

The `ROUTING_MODE` environment variable is the recommended way to activate a mode at runtime, especially in Docker, Kubernetes, or OCI.

---

### Option 1: Enterprise Router

Flow:

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

Recommended when each message should be handled by a single specialist agent.

Examples:

- `Minha fatura veio alta` -> `billing_agent`
- `Onde está meu pedido?` -> `orders_agent`
- `Quero trocar um produto com defeito` -> `support_agent`

Advantages:

- Lower latency.
- Lower token cost.
- Simpler debugging.
- Easier to operate in production.

Limitation:

- A message with multiple subjects must be routed to a primary agent or handled by handoff.

---

### Option 2: Supervisor

Flow:

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

Recommended when a single message may involve several agents.

Example:

```text
Meu pedido não chegou e também fui cobrado duas vezes.
```

In this case, the supervisor may activate:

- `orders_agent`
- `billing_agent`

Advantages:

- Supports multiple intents in the same message.
- Allows response consolidation.
- Facilitates enterprise scenarios with multiple domains.

Costs:

- Higher latency.
- Higher token consumption.
- Greater operational complexity.

---

### What changed in the code

### 1. Configuration

File:

```text
agent_framework/src/agent_framework/config/settings.py
```

The following configuration was added:

```python
ROUTING_MODE: Literal['router','supervisor'] = 'router'
```

### 2. LangGraph workflow

File:

```text
agent_template_backend/app/workflows/agent_graph.py
```

The `enterprise_route` node was replaced by a generic node:

```text
routing_decision
```

This node decides the path based on `ROUTING_MODE`:

- `router` uses `EnterpriseRouter`.
- `supervisor` uses `Supervisor.route_plan`.

The following node was also added:

```text
supervisor_agent
```

It executes one or more agents and consolidates the result.

### 3. Supervisor

File:

```text
agent_framework/src/agent_framework/supervisor/supervisor.py
```

The following structure was added:

```python
SupervisorPlan
```

And the method:

```python
route_plan(state)
```

This method returns a list of agents to execute.

### 4. Debug

Endpoint:

```text
POST /debug/route
```

It now respects `ROUTING_MODE` and allows you to quickly check how a message will be routed.

---

### How to test locally

### Installation

```bash
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ../agent_framework
pip install -r requirements.txt
```

### Router mode

```bash
export ROUTING_MODE=router
uvicorn app.main:app --reload --port 8000
```

Test:

```bash
curl -X POST http://localhost:8000/debug/route \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"Onde está meu pedido?","session_id":"s1"}}'
```

Expected result:

```json
{
  "mode": "router",
  "route": "orders_agent"
}
```

### Supervisor mode

```bash
export ROUTING_MODE=supervisor
uvicorn app.main:app --reload --port 8000
```

Test:

```bash
curl -X POST http://localhost:8000/debug/route \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"text":"Meu pedido atrasou e minha fatura veio duplicada","session_id":"s2"}}'
```

Expected result:

```json
{
  "mode": "supervisor",
  "route": "supervisor_agent",
  "agents": ["billing_agent", "orders_agent"]
}
```

---

### Isolation

The logical isolation key remains:

```text
tenant_id:agent_id:session_id
```

Use this key for memory, session, checkpoint, and telemetry. In production, standardize `agent_id` per specialist agent or per template, depending on the desired level of isolation.

---

### Recommendation

Start production with:

```bash
ROUTING_MODE=router
```

Enable:

```bash
ROUTING_MODE=supervisor
```

when there is a real need for multiple agents in the same message.

### Enterprise Routing and LLM fallback

> Content consolidated from `Documentacao/README_ENTERPRISE_ROUTING.md`.

This version includes the complete project with:

- `agent_framework`: reusable framework.
- `agent_template_backend`: FastAPI backend with LangGraph, OCI Generative AI, Langfuse, guardrails, judges, supervisor, and enterprise routing.
- `agent_frontend`: independent web frontend.
- `templates/template_telecom_billing_product`: example telecom template with Billing and Product agents.
- `templates/template_retail_orders_support`: example e-commerce template with Orders and Support agents.

### Enterprise routing

Routing is located in:

```text
agent_framework/src/agent_framework/routing/
```

Main components:

- `models.py`: `IntentDefinition`, `RouterStatePolicy`, and `RouteDecision` models.
- `config_loader.py`: loads intents and policies from YAML.
- `enterprise_router.py`: decides the destination agent by state, keyword, LLM, or fallback.

The template uses:

```text
agent_template_backend/config/routing.yaml
```

### Decision order

1. Conversational state (`state_policies`).
2. Configurable keywords/intents.
3. Optional LLM Router (`ENABLE_LLM_ROUTER=true`).
4. Fallback (`router.fallback_agent`).

### How to test routing without calling the final agent

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

Expected response:

```json
{
  "route": "billing_agent",
  "agent": "billing_agent",
  "intent": "billing_invoice_explanation",
  "method": "keyword"
}
```

### How to enable LLM routing

In the backend `.env`:

```env
LLM_PROVIDER=oci_openai
OCI_GENAI_API_KEY=...
OCI_GENAI_BASE_URL=https://inference.generativeai.sa-saopaulo-1.oci.oraclecloud.com/openai/v1
OCI_GENAI_MODEL=openai.gpt-4.1
ENABLE_LLM_ROUTER=true
ROUTING_CONFIG_PATH=./config/routing.yaml
```

### How to add a new agent

1. Create the agent class under `agent_template_backend/app/agents/`.
2. Instantiate the agent in `AgentWorkflow.__init__`.
3. Add the node in LangGraph.
4. Add the route in `add_conditional_edges`.
5. Create an intent in `config/routing.yaml` pointing to `agent: agent_name`.

### Included templates

### Template 1 — Telecom

Directory:

```text
templates/template_telecom_billing_product
```

Agents:

- BillingAgent
- ProductAgent

### Template 2 — Retail/E-commerce

Directory:

```text
templates/template_retail_orders_support
```

Agents:

- OrdersAgent
- SupportAgent

This second template shows how to reuse the same architecture for another business domain.

### Generic deterministic intent shift — current behavior

> Content consolidated from `Documentacao/RELEASE_NOTES_GENERIC_DETERMINISTIC_INTENT_SHIFT_V15.md`.

### Problem fixed

Route Stickiness could preserve the previous intent when the new message matched an intent configured in `routing.yaml`, but the user's phrasing omitted short connector words present in the configured keyword.

Real configuration example:

- keyword: `qual é o meu plano`
- message: `qual o meu plano`

The deterministic classification did not recognize the new intent, and continuity ended up preserving the previous intent.

### Fix

The `EnterpriseRouter` continues to use, in this order:

1. exact match;
2. complete token sequence with inserted words (`ordered_tokens`);
3. informative-token sequence that tolerates omission of short connectors present in the keyword (`ordered_content_tokens`).

The third strategy ignores, only on the keyword side, tokens of up to two characters and requires at least two informative tokens. There are no hardcoded intent names, agent names, domains, or business verbs.

Thus, the solution is driven entirely by the intents loaded from the application's `routing.yaml`.

### Precedence over Route Stickiness

When the deterministic candidate found differs from the active intent, it preempts stickiness and returns:

- `route_stickiness_preempted: true`
- `previous_agent`
- `previous_intent`
- `keyword_match_strategy`

The continuity LLM is not called on this path.

### Covered cases

### Same agent, new intent

`retail_order_tracking` -> `quero cancelar meu pedido` -> `retail_order_cancel`

### Same agent, different tools

`contas_invoice_query` -> `qual o meu plano` -> `contas_plan_information`

Even if both intents use `faturas_agent`, the tools change from `consultar_faturas` to `consultar_plano`.

### Intent-shift precedence over stickiness

> Content consolidated from `Documentacao/RELEASE_NOTES_ROUTE_STICKINESS_DETERMINISTIC_INTENT_SHIFT_V14.md`.

### Problem fixed

A multi-token keyword such as `cancelar pedido` was not recognized in phrases such as `quero cancelar meu pedido`. The legacy match used literal substring matching; therefore, the generic keyword `pedido` could preserve `retail_order_tracking`, and continuity reused the previous intent.

### Fix

The `EnterpriseRouter` now has a second deterministic stage for multi-token keywords: ordered-token matching with up to three intermediate tokens. No additional LLM call is made.

Examples recognized by the configured keyword `cancelar pedido`:

- `quero cancelar meu pedido`
- `quero cancelar o meu pedido`
- `pode cancelar esse pedido`
- `gostaria de cancelar meu pedido`

When this match identifies an intent different from the active one, it preempts route stickiness before the continuity LLM.

Expected audit metadata:

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

### LLM cost

For an explicit change recognized deterministically, the continuity LLM classifier is not called. For messages with no explicit signal, Route Stickiness continues with the configured behavior.

### Regression

Tests cover the `retail_order_tracking -> retail_order_cancel` change within the same `orders_agent`, including intermediate words. The related suite passed 18 tests.

### Shift from query to transactional action

> Content consolidated from `Documentacao/RELEASE_NOTES_ROUTE_STICKINESS_TRANSACTION_SHIFT.md`.

### Problem

After `consultar pedido 123`, the message `Quero devolver o pedido 123` could remain on `orders_agent` because of route stickiness. Because the previous intent exposed only query tools, the runtime executed `consultar_pedido` again and the direct response repeated the order status.

### Fixes

- Explicit keywords configured in `routing.yaml` can preempt route stickiness when they point to another intent/agent.
- `retail_support_exchange_return` now has a higher priority than `retail_order_tracking` for exchange/return messages.
- Transactional tools declare `selection_keywords` in `tools.yaml`.
- Direct read-only responses are blocked when the message contains a registered transactional action, even if the previous intent is still active.
- Action-tool selection uses configuration, not domain-specific aliases hardcoded in the runtime.

### Expected flow

1. `consultar pedido 123` → `orders_agent` → `consultar_pedido` → direct response.
2. `Quero devolver o pedido 123` → stickiness preemption → `support_agent` / `retail_support_exchange_return`.
3. `consultar_pedido` validates the order.
4. `solicitar_devolucao` is selected and, with mandatory confirmation, generates `AWAITING_CONFIRMATION`.
5. `Sim, confirmo` executes the action tool exactly once.

### Route-stickiness test coverage

> Content consolidated from `Documentacao/TEST_RESULTS_ROUTE_STICKINESS.md`.

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

### Source files

The files below were consolidated into this manual:

- `Documentacao/Manual de Roteamento Multi-Agent.docx`
- `Documentacao/Route_Stickiness_Semantica_Agent_Framework_OCI.docx`
- `Documentacao/README_ROUTING_MODES.md`
- `Documentacao/README_ENTERPRISE_ROUTING.md`
- `Documentacao/RELEASE_NOTES_GENERIC_DETERMINISTIC_INTENT_SHIFT_V15.md`
- `Documentacao/RELEASE_NOTES_ROUTE_STICKINESS_DETERMINISTIC_INTENT_SHIFT_V14.md`
- `Documentacao/RELEASE_NOTES_ROUTE_STICKINESS_TRANSACTION_SHIFT.md`
- `Documentacao/TEST_RESULTS_ROUTE_STICKINESS.md`

### Maintenance rule

New fixes or evolutions for this subject should update this consolidated document. Release notes may continue to exist as history, but they should not be required to understand or implement the feature.
