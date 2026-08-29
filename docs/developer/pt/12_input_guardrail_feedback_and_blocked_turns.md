# 12 — Feedback de Guardrails de Entrada e Semântica de Turno Bloqueado

## Objetivo

Este documento descreve como o `AgentWorkflow`, implementado em `app/workflows/agent_graph.py`, deve tratar um turno interrompido por guardrail de entrada sem transformar toda interrupção em uma mensagem genérica de “regra de segurança”.

A regra central é separar três coisas:

1. **decisão técnica do guardrail**, usada pelo runtime e pela observabilidade;
2. **mensagem pública ao usuário**, adequada ao tipo de bloqueio ou necessidade de esclarecimento;
3. **estado do turno**, que não pode carregar routing, tools ou judges de um turno que foi interrompido antes dessas etapas.

## Fluxo esperado

```text
mensagem do usuário
        ↓
input_guardrails
        ↓
allowed?
 ├─ sim → routing → tools/agente → composição → output_guardrails
 │
 └─ não
      ↓
    classificar tratamento público
      ↓
    limpar estado de routing/tools/judges do turno
      ↓
    construir mensagem pública segura
      ↓
    output_guardrails
      ↓
    persistência/resposta
```

Um guardrail de entrada bloqueante deve ser decidido **antes de qualquer tool com efeito colateral**.

## `reason` interno não é a resposta ao usuário

O campo `reason` deve permanecer disponível para logs, traces, eventos e diagnóstico. Ele não deve ser exibido literalmente quando puder revelar mecanismo interno ou quando a frase técnica não for apropriada ao usuário final.

Exemplo:

```text
COER.reason = "fala incompreensível ou negação ambígua na transcrição"
```

A resposta pública pode ser:

```text
"Não consegui entender sua última mensagem porque ela parece incompleta ou ambígua. Pode reformular ou completar o que você quis dizer?"
```

## Tratamento por tipo de guardrail

O comportamento exato continua configurável, mas a semântica esperada é:

| Guardrail | Tratamento público recomendado |
|---|---|
| `COER` | solicitar esclarecimento/reformulação; não tratar ambiguidade como incidente de segurança |
| `PINJ` | bloquear com mensagem segura sem explicar o mecanismo interno |
| `DLEX_IN` | bloquear ou orientar reformulação sem expor dado interno/sensível |
| `INPUT_SIZE` | solicitar redução da entrada |
| `TOX` | aplicar a política configurada para conteúdo inadequado |
| `CMP` | responder segundo a política de compliance |
| desconhecido | usar fallback seguro e genérico |

## Limpeza do estado do turno bloqueado

Quando o input é bloqueado antes do routing, o estado final daquele turno não deve reutilizar dados residuais do turno anterior.

No mínimo, o workflow deve evitar apresentar como atuais:

```text
route_decision
mcp_tools
mcp_results
judge_results
```

O metadata deve deixar explícito que o turno foi interrompido no estágio de input guardrails.

Isso evita um diagnóstico falso como:

```text
route = blocked
mcp_results = [tool executada]
```

quando a tool na realidade pertence ao turno anterior.

## Mensagem pública também passa pelos guardrails de saída

Uma resposta criada em função de um bloqueio de entrada ainda é uma saída do agente. Portanto ela deve seguir o mesmo pipeline de validação de saída antes de chegar ao usuário.

Isso permite que `DLEX_OUT`, `PINJ`, `TOXOUT`, Output Supervisor e outras políticas removam ou sanitizem informação que não deva ser apresentada.

## Relação com `agent_graph.py`

Esta feature é responsabilidade da orquestração do template, porque define a precedência entre nós do grafo e o estado do turno.

Ao alterar `app/workflows/agent_graph.py`, preserve estas invariantes:

- `input_guardrails` antecede routing/tools;
- um bloqueio de input não executa ação transacional depois do bloqueio;
- resposta pública não é o `reason` bruto do guardrail;
- estado residual de routing/tools/judges não sobrevive como resultado do turno bloqueado;
- a resposta pública passa por `output_guardrails` antes da persistência/resposta.

A mesma semântica deve ser mantida nos templates oficiais e nas variantes equivalentes em `Tuning-Performance`.

## Troubleshooting

### O usuário recebe “Não consegui seguir com essa mensagem por regra de segurança” para uma frase apenas incompleta

Verifique:

1. qual guardrail retornou `allowed=false`;
2. se `COER` está sendo tratado como esclarecimento e não como bloqueio genérico;
3. se o caminho de bloqueio usa uma mensagem pública específica;
4. se o fallback genérico está sendo usado somente quando não existe tratamento específico.

### O metadata mostra tool executada mesmo com `route=blocked`

Verifique se o ramo de bloqueio limpa o estado transitório do turno antes de retornar a resposta. Confirme também se a tool não foi executada no mesmo turno antes do guardrail de entrada.

### A mensagem de bloqueio expõe detalhes internos

Não use `reason` diretamente como texto público. Gere a mensagem pública e deixe o `reason` apenas em observabilidade.

### A resposta de bloqueio ignora guardrails de saída

Verifique a aresta do grafo. O fluxo esperado é:

```text
input_guardrails bloqueou
→ construir resposta pública
→ output_guardrails
→ persist
```

não:

```text
input_guardrails bloqueou
→ persist
```

## Testes de regressão recomendados

Cubra pelo menos:

- `COER=false` gera solicitação de esclarecimento, não mensagem genérica de segurança;
- ramo bloqueado não conserva `mcp_results`/routing de turno anterior;
- nenhuma tool transacional é executada depois de um bloqueio de input;
- mensagem pública passa pelos guardrails de saída;
- guardrail desconhecido ainda possui fallback seguro.
