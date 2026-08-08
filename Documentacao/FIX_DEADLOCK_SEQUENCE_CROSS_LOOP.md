# Correção: deadlock/espera cross-loop na geração de sequence

## Problema

A API síncrona `agent_framework.observer.event()` podia ser chamada em uma worker thread sem event loop ativo. Nesse caso, a implementação anterior executava `asyncio.run(aevent(...))`, criando um novo event loop temporário. Ao mesmo tempo, `analytics/tim_sequence.py` compartilhava instâncias globais de `asyncio.Lock` (`_mongo_index_lock` e `_memory_lock`) entre chamadas que podiam vir de event loops diferentes.

Na primeira operação Mongo, `_ensure_mongo_ttl_index_once()` mantinha `_mongo_index_lock` durante a criação do índice TTL. A contenção por outro loop podia deixar a segunda chamada aguardando indefinidamente.

## Alterações aplicadas

1. `observer.py`
   - removido `asyncio.run()` do caminho síncrono de `event()`;
   - adicionado um event loop dedicado e reutilizável para chamadas síncronas;
   - submissão cross-thread feita com `asyncio.run_coroutine_threadsafe()`;
   - encerramento best-effort do loop no shutdown do processo.

2. `analytics/tim_sequence.py`
   - `_mongo_index_lock`: `asyncio.Lock` -> `threading.Lock`;
   - `_memory_lock`: `asyncio.Lock` -> `threading.Lock`;
   - inicialização do índice TTL movida para uma função síncrona protegida por lock de thread e chamada via `asyncio.to_thread()`;
   - o contador de fallback em memória usa uma seção crítica curta e thread-safe.

3. Testes
   - `tests/test_observer_cross_loop_deadlock_fix.py` valida:
     - múltiplas worker threads usando `event()` compartilham o mesmo loop síncrono do observer;
     - sequence em memória permanece monotônica entre event loops independentes;
     - criação do índice TTL ocorre apenas uma vez sob contenção cross-loop.

## Validação executada

```bash
PYTHONPATH=libs/agent_framework/src pytest -q tests/test_observer_cross_loop_deadlock_fix.py
```

Resultado: `3 passed`.

A suíte completa do repositório possui falhas preexistentes/independentes desta alteração, incluindo conflitos de coleta de arquivos `test_long_term_memory.py`, caminhos estáticos de template e testes de checkpoint/workflow. Esses itens não foram alterados por esta correção.
