import pytest
from agent_framework.observability.langgraph_telemetry import LangGraphDeepTelemetry

class FakeTelemetry:
    def __init__(self): self.events=[]
    async def event(self, name, payload=None, kind='event'):
        self.events.append((name, payload or {}, kind))
    def span(self, name, **attrs):
        class CM:
            async def __aenter__(self_inner): return None
            async def __aexit__(self_inner, exc_type, exc, tb): return False
        return CM()

@pytest.mark.asyncio
async def test_langgraph_node_emits_started_completed():
    telemetry = FakeTelemetry()
    tracer = LangGraphDeepTelemetry(telemetry)
    async with tracer.node('router', {'session_id': 's1'}):
        pass
    names = [e[0] for e in telemetry.events]
    assert 'langgraph.node.started' in names
    assert 'langgraph.node.completed' in names

@pytest.mark.asyncio
async def test_langgraph_edge_event():
    telemetry = FakeTelemetry()
    tracer = LangGraphDeepTelemetry(telemetry)
    await tracer.edge('routing', 'billing', {'session_id': 's1'}, {'confidence': 0.9})
    assert telemetry.events[0][0] == 'langgraph.edge.selected'
