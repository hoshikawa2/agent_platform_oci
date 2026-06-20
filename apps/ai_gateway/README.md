# AI Gateway

Camada desacoplada para abstração, roteamento, controle e governança de chamadas LLM.

Este componente não substitui o Agent Runtime. Ele centraliza políticas de modelo, seleção de provider, fallback, telemetria e controles corporativos.

## Rotas

- `GET /health`
- `GET /models`
- `POST /v1/chat/completions`

## Execução local

```bash
cd apps/ai_gateway
uvicorn app.main:app --host 0.0.0.0 --port 9100 --reload
```
