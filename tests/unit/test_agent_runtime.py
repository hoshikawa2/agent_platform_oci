import pytest
from types import SimpleNamespace
from app.agents.runtime import AgentRuntimeMixin

class DummyAgent(AgentRuntimeMixin):
    def __init__(self):
        self.settings = SimpleNamespace(CACHE_TTL_SECONDS=10)
        self.calls = 0
        self.cache = None
        self.rag_service = None
        self.telemetry = None
        class LLM:
            async def ainvoke(inner, messages):
                self.calls += 1
                return 'ok'
        self.llm = LLM()

@pytest.mark.asyncio
async def test_agent_runtime_without_cache_invokes_llm():
    agent = DummyAgent()
    answer = await agent._invoke_llm_cached({'user_text':'oi'}, 'dummy', [{'role':'user','content':'oi'}])
    assert answer == 'ok'
    assert agent.calls == 1
