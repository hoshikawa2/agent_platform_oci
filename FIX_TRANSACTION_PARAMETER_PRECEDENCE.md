# Precedência transacional + extração LLM de parâmetros

Esta correção remove a extração textual hardcoded de parâmetros transacionais e faz a coleta de `policy.requires` por um extrator LLM genérico.

## Regra de precedência

Enquanto existir uma transação ativa, o framework trata o turno nesta ordem:

```text
ACTIVE_TRANSACTION
       |
       +-- COLLECTING_PARAMETERS
       |      |
       |      +-- LLM tenta extrair SOMENTE os parâmetros ainda pendentes
       |      |
       |      +-- extraiu >= 1 ?
       |             |
       |             +-- SIM -> continua a transação; NÃO avalia intent_shift
       |             |
       |             +-- NÃO -> libera EnterpriseRouter para avaliar intent_shift
       |
       +-- AWAITING_CONFIRMATION
              |
              +-- reconhece confirmação/rejeição explícita
              |
              +-- reconheceu ?
                     |
                     +-- SIM -> continua/cancela a transação; NÃO avalia intent_shift
                     |
                     +-- NÃO -> libera EnterpriseRouter para avaliar intent_shift
```

## TransactionParameterExtractor

Novo componente:

`libs/agent_framework/src/agent_framework/runtime/transaction_parameters.py`

A extração textual dos parâmetros de negócio é feita exclusivamente por LLM. O componente recebe:

- nome da tool/transação ativa;
- parâmetros atualmente pendentes;
- argumentos já conhecidos;
- schema/tipos declarados em `tools.yaml` quando disponíveis;
- descrição da tool;
- mensagem atual do usuário.

Ele não conhece nomes de domínio como `order_id`, `reason`, `subject`, `valor`, TIM ou retail. Não há regex de entidades de negócio.

A LLM pode interpretar, por exemplo:

- `PED-1001` quando só há um parâmetro compatível pendente;
- `o pedido é PED-1001`;
- `PED-1001, desisti da compra` preenchendo dois parâmetros no mesmo turno;
- respostas com o nome do parâmetro seguido do valor;
- respostas apenas com o valor, quando semanticamente inequívocas.

Em caso de dúvida, o prompt manda retornar `null`. Uma nova solicitação não deve ser transformada em valor de parâmetro.

## Separação de responsabilidades

`tool_policies.yaml` continua sendo a fonte de verdade para `requires`.

`tools.yaml` pode fornecer tipos via `args_schema` e descrição da tool para melhorar a interpretação sem introduzir código específico de domínio.

`mcp_parameter_mapping.yaml` continua responsável pelos parâmetros auxiliares/contrato MCP. As strategies do mapper são explicitamente excluídas dos campos presentes em `policy.requires`, para não misturar extração MCP com coleta transacional.

O `EnterpriseRouter` usa o mesmo extrator LLM apenas como *probe* de precedência. Se pelo menos um parâmetro pendente for encontrado, o turno permanece no estado transacional. Os valores extraídos são colocados no metadata da decisão e reutilizados pelo runtime, evitando uma segunda chamada LLM no mesmo turno.

## Profile LLM

Foi adicionado aos templates:

```yaml
transaction_parameter_extraction:
  provider: oci_openai
  model: openai.gpt-4.1-mini
  temperature: 0
  max_tokens: 500
  timeout_seconds: 8
```

Generation/component:

- `llm.transaction_parameter_extraction`
- `transaction_parameter_extraction`

## Limpeza de estado

Em `intent_shift`, `transaction_pre_validation` da transação abandonada é removido para não contaminar a nova transação. O resultado de pre-validation continua preservado enquanto pertence à própria transação para auditoria.

## Testes adicionados

`tests/test_transaction_parameter_llm_precedence.py`

Cobertura:

1. dois parâmetros extraídos no mesmo turno;
2. um parâmetro preenchido ganha precedência sobre keyword que indicaria outra intent;
3. nenhum parâmetro encontrado libera `intent_shift`;
4. ausência do antigo `_extract_action_arguments()` hardcoded;
5. confirmação `sim` ganha precedência sobre intent shift.
