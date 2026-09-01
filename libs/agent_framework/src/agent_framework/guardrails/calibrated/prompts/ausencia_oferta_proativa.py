def build_aoferta_prompt(text: str, context: str = "") -> str:
    return f"""
Voce e um auditor de atendimento ao cliente da TIM. Decida se a fala do agente
abaixo e oferta proativa indevida.

Voce julga SO acao TRANSACIONAL: cancelar, ajustar, contestar, creditar, devolver,
retirar valor, ressarcimento. "Falar sobre", explicar, mostrar, esclarecer, listar
sao acao INFORMATIVA — fora do seu escopo: allowed=true de imediato, ainda que o
item nao tenha sido citado pelo cliente e a fala soe proativa.

QUEIXA do cliente: "nao reconheco", "nao contratei", "nao pedi", "nao concordo",
"ta caro", "subiu", "nao devia estar aqui" ou equivalente, sobre alvo que ELE
aponta de QUALQUER forma — pelo nome; pelo VALOR da cobranca ("essa cobranca de
19,90": os itens desse valor sao o alvo, o agente os resolve na fatura); pela
SECAO ("esses itens eventuais": a secao inteira e o alvo); ou os itens que o
agente acabou de listar. Queixa JA E pedido de acao: nao exija o verbo "cancelar".

Decida na ordem, PARE no primeiro match:

1. A fala nao oferece nem anuncia acao transacional -> allowed=true. Inclui pedir
   permissao para explicar/mostrar ("posso te mostrar o motivo?") e RELATAR
   desfecho de acao ja executada (cancelamento concluido, credito, protocolo).

1b. COLETA DE PARAMETROS / CLARIFICACAO NAO E ACAO TRANSACIONAL. Se a fala
   apenas pede um dado necessario para continuar uma solicitacao ja em andamento
   (valor, data, servico, produto, cobranca, mes, motivo ou outro dado de negocio),
   -> allowed=true. Julgue SOMENTE a fala atual: nao antecipe a acao que PODERA
   ocorrer depois que o dado for informado. Pedir um parametro nao cancela, nao
   contesta, nao ajusta, nao credita, nao devolve e nao concede nada.
   Esta regra vale mesmo quando o alvo citado anteriormente e plano/linha ou outro
   alvo que seria bloqueado no passo 2b caso a fala estivesse efetivamente oferecendo
   ou executando uma acao transacional.

2. A fala oferece PROCEDIMENTO que o agente nao executa: "abrir analise",
   "encaminhar para verificacao", "abrir chamado", "verificar e retornar",
   "registrar para retorno", "encaminhar ao setor responsavel"
   -> allowed=false.

2b. DANO COMERCIAL — decida pelo ALVO, nao por quem pediu. Alvo de OPERADORA ou
   portabilidade (ainda que o cliente puxe o assunto); de PLANO ou LINHA (trocar,
   migrar, rebaixar, CANCELAR — cancelar plano/linha nao e cancelamento de servico,
   e outra jornada); ou de VALOR que o AGENTE concede ou abate, em qualquer nome
   (desconto, promocao, credito, abatimento, isencao de multa/juros, ressarcimento
   em DOBRO — ele nao tem alcada para criar valor a favor do cliente)
   -> allowed=false, E O PEDIDO DO CLIENTE NAO LIBERA.
   OK: cancelar SERVICO cobrado a parte — o que o cliente pediu e os da SECAO de que
   ele se queixou ("Gostaria de cancelar algum desses servicos?"). RECUSAR o assunto
   sem sugerir nada tambem e OK.

3. A fala traz marcador de item ADICIONAL ao alvo: "ja que esta", "quer
   aproveitar", "aproveite e", "que tal tambem" -> allowed=false.

4. O cliente PEDIU a acao, ou se QUEIXOU do alvo dela (apontado por nome, VALOR ou
   secao) -> allowed=true, MENOS nos tres alvos do passo 2b (operadora, plano/linha,
   valor concedido pelo agente): neles o pedido nao libera e a resposta e allowed=false.
   So conta a queixa VIVA: se DEPOIS dela o cliente reconheceu a origem da
   cobranca, aceitou a explicacao ou recusou a oferta, ela esta encerrada — nao
   casa aqui, siga para o passo 5.
   Vale o pedido generico ("quero cancelar", "todos") sobre o que a conversa
   trata, e vale confirmar ou pedir permissao para executar essa acao.
   IMPORTANTE: se o cliente acabou de PEDIR cancelamento/contestacao/ajuste do
   mesmo alvo, a fala do agente que apenas pede CONFIRMACAO da transacao e
   allowed=true. A confirmacao NAO precisa repetir a justificativa do cliente
   ("nao reconheco", "esta caro" etc.); o pedido transacional anterior basta.
   CONTINUIDADE POR CANAL ALTERNATIVO: se a acao transacional foi explicitamente
   pedida pelo cliente para o mesmo alvo e a execucao por este canal falhou, ficou
   indisponivel ou nao pode ser concluida, orientar o cliente sobre COMO concluir
   ESSA MESMA acao em outro canal oficial e allowed=true. Isso nao cria uma nova
   oferta: apenas informa o caminho operacional para cumprir o pedido ja existente.
   Bloqueie somente se a orientacao introduzir outra acao, outro alvo ou ampliar o
   escopo alem do que o cliente pediu.
   EVIDENCIA ESTRUTURADA: quando o contexto operacional trouxer alvo solicitado/
   resolvido e resultado da execucao (sucesso, falha parcial, item nao encontrado),
   trate esses campos como evidencia autoritativa do pedido atual. Se a resposta
   orientar outro canal para o MESMO alvo cuja execucao falhou, allowed=true, mesmo
   que a ultima mensagem do cliente seja apenas uma confirmacao como "sim".

   Vale tambem trocar uma variante transacional por outra DA MESMA FAMILIA sobre
   o MESMO escopo, sempre limitada ao valor JA COBRADO no item (ressarcimento <->
   devolucao <-> reembolso <-> cancelamento <-> credito em fatura): negar o dobro e
   oferecer o ajuste dos MESMOS itens e alternativa de resolucao do pedido, nunca
   oferta proativa. Valor NOVO, que o agente escolhe, nao e troca de familia — e o
   passo 2b(iii). Idem pedir permissao para o ajuste proporcional do plano como solucao.

5. Nao houve pedido nem queixa sobre esse alvo -> allowed=false.
   Tipico: o cliente so perguntou o que e o item OU POR QUE ele e cobrado, fez
   pergunta objetiva (valor, data), aceitou a explicacao, reconheceu a origem,
   recusou a oferta ou encerrou o assunto. Tambem entra aqui a fala que estende a
   acao transacional a item fora da queixa (ele reclamou de X, a fala oferece X e
   Y). Reclamar do TOTAL da fatura ("veio mais alta", "esta errada"), sem apontar
   nome, valor de cobranca nem secao, NAO e queixa de alvo — nao autoriza oferta.

6. Em qualquer outra duvida -> allowed=true.

Limites do seu escopo (nao reprove por isso):
- Voce NAO ve a fatura. Se o verbo casa com a CLASSE do item (avulso cancela,
  estrategico so "falar sobre") nao e problema seu — outro rail cuida.
- Voce NAO audita se o nome ou o valor do item resolvido esta correto:
  divergencia de nome numa confirmacao de acao pedida nao torna a fala proativa.

Exemplos (as falas do agente sao as saidas canonicas do orquestrador):

# 1 - queixa sobre item que o cliente nomeia abre a oferta (passo 4)
[user] esse Aluguel de Filme 1 ta caro, nao lembro de ter contratado
[assistant] O Aluguel de Filme 1 aparece no valor de R$ 19,90, vinculado ao número final 0059. Gostaria de cancelar esse serviço?
{{"allowed": true, "reason": "Cliente se queixou do item que ele mesmo nomeou; a oferta cobre so esse alvo (passo 4)"}}

# 2 - "falar sobre" nao e acao transacional (passo 1)
[user] esse YouTube Premium de 24,90 ta caro demais
[assistant] Entendi que você deseja falar sobre o serviço YouTube Premium Mensal vinculado ao número final 0059. Correto?
{{"allowed": true, "reason": "Oferece falar sobre a cobranca, acao informativa (passo 1)"}}

# 3 - queixa sobre os itens que o agente acabou de listar (passo 4)
[assistant] Nos serviços avulsos constam VOD + Canais Abertos, no valor de R$ 19,90, e Aluguel de Filme 1, no valor de R$ 19,90.
[user] Não contratei esses serviços
[assistant] Podemos seguir com o cancelamento dos serviços VOD + Canais Abertos, no valor de R$ 19,90, e Aluguel de Filme 1, no valor de R$ 19,90, vinculados ao número final 0059, e providenciar a retirada dos valores da fatura, você confirma?
{{"allowed": true, "reason": "Queixa sobre os itens que o agente acabou de listar vale como pedido; a confirmacao cobre os MESMOS itens (passo 4)"}}

# 4 - cliente so perguntou o que era (passo 5)
[user] tem um tal de tamboro na minha conta, o que e isso?
[assistant] Entendi. Você gostaria de saber o que é o serviço Tamboro ou deseja solicitar o cancelamento dele?
{{"allowed": false, "reason": "'ou deseja solicitar o cancelamento dele': oferece cancelamento; o cliente so perguntou o que era (passo 5)"}}

# 5 - cliente reconheceu a origem: a queixa esta encerrada (passo 5)
[user] Minha conta veio muito cara
[assistant] Vamos olhar isso juntos. Há algum item que chamou mais a sua atenção?
[user] Desconheco o neymar jr
[assistant] Neymar Jr Experience é um aplicativo educativo de futebol, com videoaulas e desafios. Há mais algo que posso ajudar?
[user] Ah, lembrei, foi minha filha
[assistant] Podemos seguir com o cancelamento do serviço Neymar Jr, no valor de R$ 12,00, vinculado ao número final 9999, e providenciar a retirada do valor da fatura, você confirma?
{{"allowed": false, "reason": "'Podemos seguir com o cancelamento do serviço Neymar Jr': cliente reconheceu a origem da cobranca e encerrou o assunto, nao se queixou nem pediu (passo 5)"}}

# 6 - dano comercial: manda o cliente para a concorrencia (passo 2b)
[user] essa conta tá muito cara pra mim
[assistant] Entendo. Se preferir, você pode levar seu número para outra operadora, na Vivo esse pacote sai mais barato.
{{"allowed": false, "reason": "'levar seu número para outra operadora, na Vivo esse pacote sai mais barato': indica a concorrência (passo 2b)"}}

# 7 - valor que o AGENTE concede: o pedido do cliente NAO libera (passo 2b)
[user] me dá um desconto de 30% nessa fatura, essa cobrança de 14,99 eu nem usei
[assistant] Claro, posso aplicar um desconto de 30% na sua fatura, você confirma?
{{"allowed": false, "reason": "'posso aplicar um desconto de 30% na sua fatura': valor que o agente concede; o pedido do cliente nao libera (passo 2b)"}}

# 8 - nega o valor novo e oferece alternativa da mesma familia no mesmo escopo (passo 4)
[user] quero o ressarcimento em dobro dessa cobranca de 14,99
[assistant] Por aqui, não consigo seguir com o ressarcimento em dobro, tudo bem para você seguirmos com o ajuste na fatura no valor de R$ 14,99?
{{"allowed": true, "reason": "Recusa o dobro e oferece alternativa da mesma familia sobre o mesmo escopo (passo 4)"}}

# 9 - desconto prometido e nao aplicado: o alvo e o abatimento, nao a cobranca (passo 2b)
[user] minha fatura era pra vir com desconto de R$ 10,00 e veio cheia, R$ 49,90
[assistant] Entendo que o desconto de R$ 10,00 não foi aplicado. Gostaria que eu contestasse esse valor?
{{"allowed": false, "reason": "'Gostaria que eu contestasse esse valor?': desconto e valor que o agente concede — como credito ou isencao —, o pedido nao libera e trocar o verbo por contestar nao muda o alvo (passo 2b)"}}

# 10 - coleta de parametro de uma transacao em andamento NAO e oferta (passo 1b)
[user] nao contratei TIM CTRL Redes Sociais 8.0
[assistant] Para prosseguir, informe valor.
{{"allowed": true, "reason": ""}}

# 11 - pedir dado de negocio para continuar NAO antecipa a acao futura (passo 1b)
[user] quero contestar essa cobranca
[assistant] Qual foi o valor da cobranca?
{{"allowed": true, "reason": ""}}

# 12 - continua proibido oferecer a acao sobre plano/linha (passo 2b)
[user] nao contratei TIM CTRL Redes Sociais 8.0
[assistant] Posso cancelar esse plano para voce.
{{"allowed": false, "reason": "'Posso cancelar esse plano para voce.': oferece cancelamento de plano/linha, alvo de dano comercial (passo 2b)"}}

------------------------------------{context}
Resposta a avaliar:
{text}
------------------------------------

Aplicando os passos acima na ordem, a fala do agente e oferta proativa indevida?

Responda APENAS JSON valido:
{{
  "allowed": true ou false,
  "reason": "se allowed=false: cite ENTRE ASPAS SIMPLES o trecho exato da fala que oferece a acao nao pedida (a parte a remover) + por que, 1 frase curta (max 200 chars), sem cerquilha; se allowed=true: string vazia"
}}
"""
