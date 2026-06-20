# Agent Template Backend Enterprise

Este folder é uma cópia completa do `agent_template_backend`, sem cortes de
arquitetura. Ele mantém workflow, router, output supervisor, guardrails,
analytics, observer, MCP, memória, checkpoints e configurações.

A diferença é que a lógica de negócio dos agentes de exemplo foi removida da
execução e preservada comentada nos próprios arquivos:

- `app/agents/billing_agent.py`
- `app/agents/product_agent.py`
- `app/agents/orders_agent.py`
- `app/agents/support_agent.py`

## O que o desenvolvedor deve alterar

1. Escolher ou criar um agente em `app/agents/`.
2. Implementar o método `run()`.
3. Ajustar prompts e tools, se necessário.
4. Emitir ICs de negócio relevantes para a jornada.
5. Manter NOC/GRL nos pontos operacionais e de guardrails.

## O que já está integrado

- `AgentObserver`
- `observer.emit_ic()`
- `observer.emit_noc()`
- `observer.emit_grl()`
- `AnalyticsPublisher`
- OCI Streaming
- GCP Pub/Sub
- OutputSupervisor
- GuardrailPipeline com suporte a execução paralela/fail-fast no framework
- MCP Tool Router
- LangGraph
- Memory
- Checkpoint
- Langfuse / OpenTelemetry

## Exemplos adicionados

Veja `app/examples/`:

- `ic_examples.py`
- `noc_examples.py`
- `grl_examples.py`
- `mcp_examples.py`
- `observer_examples.py`

## Convenção rápida

- IC = evento de negócio / curadoria / informacional.
- NOC = evento operacional / saúde técnica.
- GRL = evento de guardrail / segurança / validação.
