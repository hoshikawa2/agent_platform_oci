# Guardrails implementados no framework

Esta versão adiciona uma camada pragmática de guardrails ao `agent_framework`, inspirada na separação de rails por estágio: input, output, retrieval e execução/tool.

## Rails de input

- `MSIZE` — bloqueia mensagens excessivamente grandes.
- `MSK` — mascara CPF, CNPJ, telefone, e-mail, cartão, CEP, RG, tokens e chaves.
- `TOX` — detecta toxicidade e registra severidade sem bloquear por padrão.
- `PINJ` — detecta prompt injection e registra score.
- `JBRK` — detecta jailbreak/roleplay de burla e registra score.
- `VLOOP` — bloqueia loop conversacional repetitivo.

## Rails de output

- `PII_OUT` — mascara PII na resposta do agente.
- `CMP` — suaviza promessas absolutas e linguagem de garantia excessiva.
- `REVPREC` — bloqueia verbalização de ação operacional sem confirmação de tool.
- `GND` — sinaliza groundedness/risco quando há resposta específica sem evidência.
- `ALUC_RISK` — marca risco de alucinação para telemetria e judges.

## Rails opcionais

- `RET_REL` — valida relevância de chunks de retrieval por score mínimo.
- `TOOL_VAL` — valida ferramenta MCP/tool, argumentos obrigatórios, valores negativos e allowlist.

## Arquivos alterados

- `agent_framework/src/agent_framework/guardrails/rails.py`
- `agent_framework/src/agent_framework/guardrails/pipeline.py`
- `agent_framework/src/agent_framework/guardrails/__init__.py`

## Uso rápido

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
