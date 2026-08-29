# Implementação no framework

A evolução adiciona `WorkflowPause` e `WorkflowExpectedInput` ao modelo de workflow e mantém o LangGraph como detalhe interno de `WorkflowRuntime`.

O runtime aceita condições declarativas `all`, `any`, `not`, `eq`, `neq`, `exists`, `path/equals`, `path/not_equals` e `path/in`. Em um nó com `pause`, a action é executada primeiro e a interrupção ocorre em um nó técnico separado. Na retomada, `langgraph.types.Command(resume=...)` injeta o valor esperado e segue para `resume_from` sem repetir a action que precedeu o pause.

`FrameworkStateGraph` é a facade para aplicações que ainda precisam compor um grafo de agentes; templates oficiais devem usar a facade e não importar LangGraph diretamente.

## Preservação de estado em falhas posteriores

O `WorkflowRuntime` também preserva o último snapshot persistido do LangGraph quando uma action posterior falha. O resultado `FAILED` contém `output`, `state` e `trace` dos nodes que já terminaram com sucesso.

Isso é necessário para workflows transacionais: por exemplo, se um protocolo foi criado e uma chamada posterior falha, o chamador ainda recebe o `protocol_number` persistido e pode executar recuperação/idempotência sem repetir o primeiro side effect.

O runtime não transforma falha em sucesso e não reexecuta automaticamente a action; ele apenas preserva a evidência durável já existente no checkpointer.

## Tratamento genérico de entrada fora das opções (`unmatched`)

`expected_input` mantém compatibilidade com o comportamento anterior.
Sem `semantic_classifier`, qualquer entrada que não pertença literalmente a
`allowed_values` permanece no workflow e recebe o `reprompt`.

Quando o agente precisa aceitar linguagem natural, ele declara um prompt
classificatório cujo resultado deve ser uma das próprias opções dinâmicas:

```yaml
expected_input:
  key: resposta_usuario
  allowed_values: [SIM, NAO]
  normalize: upper_strip
  reprompt: "Não entendi. Responda sim ou não."
  semantic_classifier:
    enabled: true
    prompt: |
      Classifique a fala em exatamente uma opção de {{ allowed_values }}.
      Pergunta pendente: {{ pending_prompt }}
      Fala do usuário: {{ user_input }}
      Retorne somente uma opção de {{ allowed_values }}.
```

O framework não possui classes fixas. `allowed_values` pode conter duas, três ou
mais opções; o prompt do agente define a semântica de cada uma. O framework
renderiza os placeholders, chama a LLM e rejeita qualquer saída que não pertença
à allowlist, usando `reprompt` nesse caso. O texto original do usuário é mantido
nos metadados da decisão para auditoria.

Nesse modo, `COER` delega a interpretação semântica ao classificador configurado.
Rails de segurança independentes — por exemplo PINJ, toxicidade, PII e limites
de tamanho — continuam podendo bloquear o turno normalmente.

O exemplo executável está em `agent_template_backend/` e, por compatibilidade
com a estrutura histórica desta feature, também em
`agent_template_backend_pause_resume/`.


### Reentrada contextual por opção

Uma opção do `semantic_classifier` pode declarar `option_actions.<OPCAO>.action: contextual_reentry`. Nesse caso o workflow pausado não é retomado: o framework libera a pausa e reexecuta o roteamento usando somente o contexto conversacional ancorado que originou a decisão mais a fala atual. A fala original é preservada para auditoria e o contexto reconstruído não vira evidência de negócio; parâmetros candidatos continuam sujeitos a validação e confirmação normais.
