# Teste e diagnóstico de Long-Term Memory

## O que foi corrigido

1. A LTM agora é carregada explicitamente antes do roteamento.
2. O estado recebe uma chave estável em `long_term_memory_subject_key`, baseada em `business_context.customer_key` e, como fallback, `user_id`.
3. O resultado de carga e persistência aparece em `metadata.long_term_memory` da resposta.
4. `/health` informa a configuração efetiva de LTM carregada pelo processo.
5. Falhas de leitura e gravação geram eventos `long_term_memory.load.failed` e `long_term_memory.persist.failed`.

## Teste

Primeira sessão:

```bash
curl -s http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{
    "channel":"web",
    "payload":{
      "text":"Meu nome preferido é Cris e minha linguagem preferida é Python.",
      "session_id":"ltm-session-001",
      "user_id":"ltm-user-001",
      "customer_id":"ltm-customer-001"
    }
  }'
```

Verifique na resposta:

```json
"long_term_memory": {
  "subject_key": "ltm-customer-001",
  "write_result": {
    "saved": 2
  }
}
```

Nova sessão, mesma identidade:

```bash
curl -s http://localhost:8000/gateway/message \
  -H 'Content-Type: application/json' \
  -d '{
    "channel":"web",
    "payload":{
      "text":"Qual é meu nome preferido e qual linguagem eu prefiro?",
      "session_id":"ltm-session-002",
      "user_id":"ltm-user-001",
      "customer_id":"ltm-customer-001"
    }
  }'
```

Na segunda resposta, confira:

- `metadata.long_term_memory.subject_key` igual à primeira chamada;
- `metadata.long_term_memory.loaded` com registros;
- `metadata.long_term_memory.context` preenchido;
- ausência de `load_error`.

## Diagnóstico rápido

```bash
curl -s http://localhost:8000/health
```

A seção `long_term_memory` deve mostrar:

```json
{
  "enabled": true,
  "provider": "sqlite",
  "sqlite_path": "./data/agent_framework.db",
  "table": "agentfw_long_term_memory",
  "auto_extract": true,
  "inject_context": true
}
```

Execute o backend com o diretório do projeto como diretório de trabalho. Como o caminho SQLite é relativo, iniciar a aplicação em outro diretório pode criar ou consultar outro arquivo `./data/agent_framework.db`.
