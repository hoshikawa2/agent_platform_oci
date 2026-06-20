# agent_framework_evaluator

## 1. O que é o `agent_framework_evaluator`?

O `agent_framework_evaluator` é um serviço complementar ao `agent_framework_oci` criado para avaliar conversas reais executadas pelos agentes do framework.

Ele coleta conversas de uma fonte, normalmente o Langfuse, reconstrói o contexto da interação, executa um Judge LLM, grava os resultados em banco Oracle/ADB, gera arquivos legados no formato TXT.GZ e, opcionalmente, publica scores de volta no Langfuse.

Em termos simples:

```text
agent_framework_oci gera conversas e telemetria
        ↓
Langfuse armazena traces, spans, generations, metadata e usage
        ↓
agent_framework_evaluator coleta essas conversas
        ↓
LLM Judge avalia qualidade, precisão, alucinação, resolução e CSI
        ↓
Oracle/ADB persiste runs, itens, resultados, achados e progresso
        ↓
Exporter gera arquivo legado AGENTE_<agent>_LLM_JUDGE_YYYYMMDD.TXT.GZ
```

O evaluator não substitui os guardrails, judges online ou telemetria do `agent_framework_oci`. Ele atua como uma camada offline/batch de avaliação, auditoria e exportação.

---

## 2. Objetivo da solução

O objetivo do evaluator é permitir que conversas já executadas sejam analisadas posteriormente com critérios padronizados.

Ele atende principalmente estes cenários:

- avaliação diária de conversas por agente;
- geração de arquivos legados de avaliação;
- auditoria de qualidade de respostas;
- identificação de alucinação, baixa precisão, baixa resolução ou baixa experiência do cliente;
- comparação entre agentes como `telecom_contas`, `retail_orders` e `financeiro_agent`;
- publicação opcional de scores no Langfuse;
- persistência de histórico de avaliações no Oracle/ADB;
- acompanhamento de progresso via API ou CLI.

---

## 3. Como ele se integra ao `agent_framework_oci`

O `agent_framework_oci` é o runtime principal dos agentes. Ele executa o fluxo conversacional com LangGraph, supervisor, guardrails, judges, MCP tools, memória, RAG e telemetria.

Durante a execução, o framework publica traces no Langfuse contendo:

- `trace_id`;
- `session_id`;
- `message_id`;
- `agent_id`;
- `channel`;
- `business_context` canônico;
- eventos IC/NOC/GRL;
- spans de LangGraph;
- spans de guardrails;
- spans de judges;
- generations LLM;
- usage de modelo, quando disponível;
- `prompt_tokens`, `completion_tokens` e `total_tokens`, quando retornados pelo provider;
- `input_size`, quando emitido pelos spans do framework.

O evaluator usa essa telemetria como fonte de dados.

A integração principal acontece assim:

```text
agent_framework_oci
  ├── executa agentes
  ├── resolve identidade via identity.yaml
  ├── monta BusinessContext canônico
  ├── chama MCP/RAG/LLM
  ├── emite telemetria Langfuse
  └── grava usage/model/tokens quando disponíveis

agent_framework_evaluator
  ├── lê traces no Langfuse
  ├── aplica identity.yaml para normalizar identidade
  ├── reconstrói ConversationRecord
  ├── executa LLM Judge offline
  ├── grava resultados no Oracle/ADB
  ├── exporta TXT.GZ legado
  └── opcionalmente publica scores no Langfuse
```

---

## 4. Arquitetura geral

```text
+------------------------+
| agent_framework_oci    |
|------------------------|
| LangGraph              |
| Supervisor             |
| Guardrails             |
| Judges online          |
| MCP Tool Router        |
| RAG                    |
| Memory / Checkpoint    |
| Langfuse Telemetry     |
+-----------+------------+
            |
            v
+------------------------+
| Langfuse               |
|------------------------|
| Traces                 |
| Spans                  |
| Generations            |
| Metadata               |
| Usage / Tokens         |
+-----------+------------+
            |
            v
+------------------------+
| agent_framework_       |
| evaluator              |
|------------------------|
| Collectors             |
| Identity Resolver      |
| Conversation Records   |
| LLM Judge              |
| VLoop analytics        |
| Repository Oracle      |
| Legacy Exporter        |
| API / CLI              |
+-----------+------------+
            |
            v
+------------------------+
| Oracle ADB             |
|------------------------|
| EVALUATION_RUN         |
| EVALUATION_ITEM        |
| EVALUATION_RESULT      |
| EVALUATION_FINDING     |
| EVALUATION_PROGRESS    |
| EVALUATION_METRIC      |
+-----------+------------+
            |
            v
+------------------------+
| Output                 |
|------------------------|
| TXT.GZ legado          |
| API dashboard          |
| Langfuse scores        |
+------------------------+
```

---

## 5. Componentes da solução

### 5.1 CLI

Arquivo principal:

```text
evaluator/cli.py
```

Responsável por expor comandos como:

```bash
python -m evaluator.cli init-db
python -m evaluator.cli show-config
python -m evaluator.cli run --source langfuse
python -m evaluator.cli run-agents --source langfuse
python -m evaluator.cli runs
python -m evaluator.cli progress <run_id>
```

A CLI é a forma principal de operar o evaluator em modo batch.

---

### 5.2 API

Arquivo principal:

```text
evaluator/api/main.py
```

Expõe endpoints HTTP para consultar progresso, runs e resultados.

Exemplos esperados:

```text
GET /health
GET /runs
GET /runs/{run_id}/progress
GET /runs/{run_id}/results
GET /runs/{run_id}/findings
```

A API permite construir uma interface gráfica simples ou integrar o evaluator com outros sistemas.

---

### 5.3 EvaluationEngine

Arquivo principal:

```text
evaluator/engine.py
```

É o orquestrador central do evaluator.

Responsabilidades:

1. criar uma nova execução de avaliação (`EVALUATION_RUN`);
2. escolher o collector conforme `source`;
3. coletar conversas;
4. aplicar amostragem por agente;
5. inserir itens em `EVALUATION_ITEM`;
6. processar cada item;
7. chamar o LLM Judge;
8. salvar resultado de trace;
9. executar avaliação de sessão;
10. salvar resultado de sessão;
11. exportar arquivo legado;
12. marcar status final da execução;
13. emitir eventos de progresso.

Fluxo simplificado:

```text
run_agent()
  ↓
collector.collect()
  ↓
repository.insert_items()
  ↓
_process()
  ↓
judge.judge_trace()
  ↓
repository.save_trace_result()
  ↓
judge.judge_sessions()
  ↓
repository.save_session_result()
  ↓
export_legacy_txt_gz()
```

---

### 5.4 Collectors

Diretório:

```text
evaluator/collectors/
```

Collectors são responsáveis por buscar conversas em uma fonte externa e convertê-las para `ConversationRecord`.

Collectors típicos:

```text
evaluator/collectors/langfuse.py
evaluator/collectors/agent_framework.py
evaluator/collectors/mock.py
evaluator/collectors/base.py
```

#### LangfuseCollector

É o collector principal.

Responsabilidades:

- buscar traces no Langfuse;
- filtrar por período;
- filtrar por agente/alias;
- recuperar detalhes do trace;
- extrair input/output;
- reconstruir mensagens;
- coletar metadata;
- aplicar `identity.yaml`;
- montar `BusinessContext` canônico;
- preencher `ConversationRecord`.

O collector deve normalizar dados para que o exporter não precise conhecer detalhes internos do Langfuse.

---

### 5.5 Identity Resolver

Diretório recomendado:

```text
evaluator/identity/
```

Arquivo principal:

```text
evaluator/identity/resolver.py
```

O evaluator deve usar o mesmo conceito de identidade do `agent_framework_oci`, baseado no arquivo:

```text
configs/identity.yaml
```

A função do `identity.yaml` é mapear campos variáveis de entrada para um modelo canônico:

```text
customer_key
contract_key
interaction_key
account_key
resource_key
session_key
```

Exemplo conceitual:

```yaml
identity:
  version: 2
  keys:
    customer_key:
      sources:
        - business_context.customer_key
        - metadata.customer_key
        - user_id
    contract_key:
      sources:
        - business_context.contract_key
        - metadata.contract_key
    interaction_key:
      sources:
        - business_context.interaction_key
        - metadata.ura_call_id
        - metadata.message_id
        - message_id
    session_key:
      sources:
        - business_context.session_key
        - session_id
        - conversation_key
```

Com isso, o evaluator não fica preso a campos como `ura_call_id`, `call_id`, `message_id` ou `interaction_key` diretamente. Ele resolve tudo para `interaction_key`.

---

### 5.6 Models

Arquivo principal:

```text
evaluator/core/models.py
```

Define os objetos centrais do evaluator.

Principais modelos:

```python
class ConversationRecord
class ConversationMessage
class TraceJudgeResult
class SessionJudgeResult
class CombinedJudgeResult
class RunStatus
class ItemStatus
```

#### ConversationRecord

Representa uma conversa ou turno avaliado.

Campos comuns:

```text
trace_id
session_id
message_id
agent_id
channel
input_text
output_text
messages
metadata
raw
```

O campo `metadata` deve conter dados normalizados:

```text
business_context
uraCallId
channelId
messageId
promptLength
```

O campo `raw` mantém o payload original para auditoria e fallback.

---

### 5.7 LLM Judge

Arquivo principal:

```text
evaluator/judges/llm_judge.py
```

Classe principal:

```python
TIMStyleLLMJudge
```

Responsabilidades:

- carregar prompts de avaliação;
- montar prompt de trace;
- montar prompt de sessão;
- chamar LLM via client configurado;
- interpretar resposta JSON;
- retornar `TraceJudgeResult` e `SessionJudgeResult`.

O judge avalia métricas como:

```text
judgeScore
accuracyScore
alucinationScore
inferredCsiScore
resolution
conversationPrecision
rationale
```

O judge deve ser LLM-based, não determinístico.

---

### 5.8 Prompts

Diretório:

```text
evaluator/prompts/
```

Arquivos esperados:

```text
trace_judge_prompt.md
session_judge_prompt.md
loader.py
```

O prompt de trace avalia uma resposta individual.

O prompt de sessão avalia a conversa agrupada por `session_id`.

Exemplo de saída esperada do LLM para trace:

```json
{
  "judgeScore": 0.8,
  "accuracyScore": 0.9,
  "alucinationScore": 0.1,
  "rationale": "Resposta aderente ao contexto e baseada em dados disponíveis."
}
```

Exemplo de saída esperada para sessão:

```json
{
  "inferredCsiScore": 0.5,
  "resolution": 1,
  "conversationPrecision": 1,
  "rationale": "A conversa foi resolvida com informações consistentes."
}
```

---

### 5.9 LLM Client

Diretório:

```text
evaluator/llm/
```

Arquivos típicos:

```text
evaluator/llm/client.py
evaluator/llm/oci_openai.py
```

O evaluator deve usar o mesmo padrão de acesso a LLM do `agent_framework_oci`, preferencialmente via provider `oci_openai`.

Variáveis comuns:

```env
LLM_PROVIDER=oci_openai
OCI_GENAI_ENDPOINT=...
OCI_GENAI_MODEL_ID=...
OCI_GENAI_API_KEY=...
OCI_GENAI_COMPARTMENT_ID=...
```

O client precisa retornar texto bruto para o Judge interpretar como JSON.

---

### 5.10 Repository / Oracle Store

Diretório:

```text
evaluator/persistence/
```

Arquivos principais:

```text
evaluator/persistence/oracle_store.py
evaluator/persistence/repository.py
```

O `OracleStore` cuida de:

- conexão com ADB/Oracle;
- wallet;
- DSN;
- criação/ajuste de schema;
- execução thread-safe para chamadas assíncronas;
- prefixo de tabelas.

O `EvaluationRepository` cuida de:

- criar runs;
- gravar progresso;
- inserir itens;
- buscar próximos itens;
- marcar item como `PROCESSING`, `COMPLETED` ou `FAILED`;
- salvar resultados;
- salvar findings;
- sumarizar run;
- listar runs;
- consultar progresso.

---

### 5.11 Legacy Exporter

Arquivo principal:

```text
evaluator/output/legacy_exporter.py
```

Gera o arquivo legado:

```text
output/AGENTE_<agent_id>_LLM_JUDGE_YYYYMMDD.TXT.GZ
```

Formato das colunas:

```text
judgeScore
accuracyScore
alucinationScore
promptLength
loop
inferredCsiScore
resolution
conversationPrecision
uraCallId
channelId
sessionId
messageId
```

Exemplo:

```text
"0.8"|;"0.9"|;"0.1"|;"732"|;"0"|;"0.5"|;"1"|;"1"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"|;"web"|;"eba23248-e038-4d33-bc2c-6465ef677d07"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"
"TOTAL"|;"19"
```

#### promptLength

O campo `promptLength` deve usar esta prioridade:

1. `prompt_tokens` / `promptTokens` / `input_tokens` / `inputTokens` nas observations do Langfuse;
2. `usage.input` ou `usageDetails.input`;
3. `metadata.input_size` emitido pelo framework;
4. fallback para tamanho textual de `input_text`, `output_text` e `messages`.

Exemplo:

```text
promptLength = 732
```

#### loop

O campo `loop` usa o detector VLoop.

```text
0 = sem loop detectado
1 = loop detectado
```

---

### 5.12 VLoop Analytics

Arquivo principal:

```text
evaluator/analytics/vloop.py
```

Responsável por detectar repetição/loop conversacional em padrão semelhante ao guardrail VLoop do `agent_framework_oci`.

A função normalmente exposta é:

```python
vloop_flag(raw) -> int
```

Ela retorna:

```text
0 quando não há evidência de loop
1 quando há repetição suspeita
```

---

### 5.13 Langfuse Score Publisher

Arquivo principal:

```text
evaluator/publishers/langfuse_scores.py
```

Responsável por publicar scores de avaliação de volta no Langfuse, quando habilitado.

Variável de controle:

```env
PUBLISH_LANGFUSE_SCORES=true
```

Quando desabilitado, o evaluator apenas grava no banco e exporta arquivo.

---

## 6. Estrutura de diretórios

```text
agent_framework_evaluator/
├── configs/
│   ├── identity.yaml
│   └── judge/
│       └── agents.yaml
├── docs/
├── evaluator/
│   ├── __init__.py
│   ├── cli.py
│   ├── engine.py
│   ├── api/
│   │   └── main.py
│   ├── analytics/
│   │   └── vloop.py
│   ├── collectors/
│   │   ├── base.py
│   │   ├── langfuse.py
│   │   ├── agent_framework.py
│   │   └── mock.py
│   ├── config/
│   │   ├── settings.py
│   │   └── agents.py
│   ├── core/
│   │   └── models.py
│   ├── identity/
│   │   └── resolver.py
│   ├── judges/
│   │   └── llm_judge.py
│   ├── llm/
│   │   ├── client.py
│   │   └── oci_openai.py
│   ├── output/
│   │   └── legacy_exporter.py
│   ├── persistence/
│   │   ├── oracle_store.py
│   │   └── repository.py
│   ├── prompts/
│   │   ├── loader.py
│   │   ├── trace_judge_prompt.md
│   │   └── session_judge_prompt.md
│   └── publishers/
│       └── langfuse_scores.py
├── output/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

## 7. Configuração

### 7.1 Arquivo `.env`

Exemplo:

```env
# Oracle / ADB
ADB_USER=ADMIN
ADB_PASSWORD=your_password
ADB_DSN=oradb23ai_high
ADB_WALLET_DIR=/path/to/Wallet_ORADB23ai
DB_TABLE_PREFIX=AGENTFW_

# Langfuse
LANGFUSE_ENABLED=true
LANGFUSE_HOST=http://localhost:3005
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
PUBLISH_LANGFUSE_SCORES=false

# LLM
LLM_PROVIDER=oci_openai
OCI_GENAI_ENDPOINT=https://...
OCI_GENAI_MODEL_ID=...
OCI_GENAI_API_KEY=...
OCI_GENAI_COMPARTMENT_ID=...

# Evaluator
EVALUATOR_OUTPUT_DIR=output
EVALUATOR_BATCH_SIZE=10
EVALUATOR_MAX_ATTEMPTS=2
EVALUATOR_AGENTS_CONFIG=configs/judge/agents.yaml
IDENTITY_CONFIG_PATH=configs/identity.yaml
TRACE_PROMPT_PATH=evaluator/prompts/trace_judge_prompt.md
SESSION_PROMPT_PATH=evaluator/prompts/session_judge_prompt.md
```

---

### 7.2 Configuração de agentes

Arquivo:

```text
configs/judge/agents.yaml
```

Exemplo:

```yaml
agents:
  - agent_id: telecom_contas
    enabled: true
    aliases:
      - telecom_contas
      - billing_agent
      - financeiro_agent
    percentage: 1.0

  - agent_id: retail_orders
    enabled: true
    aliases:
      - retail_orders
      - orders_agent
    percentage: 1.0

  - agent_id: financeiro_agent
    enabled: true
    aliases:
      - financeiro_agent
    percentage: 1.0
```

O campo `aliases` é importante porque o Langfuse pode registrar o agente de formas diferentes, por exemplo:

```text
agent_id = telecom_contas
route = financeiro_agent
agent = financeiro_agent
```

---

### 7.3 Configuração de identidade

Arquivo:

```text
configs/identity.yaml
```

O evaluator deve usar o mesmo padrão do framework.

Exemplo:

```yaml
identity:
  version: 2
  keys:
    customer_key:
      sources:
        - business_context.customer_key
        - metadata.customer_key
        - user_id

    contract_key:
      sources:
        - business_context.contract_key
        - metadata.contract_key

    interaction_key:
      sources:
        - business_context.interaction_key
        - metadata.ura_call_id
        - metadata.message_id
        - message_id

    session_key:
      sources:
        - business_context.session_key
        - metadata.session_key
        - session_id
        - conversation_key
```

O campo `interaction_key` é usado para preencher o `uraCallId` no export legado.

---

## 8. Como executar

### 8.1 Instalar dependências

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Se estiver usando Conda:

```bash
conda activate py313
pip install -e .
```

---

### 8.2 Validar configuração

```bash
python -m evaluator.cli show-config
```

Saída esperada:

```text
{
  "env_path": ".../.env",
  "adb_dsn": "oradb23ai_high",
  "wallet": ".../Wallet_ORADB23ai",
  "langfuse": true,
  "publish_langfuse_scores": false,
  "llm_provider": "oci_openai",
  "agents_config": "configs/judge/agents.yaml"
}
```

---

### 8.3 Criar/validar schema

```bash
python -m evaluator.cli init-db
```

Saída esperada:

```text
{'status': 'OK', 'message': 'Evaluator schema checked/created successfully.'}
```

---

### 8.4 Rodar avaliação por período

```bash
python -m evaluator.cli run \
  --period-start 2026-06-11T00:00:00 \
  --period-end 2026-06-12T00:00:00 \
  --source langfuse
```

---

### 8.5 Rodar avaliação por agentes configurados

```bash
python -m evaluator.cli run-agents --source langfuse
```

Saída esperada:

```text
[
  {
    'status': 'COMPLETED',
    'run_id': '...',
    'total_items': 19,
    'completed_items': 19,
    'failed_items': 0,
    'evaluations': 19,
    'avg_score': 0.72,
    'agent_id': 'telecom_contas',
    'output_file': 'output/AGENTE_telecom_contas_LLM_JUDGE_20260612.TXT.GZ',
    'uploaded_to': None
  }
]
```

---

### 8.6 Consultar progresso

```bash
python -m evaluator.cli progress <run_id>
```

Ou via API:

```bash
curl http://localhost:8001/runs/<run_id>/progress
```

---

### 8.7 Ver arquivo exportado

```bash
gzip -cd output/AGENTE_telecom_contas_LLM_JUDGE_20260612.TXT.GZ
```

Exemplo de linha válida:

```text
"0.8"|;"0.9"|;"0.1"|;"732"|;"0"|;"0.5"|;"1"|;"1"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"|;"web"|;"eba23248-e038-4d33-bc2c-6465ef677d07"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"
"TOTAL"|;"19"
```

---

## 9. Banco de dados

### 9.1 Tabelas principais

#### EVALUATION_RUN

Armazena uma execução de avaliação.

Campos principais:

```text
RUN_ID
PERIOD_START
PERIOD_END
SOURCE
AGENT_ID
STATUS
TOTAL_ITEMS
PROCESSED_ITEMS
FAILED_ITEMS
LAST_HEARTBEAT_AT
CREATED_AT
UPDATED_AT
ERROR_MESSAGE
```

---

#### EVALUATION_ITEM

Armazena cada conversa/turno coletado.

Campos principais:

```text
ITEM_ID
RUN_ID
TRACE_ID
SESSION_ID
MESSAGE_ID
AGENT_ID
CHANNEL
STATUS
ATTEMPT_COUNT
RAW_JSON
CREATED_AT
UPDATED_AT
ERROR_MESSAGE
```

---

#### EVALUATION_RESULT

Armazena resultados de trace e sessão.

Campos principais:

```text
RESULT_ID
RUN_ID
ITEM_ID
TRACE_ID
SESSION_ID
AGENT_ID
JUDGE_TYPE
JUDGE_NAME
JUDGE_SCORE
ACCURACY_SCORE
ALUCINATION_SCORE
INFERRED_CSI_SCORE
RESOLUTION
CONVERSATION_PRECISION
RATIONALE
RESULT_JSON
CREATED_AT
```

`JUDGE_TYPE` pode ser:

```text
TRACE
SESSION
```

---

#### EVALUATION_PROGRESS_EVENT

Armazena eventos de progresso da execução.

Exemplos de stage:

```text
RUN_CREATED
COLLECTING
COLLECTED
SAMPLED
ITEMS_INSERTED
BATCH_STARTED
ITEM_COMPLETED
ITEM_FAILED
SESSION_JUDGE_COMPLETED
EXPORTED
COMPLETED
PARTIAL
```

---

## 10. Como os códigos funcionam em conjunto

### 10.1 Fluxo completo de execução

```text
CLI run-agents
  ↓
carrega configs/judge/agents.yaml
  ↓
para cada agente habilitado
  ↓
EvaluationEngine.run_agent(agent)
  ↓
cria EVALUATION_RUN
  ↓
LangfuseCollector.collect(...)
  ↓
IdentityResolver.resolve(...)
  ↓
ConversationRecord
  ↓
EvaluationRepository.insert_items(...)
  ↓
EvaluationEngine._process(run_id)
  ↓
TIMStyleLLMJudge.judge_trace(record)
  ↓
LLMClient.complete(prompt)
  ↓
save_trace_result(...)
  ↓
TIMStyleLLMJudge.judge_sessions(records)
  ↓
save_session_result(...)
  ↓
export_legacy_txt_gz(...)
  ↓
COMPLETED
```

---

### 10.2 Papel do collector

O collector é responsável por transformar dados externos em dados canônicos.

Ele deve esconder diferenças entre fontes como:

```text
Langfuse
agent_framework database
mock data
```

A saída sempre deve ser:

```python
ConversationRecord
```

---

### 10.3 Papel do judge

O judge recebe um `ConversationRecord`, monta um prompt e chama o LLM.

Ele não deve conhecer Oracle, Langfuse, export legado ou API.

Ele só avalia.

---

### 10.4 Papel do repository

O repository é a camada de persistência.

Ele não deve conter regra de negócio de avaliação.

Ele apenas grava, busca e atualiza dados.

---

### 10.5 Papel do exporter

O exporter transforma dados persistidos em arquivo legado.

Ele não deve resolver identidade de forma complexa.

O ideal é que ele leia campos já normalizados:

```text
metadata.business_context.interaction_key
metadata.channelId
metadata.messageId
metadata.promptLength
```

No entanto, para resiliência, ele também pode consultar `RAW_JSON` como fallback.

---

## 11. Regras importantes de desenho

### 11.1 O evaluator não deve ficar chumbado para um agente

Evite lógica como:

```python
if agent_id == "telecom_contas":
    ura_call_id = metadata["ura_call_id"]
```

O correto é usar `identity.yaml`.

---

### 11.2 O exporter não deve conhecer detalhes internos do Langfuse

Evite acoplamento excessivo a caminhos como:

```text
raw.detail.observations[0].metadata.ura_call_id
raw.trace.input.business_context.interaction_key
```

Isso deve ser resolvido no collector.

---

### 11.3 `promptLength` deve vir de tokens quando possível

Prioridade recomendada:

```text
1. prompt_tokens / promptTokens
2. input_tokens / inputTokens
3. usage.input / usageDetails.input
4. metadata.input_size
5. tamanho textual de input/output/messages
```

---

### 11.4 `uraCallId` deve vir do BusinessContext

O campo legado `uraCallId` deve ser mapeado para:

```text
business_context.interaction_key
```

Esse é o nome canônico do framework.

---

### 11.5 `sessionId` deve vir do BusinessContext

O campo legado `sessionId` deve ser mapeado para:

```text
business_context.session_key
```

Não confundir com a chave composta completa:

```text
default:telecom_contas:<uuid>
```

O evaluator pode guardar a chave completa, mas o export legado normalmente deve usar o identificador de sessão limpo.

---

## 12. Testes recomendados

### 12.1 Teste de configuração

```bash
python -m evaluator.cli show-config
```

Validar:

```text
ADB_DSN
Wallet
Langfuse enabled
LLM provider
Agents config
Identity config
```

---

### 12.2 Teste de banco

```bash
python -m evaluator.cli init-db
```

Depois validar tabelas:

```sql
select table_name
from user_tables
where table_name like 'AGENTFW_EVALUATION%';
```

---

### 12.3 Teste com mock

```bash
python -m evaluator.cli run --source mock
```

Use esse teste para validar schema, judge e export sem depender do Langfuse.

---

### 12.4 Teste com Langfuse

```bash
python -m evaluator.cli run-agents --source langfuse
```

Validar:

```text
total_items > 0
completed_items > 0
failed_items = 0
evaluations > 0
output_file preenchido
```

---

### 12.5 Teste do export

```bash
gzip -cd output/AGENTE_telecom_contas_LLM_JUDGE_YYYYMMDD.TXT.GZ
```

Validar colunas:

```text
judgeScore              preenchido
accuracyScore           preenchido
alucinationScore        preenchido
promptLength            maior que 0
loop                    0 ou 1
inferredCsiScore        preenchido
resolution              0 ou 1
conversationPrecision   0 ou 1
uraCallId               preenchido
channelId               preenchido
sessionId               preenchido
messageId               preenchido
```

---

## 13. Troubleshooting

### 13.1 `promptLength` sai 0

Causas comuns:

- `find_prompt_tokens` não foi incluído no arquivo;
- `promptTokens` está zerado no Langfuse;
- `input_size` não está sendo percorrido;
- `RAW_JSON` está vindo como string não convertida;
- exporter antigo ainda está rodando;
- `except Exception: pass` está mascarando erro.

Debug recomendado:

```python
print("PROMPT_LENGTH", extract_prompt_length(raw))
print("RAW_TYPE", type(raw))
print("RAW_KEYS", list(raw.keys())[:20])
```

---

### 13.2 `uraCallId` sai vazio

Causas comuns:

- `identity.yaml` não está sendo carregado;
- collector não está copiando `business_context` para `metadata`;
- `interaction_key` não existe no trace;
- exporter não usa `business_context.interaction_key`.

Validação:

```sql
select RAW_JSON
from AGENTFW_EVALUATION_ITEM
where MESSAGE_ID = '<message_id>';
```

Procurar:

```text
interaction_key
ura_call_id
business_context
```

---

### 13.3 `ORA-00904 invalid identifier`

Geralmente indica schema antigo.

Exemplos já encontrados:

```text
ORA-00904: UPDATED_AT invalid identifier
ORA-00904: REASONING invalid identifier
ORA-00904: JUDGE_TYPE invalid identifier
```

Correção:

```bash
python -m evaluator.cli init-db
```

Se a tabela já existir sem a coluna nova, o `_init_schema` precisa executar `ALTER TABLE ADD` de forma idempotente.

---

### 13.4 `ORA-00054 resource busy`

Indica lock em tabela.

Causas comuns:

- API rodando enquanto `init-db` tenta alterar schema;
- outro processo usando a tabela;
- transação aberta no SQL Developer.

Correção:

1. parar API/CLI;
2. fechar sessões abertas;
3. executar novamente `init-db`.

---

### 13.5 `OCI LLM 401`

Indica problema de autenticação no LLM.

Validar:

```env
OCI_GENAI_ENDPOINT
OCI_GENAI_MODEL_ID
OCI_GENAI_API_KEY
OCI_GENAI_COMPARTMENT_ID
```

Também confirmar se o evaluator está lendo o `.env` correto:

```bash
python -m evaluator.cli show-config
```

---

### 13.6 `Entity with key ${OCI_GENAI_MODEL_ID} not found`

Indica que o valor literal `${OCI_GENAI_MODEL_ID}` chegou ao provider.

Causas comuns:

- variável não expandida;
- YAML usando `${OCI_GENAI_MODEL_ID}` sem interpolação;
- `.env` não carregado;
- configuração do LLM client não resolve placeholders.

Correção:

- colocar o model ID real no `.env`;
- garantir interpolação em `settings.py`;
- validar com `show-config`.

---

## 14. Checklist de validação final

Antes de considerar o evaluator pronto, validar:

```text
[ ] init-db executa sem erro
[ ] show-config mostra .env correto
[ ] Langfuse retorna traces
[ ] run-agents coleta itens por agente
[ ] LLM Judge responde JSON válido
[ ] EVALUATION_RESULT grava TRACE e SESSION
[ ] progress mostra eventos úteis
[ ] export TXT.GZ é gerado
[ ] promptLength > 0
[ ] uraCallId preenchido
[ ] sessionId preenchido
[ ] messageId preenchido
[ ] loop preenchido com 0 ou 1
[ ] arquivo termina com TOTAL
[ ] scores podem ser publicados no Langfuse quando habilitado
```

---

## 15. Exemplo de resultado final validado

```text
"0.8"|;"0.9"|;"0.1"|;"732"|;"0"|;"0.5"|;"1"|;"1"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"|;"web"|;"eba23248-e038-4d33-bc2c-6465ef677d07"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"
"0.9"|;"1"|;"0"|;"642"|;"0"|;"0.5"|;"1"|;"1"|;"5ab3ea80-7428-402f-98ec-04e7cd5327e4"|;"web"|;"eba23248-e038-4d33-bc2c-6465ef677d07"|;"5ab3ea80-7428-402f-98ec-04e7cd5327e4"
"TOTAL"|;"19"
```

Esse resultado indica:

- Judge funcionando;
- prompt tokens extraídos corretamente;
- VLoop sem ocorrência;
- métricas de sessão preenchidas;
- identidade canônica funcionando;
- export legado no layout esperado.

---

## 16. Resumo executivo

O `agent_framework_evaluator` é a camada batch/offline de avaliação do ecossistema `agent_framework_oci`.

Ele consome a telemetria gerada pelo framework, aplica um Judge LLM com regras de avaliação, persiste resultados em Oracle/ADB, gera arquivo e pode republicar scores no Langfuse.

A arquitetura correta separa responsabilidades:

```text
Collector normaliza dados
IdentityResolver resolve identidade
Judge avalia conversa
Repository persiste
Exporter gera legado
API/CLI operam a solução
```

Com isso, o evaluator fica genérico para múltiplos agentes e evita acoplamento direto a formatos específicos de trace ou payload.
