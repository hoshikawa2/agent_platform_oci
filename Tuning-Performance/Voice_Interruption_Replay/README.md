# Voice Interruption / Replay — framework-native

Esta melhoria move para `agent_framework.channels.interruption` comportamentos que antes costumavam ser implementados dentro de agentes de voz específicos.

## Objetivo

Evitar que `idle_nudge`, barge-in e fala residual pós-finalização reabram desnecessariamente o LangGraph principal, executem tools novamente ou confundam uma resposta de continuidade com uma nova intenção.

## Ordem de decisão

1. **Sessão encerrada**: replay da última fala terminal (ou fallback), preservando `terminal_status`. Não chama LangGraph, tools ou guardrails.
2. **Idle nudge**: replay da última fala real do assistente. Não chama LangGraph, tools ou guardrails.
3. **Fala não interrompível**: replay literal.
4. **Fala interrompível com contexto anterior**: executa `processing_interruption_classifier` pelo `LLMProvider` do framework.
   - `1`: reprocessa o complemento;
   - `0`, erro ou resposta inválida: replay fail-safe.
5. **Sem fala anterior suficiente**: processa normalmente.

## Classificador

O classificador usa o profile `processing_interruption_classifier` e solicita resposta binária `1/0`. Ele não possui gateway LLM próprio e não depende do domínio do agente.

## Telemetria

O backend emite `channel.processing_interruption.classified` com `regenerate=true|false`. Replays retornam metadata:

```json
{
  "replay": true,
  "replay_reason": "post_finalize|idle_nudge|non_interruptible_speech|classifier_result_0",
  "framework_short_circuit": true,
  "llm_called": false,
  "tools_called": false,
  "guardrails_called": false
}
```

No caso `classifier_result_0`, o LLM chamado é apenas o classificador leve; o LangGraph conversacional e o LLM do agente não são executados.

## Templates

A funcionalidade foi aplicada em:

- `templates/agent_template_backend/app/main.py`
- `templates/agent_template_backend_day_zero/app/main.py`

Portanto novos agentes herdam o comportamento sem copiar código de domínio.
