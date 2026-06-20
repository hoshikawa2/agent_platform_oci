import pytest
from types import SimpleNamespace
from agent_framework.rag.rag_service import RagService

@pytest.mark.asyncio
async def test_rag_service_retrieves_relevant_document():
    settings = SimpleNamespace(VECTOR_STORE_PROVIDER='memory', GRAPH_STORE_PROVIDER='memory', RAG_TOP_K=2)
    rag = RagService(settings)
    await rag.add_documents(['fatura alta por roaming internacional', 'pedido de troca de aparelho'], namespace='billing')
    result = await rag.retrieve('minha fatura veio alta', namespace='billing')
    assert result.documents
    assert 'fatura' in result.as_prompt_context().lower()
