# Testes unitários do framework

Esta versão inclui uma pasta `tests/unit` cobrindo os componentes principais:

- cache local e distribuído;
- SSE com encode, persistência e replay;
- RAG com busca vetorial em memória;
- checkpoint saver compatível com LangGraph;
- telemetria profunda de LangGraph;
- runtime dos agentes com cache/RAG;
- verificação estática do workflow para garantir que não usa mais `MemorySaver()` diretamente.

## Como executar

```bash
cd projeto_agent_framework_first_ready
python -m venv .venv
source .venv/bin/activate
pip install -r agent_template_backend/requirements.txt
pip install pytest pytest-asyncio
pytest -q
```

Para rodar apenas os testes unitários:

```bash
pytest -q tests/unit
```
