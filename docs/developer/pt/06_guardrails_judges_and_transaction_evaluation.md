
### Guardrails, Judges e Avaliação Transacional

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **guardrails nativos/externos, judges, sampling transacional e grounding**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

Guardrails nativos/externos, judges, sampling transacional e grounding.

### Conteúdo técnico consolidado

### Guardrails, Judges e Avaliação Transacional

Manual para guardrails de entrada/saída, extensões específicas por agente, judges externos, execução obrigatória em transações e sinais/evidências usados na avaliação.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### Guardrails implementados no framework

> Conteúdo consolidado a partir de `Documentacao/README_GUARDRAILS_IMPLEMENTADOS.md`.

Esta versão adiciona uma camada pragmática de guardrails ao `agent_framework`, inspirada na separação de rails por estágio: input, output, retrieval e execução/tool.

### Rails de input

- `MSIZE` — bloqueia mensagens excessivamente grandes.
- `MSK` — mascara CPF, CNPJ, telefone, e-mail, cartão, CEP, RG, tokens e chaves.
- `TOX` — detecta toxicidade e registra severidade sem bloquear por padrão.
- `PINJ` — detecta prompt injection e registra score.
- `JBRK` — detecta jailbreak/roleplay de burla e registra score.
- `VLOOP` — bloqueia loop conversacional repetitivo.

### Rails de output

- `PII_OUT` — mascara PII na resposta do agente.
- `CMP` — suaviza promessas absolutas e linguagem de garantia excessiva.
- `REVPREC` — bloqueia verbalização de ação operacional sem confirmação de tool.
- `GND` — sinaliza groundedness/risco quando há resposta específica sem evidência.
- `ALUC_RISK` — marca risco de alucinação para telemetria e judges.

### Rails opcionais

- `RET_REL` — valida relevância de chunks de retrieval por score mínimo.
- `TOOL_VAL` — valida ferramenta MCP/tool, argumentos obrigatórios, valores negativos e allowlist.

### Contrato para protocolos autorizados em guardrails de saída

Quando um workflow ou tool produz um **protocolo que deve ser exibido ao próprio cliente**, o código de integração do agente deve registrar esse valor no contexto de saída antes da execução dos guardrails:

```python
ctx["expected_protocols"] = [protocol_number]
```

Esse campo é um **contrato do framework**. Ele informa que aqueles valores específicos foram produzidos ou validados pelo fluxo atual e, portanto, podem ser usados pelos guardrails de saída como evidência de autorização.

Fluxo esperado:

```text
workflow/tool gera protocolo
        ↓
agente registra em expected_protocols
        ↓
CMP valida que o protocolo exibido pertence aos valores esperados
        ↓
DLEX_OUT não bloqueia esse protocolo apenas por classificá-lo como identificador
        ↓
resposta pode informar o protocolo ao cliente
```

Regras importantes:

- `expected_protocols` deve conter **somente protocolos realmente produzidos/esperados no turno ou transação atual**.
- Não use `expected_protocols` para liberar tokens, credenciais, IDs internos arbitrários ou dados de terceiros.
- A autorização vale somente para os valores listados; outro identificador continua sujeito às regras normais de `DLEX_OUT`.
- O valor deve ser propagado **antes de `output_guardrails`**. Se o protocolo só for adicionado depois, a autorização não terá efeito.
- Em respostas transacionais, mantenha a evidência do protocolo no resultado da tool/workflow para que `CMP`, `GND` e observabilidade consigam correlacionar o valor.

Exemplo:

```python
result = await executar_workflow(...)
protocol_number = result.get("protocol_number") or result.get("protocolo_id")
if protocol_number:
    ctx["expected_protocols"] = [str(protocol_number)]
```

#### Troubleshooting: workflow concluiu, mas a resposta foi substituída por mensagem de segurança

Sintoma típico:

```text
workflow = COMPLETED
CMP = allowed
DLEX_OUT = blocked por "protocolo interno"
resposta final = "Não consegui validar essa resposta com segurança..."
```

Verifique, nesta ordem:

1. O protocolo gerado está presente no resultado/evidência da tool ou workflow?
2. O agente propagou o mesmo valor em `ctx["expected_protocols"]`?
3. `expected_protocols` foi preenchido antes de `output_guardrails`?
4. O protocolo presente na resposta é exatamente um dos valores esperados?
5. O `DLEX_OUT` está bloqueando por outro motivo real, como segredo, token ou dado de terceiro?

Se `expected_protocols` estiver ausente, o framework não deve presumir que qualquer identificador textual é seguro para divulgação.


### Arquivos alterados

- `agent_framework/src/agent_framework/guardrails/rails.py`
- `agent_framework/src/agent_framework/guardrails/pipeline.py`
- `agent_framework/src/agent_framework/guardrails/__init__.py`

### Uso rápido

```python
from agent_framework.guardrails.pipeline import GuardrailPipeline

pipeline = GuardrailPipeline()

sanitized_input, input_decisions = await pipeline.run_input(
    user_text,
    {"history_texts": history_texts},
)

final_answer, output_decisions = await pipeline.run_output(
    answer,
    context,
)
```

Para tools/MCP:

```python
_, decisions = await pipeline.run_tool(
    "cancelar_produto",
    {"produto": "VAS", "valor": 0},
    {
        "required_args": ["produto"],
        "allowed_tools": ["cancelar_produto", "consultar_fatura"],
    },
)
```

### SPI de guardrails e judges externos

> Conteúdo consolidado a partir de `docs/EXTERNAL_GUARDRAILS_JUDGES.md`.

`agent_framework_oci` supports agent-owned guardrails and judges without importing domain code into the core.

```yaml
output:
  - code: ACME_POLICY
    type: external
    class: app.extensions.guardrails:AcmePolicyRail
```

```yaml
judges:
  - name: acme_quality
    type: external
    class: app.extensions.judges:AcmeQualityJudge
    threshold: 0.7
```

Native entries remain unchanged. External synchronous `evaluate()` methods execute in worker threads via `asyncio.to_thread`; asynchronous methods execute concurrently on the framework event loop. Judges run concurrently with `asyncio.gather`, preserving YAML result order. Agent plugins should reuse the LLM supplied by the framework rather than instantiate a separate provider.

The core must not reference a concrete agent package, company, product, telecom identifier or domain-specific policy. Domain-specific variants belong to the agent and should receive distinct public codes/names.

### Compatibility rule
Domain policies must not be replaced by cosmetically generic text inside the core while losing the original policy. The generic core implementation and the agent-specific implementation may coexist; the embedding agent explicitly selects its own code/name in YAML.

Legacy business validators should migrate to the agent domain. A temporary compatibility shim is acceptable for old imports, but new application code must import the agent-owned implementation.

### Execução obrigatória de judges em transações

> Conteúdo consolidado a partir de `docs/JUDGES_TRANSACTIONAL_SAMPLING_FIX.md`.

### Problema

Mesmo com `always_run_for_transactional: true`, os judges podiam ser ignorados
pela amostragem porque o nó `judge` enviava apenas `context`, `route`, `intent` e
`mcp_results`. Os campos transacionais produzidos pelo runtime não chegavam ao
`JudgePipeline`.

### Correção

O nó `judge` agora repassa:

- `transaction_status`
- `confirmation_required`
- `confirmation_received`
- `tool_policy_result`
- `selected_tool_call`
- `pending_tool_call`
- `mcp_results` como evidência

O `JudgePipeline` detecta transações por múltiplos sinais e avalia
`always_run_for_transactional` antes de aplicar `sample_rate`.

Com a configuração abaixo, consultas comuns continuam sendo amostradas em 25%,
mas turnos `AWAITING_CONFIRMATION`, `COMPLETED`, `FAILED` ou `CANCELLED` executam
os judges sempre.

```yaml
enabled: true
sample_rate: 0.25
always_run_for_transactional: true
```

### Validação do Global Supervisor

> Conteúdo consolidado a partir de `docs/docs_GLOBAL_SUPERVISOR_VALIDATION.txt`.

VALIDAÇÃO - GLOBAL SUPERVISOR

Alterações implementadas:

1. Framework
- agent_framework.global_supervisor.models
- agent_framework.global_supervisor.config
- agent_framework.global_supervisor.session_store
- agent_framework.global_supervisor.router
- agent_framework.global_supervisor.client

2. Novo serviço
- agent_gateway/app/main.py
- agent_gateway/app/settings.py
- agent_gateway/config/backends.yaml
- agent_gateway/README.md
- agent_gateway/Dockerfile
- agent_gateway/docs/ARQUITETURA_GLOBAL_SUPERVISOR.md

3. Docker Compose
- serviço agent-gateway adicionado na porta 8010.

Validações executadas:

- python3 -m compileall -q agent_framework/src/agent_framework/global_supervisor agent_gateway/app
  Resultado: OK

- Smoke test do roteamento híbrido:
  Entrada 1: "Minha fatura veio alta" -> contas
  Entrada 2: "e esse valor?" na mesma session_id -> contas por active_backend
  Resultado: OK

- Smoke test de import do app FastAPI:
  from app.main import app, registry, router
  Resultado: OK

Observação:
- O proxy SSE do gateway foi deixado como etapa futura. O endpoint /gateway/message/sse já roteia e encaminha como mensagem normal; para SSE fim-a-fim, pode-se implementar proxy de /gateway/events/{session_id} para o backend ativo.

### Validação de eventos de guardrail

> Conteúdo consolidado a partir de `docs/docs_VALIDATION_GUARDRAILS_IC.txt`.

VALIDATION REPORT - guardrails parallel fail-fast + observer IC
Date: 2026-06-03

compileall: OK
smoke-tests: OK

### Arquivos de origem

Os arquivos abaixo foram consolidados neste manual:

- `Documentacao/README_GUARDRAILS_IMPLEMENTADOS.md`
- `docs/EXTERNAL_GUARDRAILS_JUDGES.md`
- `docs/JUDGES_TRANSACTIONAL_SAMPLING_FIX.md`
- `docs/docs_GLOBAL_SUPERVISOR_VALIDATION.txt`
- `docs/docs_VALIDATION_GUARDRAILS_IC.txt`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.
