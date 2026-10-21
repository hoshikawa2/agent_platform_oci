# Frontend A2A para o Agent Framework OCI

Interface estática, sem build e sem dependências JavaScript de produção. Usa os
endpoints A2A que já existem no pacote: pode falar com o template de backend
ou com o Agent Gateway. O frontend nativo em `apps/agent_frontend` é preservado.

## Experimentar sem OCI

Na raiz do framework:

```sh
python -m pip install -e 'libs/agent_framework[a2a]' uvicorn
python -m uvicorn examples.a2a_frontend_demo:app --host 127.0.0.1 --port 8000
```

Abra **http://localhost:8000** e clique em **Conectar ao serviço**. O exemplo
serve a tela e a API na mesma origem, sem precisar configurar CORS.

A demonstração usa o **adaptador A2A e o SDK reais**, com a lógica de negócio
simulada. Digite uma mensagem e acompanhe a tarefa. Comandos de demonstração:

- `/confirmar`: aguarda sua resposta e retoma a mesma Task.
- `/lento`: permite testar o botão de cancelamento.
- `/erro`: demonstra uma Task que termina em falha.

Se a porta 8000 estiver ocupada, altere a porta ao iniciar e informe o novo
endereço no campo **Endereço do serviço**, ou use `?service=http://localhost:NOVA_PORTA`.

## Usar com seu agente ou Gateway

Habilite A2A no serviço, conforme `docs/A2A_ASSINCRONO.md`, e sirva este diretório:

```sh
python -m http.server 5173 --directory apps/agent_frontend_a2a
```

Abra **http://localhost:5173**. Não abra `index.html` como arquivo local, pois a
interface usa módulos JavaScript e requisições HTTP.

| Uso | Endereço do serviço | Destino na interface | Seleção carregada do Agent Card |
| --- | --- | --- | --- |
| Template de agente | `http://localhost:8000` | Agente | Perfis de `agents.yaml` |
| Agent Gateway | `http://localhost:8010` | Gateway | Backends do catálogo |

Use **Seleção automática** para deixar a decisão com o serviço. No Gateway,
um backend selecionado é enviado como `message.metadata.backend_id`. Um perfil
opcional dentro dele pode ser informado em **Perfil do agente no backend**.
O adaptador A2A encaminha a seleção ao roteador existente; os contratos nativos
não são alterados.

O serviço deve permitir a origem da interface em `CORS_ORIGINS`. O valor padrão
do pacote já permite `http://localhost:5173`. Se mudar o host ou a porta,
configure a origem exata, por exemplo:

```dotenv
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
ENABLE_A2A=true
A2A_TASK_MODE=true
```

Para publicar com Docker:

```sh
docker build -t agent-frontend-a2a apps/agent_frontend_a2a
docker run --rm -p 5173:80 agent-frontend-a2a
```

O navegador precisa alcançar o endereço informado no formulário. Para uso
externo, informe a URL pública do backend/Gateway, não o nome interno do
container. Uma interface HTTPS deve acessar um serviço HTTPS.

## O que a interface oferece

- Descoberta do Agent Card e escolha de versão automática ou explícita (1.0/0.3).
- Envio de mensagem com retorno imediato de Task.
- Acompanhamento por POST SSE com `SubscribeToTask`/`tasks/resubscribe`.
- Recuperação por `GetTask`/`tasks/get` quando o fluxo termina ou cai.
- Consulta periódica como alternativa ao streaming.
- Cancelamento solicitado ao serviço, incluindo tarefas aguardando input.
- Continuação de tarefas em input-required/auth-required.
- Exibição de respostas diretas e dos artefatos de Tasks, com suporte aos
  resultados estruturados de múltiplos agentes do framework.
- Contexto de negócio opcional (cliente e contrato/pedido).
- Identificadores da conversa/tarefa preservados em `sessionStorage` para
  retomar após recarregar a mesma aba. O conteúdo do chat não é persistido.
- Nova conversa independente, sem reaproveitar uma Task concluída.

O frontend usa `fetch` para SSE, permitindo enviar os mesmos cabeçalhos de
autenticação nas consultas e no acompanhamento. Em **Contexto e autenticação**,
informe o nome e o valor completo do cabeçalho exigido pelo serviço, por
exemplo `Authorization` / `Bearer ...`, ou `x-api-key` / valor da chave.
Credenciais ficam somente na memória e precisam ser informadas novamente após
recarregar. Não são gravadas em `sessionStorage` nem colocadas na URL.

Nenhuma operação de envio é repetida automaticamente. Se a resposta do envio
não chegar, a tela informa a incerteza, pois o serviço pode ter aceitado a
mensagem. O botão **Retomar** consulta a mesma Task, quando seu ID é conhecido.
Trocar conexão, tenant, perfil ou backend requer reconectar e inicia outra
conversa quando a identidade da configuração mudou.

## Limites herdados do serviço

O frontend não transforma o armazenamento em memória em armazenamento durável.
Uma Task perdida ao reiniciar o serviço não pode ser recuperada pela tela.
O cancelamento local não desfaz efeitos externos já confirmados e não garante
cancelar uma operação já aceita por um agente remoto.

`auth-required` indica que a tarefa aguarda autorização, mas esta interface não
implementa login OAuth nem aprovação externa automática. Realize o fluxo exigido
pelo agente, atualize a credencial se necessário e retome a tarefa.

Não há upload de arquivos, push notifications, gRPC ou emissão de tokens do LLM.
A seleção de versão 0.3 é explícita quando o serviço publica um Agent Card 1.0
mas também aceita o formato 0.3, como ocorre no adaptador do framework.

## Testes

Sem bibliotecas JavaScript adicionais, com Node.js 22 ou superior:

```sh
cd apps/agent_frontend_a2a
node --test tests/client.test.js
```

Com a demonstração em execução:

```sh
A2A_DEMO_URL=http://localhost:8000 node --test tests/*.test.js
```

Os testes de integração exercitam o cliente JavaScript contra o SDK real do
framework: A2A 1.0 e 0.3, envio, streaming, consulta, confirmação, cancelamento
e falha. Os testes de interface também foram realizados em navegador local.
