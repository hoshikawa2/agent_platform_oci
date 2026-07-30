import asyncio
import tempfile
from types import SimpleNamespace
from agent_framework.memory.long_term_memory import create_long_term_memory_manager

async def main():
    with tempfile.TemporaryDirectory() as d:
        settings = SimpleNamespace(
            ENABLE_LONG_TERM_MEMORY=True,
            LONG_TERM_MEMORY_PROVIDER='sqlite',
            LONG_TERM_MEMORY_SQLITE_PATH=f'{d}/memory.db',
            LONG_TERM_MEMORY_TABLE='agentfw_long_term_memory',
            LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS=20,
            LONG_TERM_MEMORY_MIN_CONFIDENCE=0.70,
            LONG_TERM_MEMORY_AUTO_EXTRACT=True,
        )
        manager = create_long_term_memory_manager(settings)
        first = {'tenant_id':'default','agent_id':'memory_test','session_id':'a','user_text':'Me chame de Cris. Minha linguagem preferida é Python. Meu projeto atual se chama Atlas.','context':{'business_context':{'customer_key':'MEM-001'}}}
        assert (await manager.persist_turn(first))['saved'] >= 3
        second = {'tenant_id':'default','agent_id':'memory_test','session_id':'b','context':{'business_context':{'customer_key':'MEM-001'}}}
        values = {item.key:item.value for item in await manager.load(second)}
        assert values['preferred_name'].lower() == 'cris'
        assert values['preferred_language'].lower() == 'python'
        assert values['current_project'].lower() == 'atlas'
        isolated = {'tenant_id':'default','agent_id':'memory_test','session_id':'c','context':{'business_context':{'customer_key':'MEM-002'}}}
        assert await manager.load(isolated) == []
        print('OK: persistência, recuperação entre sessões e isolamento validados')

asyncio.run(main())
