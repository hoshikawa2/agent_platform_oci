
### LLM Rich Response e reasoning_content

### Como usar este manual

Este é um **manual de referência especializado**. Ele não substitui o tutorial principal.

- Para criar um agente do início ao fim, use [`README.md`](../../../README.md).
- Use este documento quando precisar implementar, aprofundar ou diagnosticar **`ainvoke_response()`, metadados de inferência e `reasoning_content` opcional**.
- Os exemplos históricos consolidados aqui devem ser lidos à luz da API atual do framework.
- Em caso de divergência, o código da versão e o `README.md` atual prevalecem.

### Relação com o tutorial principal

O `README.md` apresenta essa capacidade no fluxo normal de desenvolvimento. Este manual reúne detalhes que estavam distribuídos em `docs/`, `Documentacao/`, release notes, validações e guias especializados.

O objetivo aqui é responder **“como essa feature funciona em profundidade e como eu resolvo problemas nela?”**, sem transformar este arquivo em uma segunda cópia do tutorial principal.

### Escopo

`ainvoke_response()`, metadados de inferência e `reasoning_content` opcional.

### Conteúdo técnico consolidado

### LLM Rich Response e reasoning_content

Guia para usar a API opt-in de resposta estruturada do LLM sem quebrar o contrato legado de ainvoke(), incluindo reasoning_content, usage, model, provider, fallback e testes.

### Como usar este documento

Este é o documento consolidado de desenvolvimento para este assunto. Ele reúne arquitetura, configuração, exemplos, comportamento de runtime, compatibilidade, testes e troubleshooting que antes estavam distribuídos em vários arquivos. As seções de origem foram preservadas quando traziam detalhes técnicos distintos; notas de release foram incorporadas como comportamento atual ou histórico de correção.

### API rica de resposta LLM

> Conteúdo consolidado a partir de `docs/LLM_RICH_RESPONSE.md`.

### Objetivo

O framework mantém `ainvoke()` como API retrocompatível, retornando apenas `str`, e adiciona `ainvoke_response()` para consumidores que precisam de metadados adicionais da inferência, incluindo `reasoning_content` quando o modelo/provider/API o disponibilizar.

### APIs

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

### Backoffice

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

### Compatibilidade de providers customizados

`LLMProvider.ainvoke_response()` possui fallback. Um provider externo que implemente apenas `ainvoke()` continua funcionando e recebe automaticamente um `LLMResponse(content=<texto>)`, com `reasoning_content=None`.

Providers nativos (`mock`, OpenAI-compatible/OCI OpenAI e OCI SDK) implementam a resposta rica e tentam preservar reasoning quando presente.

### Garantias de compatibilidade

- `ainvoke()` continua retornando `str`.
- Nenhum router, judge, RAG, memória, cache ou runtime existente foi migrado para a nova API.
- `reasoning_content` nunca é fabricado pelo framework.
- Ausência de reasoning não gera erro.
- O output existente de telemetria continua sendo o conteúdo final, sem anexar reasoning automaticamente.

### Testes

Os testes específicos estão em `tests/unit/test_llm_rich_response.py` e verificam:

1. provider legado que só implementa `ainvoke()`;
2. manutenção do retorno `str` em `ainvoke()`;
3. retorno de `LLMResponse` em `ainvoke_response()`;
4. reasoning via atributo direto;
5. reasoning via `model_extra`;
6. ausência de reasoning e extração no formato OCI SDK.

### Arquivos de origem

Os arquivos abaixo foram consolidados neste manual:

- `docs/LLM_RICH_RESPONSE.md`

### Regra de manutenção

Novas correções ou evoluções deste tema devem atualizar este documento consolidado. Release notes podem continuar existindo como histórico, mas não devem ser necessárias para compreender ou implementar a funcionalidade.
