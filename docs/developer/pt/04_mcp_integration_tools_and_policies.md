
### MCP, Tools, Policies e Extração de Parâmetros

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **tools, MCP Servers, mappings, policies read-only/transacionais e extração de parâmetros**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

Tools, mcp servers, mappings, policies read-only/transacionais e extração de parâmetros.

### Conteúdo técnico consolidado

### Integração MCP, Tools, Políticas e Extração de Parâmetros

Manual de desenvolvimento para integrar MCP Servers, registrar tools, isolar tools por agente, configurar políticas read-only/transacionais, confirmação e extração contextual de parâmetros.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### Manual completo de integração MCP Servers

> Conteúdo consolidado a partir de `Documentacao/Manual_Integracao_MCP_Servers_Agent_Framework.docx`.

Manual de Integração com Servidores MCP
Agent Framework Multi-Agent - Router, Supervisor, Tools e Servidores Externos
Este documento explica os conceitos de MCP, como o projeto atual integra servidores MCP, como subir os servidores de exemplo Telecom e Retail, como configurar tools por agente e como evoluir a implementação para um MCP mais aderente ao padrão oficial. O objetivo é servir como guia de desenvolvimento, operação local e implantação em container/OCI.

### Conceitos de MCP

MCP significa Model Context Protocol. Ele define uma forma padronizada para aplicações de IA acessarem contexto externo, ferramentas e capacidades de sistemas fora do modelo. Em vez de colocar integrações diretamente dentro do prompt ou dentro do agente, o MCP separa a responsabilidade: o agente decide o que precisa, e um servidor MCP oferece tools, resources e prompts de forma controlada.
No padrão oficial, o MCP usa mensagens JSON-RPC e define transportes como stdio e Streamable HTTP. O projeto atual usa uma implementação HTTP simplificada para facilitar entendimento e testes locais, com endpoints REST /mcp/tools/list e /mcp/tools/call. Isso é adequado para tutorial e prototipação, mas pode ser evoluído para um client MCP oficial posteriormente.

### Como o projeto atual organiza MCP

A estrutura relevante do projeto é:
```
projeto_multi_agent_isolado/
  agent_framework/
    src/agent_framework/mcp/
      client.py
      models.py
      registry.py
      tool_router.py

  agent_template_backend/
    config/
      mcp_servers.yaml
      mcp_servers.docker.yaml
      tools.yaml
      mcp_parameter_mapping.yaml
    app/
      main.py
      workflows/agent_graph.py

  mcp_servers/
    telecom_mcp_server/
      main.py
      requirements.txt
      Dockerfile
    retail_mcp_server/
      main.py
      requirements.txt
      Dockerfile

  scripts/
    run_mcp_servers.sh
  docker-compose.yml
```

### Componentes principais


### Contrato HTTP simplificado usado no projeto

```
GET  /mcp/tools/list
POST /mcp/tools/call

Payload de chamada:
{
  "tool_name": "consultar_fatura",
  "arguments": {
    "msisdn": "11999999999",
    "invoice_id": "INV-001"
  }
}

Resposta esperada:
{
  "ok": true,
  "result": { ... },
  "metadata": {
    "server": "telecom",
    "tool": "consultar_fatura"
  }
}
```

### Como subir os servidores MCP de exemplo

O projeto possui dois servidores MCP de exemplo: Telecom e Retail. Eles são FastAPI apps independentes. O servidor Telecom roda na porta 8100 e expõe tools como consultar_fatura, consultar_pagamentos, consultar_plano e listar_servicos. O servidor Retail roda na porta 8200 e expõe tools como consultar_pedido, consultar_entrega, solicitar_troca e solicitar_devolucao.

### Subida local via script

```
cd projeto_multi_agent_isolado
bash ./scripts/run_mcp_servers.sh
```
O script cria uma venv no diretório raiz, instala as dependências dos servidores MCP e sobe os dois processos uvicorn em background:
```
Telecom MCP: http://localhost:8100
Retail MCP:  http://localhost:8200
```

### Subida manual do Telecom MCP

```
cd projeto_multi_agent_isolado
python -m venv .venv
source .venv/bin/activate
pip install -r mcp_servers/telecom_mcp_server/requirements.txt
uvicorn --app-dir mcp_servers/telecom_mcp_server main:app --host 0.0.0.0 --port 8100
```

### Subida manual do Retail MCP

```
cd projeto_multi_agent_isolado
source .venv/bin/activate
pip install -r mcp_servers/retail_mcp_server/requirements.txt
uvicorn --app-dir mcp_servers/retail_mcp_server main:app --host 0.0.0.0 --port 8200
```

### Subida com Docker Compose

```
cd projeto_multi_agent_isolado
docker compose up --build
```
No Docker Compose, o backend usa mcp_servers.docker.yaml porque, dentro da rede do compose, localhost apontaria para o próprio container do backend. Por isso os endpoints usam nomes de serviço: telecom-mcp e retail-mcp.
```
services:
  telecom-mcp:
    ports:
      - "8100:8100"

  retail-mcp:
    ports:
      - "8200:8200"

  backend:
    environment:
      MCP_SERVERS_CONFIG_PATH: /app/config/mcp_servers.docker.yaml
    depends_on:
      - telecom-mcp
      - retail-mcp
```

### Como testar as tools MCP


### Health check direto nos servidores

```
curl http://localhost:8100/health
curl http://localhost:8200/health
```

### Listar tools diretamente no Telecom MCP

```
curl http://localhost:8100/mcp/tools/list
```

### Chamar tool diretamente no Telecom MCP

```
curl -X POST http://localhost:8100/mcp/tools/call   -H 'Content-Type: application/json'   -d '{
    "tool_name": "consultar_fatura",
    "arguments": {
      "msisdn": "11999999999",
      "invoice_id": "INV-001"
    }
  }'
```

### Chamar tool diretamente no Retail MCP

```
curl -X POST http://localhost:8200/mcp/tools/call   -H 'Content-Type: application/json'   -d '{
    "tool_name": "consultar_pedido",
    "arguments": {
      "order_id": "PED-1001",
      "customer_id": "C-001"
    }
  }'
```

### Testar via backend do agente

Após subir os servidores MCP e o backend, o backend disponibiliza endpoints de debug para listar e chamar tools através do MCPToolRouter.
```
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -e ../agent_framework
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --reload-dir config --port 8000
curl http://localhost:8000/debug/mcp/tools

curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura   -H 'Content-Type: application/json'   -d '{"msisdn":"11999999999","invoice_id":"INV-001"}'
```

### Como o agente chama MCP no fluxo

O agente não precisa conhecer a URL do servidor. Ele chama uma tool lógica pelo MCPToolRouter. O fluxo esperado é:
```
Usuário
  -> FastAPI /gateway/message
  -> Guardrails de input
  -> Router ou Supervisor escolhe o agente
  -> LangGraph executa o agent graph
  -> Agent decide usar uma tool
  -> MCPToolRouter.call("consultar_fatura", {...})
  -> MCPRegistry resolve servidor telecom
  -> MCPHttpClient chama http://localhost:8100/mcp/tools/call
  -> Resultado volta ao agent graph
  -> Guardrails de output
  -> Judges
  -> Resposta final
```

### Exemplo conceitual em Python

```
result = await tool_router.call(
    "consultar_fatura",
    {
        "msisdn": context.get("msisdn"),
        "invoice_id": context.get("invoice_id"),
    },
)

if result.ok:
    dados_fatura = result.result
else:
    # fallback controlado, telemetria e resposta segura
    erro = result.error
```

### Exemplo via mensagem do gateway

```
curl -X POST http://localhost:8000/gateway/message   -H 'Content-Type: application/json'   -d '{
    "channel": "web",
    "payload": {
      "session_id": "sess-tel-1",
      "message": "Minha fatura veio alta",
      "context": {
        "msisdn": "11999999999",
        "invoice_id": "INV-001"
      }
    }
  }'
curl -X POST http://localhost:8000/gateway/message   -H 'Content-Type: application/json'   -d '{
    "channel": "web",
    "payload": {
      "session_id": "sess-ret-1",
      "message": "Meu pedido não chegou",
      "context": {
        "order_id": "PED-1001",
        "customer_id": "C-001"
      }
    }
  }'
```

### Como configurar novos servidores e tools


### Adicionar um novo MCP Server

Edite agent_template_backend/config/mcp_servers.yaml para execução local:
```
servers:
  crm:
    transport: http
    endpoint: http://localhost:8300/mcp
    enabled: true
    description: MCP Server de CRM.
```
Edite agent_template_backend/config/mcp_servers.docker.yaml para execução em Docker:
```
servers:
  crm:
    transport: http
    endpoint: http://crm-mcp:8300/mcp
    enabled: true
    description: MCP Server de CRM via docker-compose.
```

### Registrar uma nova tool

Edite agent_template_backend/config/tools.yaml:
```
tools:
  consultar_cliente:
    description: Consulta dados cadastrais resumidos do cliente.
    mcp_server: crm
    enabled: true
    args_schema:
      customer_id: string
      document_id: string
```

### Implementar o endpoint no servidor MCP

```
TOOLS = {
    "consultar_cliente": {
        "description": "Consulta dados cadastrais resumidos do cliente.",
        "input_schema": {
            "customer_id": "string",
            "document_id": "string"
        },
    },
}

@app.post("/mcp/tools/call")
async def call_tool(call: ToolCall):
    if call.tool_name == "consultar_cliente":
        return {
            "ok": True,
            "result": {
                "customer_id": call.arguments.get("customer_id"),
                "status": "ATIVO",
                "segmento": "PREMIUM"
            },
            "metadata": {"server": "crm", "tool": "consultar_cliente"}
        }
```

### Como isolar MCP por agente

Em uma arquitetura multi-agent, nem todo agente deve enxergar todas as tools. O agente de pedidos pode usar consultar_pedido e consultar_entrega. O agente de contas pode usar consultar_fatura e consultar_pagamentos. Esse isolamento reduz risco operacional, melhora governança e simplifica o prompt de cada agente.

### Opção simples: allowlist por agente

```
agents:
  - agent_id: billing_agent
    allowed_tools:
      - consultar_fatura
      - consultar_pagamentos
      - consultar_plano
      - listar_servicos

  - agent_id: orders_agent
    allowed_tools:
      - consultar_pedido
      - consultar_entrega
      - solicitar_troca
      - solicitar_devolucao
```

### Opção recomendada: tools por arquivo de configuração

Para projetos grandes, cada agente pode ter seu próprio arquivo tools.yaml, guardrails.yaml e judges.yaml. Isso mantém isolamento real por agente e facilita versionamento.
```
config/agents/telecom_contas/
  prompt_policy.yaml
  guardrails.yaml
  judges.yaml
  tools.yaml

config/agents/retail_orders/
  prompt_policy.yaml
  guardrails.yaml
  judges.yaml
  tools.yaml
```

### Como implantar com Docker e OCI


### Implantação local com Docker Compose

O docker-compose.yml atual já possui serviços separados para telecom-mcp, retail-mcp, backend e frontend. Essa separação é correta porque MCP Servers devem ser escaláveis e versionáveis de forma independente do backend do agente.
```
docker compose up --build

# URLs externas para teste local:
http://localhost:8100/health
http://localhost:8200/health
http://localhost:8000/debug/mcp/tools
http://localhost:5173
```

### Implantação em OCI/OKE

Em Kubernetes/OKE, cada MCP Server deve ser implantado como Deployment + Service. O backend do agente aponta para o DNS interno do Service. Exemplo conceitual:
```
apiVersion: v1
kind: Service
metadata:
  name: telecom-mcp
spec:
  selector:
    app: telecom-mcp
  ports:
    - port: 8100
      targetPort: 8100
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: telecom-mcp
spec:
  replicas: 2
  selector:
    matchLabels:
      app: telecom-mcp
  template:
    metadata:
      labels:
        app: telecom-mcp
    spec:
      containers:
        - name: telecom-mcp
          image: <registry>/telecom-mcp:1.0.0
          ports:
            - containerPort: 8100
```

### Configuração do backend em Kubernetes

```
servers:
  telecom:
    transport: http
    endpoint: http://telecom-mcp.default.svc.cluster.local:8100/mcp
    enabled: true

  retail:
    transport: http
    endpoint: http://retail-mcp.default.svc.cluster.local:8200/mcp
    enabled: true
```

### Segurança, guardrails e observabilidade

MCP aumenta muito a capacidade do agente, mas também aumenta a superfície de risco. Uma tool pode consultar dados sensíveis, abrir protocolos, cancelar serviços, gerar créditos ou executar ações de negócio. Por isso, a integração precisa ser protegida antes, durante e depois da chamada.

### Checklist de segurança mínimo

- Toda tool deve ter descrição clara e schema de argumentos.
- Toda tool de ação deve exigir confirmação explícita do usuário antes da execução.
- Cada agente deve ter allowlist de tools.
- Dados sensíveis retornados por MCP devem passar por masking/sanitização antes da resposta final.
- Toda chamada MCP deve gerar trace/span/event em Langfuse ou OpenTelemetry.
- Timeouts e limites de retries devem ser configurados por tool ou por servidor.
- Não expor MCP Servers diretamente à internet sem autenticação, TLS e controle de rede.
- Separar tools read-only de tools transacionais.

### Telemetria recomendada

```
span: mcp.tool_call
attributes:
  tenant_id
  agent_id
  session_id
  tool_name
  mcp_server
  latency_ms
  ok
  error
  input_argument_keys
  result_size

event: mcp.tool_call.completed
metadata:
  tool_name
  server
  ok
  error
```

### Evolução para MCP oficial

O projeto atual usa um contrato HTTP simplificado. Para produção corporativa, existem duas opções. A primeira é manter esse contrato interno por simplicidade, desde que ele seja bem documentado, seguro e versionado. A segunda é evoluir para um client/server MCP oficial com JSON-RPC, stdio ou Streamable HTTP.

### Passo a passo completo para o desenvolvedor

```
# 1. Baixar e abrir o projeto
cd projeto_multi_agent_isolado

# 2. Subir servidores MCP de exemplo
bash ./scripts/run_mcp_servers.sh

# 3. Em outro terminal, subir backend
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -e ../agent_framework
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --reload-dir config --port 8000

# 4. Validar tools carregadas pelo backend
curl http://localhost:8000/debug/mcp/tools

# 5. Chamar tool Telecom
curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura   -H 'Content-Type: application/json'   -d '{"msisdn":"11999999999","invoice_id":"INV-001"}'

# 6. Chamar tool Retail
curl -X POST http://localhost:8000/debug/mcp/call/consultar_pedido   -H 'Content-Type: application/json'   -d '{"order_id":"PED-1001","customer_id":"C-001"}'

# 7. Testar pelo gateway conversacional
curl -X POST http://localhost:8000/gateway/message   -H 'Content-Type: application/json'   -d '{"channel":"web","payload":{"session_id":"sess-ret-1","message":"Meu pedido não chegou","context":{"order_id":"PED-1001","customer_id":"C-001"}}}'
```

### Troubleshooting


### Referências

- Model Context Protocol Specification: https://modelcontextprotocol.io/specification
- MCP Transports: https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- MCP Resources: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- Reference MCP Servers: https://github.com/modelcontextprotocol/servers
- LangChain MCP Adapters: https://docs.langchain.com/oss/python/langchain/mcp
- Arquivos do projeto: agent_framework/src/agent_framework/mcp/*, agent_template_backend/config/mcp_servers.yaml, agent_template_backend/config/tools.yaml, mcp_servers/*

### Políticas read-only e transacionais

O framework aplica uma política conversacional mínima imediatamente antes da chamada MCP. A classificação read_only identifica consultas; transactional identifica operações que alteram estado. Autorização, idempotência, validação e atomicidade continuam sob responsabilidade do MCP Server.

### Configuração no backend

A configuração é opcional e fica em config/tool_policies.yaml no agent_template_backend. O caminho pode ser definido por TOOL_POLICIES_PATH. Não coloque políticas de domínio dentro da biblioteca compartilhada.
Exemplo:
defaults:
  operation_type: read_only
  require_confirmation: false
tool_policies:
  alterar_plano:
    operation_type: transactional
    require_confirmation: true
    requires: [new_plan_id]

### Execução e compatibilidade

- A confirmação deve chegar como confirmed: true ou confirmation: true; texto com valor true não é suficiente.
- Se tool_policies.yaml não existir, permanecem válidos tool_type, requires, confirmation_required e execution_policy de tools.yaml.
- Tools antigas sem política continuam funcionando sem alteração de comportamento.
- Uma chamada bloqueada não alcança o MCP e retorna metadados blocked_by_policy, operation_type e policy_source.

### Políticas read-only e transacionais

> Conteúdo consolidado a partir de `Documentacao/README_TOOL_POLICIES.md`.

### Objetivo

O framework diferencia operações de consulta (`read_only`) e operações que alteram estado (`transactional`) imediatamente antes da chamada MCP. Essa classificação não substitui autorização, idempotência ou regras de negócio do servidor MCP; ela acrescenta somente a proteção conversacional mínima, especialmente confirmação explícita.

### Onde configurar

A parametrização pertence ao backend da aplicação:

```text
templates/agent_template_backend/config/tool_policies.yaml
```

A biblioteca compartilhada contém apenas o loader e a validação. O caminho é opcional:

```dotenv
TOOL_POLICIES_PATH=./config/tool_policies.yaml
```

### Exemplo

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
```

Para executar `alterar_plano`, os argumentos precisam conter `new_plan_id` e um booleano literal de confirmação:

```json
{"new_plan_id": "CONTROLE_100", "confirmed": true}
```

Também é aceito `"confirmation": true`. Strings como `"true"` não são aceitas como confirmação.

### Compatibilidade

- Se `tool_policies.yaml` não existir, o framework continua usando `tool_type`, `requires`, `confirmation_required` e `execution_policy` de `tools.yaml`.
- Tools antigas sem política continuam executando como antes.
- Uma política explícita no arquivo novo prevalece para `operation_type` e confirmação daquela tool.
- O catálogo `tools.yaml` continua sendo a fonte de endpoint, schema, habilitação e cache.
- O novo arquivo não deve ser colocado em `libs/agent_framework`, pois as decisões variam por aplicação e domínio.

### Fluxo de execução

```text
agente -> MCPToolRouter -> validação da política -> mapeamento de parâmetros -> MCP Gateway/Server
```

Uma chamada bloqueada retorna `ok=false`, `metadata.blocked_by_policy=true`, o tipo da operação e a origem da política. O servidor MCP permanece a autoridade final para autenticação, autorização, validação, idempotência e transação de negócio.

### Migração recomendada

1. Atualize a biblioteca sem criar o arquivo: o comportamento permanece legado.
2. Crie `config/tool_policies.yaml` no backend.
3. Cadastre primeiro apenas operações transacionais que exigem confirmação.
4. Teste chamadas sem confirmação, com confirmação booleana e com campos obrigatórios ausentes.
5. Remova gradualmente duplicações de confirmação de `tools.yaml` quando todos os templates consumidores já usarem a nova configuração.


### Runtime transacional mínimo (correção de amarração)

A lista `mcp_tools` do roteamento é uma **allowlist**, não uma ordem para executar todas as ferramentas. O runtime agora:

1. executa automaticamente somente ferramentas `read_only`;
2. seleciona no máximo uma ação transacional compatível com o pedido do usuário;
3. quando `require_confirmation: true`, persiste `pending_tool_call` e `transaction_status: AWAITING_CONFIRMATION`;
4. no turno de confirmação, reutiliza a mesma chamada e executa com `confirmed: true`;
5. publica no estado `available_mcp_tools`, `selected_tool_call`, `tool_policy_result`, `confirmation_required` e `confirmation_received`.

Para o cenário de exemplo, o pedido `123` (ou `PED-ENTREGUE`) retorna `ENTREGUE` no MCP Retail. Use:

```text
Quero devolver o pedido 123 porque me arrependi da compra.
Sim, confirmo a devolução.
```

O contrato MCP foi padronizado para usar `reason` tanto no catálogo quanto no servidor FastMCP. `tool_policies.yaml` prevalece sobre os campos legados de `tools.yaml`; estes permanecem alinhados nos templates para compatibilidade.

### Integração e compatibilidade das tool policies

> Conteúdo consolidado a partir de `Documentacao/RELEASE_NOTES_TOOL_POLICIES.md`.

### Alterações

- Novo `ToolPolicyRegistry` opcional na biblioteca compartilhada.
- Validação central no `MCPToolRouter`, inclusive para chamadas diretas.
- Tipos mínimos `read_only` e `transactional`.
- Confirmação estrita por `confirmed: true` ou `confirmation: true`.
- Suporte opcional a campos obrigatórios por política.
- Fallback automático para `tool_type`, `requires`, `confirmation_required` e `execution_policy` de `tools.yaml`.
- `config/tool_policies.yaml` e variável `TOOL_POLICIES_PATH` nos templates principais, Day Zero e variantes de `Tuning-Performance/Normal` e `Tuning-Performance/Route_Stickness`.
- Testes unitários de política e compatibilidade adicionados em `tests/unit/test_tool_policies.py`.

### Verificações executadas

- Compilação de `libs`, `templates`, `Tuning-Performance` e `tests`: aprovada.
- Validação estrutural dos seis arquivos YAML: aprovada.
- Casos isolados do loader (política transacional, confirmação, ausência de arquivo e ausência de cadastro): aprovados.
- Renderização dos dois manuais Word atualizados: aprovada, sem cortes ou sobreposição nas páginas adicionadas.

### Limitação do ambiente de validação

A suíte `pytest` foi preparada, mas não pôde ser executada integralmente neste ambiente porque `pytest` e as dependências de runtime do projeto não estavam instalados e o acesso ao índice de pacotes expirou. Para reproduzir em um ambiente do projeto:

```bash
PYTHONPATH=libs/agent_framework/src:templates/agent_template_backend python -m pytest -q
```

### Correção de integração backend/MCP
- `mcp_tools` passou a ser tratado como allowlist.
- Ações não são mais executadas automaticamente junto com consultas.
- Confirmação transacional é persistida e retomada no turno seguinte.
- Corrigida incompatibilidade `reason`/`motivo` no MCP Retail.
- Adicionado pedido entregue determinístico para testes (`123`).
- Removida keyword genérica `produto` da intenção Telecom para evitar colisão com devoluções Retail.
- Templates Normal e Route_Stickness em `Tuning-Performance` foram sincronizados.

### Extração contextual de parâmetros MCP

> Conteúdo consolidado a partir de `Documentacao/RELEASE_NOTES_MCP_PARAMETER_EXTRACTION_FIX.md`.

### Problema corrigido

O bloco `extract` do `mcp_parameter_mapping.yaml` existia na configuração e na
documentação, mas não era executado pelo runtime. Além disso, valores do
Business Context podiam sobrescrever argumentos explícitos, fazendo
`contract_key` substituir o `order_id` informado pelo usuário.

### Correções

- implementação da extração genérica `strategy: llm` após a escolha da tool;
- suporte preservado para `strategy: month_name_pt`;
- profile dedicado `mcp_parameter_extraction`;
- telemetria `llm.mcp_parameter_extraction`;
- `extract` deixou de ser interpretado como mapeamento simples;
- argumentos explícitos/extraídos têm precedência sobre Business Context;
- remoção de `contract_key: order_id` dos templates;
- `order_id` configurado como `string`;
- atualização das variantes em `Tuning-Performance`.

### Resultado esperado

Para a mensagem `consultar pedido 123`, a chamada MCP deve receber
`order_id=123`, mesmo quando o Business Context contém outro `contract_key`.

### Uso local de MCP tools

> Conteúdo consolidado a partir de `Documentacao/README_MCP.md`.

Esta versão adiciona uma camada MCP ao framework:

- `agent_framework.mcp.MCPToolRouter`
- `agent_template_backend/config/mcp_servers.yaml`
- `agent_template_backend/config/tools.yaml`
- `mcp_servers/telecom_mcp_server`
- `mcp_servers/retail_mcp_server`

### Subir localmente

Terminal 1:

```bash
bash ./scripts/run_mcp_servers.sh
```

Terminal 2:

```bash
cd agent_template_backend
python -m venv .venv
source .venv/bin/activate
pip install -e ../agent_framework
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --reload-dir config --port 8000
```

Terminal 3:

```bash
cd agent_frontend
python -m http.server 5173
```

### Testes rápidos

Listar tools MCP carregadas pelo backend:

```bash
curl http://localhost:8000/debug/mcp/tools
```

Chamar tool diretamente via backend:

```bash
curl -X POST http://localhost:8000/debug/mcp/call/consultar_fatura \
  -H 'Content-Type: application/json' \
  -d '{"msisdn":"11999999999","invoice_id":"INV-001"}'
```

Roteamento Telecom + MCP:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"session_id":"sess-tel-1","message":"Minha fatura veio alta","context":{"msisdn":"11999999999","invoice_id":"INV-001"}}}'
```

Roteamento Retail + MCP:

```bash
curl -X POST http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{"channel":"web","payload":{"session_id":"sess-ret-1","message":"Meu pedido não chegou","context":{"order_id":"PED-1001","customer_id":"C-001"}}}'
```

### Docker Compose

```bash
docker compose up --build
```

No compose, o backend usa `config/mcp_servers.docker.yaml` para apontar para `telecom-mcp` e `retail-mcp`.

### Operações read-only e transacionais

Use `config/tool_policies.yaml` no backend para classificar somente as operações que precisam de tratamento adicional. A validação é aplicada no roteador central antes do MCP Gateway/Server. O arquivo é opcional e templates antigos continuam usando as políticas já presentes em `tools.yaml`. A configuração completa e o roteiro de migração estão em [README_TOOL_POLICIES.md](README_TOOL_POLICIES.md).

### Arquivos de origem

Os arquivos abaixo foram consolidados neste manual:

- `Documentacao/Manual_Integracao_MCP_Servers_Agent_Framework.docx`
- `Documentacao/README_TOOL_POLICIES.md`
- `Documentacao/RELEASE_NOTES_TOOL_POLICIES.md`
- `Documentacao/RELEASE_NOTES_MCP_PARAMETER_EXTRACTION_FIX.md`
- `Documentacao/README_MCP.md`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.
