# agent_framework_evaluator

## 1. What is the `agent_framework_evaluator`?

The `agent_framework_evaluator` is a complementary service to the `agent_framework_oci` created to evaluate real conversations conducted by the framework's agents.

It collects conversations from a source, usually Langfuse, reconstructs the context of the interaction, runs a Judge LLM, writes the results to an Oracle/ADB database, generates legacy files in TXT.GZ format, and optionally publishes scores back to Langfuse.

In simple terms:

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

The evaluator does not replace the guardrails, online judges, or telemetry of `agent_framework_oci`. It acts as an offline/batch layer for evaluation, auditing, and export.

---

## 2. Purpose of the solution

The purpose of the evaluator is to allow conversations that have already taken place to be analyzed later using standardized criteria.

It mainly serves these scenarios:

- daily evaluation of conversations by agent;
- generation of legacy evaluation files;
- auditing the quality of responses;
- identification of hallucination, low accuracy, low resolution or poor customer experience;
- comparison between agents such as `telecom_contas`, `retail_orders` and `financeiro_agent`;
- optional publication of scores on Langfuse;
- persistence of evaluation history in Oracle/ADB;
- progress tracking via API or CLI.

---

## 3. How it integrates with `agent_framework_oci`

`agent_framework_oci` is the main runtime for agents. It executes the conversational flow with LangGraph, supervisor, guardrails, judges, MCP tools, memory, RAG, and telemetry.

During execution, the framework publishes traces to Langfuse containing:

- `trace_id`;
- `session_id`;
- `message_id`;
- `agent_id`;
- `channel`;
- canonical `business_context`;
- IC/NOC/GRL events;
- LangGraph spans;
- guardrail spans;
- judge spans;
- LLM generations;
- model usage, when available;
- `prompt_tokens`, `completion_tokens` and `total_tokens`, when returned by the provider;
- `input_size`, when emitted by the framework spans.

The evaluator uses this telemetry as a data source.

The main integration happens like this:

```text
agent_framework_oci
├── Executes agents
├── Resolves identity via identity.yaml
├── Creates canonical BusinessContext
├── Calls MCP/RAG/LLM
├── Emits Langfuse telemetry
└── Writes usage/model/tokens when available

agent_framework_evaluator
├── Reads traces in Langfuse
├── Applies identity.yaml to normalize identity
├── Rebuilds ConversationRecord
├── Executes LLM Judge offline
├── Writes results to Oracle/ADB
├── Exports legacy TXT.GZ
└── Optionally publish scores on Langfuse
```

---

## 4. General architecture

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
| TXT.GZ legacy          |
| API dashboard          |
| Langfuse scores        |
+------------------------+
```

---

## 5. Solution components

### 5.1 CLI

Main file:

```text
evaluator/cli.py
```

Responsible for exposing commands such as:

```bash
python -m evaluator.cli init-db
python -m evaluator.cli show-config
python -m evaluator.cli run --source langfuse
python -m evaluator.cli run-agents --source langfuse
python -m evaluator.cli runs
python -m evaluator.cli progress <run_id>
```

The CLI is the main way to operate the evaluator in batch mode.

---

### 5.2 API

Main file:

```text
evaluator/api/main.py
```

Exposes HTTP endpoints to query progress, runs, and results.

Expected examples:

```text
GET /health
GET /runs
GET /runs/{run_id}/progress
GET /runs/{run_id}/results
GET /runs/{run_id}/findings
```

The API allows you to build a simple graphical interface or integrate the evaluator with other systems.

---

### 5.3 EvaluationEngine

Main file:

```text
evaluator/engine.py
```

It is the central orchestrator of the evaluator.

Responsibilities:

1. create a new evaluation run (`EVALUATION_RUN`);
2. choose the collector according to the `source`;
3. collect conversations;
4. apply sampling by agent;
5. insert items into `EVALUATION_ITEM`;
6. process each item;
7. call the LLM Judge;
8. save trace result;
9. run session evaluation;
10. save session result;
11. export legacy file;
12. mark final execution status;
13. issue progress events.

Simplified flow:

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

Directory:

```text
evaluator/collectors/
```

Collectors are responsible for fetching conversations from an external source and converting them to `ConversationRecord`.

Typical collectors:

```text
evaluator/collectors/langfuse.py
evaluator/collectors/agent_framework.py
evaluator/collectors/mock.py
evaluator/collectors/base.py
```

#### LangfuseCollector

This is the main collector.

Responsibilities:

- search for traces in Langfuse;
- filter by period;
- filter by agent/alias;
- retrieve trace details;
- extract input/output;
- reconstruct messages;
- collect metadata;
- apply `identity.yaml`;
- assemble canonical `BusinessContext`;
- fill in `ConversationRecord`.

The collector must normalize data so that the exporter does not need to know Langfuse's internal details.

---

### 5.5 Identity Resolver

Recommended directory:

```text
evaluator/identity/
```

Main file:

```text
evaluator/identity/resolver.py
```

The evaluator must use the same identity concept as `agent_framework_oci`, based on the file:

```text
configs/identity.yaml
```

The function of `identity.yaml` is to map variable input fields to a canonical model:

```text
customer_key
contract_key
interaction_key
account_key
resource_key
session_key
```

Conceptual example:

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

With this, the evaluator is not directly tied to fields such as `ura_call_id`, `call_id`, `message_id` or `interaction_key`. It resolves everything to `interaction_key`.

---

### 5.6 Models

Main file:

```text
evaluator/core/models.py
```

Defines the core objects of the evaluator.

Main models:

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

Represents an evaluated conversation or turn.

Common fields:

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

The `metadata` field must contain normalized data:

```text
business_context
uraCallId
channelId
messageId
promptLength
```

The `raw` field keeps the original payload for auditing and fallback.

---

### 5.7 LLM Judge

Main file:

```text
evaluator/judges/llm_judge.py
```

Main class:

```python
TIMStyleLLMJudge
```

Responsibilities:

- load evaluation prompts;
- set up trace prompt;
- set up session prompt;
- call LLM via configured client;
- interpret JSON response;
- return `TraceJudgeResult` and `SessionJudgeResult`.

The judge evaluates metrics such as:

```text
judgeScore
accuracyScore
alucinationScore
inferredCsiScore
resolution
conversationPrecision
rationale
```

The judge must be LLM-based, not deterministic.

---

### 5.8 Prompts

Directory:

```text
evaluator/prompts/
```

Expected files:

```text
trace_judge_prompt.md
session_judge_prompt.md
loader.py
```

The trace prompt evaluates an individual response.

The session prompt evaluates the conversation grouped by `session_id`.

Example of expected LLM output for trace:

```json
{
  "judgeScore": 0.8,
  "accuracyScore": 0.9,
  "alucinationScore": 0.1,
  "rationale": "A response that is relevant to the context and based on available data."
}
```

Example of expected output for session:

```json
{
  "inferredCsiScore": 0.5,
  "resolution": 1,
  "conversationPrecision": 1,
  "rationale": "The conversation was resolved with consistent information."
}
```

---

### 5.9 LLM Client

Directory:

```text
evaluator/llm/
```

Typical files:

```text
evaluator/llm/client.py
evaluator/llm/oci_openai.py
```

The evaluator must use the same LLM access pattern as `agent_framework_oci`, preferably via the `oci_openai` provider.

Common variables:

```env
LLM_PROVIDER=oci_openai
OCI_GENAI_ENDPOINT=...
OCI_GENAI_MODEL_ID=...
OCI_GENAI_API_KEY=...
OCI_GENAI_COMPARTMENT_ID=...
```

The client needs to return raw text for the Judge to interpret as JSON.

---

### 5.10 Repository / Oracle Store

Directory:

```text
evaluator/persistence/
```

Main files:

```text
evaluator/persistence/oracle_store.py
evaluator/persistence/repository.py
```

`OracleStore` takes care of:

- connection with ADB/Oracle;
- wallet;
- DSN;
- schema creation/adjustment;
- thread-safe execution for asynchronous calls;
- table prefix.

The `EvaluationRepository` takes care of:

- creating runs;
- recording progress;
- inserting items;
- search for next items;
- marking an item as `PROCESSING`, `COMPLETED` or `FAILED`;
- save results;
- save findings;
- summarize run;
- list runs;
- check progress.

---

### 5.11 Legacy Exporter

Main file:

```text
evaluator/output/legacy_exporter.py
```

Generates the legacy file:

```text
output/AGENTE_<agent_id>_LLM_JUDGE_YYYYMMDD.TXT.GZ
```

Column format:

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

Example:

```text
"0.8"|;"0.9"|;"0.1"|;"732"|;"0"|;"0.5"|;"1"|;"1"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"|;"web"|;"eba23248-e038-4d33-bc2c-6465ef677d07"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"
"TOTAL"|;"19"
```

#### promptLength

The `promptLength` field must use this priority:

1. `prompt_tokens`/ `promptTokens` /`input_tokens`/ `inputTokens` in Langfuse observations;
2. `usage.input` or `usageDetails.input`;
3. `metadata.input_size` issued by the framework;
4. fallback for text size of `input_text`, `output_text`, and `messages`.

Example:

```text
promptLength = 732
```

#### loop

The `loop field` uses the VLoop detector.

```text
0 = sem loop detectado
1 = loop detectado
```

---

### 5.12 VLoop Analytics

Main file:

```text
evaluator/analytics/vloop.py
```

Responsible for detecting conversational repetition/loop in a pattern similar to the VLoop guardrail of `agent_framework_oci`.

The function normally exposed is:

```python
vloop_flag(raw) -> int
```

It returns:

```text
0 when there is no evidence of a loop
1 when there is suspected repetition
```

---

### 5.13 Langfuse Score Publisher

Main file:

```text
evaluator/publishers/langfuse_scores.py
```

Responsible for publishing evaluation scores back to Langfuse, when enabled.

Control variable:

```env
PUBLISH_LANGFUSE_SCORES=true
```

When disabled, the evaluator only writes to the database and exports the file.

---

## 6. Directory structure

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

## 7. Configuration

### 7.1 `.env file`

Example:

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

### 7.2 Agent configuration

File:

```text
configs/judge/agents.yaml
```

Example:

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

The `aliases` field is important because Langfuse can register the agent in different ways, for example:

```text
agent_id = telecom_contas
route = financeiro_agent
agent = financeiro_agent
```

---

### 7.3 Identity configuration

File:

```text
configs/identity.yaml
```

The evaluator must use the same pattern as the framework.

Example:

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

The `interaction_key` field is used to populate the `uraCallId` in the legacy export.

---

## 8. How to run

### 8.1 Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

If you are using Conda:

```bash
conda activate py313
pip install -e .
```

---

### 8.2 Validate configuration

```bash
python -m evaluator.cli show-config
```

Expected output:

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

### 8.3 Create/validate schema

```bash
python -m evaluator.cli init-db
```

Expected output:

```text
{'status': 'OK', 'message': 'Evaluator schema checked/created successfully.'}
```

---

### 8.4 Run evaluation by period

```bash
python -m evaluator.cli run \
  --period-start 2026-06-11T00:00:00 \
  --period-end 2026-06-12T00:00:00 \
  --source langfuse
```

---

### 8.5 Run evaluation by configured agents

```bash
python -m evaluator.cli run-agents --source langfuse
```

Expected output:

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

### 8.6 Check progress

```bash
python -m evaluator.cli progress <run_id>
```

Or via API:

```bash
curl http://localhost:8001/runs/<run_id>/progress
```

---

### 8.7 View exported file

```bash
gzip -cd output/AGENTE_telecom_contas_LLM_JUDGE_20260612.TXT.GZ
```

Example of a valid line:

```text
"0.8"|;"0.9"|;"0.1"|;"732"|;"0"|;"0.5"|;"1"|;"1"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"|;"web"|;"eba23248-e038-4d33-bc2c-6465ef677d07"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"
"TOTAL"|;"19"
```

---

## 9. Database

### 9.1 Main tables

#### EVALUATION_RUN

Stores an evaluation run.

Main fields:

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

Stores each conversation/turn collected.

Main fields:

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

Stores trace and session results.

Main fields:

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

`JUDGE_TYPE` can be:

```text
TRACE
SESSION
```

---

#### EVALUATION_PROGRESS_EVENT

Stores execution progress events.

Stage examples:

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

## 10. How the codes work together

### 10.1 Complete execution flow

```text
CLI run-agents
  ↓
load configs/judge/agents.yaml
  ↓
for each enabled agent
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

### 10.2 Role of the collector

The collector is responsible for transforming external data into canonical data.

It must hide differences between sources such as:

```text
Langfuse
agent_framework database
mock data
```

The output must always be:

```python
ConversationRecord
```

---

### 10.3 Role of the judge

The judge receives a `ConversationRecord`, assembles a prompt, and calls the LLM.

It should not know about Oracle, Langfuse, legacy export, or API.

It only evaluates.

---

### 10.4 Role of the repository

The repository is the persistence layer.

It must not contain an evaluation business rule.

It only writes, retrieves, and updates data.

---

### 10.5 Role of the exporter

The exporter transforms persisted data into a legacy file.

It should not resolve identity in a complex way.

Ideally, it should read fields that are already normalized:

```text
metadata.business_context.interaction_key
metadata.channelId
metadata.messageId
metadata.promptLength
```

However, for resilience, it can also query `RAW_JSON` as a fallback.

---

## 11. Important design rules

### 11.1 The evaluator must not be anchored to an agent

Avoid logic like:

```python
if agent_id == "telecom_contas":
    ura_call_id = metadata["ura_call_id"]
```

The correct thing to do is to use `identity.yaml`.

---

### 11.2 The exporter must not know internal details of Langfuse

Avoid excessive coupling to paths such as:

```text
raw.detail.observations[0].metadata.ura_call_id
raw.trace.input.business_context.interaction_key
```

This should be resolved in the collector.

---

### 11.3 `promptLength` should come from tokens when possible

Recommended priority:

```text
1. prompt_tokens / promptTokens
2. input_tokens / inputTokens
3. usage.input / usageDetails.input
4. metadata.input_size
5. tamanho textual de input/output/messages
```

---

### 11.4 `uraCallId` must come from BusinessContext

The legacy field `uraCallId` must be mapped to:

```text
business_context.interaction_key
```

This is the canonical name of the framework.

---

### 11.5 `sessionId` must come from BusinessContext

The legacy `sessionId` field must be mapped to:

```text
business_context.session_key
```

Not to be confused with the full composite key:

```text
default:telecom_contas:<uuid>
```

The evaluator can store the full key, but the legacy export should normally use the clean session identifier.

---

## 12. Recommended tests

### 12.1 Configuration test

```bash
python -m evaluator.cli show-config
```

Validate:

```text
ADB_DSN
Wallet
Langfuse enabled
LLM provider
Agents config
Identity config
```

---

### 12.2 Database test

```bash
python -m evaluator.cli init-db
```

Then validate tables:

```sql
select table_name
from user_tables
where table_name like 'AGENTFW_EVALUATION%';
```

---

### 12.3 Mock test

```bash
python -m evaluator.cli run --source mock
```

Use this test to validate schema, judge, and export without relying on Langfuse.

---

### 12.4 Test with Langfuse

```bash
python -m evaluator.cli run-agents --source langfuse
```

Validate:

```text
total_items > 0
completed_items > 0
failed_items = 0
evaluations > 0
output_file preenchido
```

---

### 12.5 Export test

```bash
gzip -cd output/AGENTE_telecom_contas_LLM_JUDGE_YYYYMMDD.TXT.GZ
```

Validate columns:

```text
judgeScore            filled in
accuracyScore         filled in
hallucinationScore    filled in
promptLength          greater than 0
loop                  0 or 1
inferredCsiScore      filled in
resolution            0 or 1
conversationPrecision 0 or 1
uraCallId             filled in
channelId             filled in
sessionId             filled in
messageId             filled in
```

---

## 13. Troubleshooting

### 13.1 `promptLength` outputs 0

Common causes:

- `find_prompt_tokens` was not included in the file;
- `promptTokens` is zeroed in Langfuse;
- `input_size` is not being traversed;
- `RAW_JSON` is coming as an unconverted string;
- old exporter is still running;
- `except Exception: pass` is masking error.

Recommended debug:

```python
print("PROMPT_LENGTH", extract_prompt_length(raw))
print("RAW_TYPE", type(raw))
print("RAW_KEYS", list(raw.keys())[:20])
```

---

### 13.2 `uraCallId` comes out empty

Common causes:

- `identity.yaml` is not being loaded;
- collector is not copying `business_context` to `metadata`;
- `interaction_key` does not exist in the trace;
- exporter does not use `business_context.interaction_key`.

Validation:

```sql
select RAW_JSON
from AGENTFW_EVALUATION_ITEM
where MESSAGE_ID = '<message_id>';
```

Search:

```text
interaction_key
ura_call_id
business_context
```

---

### 13.3 `ORA-00904 invalid identifier`

Usually indicates an old schema.

Examples already found:

```text
ORA-00904: UPDATED_AT invalid identifier
ORA-00904: REASONING invalid identifier
ORA-00904: JUDGE_TYPE invalid identifier
```

Correction:

```bash
python -m evaluator.cli init-db
```

If the table already exists without the new column,`_init_schema` needs to run `ALTER TABLE ADD` in an idempotent manner.

---

### 13.4 `ORA-00054 resource busy`

Indicates a lock on the table.

Common causes:

- API running while `init-db` tries to change schema;
- another process using the table;
- transaction open in SQL Developer.

Correction:

1. stop API/CLI;
2. close open sessions;
3. run `init-db` again.

---

### 13.5 `OCI LLM 401`

Indicates an authentication problem in the LLM.

Validate:

```env
OCI_GENAI_ENDPOINT
OCI_GENAI_MODEL_ID
OCI_GENAI_API_KEY
OCI_GENAI_COMPARTMENT_ID
```

Also confirm that the evaluator is reading the correct `.env`:

```bash
python -m evaluator.cli show-config
```

---

### 13.6 `Entity with key ${OCI_GENAI_MODEL_ID} not found`

Indicates that the literal value `${OCI_GENAI_MODEL_ID}` has reached the provider.

Common causes:

- variable not expanded;
- YAML using `${OCI_GENAI_MODEL_ID}` without interpolation;
- `.env` not loaded;
- LLM client configuration does not resolve placeholders.

Correction:

- put the real model ID in `the .env`;
- ensure interpolation in `settings.py`;
- validate with `show-config`.

---

## 14. Final validation checklist

Before considering the evaluator ready, validate:

```text
[ ] init-db executes without error
[ ] show-config displays correct .env file
[ ] Langfuse returns traces
[ ] run-agents collects items per agent
[ ] LLM Judge responds with valid JSON
[ ] EVALUATION_RESULT records TRACE and SESSION data
[ ] progress displays useful events
[ ] export TXT.GZ is generated
[ ] promptLength > 0
[ ] uraCallId populated
[ ] sessionId populated
[ ] messageId populated
[ ] loop populated with 0 or 1
[ ] file ends with TOTAL
[ ] scores can be published to Langfuse when enabled
```

---

## 15. Example of validated final result

```text
"0.8"|;"0.9"|;"0.1"|;"732"|;"0"|;"0.5"|;"1"|;"1"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"|;"web"|;"eba23248-e038-4d33-bc2c-6465ef677d07"|;"6d7e85b0-ddd0-4f23-a372-30e754a4491a"
"0.9"|;"1"|;"0"|;"642"|;"0"|;"0.5"|;"1"|;"1"|;"5ab3ea80-7428-402f-98ec-04e7cd5327e4"|;"web"|;"eba23248-e038-4d33-bc2c-6465ef677d07"|;"5ab3ea80-7428-402f-98ec-04e7cd5327e4"
"TOTAL"|;"19"
```

This result indicates:

- Judge working;
- prompt tokens extracted correctly;
- VLoop without occurrence;
- session metrics filled in;
- canonical identity working;
- legacy export in the expected layout.

---

## 16. Executive summary

The `agent_framework_evaluator` is the batch/offline evaluation layer of the `agent_framework_oci` ecosystem.

It consumes the telemetry generated by the framework, applies a Judge LLM with evaluation rules, persists results in Oracle/ADB, generates a file, and can republish scores in Langfuse.

The correct architecture separates responsibilities:

```text
Collector normalizes data. 
IdentityResolver resolves identity. 
Judge evaluates conversation. 
Repository persists data. 
Exporter generates legacy data. 
API/CLI operate the solution.
```

This makes the evaluator generic for multiple agents and avoids direct coupling to specific trace or payload formats.
