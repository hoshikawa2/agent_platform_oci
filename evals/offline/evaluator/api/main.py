from __future__ import annotations
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from evaluator.persistence.repository import EvaluationRepository
from fastapi import Request
from fastapi.responses import JSONResponse
import traceback

app = FastAPI(title='Agent Framework Evaluator')

@app.get('/health')
def health(): return {'status':'ok'}

@app.get('/runs')
async def runs(limit:int=20): return await EvaluationRepository(auto_init_schema=False).alist_runs(limit)

@app.get('/runs/{run_id}/progress')
async def run_progress(run_id:str, events:int=20):
    return await EvaluationRepository(auto_init_schema=False).aget_run_progress(run_id, events)

@app.get("/runs/{run_id}/results")
async def results(run_id: str, limit: int = 100):
    return await EvaluationRepository(auto_init_schema=False).alist_results(run_id, limit)

@app.get('/ui', response_class=HTMLResponse)
def ui():
    return '''<!doctype html><html><head><title>Agent Framework Evaluator</title><style>body{font-family:Arial;margin:32px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}th{background:#eee}</style></head><body><h1>Agent Framework Evaluator</h1><p>Offline LLM-as-a-Judge with Agent Framework telemetry.</p><table id="runs"><thead><tr><th>Run</th><th>Agent</th><th>Source</th><th>Status</th><th>Total</th><th>Processed</th><th>Failed</th><th>Created</th></tr></thead><tbody></tbody></table><script>async function load(){const r=await fetch('/runs'); const data=await r.json(); document.querySelector('#runs tbody').innerHTML=data.map(x=>`<tr><td><a href="/runs/${x.run_id}/progress">${x.run_id}</a></td><td>${x.agent_id||''}</td><td>${x.source}</td><td>${x.status}</td><td>${x.total_items}</td><td>${x.processed_items}</td><td>${x.failed_items}</td><td>${x.created_at}</td></tr>`).join('')} load(); setInterval(load,5000);</script></body></html>'''

@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "traceback": traceback.format_exc(),
        },
    )
