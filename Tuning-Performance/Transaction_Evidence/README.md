# Transaction Evidence / Evidência Operacional de Transação

Esta variante demonstra a funcionalidade **Transaction Evidence** do `agent_framework_oci`.
Ela preserva o resultado estruturado de transações executadas no estado/checkpoint do
LangGraph e o reutiliza, quando relevante, em turnos posteriores como evidência
operacional para composição de resposta e groundedness.

> Transaction Evidence **não é Long Term Memory**. É estado operacional associado à
> sessão/workflow e aos recursos envolvidos na transação.

## Problema que resolve

Sem esta funcionalidade, uma transação pode ocorrer corretamente em um turno:

```text
quero cancelar pedido
PED-1001
sim
→ protocolo CANCEL-2026-001
```

mas, no turno seguinte:

```text
quero meu pedido
```

o runtime pode consultar apenas `consultar_pedido`. Se a resposta mencionar o
cancelamento/protocolo visto no turno anterior, o judge de groundedness pode tratar
isso como informação não evidenciada.

Com Transaction Evidence, o resultado transacional confirmado fica estruturado em
`transaction_evidence` e pode aparecer como `relevant_transaction_evidence` quando
correlacionado ao recurso atual.

## Fluxo demonstrado

```text
cancelar_pedido(PED-1001)
        ↓
transação executada
        ↓
transaction_evidence
  - tool_name
  - arguments
  - transaction_id
  - status
  - result/protocolo
        ↓
checkpoint da sessão
        ↓
novo turno: "quero meu pedido"
        ↓
consultar_pedido(PED-1001)
        +
relevant_transaction_evidence(PED-1001)
        ↓
resposta + groundedness com evidência operacional
```

## Regras de segurança e correlação

A implementação do framework:

- registra apenas resultados transacionais efetivamente executados;
- mantém histórico bounded das evidências mais recentes;
- correlaciona por identificadores de recurso, como `order_id`, `invoice_id`,
  `asset_id`, `resource_key` e outros campos `*_id`;
- evita reutilizar evidência de um recurso diferente;
- disponibiliza somente a evidência relevante do turno em
  `relevant_transaction_evidence`;
- expõe a evidência relevante no metadata da resposta para diagnóstico;
- inclui a evidência relevante no contexto usado pelos judges/groundedness.

## Configuração

Não existe uma variável obrigatória `ENABLE_TRANSACTION_EVIDENCE` nesta versão.
A funcionalidade faz parte do runtime transacional do framework e depende da
persistência de estado/checkpoint já usada pelo agente.

Os principais pontos do exemplo são:

- `app/state.py`: campos `transaction_evidence`, `last_transaction_evidence` e
  `relevant_transaction_evidence`;
- `app/workflows/agent_graph.py`: injeta evidência relevante no contexto dos judges;
- `app/main.py`: publica `transaction_evidence` no metadata da resposta;
- framework: `runtime/agent_runtime.py`: grava, correlaciona e materializa a evidência.

## Executar

```bash
cd Tuning-Performance/Transaction_Evidence/agent_template_backend
pip install -e ../../../libs/agent_framework
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Use o frontend normalmente apontando para `http://localhost:8000`.

## Cenário de teste recomendado

Execute na mesma sessão:

```text
quero meu pedido
quero cancelar pedido
PED-1001
sim
quero meu pedido
```

Na última rodada, valide no JSON de resposta:

```json
{
  "route": "orders_agent",
  "intent": "retail_order_tracking",
  "transaction_evidence": [
    {
      "tool_name": "cancelar_pedido",
      "status": "COMPLETED"
    }
  ]
}
```

A estrutura exata do `result` depende da tool transacional, mas o protocolo retornado
pela transação deve estar presente na evidência relevante quando o recurso correlacionar.

## Resultado esperado

No último `quero meu pedido`:

1. a intent deve ser `retail_order_tracking`;
2. `consultar_pedido` deve ser executada normalmente;
3. a evidência da transação anterior de `PED-1001` deve ser recuperada;
4. a resposta pode mencionar o cancelamento/protocolo porque essa informação agora
   está suportada por evidência operacional;
5. o judge de groundedness deve receber essa mesma evidência.

## Diferença para Long Term Memory

| Transaction Evidence | Long Term Memory |
|---|---|
| Estado operacional | Memória semântica/pessoal |
| Resultado de tools/transações | Preferências e fatos duráveis |
| Correlacionado a recursos | Correlacionado ao sujeito |
| Usado para grounding operacional | Usado para personalização/contexto |
| Curto/médio prazo de workflow | Longo prazo entre conversas |

---

## English summary

This variant demonstrates **Transaction Evidence**: executed transactional tool
outcomes are persisted as structured operational evidence in LangGraph state/checkpoint.
On later turns, the runtime correlates prior evidence with the current resource and
exposes it as `relevant_transaction_evidence` to both response composition and
judges/groundedness. It is operational workflow state, not Long Term Memory.

Recommended test sequence:

```text
show my order
cancel my order
PED-1001
yes
show my order
```

On the last turn, verify that the response metadata contains relevant transaction
evidence for the cancellation of `PED-1001`.
