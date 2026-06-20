# guardrails.yaml como fonte da verdade

## Problema corrigido

O framework estava instanciando o bundle default de guardrails diretamente dentro de `GuardrailPipeline` e `CustomRails`.
Na prática, isso fazia com que todos os guardrails disponíveis fossem executados mesmo quando `config/guardrails.yaml` declarava apenas alguns rails habilitados.

## Regra atual

Agora a regra é:

```text
Se config/guardrails.yaml existir:
  somente os rails listados e enabled=true serão executados.

Se config/guardrails.yaml não existir:
  o framework mantém o comportamento legado e carrega o bundle default.
```

## Exemplo

```yaml
input:
  - code: MSK
    enabled: true
  - code: VLOOP
    enabled: true

output:
  - code: REVPREC
    enabled: true
```

Com esse arquivo, o input executa apenas `MSK` e `VLOOP`, e o output executa apenas `REVPREC`.
Guardrails como `PINJ`, `TOX`, `DLEX_IN`, `AOFERTA`, `DLEX_OUT`, `CMP` e `RAGSEC` não são instanciados se não estiverem no YAML.

## Guardrail LLM

Quando um rail LLM está habilitado no YAML, ele usa o profile adequado do `llm_profiles.yaml`:

```text
PINJ, TOX, OOS, DLEX_IN, RAGSEC -> profile guardrail
REVPREC, AOFERTA, DLEX_OUT      -> profile grl
```

Se o modelo do profile estiver errado, o erro não deve ser escondido por fallback silencioso.

## Rails conhecidos

Principais códigos aceitos:

```text
INPUT_SIZE
MSK
TOX
PINJ
VLOOP
DLEX_IN
OOS
TOXOUT
CMP
AOFERTA
REVPREC
DLEX_OUT
GND
ALUC_RISK
RET_REL
RAGSEC
TOOL_VAL
```

Também existem aliases de compatibilidade, como `JAILBREAK`, `GROUNDEDNESS`, `HALLUCINATION_RISK`, `TOX_OUT`, `MSK_OUT` e `TOOL_VALIDATION`.
