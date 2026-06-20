# Agent Platform Certification Tests

Este pacote executa uma validação operacional **sem pytest**, usando chamadas `curl` contra o backend na porta 8000 e gerando evidências em arquivos JSON, HTML e logs.

Ele foi montado para o projeto `agent_framework_oci`, usando os endpoints reais do backend:

- `GET /health`
- `GET /debug/env`
- `POST /debug/route`
- `GET /debug/mcp/tools`
- `POST /debug/mcp/call/{tool_name}`
- `POST /gateway/message`
- `GET /sessions/{session_id}/messages`
- `GET /sessions/{session_id}/checkpoint`

## Como instalar

Copie a pasta `agent_certification_tests` para a raiz do projeto, ao lado do `.env` e do `docker-compose.yml`.

Exemplo:

```bash
unzip agent_certification_tests.zip
cp -R agent_certification_tests/* ./agent_framework_oci/
cd agent_framework_oci
```

## Como subir a aplicação

Na raiz do projeto:

```bash
docker compose up -d --build
```

Confirme manualmente:

```bash
curl http://localhost:8000/health
curl http://localhost:5173
curl http://localhost:8100/health
curl http://localhost:8200/health
```

## Como executar a certificação

```bash
./run_certification.sh
```

Com parâmetros:

```bash
BACKEND_URL=http://localhost:8000 \
FRONTEND_URL=http://localhost:5173 \
ENV_FILE=.env \
LOAD_VUS=10 \
LOAD_REQUESTS_PER_VU=5 \
./run_certification.sh
```

Sem teste de carga:

```bash
./run_certification.sh --skip-load
```

## Evidências geradas

Cada execução cria uma pasta:

```text
evidencias/YYYYMMDD_HHMMSS/
├── json/
├── logs/
├── html/report.html
└── report.json
```

O arquivo principal é:

```bash
open evidencias/<execucao>/html/report.html
```

No WSL/Linux:

```bash
xdg-open evidencias/<execucao>/html/report.html
```

## O que é validado

1. Backend vivo em `:8000`
2. Configuração lida de `/debug/env` e `.env`
3. Persistência local SQLite, quando `SQLITE_DB_PATH` existir
4. Lista de tools MCP
5. Chamada direta às tools MCP `consultar_fatura` e `consultar_pedido`
6. Roteamento por `router` ou `supervisor`
7. Fluxo E2E em `/gateway/message`
8. Memória da sessão
9. Checkpoint
10. Guardrails básicos
11. Langfuse, se habilitado no `.env`
12. Frontend vivo
13. Carga simples concorrente

## Langfuse

Se `ENABLE_LANGFUSE=true`, o script tenta consultar a API pública do Langfuse usando:

```env
LANGFUSE_HOST=http://localhost:3005
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

Se as chaves não existirem, a evidência registra que Langfuse está habilitado, mas a validação da API não conseguiu ser feita.

## Teste de carga com k6 opcional

Além do teste de carga interno em Python, há um script k6:

```bash
BACKEND_URL=http://localhost:8000 K6_VUS=50 K6_DURATION=2m k6 run load/k6_gateway_load.js
```

## Screenshot opcional do frontend

Instale Playwright no projeto:

```bash
npm init -y
npm i -D @playwright/test
npx playwright install chromium
```

Execute:

```bash
FRONTEND_URL=http://localhost:5173 npx playwright test playwright/frontend_smoke.spec.js
```

A screenshot será salva em:

```text
evidencias/screenshots/frontend-smoke.png
```

## Observação importante

Os testes de guardrail e judge dependem das regras ativas, do LLM configurado e da forma como o backend responde. Por isso, alguns cenários são tratados como validação de comportamento/evidência, não como teste unitário rígido.
