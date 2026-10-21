"""Local frontend demo, using the actual framework A2A adapter and SDK.

From the framework root:
  pip install -e 'libs/agent_framework[a2a]' uvicorn
  uvicorn examples.a2a_frontend_demo:app --host 127.0.0.1 --port 8000

This demo simulates business processing; it never calls OCI or an external tool.
"""
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from agent_framework.a2a.server import install_backend_a2a
from agent_framework.a2a.progress import report_progress

app = FastAPI(title='Agent Framework · A2A Frontend Demo')


async def demo_agent(request):
    text = request['payload']['message']
    await report_progress('workflow.started', {'agent': request.get('agent_id') or 'demo'})
    await asyncio.sleep(1)
    if text.strip().lower() == '/erro':
        raise RuntimeError('Simulated demo error')
    if text.strip().lower() == '/lento':
        await asyncio.sleep(20)
    await report_progress('workflow.completed', {'agent': 'demo'})
    if text.strip().lower() == '/confirmar':
        return {'text': 'Deseja continuar com a demonstração? Responda sim para prosseguir.',
                'metadata': {'a2a_task_state': 'input-required', 'agent_id': 'demo'}}
    return {'text': f'Recebi sua mensagem: “{text}”.\n\nA tarefa A2A foi concluída. Este exemplo usa o adaptador real do framework, com processamento de negócio simulado.',
            'session_id': request['session_id'], 'metadata': {'agent_id': 'demo'}}


profiles = SimpleNamespace(list_profiles=lambda: [SimpleNamespace(
    agent_id='demo', name='Agente de demonstração', description='Exemplo local de agente A2A assíncrono')])
settings = SimpleNamespace(A2A_PUBLIC_URL=os.getenv('A2A_PUBLIC_URL', 'http://localhost:8000'),
    A2A_TASK_MODE=True, A2A_TASK_TIMEOUT_SECONDS=60, A2A_SECURITY_SCHEMES={}, A2A_SECURITY=[], APP_NAME='Agente de demonstração')
install_backend_a2a(app, demo_agent, profiles, settings)
app.mount('/', StaticFiles(directory=Path(__file__).resolve().parents[1] / 'apps' / 'agent_frontend_a2a', html=True), name='frontend')
