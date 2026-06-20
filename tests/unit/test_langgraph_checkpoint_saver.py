import pytest
from types import SimpleNamespace
from agent_framework.checkpoints.langgraph_saver import RepositoryCheckpointSaver

@pytest.mark.asyncio
async def test_repository_checkpoint_saver_put_get(tmp_path):
    settings = SimpleNamespace(CHECKPOINT_REPOSITORY_PROVIDER='sqlite', SQLITE_DB_PATH=str(tmp_path/'db.sqlite'))
    saver = RepositoryCheckpointSaver(settings)
    config = {'configurable': {'thread_id': 't1'}}
    next_config = await saver.aput(config, {'id': 'cp1', 'channel_values': {'x': 1}}, {'source': 'test'}, {})
    assert next_config['configurable']['checkpoint_id'] == 'cp1'
    tup = await saver.aget_tuple(config)
    checkpoint = tup.checkpoint if hasattr(tup, 'checkpoint') else tup['checkpoint']
    assert checkpoint['id'] == 'cp1'
