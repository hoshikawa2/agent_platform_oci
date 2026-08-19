# Implementação no framework

A evolução adiciona `WorkflowPause` e `WorkflowExpectedInput` ao modelo de workflow e mantém o LangGraph como detalhe interno de `WorkflowRuntime`.

O runtime aceita condições declarativas `all`, `any`, `not`, `eq`, `neq`, `exists`, `path/equals`, `path/not_equals` e `path/in`. Em um nó com `pause`, a action é executada primeiro e a interrupção ocorre em um nó técnico separado. Na retomada, `langgraph.types.Command(resume=...)` injeta o valor esperado e segue para `resume_from` sem repetir a action que precedeu o pause.

`FrameworkStateGraph` é a facade para aplicações que ainda precisam compor um grafo de agentes; templates oficiais devem usar a facade e não importar LangGraph diretamente.

## Preservação de estado em falhas posteriores

O `WorkflowRuntime` também preserva o último snapshot persistido do LangGraph quando uma action posterior falha. O resultado `FAILED` contém `output`, `state` e `trace` dos nodes que já terminaram com sucesso.

Isso é necessário para workflows transacionais: por exemplo, se um protocolo foi criado e uma chamada posterior falha, o chamador ainda recebe o `protocol_number` persistido e pode executar recuperação/idempotência sem repetir o primeiro side effect.

O runtime não transforma falha em sucesso e não reexecuta automaticamente a action; ele apenas preserva a evidência durável já existente no checkpointer.
