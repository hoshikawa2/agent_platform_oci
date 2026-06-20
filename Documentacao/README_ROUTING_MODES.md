# Modos de roteamento multi-agent: Enterprise Router e Supervisor

Este projeto suporta dois desenhos arquiteturais para roteamento entre agentes, sem precisar criar dois frameworks diferentes.

## Modos disponíveis

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

## Opção 1: Enterprise Router

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

## Opção 2: Supervisor

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

## O que foi alterado no código

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

## Como testar localmente

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

## Isolamento

A chave lógica de isolamento permanece:

```text
tenant_id:agent_id:session_id
```

Use essa chave para memória, sessão, checkpoint e telemetria. Em produção, recomenda-se padronizar `agent_id` por agente especialista ou por template, dependendo do nível de isolamento desejado.

---

## Recomendação

Comece em produção com:

```bash
ROUTING_MODE=router
```

Ative:

```bash
ROUTING_MODE=supervisor
```

quando houver necessidade real de múltiplos agentes na mesma mensagem.
