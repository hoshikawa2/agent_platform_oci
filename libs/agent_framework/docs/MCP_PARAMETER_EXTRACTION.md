# MCP Parameter Extraction (`extract`)

## Objetivo

O recurso `extract` permite que o framework extraia parâmetros adicionais da mensagem do usuário antes da chamada do MCP Server.

Esses parâmetros não fazem parte do Business Context (`customer_key`, `contract_key`, `interaction_key`, `account_key`, `resource_key`, `session_key`). Eles representam dados específicos de uma tool MCP.

Exemplos genéricos:

- período solicitado;
- quantidade solicitada;
- código citado pelo usuário;
- identificador informado na mensagem;
- data textual mencionada;
- qualquer entidade de negócio necessária para a tool.

## Princípio arquitetural

O mecanismo é declarativo e genérico.

O framework não deve conhecer nomes de campos específicos, regras de domínio ou valores possíveis. A semântica de cada campo vem exclusivamente da configuração da tool no `mcp_parameter_mapping.yaml`.

```text
identity.yaml
    → resolve identidade e chaves canônicas

mcp_parameter_mapping.yaml
    → mapeia parâmetros MCP e declara extrações específicas de tool
```

## Quando usar

Use `extract` quando:

1. a informação está presente na mensagem em linguagem natural;
2. a informação não é uma chave canônica do Business Context;
3. a informação só é necessária para uma tool específica;
4. o MCP Server deve receber o valor já estruturado em `args`.

## Quando não usar

Não use `extract` para resolver:

- `customer_key`;
- `contract_key`;
- `interaction_key`;
- `account_key`;
- `resource_key`;
- `session_key`.

Essas chaves pertencem ao mecanismo de identidade e devem ser resolvidas por `identity.yaml`.

## Exemplo de configuração

```yaml
mcp_parameter_mapping:
  tools:
    minha_tool:
      map:
        customer_key: customer_id
        contract_key: contract_id
        session_key: session_id

      extract:
        parametro_externo:
          from: message
          type: string
          strategy: llm
          description: >
            Extraia da mensagem do usuário o valor necessário para preencher
            parametro_externo. Retorne null quando a informação não estiver
            presente no texto.
```

## Fluxo de execução

```text
Mensagem do usuário
        │
        ▼
Router identifica intent
        │
        ▼
Framework escolhe a tool MCP
        │
        ▼
MCPParameterMapper aplica map/defaults
        │
        ▼
MCPToolRouter verifica extract da tool escolhida
        │
        ▼
Executor genérico chama LLM para cada extractor declarado
        │
        ▼
Campos extraídos são injetados em args
        │
        ▼
MCP Server é chamado
```

## Exemplo conceitual

Mensagem do usuário:

```text
Texto em linguagem natural contendo uma informação necessária para a tool.
```

Resultado esperado da extração:

```json
{
  "parametro_externo": "valor_extraido"
}
```

Payload enviado ao MCP:

```json
{
  "customer_id": "123",
  "contract_id": "ABC",
  "session_id": "S1",
  "parametro_externo": "valor_extraido"
}
```

No MCP Server:

```python
valor = args.get("parametro_externo")
```

## Logs esperados

Quando a extração é executada com sucesso:

```text
mcp.parameter.llm_extracted tool=minha_tool field=parametro_externo value=valor_extraido
```

Quando o valor não é encontrado:

```text
mcp.parameter.llm_extracted_null tool=minha_tool field=parametro_externo
```

Quando o LLM não está disponível ou ocorre erro:

```text
mcp.parameter.llm_extract_failed tool=minha_tool field=parametro_externo error=...
```

## Boas práticas

- Mantenha `identity.yaml` apenas para identidade e chaves canônicas.
- Declare parâmetros adicionais no `mcp_parameter_mapping.yaml`.
- Não coloque regras de domínio hardcoded no framework.
- Não coloque parsing de linguagem natural dentro do MCP Server.
- Nomeie os parâmetros extraídos de forma estável.
- Use `description` para orientar o LLM sobre o que deve ser extraído.

## Regra principal

O framework deve executar extração somente quando:

```text
1. a tool MCP já foi escolhida;
2. essa tool possui extract configurado;
3. o extractor usa uma estratégia suportada, como strategy: llm.
```

Sem `extract` declarado, nada é extraído.
