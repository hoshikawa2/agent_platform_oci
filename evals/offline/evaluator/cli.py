from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
import typer
from rich import print
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from evaluator.config.agents import load_agents
from evaluator.engine import EvaluationEngine
from evaluator.persistence.repository import EvaluationRepository
from evaluator.config.settings import settings

app = typer.Typer(help='Agent Framework TIM-style LLM Judge Evaluator')


def _run_progress(coro_factory):
    async def runner():
        state={'run_id': None}
        with Progress(SpinnerColumn(), TextColumn('[bold blue]{task.fields[stage]}'), BarColumn(), TextColumn('{task.completed}/{task.total}'), TextColumn('{task.percentage:>3.0f}%'), TimeElapsedColumn()) as progress:
            task=progress.add_task('evaluation', total=1, stage='starting')
            async def cb(event):
                state['run_id'] = event.get('run_id') or state['run_id']
                stage = event.get('stage','')
                msg = event.get('message','')
                if state['run_id']:
                    snap = await EvaluationRepository(auto_init_schema=False).aget_run_progress(state['run_id'], event_limit=1)
                    total=int(snap.get('total_items') or 0) or 1
                    done=int(snap.get('done_items') or 0)
                    progress.update(task,total=total,completed=done,stage=f'{stage}: {msg}'[:120])
            result = await coro_factory(cb)
            progress.update(task, completed=1, total=1, stage='finished')
            return result
    return asyncio.run(runner())

@app.command("reset-db")
def reset_db():
    repo = EvaluationRepository(auto_init_schema=False)
    repo.store.drop_schema()
    repo.store._init_schema()
    print({"status": "OK", "message": "Evaluator schema dropped and recreated successfully."})

@app.command('init-db')
def init_db():
    EvaluationRepository(auto_init_schema=True)
    print({'status':'OK','message':'schema checked/created'})

@app.command('show-config')
def show_config():
    print({'env_path': str(settings.project_root / '.env'), 'adb_dsn': settings.ADB_DSN, 'wallet': settings.ADB_WALLET_LOCATION, 'langfuse': settings.enable_langfuse, 'publish_langfuse_scores': settings.publish_langfuse_scores, 'llm_provider': settings.llm_provider, 'llm_profile': settings.llm_profile, 'oci_genai_base_url': settings.OCI_GENAI_BASE_URL, 'oci_genai_model': settings.OCI_GENAI_MODEL, 'oci_genai_api_key_configured': bool(settings.OCI_GENAI_API_KEY), 'agents_config': settings.agents_config_path})

@app.command('run')
def run(period_start: datetime, period_end: datetime, source: str='langfuse', limit: int|None=None, show_progress: bool=True):
    if show_progress:
        result = _run_progress(lambda cb: EvaluationEngine(progress_callback=cb).run(period_start, period_end, source, limit))
    else:
        result = asyncio.run(EvaluationEngine().run(period_start, period_end, source, limit))
    print(result)

@app.command('run-agents')
def run_agents(source: str='langfuse', agent_id: str|None=None, limit: int|None=None):
    async def main():
        results=[]
        now=datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        for agent in load_agents():
            if agent_id and agent.agent_id != agent_id: continue
            start = now - timedelta(days=agent.days_back)
            engine=EvaluationEngine()
            results.append(await engine.run_agent(agent, start, now, source=source, limit=limit))
        return results
    print(asyncio.run(main()))

@app.command('progress')
def progress(run_id: str, events: int=20):
    print(asyncio.run(EvaluationRepository(auto_init_schema=False).aget_run_progress(run_id, event_limit=events)))

@app.command('runs')
def runs(limit: int=20):
    print(asyncio.run(EvaluationRepository(auto_init_schema=False).alist_runs(limit)))

if __name__ == '__main__':
    app()
