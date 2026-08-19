# Workflow Error Recovery

O `WorkflowRuntime` preserva o último snapshot válido do LangGraph e, nesta versão, também expõe `error_details` estruturado quando a exceção externa oferece campos como `status_code`, `body` e `attempts`.

Isso permite que o domínio diferencie erro técnico de erro de negócio sem acoplar o framework ao provider. O framework continua responsável por runtime/checkpoint/trace; o domínio interpreta apenas o contrato do seu provider.

Exemplo conceitual:

```python
result = await runtime.arun("workflow_transacional", payload)
if result.status == "FAILED":
    print(result.output)         # nodes concluídos antes da falha
    print(result.trace)          # trace parcial
    print(result.error)          # mensagem humana/técnica
    print(result.error_details)  # status/body/attempts se disponíveis
```
