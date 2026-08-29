# Pause/Resume Workflow — LangGraph encapsulado pelo Agent Framework OCI

Este exemplo demonstra uma capability genérica do `agent_framework_oci`: workflows determinísticos podem interromper a execução para obter uma resposta do cliente e retomar posteriormente pelo mesmo `execution_id`, sem que o domínio importe ou monte um `StateGraph`.

## Conceito

A aplicação declara o workflow em YAML. `WorkflowRuntime` transforma a definição em LangGraph internamente, utiliza o checkpointer configurado pelo framework e expõe somente:

- `arun(name, payload)` — inicia ou executa o workflow;
- `aresume(name, execution_id, value)` — retoma o workflow pausado;
- `WorkflowRunResult.status` — `PAUSED`, `COMPLETED` ou `FAILED`.

O `pause` é compilado em um nó separado da action anterior. Isto impede que uma action com efeito colateral seja executada novamente quando o cliente responde.

## Executar

A partir da raiz do exemplo, com as dependências do framework instaladas:

```bash
python -m app.demo
pytest -q
```

## YAML

`workflows/confirmacao.v1.yaml` mostra `expected_input`, normalização, valores permitidos e `resume_from`.

## Persistência

O exemplo usa `MemorySaver` apenas para ser autocontido. Em aplicações reais use `create_langgraph_checkpointer(settings)`. Assim `execution_id` é o `thread_id` do LangGraph e a retomada sobrevive a processos/replicas conforme o provider configurado (por exemplo Autonomous Database).

## Regra arquitetural

Código de domínio não deve importar `langgraph.graph.StateGraph`. Para grafos de agentes use `FrameworkStateGraph`; para workflows determinísticos de negócio use `WorkflowRuntime`.

## Entrada enumerada, reprompt e `semantic_classifier`

O contrato `expected_input` pode declarar qualquer conjunto de opções em
`allowed_values`. O match literal continua determinístico; quando a resposta não
coincide literalmente com uma opção, o agente pode habilitar um classificador
semântico com prompt próprio.

```yaml
expected_input:
  key: resposta_usuario
  allowed_values: [SIM, NAO]
  normalize: upper_strip
  reprompt: "Não entendi. Responda sim ou não."
  semantic_classifier:
    enabled: true
    prompt: |
      Classifique {{ user_input }} em exatamente uma opção de {{ allowed_values }}.
      Para este workflow, aceitação/entendimento => SIM; negação, nova pergunta
      ou hipótese factual a validar => NAO.
      Retorne somente uma opção de {{ allowed_values }}.
```

O framework não conhece o significado de `SIM`, `NAO` nem de nenhuma outra
opção. Ele apenas injeta `allowed_values`, `pending_prompt` e `user_input`, chama
a LLM e valida estritamente se a saída pertence à lista declarada. Uma saída
fora da lista usa o `reprompt`.

O mesmo mecanismo funciona sem alteração do framework para, por exemplo,
`[CONFIRMAR, ALTERAR, CANCELAR]` ou qualquer outra lista configurada pelo agente.
O rail `COER` delega a semântica ao `semantic_classifier` nesse modo; PINJ,
toxicidade, PII e os demais rails de segurança continuam independentes.

Há dois diretórios equivalentes para facilitar comparação com os demais
cenários de Tuning-Performance:

- `agent_template_backend/` — nome padrão de template;
- `agent_template_backend_pause_resume/` — nome histórico deste exemplo.

Ambos contêm o mesmo workflow `confirmacao.v1.yaml`.



### Reentrada contextual por opção

Uma opção do `semantic_classifier` pode declarar `option_actions.<OPCAO>.action: contextual_reentry`. Nesse caso o workflow pausado não é retomado: o framework libera a pausa e reexecuta o roteamento usando somente o contexto conversacional ancorado que originou a decisão mais a fala atual. A fala original é preservada para auditoria e o contexto reconstruído não vira evidência de negócio; parâmetros candidatos continuam sujeitos a validação e confirmação normais.
