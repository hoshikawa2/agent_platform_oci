# Transaction Pre-Validation / Pré-validação Transacional

Esta variante demonstra a capability genérica de **pré-validação MCP antes da confirmação**.

A regra de negócio continua no MCP. O framework apenas orquestra o contrato genérico:

```text
parâmetros completos
      ↓
MCP validator (read-only / side-effect-free)
      ↓
eligible?
 ├─ false → OUT_OF_SCOPE / NOT_ELIGIBLE → responde sem pedir confirmação
 └─ true  → AWAITING_CONFIRMATION → usuário confirma → tool transacional executa
```

Nenhum LLM adicional é usado pela pré-validação.

## Por que existe

Sem pre-validation, uma aplicação pode pedir confirmação para uma operação que o domínio já
sabe que é inválida. Exemplo: tentar cancelar um pedido já entregue ou contestar uma categoria
que não é elegível para contestação.

O framework **não contém essas regras de negócio**. Ele apenas consulta uma tool MCP declarada
na policy e interpreta o campo genérico `eligible`.

## Policy

`config/tool_policies.yaml`:

```yaml
tool_policies:
  cancelar_pedido:
    operation_type: transactional
    require_confirmation: true
    requires: [order_id]
    pre_validation:
      enabled: true
      tool: validar_cancelamento_pedido
      fail_open: false
```

A tool `validar_cancelamento_pedido` é read-only/internal e deve ser side-effect-free.

## Contrato MCP esperado

Elegível:

```json
{
  "eligible": true,
  "status": "ELIGIBLE",
  "order_id": "PED-1001"
}
```

Não elegível:

```json
{
  "eligible": false,
  "status": "NOT_ELIGIBLE",
  "order_id": "PED-ENTREGUE",
  "reason": "Pedido já entregue não pode ser cancelado por esta operação."
}
```

## Cenário de teste

Suba o Retail MCP de exemplo:

```bash
cd agent_framework_oci/mcp/servers/retail_mcp_server
uvicorn main:app --host 0.0.0.0 --port 8200
```

Em outro terminal:

```bash
cd agent_framework_oci/Tuning-Performance/Transaction_Pre_Validation/agent_template_backend
pip install -e ../../../libs/agent_framework
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Caso elegível

```text
quero cancelar o pedido PED-1001
```

Esperado:

```text
validar_cancelamento_pedido(PED-1001)
→ eligible=true
→ AWAITING_CONFIRMATION
→ nenhuma execução de cancelar_pedido ainda
```

Após `sim`, `cancelar_pedido` é executada.

### Caso não elegível

```text
quero cancelar o pedido PED-ENTREGUE
```

Esperado:

```text
validar_cancelamento_pedido(PED-ENTREGUE)
→ eligible=false
→ OUT_OF_SCOPE
→ NÃO entra em AWAITING_CONFIRMATION
→ cancelar_pedido NÃO é executada
```

## Telemetria

Procure pelos eventos:

- `IC.TRANSACTION_PREVALIDATION_REQUESTED`
- `IC.TRANSACTION_PREVALIDATION_PASSED`
- `IC.TRANSACTION_PREVALIDATION_REJECTED`
- `IC.TRANSACTION_CONFIRMATION_REQUIRED` somente após pre-validation aprovada.

No estado/metadata, `transaction_pre_validation` registra o validator utilizado e o resultado.

## Fail-open x fail-closed

`fail_open: false` é o padrão recomendado para operações sensíveis: se o validator estiver
indisponível, a transação não avança para confirmação.

`fail_open: true` deve ser usado apenas quando o domínio aceitar explicitamente prosseguir sem
a pré-validação.

## Separação de responsabilidades

**Framework**: ordem das etapas, estado, confirmação, idempotência e telemetria.

**MCP/domínio**: regra de elegibilidade, consulta aos sistemas de registro e motivo da rejeição.

A capability é genérica: pode ser usada para cancelamento, contestação, devolução, troca,
suspensão ou qualquer outra operação transacional que possua uma precondição de domínio.

## Rejeição encerra o estado transacional

Quando o validator retorna `eligible: false`, o framework encerra imediatamente o latch transacional. Isso significa que `selected_tool_call`, `pending_tool_call` e `missing_parameters` são limpos, `confirmation_required=false`, `next_state=null` e `transaction_status=OUT_OF_SCOPE`.

O resultado da pré-validação também é propagado no estado/metadata como `transaction_pre_validation`, por exemplo:

```json
{
  "transaction_pre_validation": {
    "tool_name": "contestar_cobranca",
    "validator_tool": "validar_contestacao",
    "eligible": false,
    "status": "OUT_OF_SCOPE",
    "terminal": true
  }
}
```

Assim, o turno seguinte volta ao roteamento normal e não permanece preso em `COLLECTING_*` ou `WAITING_*`. A rejeição não vira `transaction_evidence`, pois a operação de negócio não foi executada.
