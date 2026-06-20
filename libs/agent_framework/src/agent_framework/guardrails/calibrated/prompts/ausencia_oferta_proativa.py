def build_aoferta_prompt(text: str, context: str = "") -> str:
    return f"""
Voce e um auditor de atendimento ao cliente da TIM. Sua unica tarefa e
classificar a fala do agente abaixo como OFERTA_OK ou
OFERTA_PROATIVA_INDEVIDA.

Definicao de OFERTA_PROATIVA_INDEVIDA (AMBOS os criterios obrigatorios):
- CRITERIO A: A fala oferece/anuncia uma acao transacional (cancelar,
  ajustar, contestar, creditar, devolver, retirar valor, trocar plano, ressarcimento).
- CRITERIO B: Essa acao e ADICIONAL ou DIFERENTE do que o cliente pediu,
  isto e: NAO foi solicitada pelo cliente nem se refere aos itens/planos
  que sao objeto explicito da conversa atual.
  IMPORTANTE: substituir uma variante transacional por outra DA MESMA
  FAMILIA (ressarcimento <-> devolucao <-> reembolso <-> cancelamento
  de cobranca/servico <-> credito em fatura) sobre o MESMO escopo NAO
  conta como "diferente" — e alternativa de resolucao do mesmo pedido.

Se faltar QUALQUER um dos dois criterios, NAO e OFERTA_PROATIVA_INDEVIDA.

EXCECAO DURA (verificar ANTES do algoritmo, prevalece sobre tudo):
Se a fala nega/recusa ressarcimento/devolucao/reembolso/dobro pedido
pelo cliente E na sequencia oferece cancelamento/credito/contestacao
sobre os MESMOS itens/cobrancas/servicos em discussao -> OFERTA_OK.
Isso e alternativa de resolucao do MESMO pedido, NUNCA proativa,
independentemente de quantos itens estejam envolvidos.

Algoritmo de decisao (siga na ordem, PARE no primeiro match):

0. A fala e uma confirmacao de entendimento ou pergunta de escopo
   ("Entendi que voce quer X, correto?", "Voce deseja falar sobre Y?")
   -> OFERTA_OK. Confirmar entendimento NUNCA e proativa. No nosso contexto cancelamento
   e contestação são a mesma coisa.

0b. A fala RELATA o desfecho de acao ja executada (cancelamento
    concluido, credito gerado como consequencia, SMS enviado, protocolo, item nao
    tratado) -> OFERTA_OK. Resultado de acao pedida nao e oferta.

1. A fala e um pedido de permissao para ESCLARECER, EXPLICAR, MOSTRAR,
   ENTENDER ou CONFIRMAR algo (com "posso/podemos/poderia/poderiamos"):
   ex.: "Posso explicar a cobranca proporcional?",
        "Podemos seguir com essa explicacao?",
        "Antes de cancelar, posso te mostrar o motivo?"
   -> OFERTA_OK. Acao informativa NUNCA e proativa.

2. A fala contem marcadores explicitos de upsell/proatividade:
   "ja que esta", "quer aproveitar", "aproveite e", "que tal tambem",
   "tambem cancelar/ajustar/contestar", "posso ja contestar",
   "posso ja cancelar", "que tal X tambem"
   -> OFERTA_PROATIVA_INDEVIDA. Pare aqui.

3. A fala e um pedido de permissao para EXECUTAR uma acao transacional
   (cancelar/ajustar/contestar/seguir/prosseguir) com
   "posso/podemos/poderia/poderiamos":

   3r. Se o cliente pediu devolucao, reembolso, ressarcimento ou
       ressarcimento em dobro — seja nomeando itens, seja de forma
       generica sobre o que ja esta sendo tratado na conversa — e a
       fala nega o dobro e pede permissao para cancelar/contestar/
       creditar os itens/cobrancas que SAO o objeto da conversa (um
       ou varios) -> OFERTA_OK. Pare aqui. Oferecer alternativa
       transacional sobre o MESMO escopo NAO e proativa, mesmo que o
       cliente nao tenha listado os itens nominalmente.
       "Por aqui, não consigo seguir com o ressarcimento em dobro, tudo bem para você seguirmos 
       com o ajuste na fatura no valor de quatorze reais e noventa e nove centavos?"
       -> OFERTA_OK

   3a. A acao se refere a itens/planos/cobrancas que o cliente JA
       mencionou explicitamente OU que sao o assunto explicito da
       conversa atual (mesmo que o cliente nao tenha repetido os
       nomes na ultima fala). Ex.: a conversa toda esta tratando dos
       planos TIM Black e TIM Controle e o cliente diz "quero
       cancelar"; o agente pergunta "Podemos seguir com o
       cancelamento dos dois planos?" -> OFERTA_OK. Pedido de
       permissao para acao sobre o assunto da conversa NUNCA e
       proativa, mesmo quando envolve multiplos itens.

   3b. O cliente expressou intencao GENERICA de cancelar/ajustar/
       contestar (sem listar itens) e a fala pede permissao para
       executar essa acao sobre os itens que estavam sendo discutidos
       -> OFERTA_OK. Quando o pedido do cliente e ambiguo, o agente
       confirmando o escopo NAO e proativa — e o jeito certo de
       esclarecer.

   3c. A acao se refere a itens/planos/servicos que o cliente NAO
       mencionou e que NAO sao objeto da conversa, OU o agente esta
       sugerindo uma acao de FAMILIA DIFERENTE da que o cliente
       pediu (ex.: cliente pediu explicacao, agente oferece ajuste
       de plano)
       -> OFERTA_PROATIVA_INDEVIDA.

4. A fala anuncia/oferece uma acao transacional sem ter sido pedida e
   sem se referir aos itens da conversa
   -> OFERTA_PROATIVA_INDEVIDA.

5. Em qualquer outra duvida, especialmente quando a fala se relaciona
   ao que o cliente pediu -> OFERTA_OK.

Regra critica: pedir permissao para executar a acao sobre os itens que
SAO o assunto da conversa NUNCA e proativa, mesmo quando o cliente nao
listou os itens nominalmente na ultima fala. A ambiguidade do pedido do
cliente NAO transforma o agente em proativo — pelo contrario, perguntar
para confirmar o escopo e exatamente o comportamento correto.

Excecao explicita ja consolidada: o agente pode pedir permissao para
oferecer ajuste de plano como solucao:
"Para buscarmos a melhor solucao, posso solicitar o ajuste proporcional
do plano Controle?" -> OFERTA_OK.

Exemplos OFERTA_OK (devem passar):
- "Entendi que voce deseja falar sobre os planos TIM Black e TIM
  Controle, correto?"
- "Posso explicar a cobranca proporcional dos dois planos?"
- "Podemos seguir com essa explicacao?"
- "Podemos seguir com a solicitacao de cancelamento da cobranca dos
  dois planos na sua fatura?" (quando a conversa toda e sobre os dois
  planos e o cliente disse que quer cancelar)
- "Podemos seguir com o cancelamento dos servicos Tamboro Mensal, Tim
  Fashion e Neymar Jr?" (cliente disse "nao pedi isso, quero cancelar"
  referindo-se a esses servicos listados antes)
- "Para buscarmos a melhor solucao, posso solicitar o ajuste
  proporcional do plano Controle?"
- "Por aqui, nao consigo seguir com o ressarcimento em dobro. Podemos
  seguir com o cancelamento dos servicos Tamboro Mensal, Tim Fashion
  e Neymar Jr?" (cliente pediu ressarcimento em dobro de forma
  generica e esses servicos sao o assunto da conversa)
- "O cancelamento foi feito com sucesso. O credito de doze reais
  ficou registrado para sua proxima fatura. Protocolo ..." (desfecho)

Exemplos OFERTA_PROATIVA_INDEVIDA (devem bloquear):
- "Ja que esta cancelando um, quer aproveitar e cancelar os outros?"
- "Que tal tambem ajustar o seu plano?"
- "Posso ja contestar o valor da fatura para voce?" (cliente nao pediu
  contestacao)
- "Aproveite e cancele tambem o servico Y." (cliente nao mencionou Y)

Exemplos com historico completo (mesmo formato do bloco de contexto):

# 1 - Cliente so perguntou o que era; agente oferece cancelamento nao pedido
[user] tem um tal de tamboro na minha conta
[assistant] Entendi. Voce gostaria de saber o que e o servico Tamboro ou deseja solicitar o cancelamento dele?
{{"allowed": false, "label": "OFERTA_PROATIVA_INDEVIDA", "reason": "Cliente apenas perguntou o que era o servico e foi oferecido cancelamento que ele nao pediu (criterio A+B; passo 3c)"}}

# 2 - Confirmacao de entendimento sobre o assunto da conversa (passo 0)
[user] quero entender essas cobrancas dos planos TIM Black e TIM Controle
[assistant] Entendi que voce deseja falar sobre os planos TIM Black e TIM Controle, correto?
{{"allowed": true, "label": "OFERTA_OK", "reason": "Apenas confirma o escopo da conversa, nao oferece acao transacional (passo 0)"}}

# 3 - Pedido de permissao para acao sobre o assunto da conversa, mesmo com varios itens (passo 3a)
[user] nao reconheco esses servicos Tamboro Mensal e Tim Fashion, quero cancelar
[assistant] Vamos seguir com o cancelamento dos serviços Tamboro Mensal, no valor de quatorze reais e noventa e nove centavos, e Tim Fashion, no valor de dez reais, vinculados ao número final 9999 e providenciar a retirada dos valores da fatura. Você confirma?
{{"allowed": true, "label": "OFERTA_OK", "reason": "Pede permissao para executar o cancelamento que o cliente pediu sobre os itens em discussao (passo 3a)"}}

# 4 - Nega o dobro e oferece alternativa da mesma familia sobre o mesmo escopo (excecao dura / passo 3r)
[user] quero o ressarcimento em dobro dessa cobranca de 14,99
[assistant] Por aqui nao consigo seguir com o ressarcimento em dobro, tudo bem seguirmos com o ajuste na fatura no valor de quatorze reais e noventa e nove centavos?
{{"allowed": true, "label": "OFERTA_OK", "reason": "Recusa o dobro e oferece alternativa da mesma familia (ajuste/credito) sobre o mesmo escopo (excecao dura; passo 3r)"}}

# 5 - Marcador explicito de upsell (passo 2)
[user] quero cancelar o servico Tamboro
[assistant] Claro! E ja que esta cancelando, quer aproveitar e cancelar tambem o Tim Fashion?
{{"allowed": false, "label": "OFERTA_PROATIVA_INDEVIDA", "reason": "Marcador de upsell 'ja que esta' + 'quer aproveitar' oferecendo cancelar item nao pedido (passo 2)"}}

# 6 - Acao de familia diferente da pedida pelo cliente (passo 3c)
[user] pode me explicar por que essa fatura veio mais alta?
[assistant] Posso ja contestar esse valor da fatura para voce?
{{"allowed": false, "label": "OFERTA_PROATIVA_INDEVIDA", "reason": "Cliente pediu explicacao (informativo) e o agente oferece contestacao (transacional) que nao foi pedida (passo 3c)"}}

# 7 - Relato de desfecho de acao ja executada (passo 0b)
[user] entao pode cancelar
[assistant] O cancelamento foi feito com sucesso. O credito de doze reais ficou registrado para a sua proxima fatura. Protocolo 2026...
{{"allowed": true, "label": "OFERTA_OK", "reason": "Relata o desfecho de uma acao ja pedida e executada, nao e oferta (passo 0b)"}}
------------------------------------{context}
Resposta:
{text}
------------------------------------

Aplicando o algoritmo acima na ordem, a fala do agente e oferta
proativa indevida?

Responda APENAS JSON valido:
{{
  "allowed": true ou false,
  "label": "OFERTA_OK" ou "OFERTA_PROATIVA_INDEVIDA",
  "reason": "explicacao curta"
}}
"""
