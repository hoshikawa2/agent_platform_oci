# Agent Gateway — Global Supervisor

Este serviço roteia uma mesma conversa entre vários backends de agentes independentes, todos usando o `agent_framework`.

## Papel do Gateway

```text
Frontend
  ↓
Agent Gateway / Global Supervisor
  ↓
Backend Contas | Backend Ofertas | Backend Suporte | ...
```

O Gateway não executa a lógica de negócio dos agentes. Ele decide **qual backend** deve receber a mensagem e encaminha a requisição para o endpoint `/gateway/message` do backend escolhido.

## Modos de roteamento

- `router`: usa regras, keywords e domínios do `config/backends.yaml`.
- `supervisor`: usa LLM para escolher o backend.
- `hybrid`: mantém o backend ativo quando a mensagem parece continuação; usa regras; chama LLM em ambiguidade.

## Como subir localmente

```bash
cd agent_gateway
cp .env.example .env
export PYTHONPATH=../agent_framework/src:.
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

Suba seus backends nas portas definidas em `config/backends.yaml`.

## Teste de rota

```bash
curl -X POST http://localhost:8010/debug/route \
  -H 'content-type: application/json' \
  -d '{"channel":"web","payload":{"text":"Minha fatura veio alta","session_id":"s1"}}'
```

## Enviar mensagem

```bash
curl -X POST http://localhost:8010/gateway/message \
  -H 'content-type: application/json' \
  -d '{"channel":"web","payload":{"text":"Minha fatura veio alta","session_id":"s1"}}'
```

## Handoff entre backends

Um backend pode solicitar troca retornando no `metadata`:

```json
{
  "metadata": {
    "handover_backend": "ofertas"
  }
}
```

O Gateway chamará automaticamente o novo backend.

## IC/NOC

O Gateway emite eventos de observabilidade:

- `IC.GLOBAL_GATEWAY_RECEIVED`
- `IC.GLOBAL_BACKEND_SELECTED`
- `IC.GLOBAL_BACKEND_HANDOVER`
- `IC.GLOBAL_GATEWAY_COMPLETED`
- `NOC.005` em falhas
- `NOC.006` em conclusão HTTP
