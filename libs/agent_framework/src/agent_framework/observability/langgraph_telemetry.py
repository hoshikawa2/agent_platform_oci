from __future__ import annotations
import time
from contextlib import asynccontextmanager
from typing import Any


_LANGGRAPH_STEP_ORDER = {
    "__start__": 0,
    "input_guardrails": 1,
    "routing_decision": 2,
    "billing_agent": 3,
    "product_agent": 3,
    "orders_agent": 3,
    "support_agent": 3,
    "handoff": 3,
    "supervisor_agent": 3,
    "output_supervisor": 4,
    "output_guardrails": 5,
    "judge": 6,
    "supervisor_review": 7,
    "persist": 8,
    "__end__": 9,
}


def _langgraph_step(name: str, state: dict[str, Any]) -> int:
    explicit_steps = state.get("langgraph_steps")
    if isinstance(explicit_steps, dict) and name in explicit_steps:
        try:
            return int(explicit_steps[name])
        except (TypeError, ValueError):
            pass
    return _LANGGRAPH_STEP_ORDER.get(name, 50)


class LangGraphDeepTelemetry:
    """Eventos profundos do LangGraph no padrão FIRST.

    Use `async with tracer.node("router", state): ...` nos nós e
    `await tracer.edge("router", "billing_agent", reason={...})` nas decisões.
    """
    def __init__(self, telemetry):
        self.telemetry=telemetry

    @asynccontextmanager
    async def node(self, name: str, state: dict[str, Any] | None = None):
        state=state or {}
        session_id=state.get('conversation_key') or state.get('session_id')
        payload={
            'node': name,
            'langgraph_node': name,
            'langgraph_step': _langgraph_step(name, state),
            'framework': 'langgraph',
            'session_id': session_id,
            'agent_id': state.get('agent_id'),
            'tenant_id': state.get('tenant_id'),
            'input_size': len(str(state.get('user_text') or state.get('sanitized_input') or '')),
        }
        start=time.time()
        await self.telemetry.event('langgraph.node.started', payload, kind='langgraph')
        async with self.telemetry.span(f'langgraph.node.{name}', **payload):
            try:
                yield
                await self.telemetry.event('langgraph.node.completed', {**payload, 'duration_ms': int((time.time()-start)*1000)}, kind='langgraph')
            except Exception as exc:
                await self.telemetry.event('langgraph.node.failed', {**payload, 'error': str(exc), 'duration_ms': int((time.time()-start)*1000)}, kind='langgraph')
                raise

    async def edge(self, source: str, target: str, state: dict[str, Any] | None = None, reason: dict[str, Any] | None = None):
        state=state or {}
        await self.telemetry.event('langgraph.edge.selected', {
            'source': source, 'target': target,
            'session_id': state.get('conversation_key') or state.get('session_id'),
            'agent_id': state.get('agent_id'), 'tenant_id': state.get('tenant_id'),
            'reason': reason or {},
        }, kind='langgraph')
