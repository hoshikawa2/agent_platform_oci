# LLM Rich Response (`ainvoke_response`)

## Objetivo

O framework mantém `ainvoke()` como API retrocompatível, retornando apenas `str`, e adiciona `ainvoke_response()` para consumidores que precisam de metadados adicionais da inferência, incluindo `reasoning_content` quando o modelo/provider/API o disponibilizar.

## APIs

### API legada — sem alteração

```python
answer = await llm.ainvoke(messages)
assert isinstance(answer, str)
```

Nenhum agente existente precisa ser alterado.

### Nova API rica — opt-in

```python
response = await llm.ainvoke_response(messages)

answer = response.content
reasoning = response.reasoning_content
usage = response.usage
model = response.model
provider = response.provider
```

`reasoning_content` é `str | None`. `None` é o comportamento esperado quando o modelo, provider ou API não expõe reasoning textual.

## Backoffice

Um consumidor que antes fazia:

```python
answer = await llm.ainvoke(messages)
template = extract_response(answer)
```

pode passar a fazer:

```python
response = await llm.ainvoke_response(messages)
template = extract_response(response.content)
reasoning_content = response.reasoning_content
```

A lógica que espera texto continua recebendo `response.content`; o reasoning fica separado e não contamina resposta, cache, memória, judges ou guardrails.

## Compatibilidade de providers customizados

`LLMProvider.ainvoke_response()` possui fallback. Um provider externo que implemente apenas `ainvoke()` continua funcionando e recebe automaticamente um `LLMResponse(content=<texto>)`, com `reasoning_content=None`.

Providers nativos (`mock`, OpenAI-compatible/OCI OpenAI e OCI SDK) implementam a resposta rica e tentam preservar reasoning quando presente.

## Garantias de compatibilidade

- `ainvoke()` continua retornando `str`.
- Nenhum router, judge, RAG, memória, cache ou runtime existente foi migrado para a nova API.
- `reasoning_content` nunca é fabricado pelo framework.
- Ausência de reasoning não gera erro.
- O output existente de telemetria continua sendo o conteúdo final, sem anexar reasoning automaticamente.

## Testes

Os testes específicos estão em `tests/unit/test_llm_rich_response.py` e verificam:

1. provider legado que só implementa `ainvoke()`;
2. manutenção do retorno `str` em `ainvoke()`;
3. retorno de `LLMResponse` em `ainvoke_response()`;
4. reasoning via atributo direto;
5. reasoning via `model_extra`;
6. ausência de reasoning e extração no formato OCI SDK.
