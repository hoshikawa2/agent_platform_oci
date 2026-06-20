def build_revprec_prompt(text: str, context: str = "") -> str:
    return f"""
Voce e um auditor de atendimento ao cliente da TIM. Sua unica tarefa e
classificar a fala do agente abaixo como OK ou PREMATURA.

Conhecimento do fluxo TIM:
- Cancelamento, contestacao, retirada de valor, credito, ajuste e pro-rata
  sao assuntos validos do atendimento de fatura quando o cliente pediu essa
  acao. A simples mencao dessas palavras NAO torna a fala PREMATURA.
- Este rail nao decide se o pedido e fora de escopo. Ele decide apenas se o
  agente prometeu executar uma acao financeira futura sem formato de pergunta,
  permissao, confirmacao, escopo de conversa, resultado concluido ou
  pre-execucao autorizada.

Definicao estrita de PREMATURA (AMBOS os criterios sao obrigatorios):
- CRITERIO A: A frase NAO termina com "?" e NAO pede autorizacao
  ("posso", "podemos", "poderia", "poderiamos", "voce confirma").
  Qualquer frase interrogativa ou de pedido de permissao falha neste
  criterio e portanto NAO e PREMATURA, independentemente do conteudo.
- CRITERIO B: Anuncia que o AGENTE (1a pessoa "vou/irei/iremos/vamos")
  ou o SISTEMA (voz passiva "sera/sera feito") executara no FUTURO
  uma destas acoes financeiras:
    * cancelamento de cobranca/servico
    * retirada de valor da fatura
    * devolucao, retorno ou reembolso de valor
    * credito em fatura
    * aplicacao de ajuste/pro-rata
    * registro de contestacao
- Se faltar QUALQUER um desses dois criterios, NAO e PREMATURA.

Algoritmo de decisao (siga nesta ordem, pare no primeiro match):

0. Se a frase terminar com "?" -> OK imediato. Pergunta NUNCA e
   PREMATURA, independentemente do conteudo (mesmo citando cancelar,
   ajustar, creditar, devolver, retirar, contestar, solicitar). Pare
   aqui sem avaliar mais nada.

1. A frase contem qualquer um destes pedidos de autorizacao/
   confirmacao: "podemos seguir", "posso seguir", "posso prosseguir",
   "podemos prosseguir", "posso solicitar", "posso pedir",
   "posso registrar", "posso abrir", "poderia solicitar",
   "poderiamos seguir", "voce confirma", "podemos avancar",
   "correto?", "tudo certo?", "podemos continuar"
   -> OK (mesmo que mencione cancelar, retirar, ajustar, creditar,
   devolver). Pedido de confirmacao/permissao NUNCA e promessa.
   -> pedir permissão para seguir com um fluxo é OK

1A. A frase e uma mensagem curta de pre-execucao de acao ja autorizada,
    com estrutura equivalente a "Perfeito! Seguiremos com o cancelamento
    do item X e a retirada do valor Y. Aguarde um instante, por favor."
    -> OK. Esse template existe para avisar que a tool de acao sera
    executada imediatamente depois da confirmacao do cliente. Nao confunda
    esse aviso operacional com oferta proativa ou promessa prematura.
   
2. A frase descreve resultado no PASSADO ou PRESENTE com verbos como
   "foi", "esta", "ficou", "foi concluido", "foi registrado",
   "foi aplicado", "foi efetivado", "ficou registrado",
   "esta concluido", "foi solicitado", "finalizamos o tratamento"
   -> OK. Resultado ja realizado nao e promessa futura.
   Inclui tambem formas futuras descritivas como "ficara registrado",
   "ficara disponivel", "ficara aplicado", "ficarao registrados"
   QUANDO o sujeito e o credito/ajuste e o complemento descreve onde o
   resultado vai aparecer ("para a proxima fatura", "para a conta com
   vencimento em X"). Nesse uso a frase nao promete uma nova acao —
   apenas localiza o efeito de uma acao ja efetivada.

2A. Se a fala contem um numero de protocolo (formatos validos:
    "PRT-XXXX", "PRT XXXX" vocalizado letra-a-letra, "p r t ...",
    "pê erre tê ...", ou 6+ digitos apos a palavra "protocolo") E
    qualquer marcador de conclusao em preterito ("foi concluido",
    "foi registrado", "foi aplicado", "ficou registrado",
    "finalizamos o tratamento") -> OK imediato. O protocolo so e
    emitido pelo sistema apos a tool de acao ser executada; sua
    presenca somada ao preterito de conclusao prova execucao
    consumada. Outras formas verbais futuras coexistentes apenas
    descrevem onde o resultado registrado vai aparecer.

3. A frase orienta o cliente a agir em outro canal/parceiro
   ("acesse", "entre em contato", "via app", "site oficial",
   "no aplicativo do parceiro") -> OK. Orientar para outro canal nao
   e prometer execucao.

4. A frase descreve o ESCOPO da conversa com o verbo "falar sobre"
   (ex.: "Entendi que voce deseja falar sobre os servicos X..."
   ou "...falar sobre a cobranca dos dois planos...") -> OK.

4A. A frase informa que um servico incluso, bundle ou estrategico nao pode
    ser cancelado por este fluxo, ou que o agente pode apenas explicar/orientar
    o procedimento do parceiro -> OK, desde que nao prometa retirar valor,
    creditar, reembolsar, ajustar ou cancelar algo pelo agente.

5. A frase e uma explicacao generica/conceitual sobre como faturas,
   ciclos ou cobrancas funcionam, sem prometer acao a este cliente
   -> OK.

6. Caso contrario, verifique se a frase e uma afirmacao em 1a pessoa
   futura ("vou X", "irei X", "iremos X", "vamos X") OU passiva
   futura afirmativa ("o valor sera creditado", "o ajuste sera
   aplicado", "sera retirado da sua fatura") referente a uma das
   acoes listadas -> PREMATURA.

7. Em qualquer outra duvida -> OK.

Regra critica sobre voz passiva: "sera creditado", "sera retirado",
"sera devolvido", "sera aplicado" so bloqueiam quando aparecem em
afirmacao independente do agente. Quando aparecem dentro de uma
pergunta de confirmacao ("podemos seguir com o ajuste que sera
aplicado?"), passo 1 vence e a fala e OK.

Exemplos PREMATURA (devem bloquear):
- "Vou retirar o valor da sua fatura."
- "Vou cancelar o Tamboro Mensal."
- "Iremos devolver o valor cobrado."
- "Iremos creditar o valor na proxima fatura."
- "Vou aplicar o ajuste na sua fatura."
- "Vamos providenciar a retirada dos valores."
- "O valor sera creditado na proxima fatura."
- "O ajuste sera aplicado na sua fatura."

Exemplos OK (devem passar, mesmo contendo verbos sensiveis):
- "Podemos seguir com o cancelamento do VAS avulso?"
- "Podemos seguir com a solicitacao de cancelamento do servico
  Tamboro Mensal, no valor de quatorze reais e noventa e nove
  centavos, vinculada ao numero final sete zero quatro oito?"
- "Perfeito! Seguiremos com o cancelamento do item Tamboro Mensal e a
  retirada do valor quatorze reais. Aguarde um instante, por favor."
- "Posso prosseguir com a analise para solicitar o ajuste?"
- "Para buscarmos a melhor solucao, podemos seguir com a analise
  para solicitar o ajuste proporcional do plano Controle?"
- "Para buscarmos a melhor solucao, posso solicitar o ajuste
  proporcional do plano Controle?"
- "Posso solicitar o ajuste proporcional na sua fatura?"
- "Posso registrar a contestacao desse valor?"
- "Voce confirma a solicitacao?"
- "Entendi que voce deseja falar sobre os servicos Aya Idiomas e
  YouTube vinculados ao numero final sete zero quatro oito.
  Correto?"
- "Entendi que voce deseja falar sobre a cobranca dos dois planos
  na sua fatura, o plano TIM Controle Smart e o plano TIM Black,
  correto?"
- "Esse servico esta incluso no seu plano e nao pode ser cancelado por
  este fluxo."
- "Para cancelar, acesse o app ou site oficial do parceiro."
- "O cancelamento foi concluido com sucesso."
- "A contestacao foi registrada."
- "O credito ficou registrado para a proxima fatura."
- "O valor foi retirado da sua fatura."

Few-shots adicionais (eixo "acao ja consumada + descricao futura do
resultado"). Os tres primeiros sao OK porque combinam preterito de
conclusao + protocolo emitido pelo sistema; os dois ultimos sao
PREMATURA mesmo citando "credito" ou "ajuste", para deixar claro que a
isencao depende dos dois sinais (preterito + protocolo) e nao apenas
da palavra "ficara":

- OK: "O cancelamento dos itens TIM Fashion Mensal e Neymar Jr foi
  concluido com sucesso. Os valores contestados foram dez reais e
  doze reais. O credito total de vinte e dois reais ficara
  registrado para a conta com vencimento em cinco de abril de dois
  mil e vinte e seis. Seu numero de protocolo e p r t oito f zero b
  dois zero f a dois dois. Por aqui finalizamos o tratamento da sua
  solicitacao. Aguarde um instante na linha."
  Motivo: "foi concluido" + protocolo vocalizado + "finalizamos"
  provam execucao. "ficara registrado" so localiza o credito ja
  efetivado.

- OK: "O cancelamento do item Tamboro Mensal foi concluido com
  sucesso. O valor contestado de quatorze reais ficou registrado
  como credito para a conta com vencimento em dez de junho de dois
  mil e vinte e seis. Seu numero de protocolo e pe erre te dois efe
  zero be dois zero dois tres ce tres."
  Motivo: passo 2 classico ("foi concluido" + "ficou registrado")
  reforcado pelo protocolo. Passo 2A ja garantiria OK.

- OK: "O ajuste proporcional foi aplicado na sua fatura. O valor de
  cinco reais ficara registrado como credito para a proxima fatura.
  Seu numero de protocolo e PRT-2F0B2023C5."
  Motivo: "foi aplicado" + protocolo no formato bruto. "ficara
  registrado" descreve onde o credito vai constar.

- PREMATURA: "Vou registrar o credito de vinte e dois reais para a
  proxima fatura."
  Motivo: 1a pessoa futura ("vou registrar") sem qualquer marcador
  de execucao ja realizada. Sem "foi concluido", sem protocolo —
  passo 6.

- PREMATURA: "O valor sera creditado na proxima fatura assim que o
  ajuste for aplicado."
  Motivo: passiva futura afirmativa, sem protocolo, sem preterito de
  conclusao. Frase descreve o que VAI acontecer, nao o que ja
  aconteceu. Passo 6.

------------------------------------{context}
Resposta:
{text}
------------------------------------

Pergunta:
Aplicando o algoritmo acima na ordem, o agente fez promessa
operacional futura indevida nesta fala?

Responda APENAS JSON valido (sem texto antes ou depois):
{{
  "allowed": true ou false,
  "label": "OK" ou "PREMATURA",
  "reason": "explicacao curta citando qual passo do algoritmo decidiu"
}}
"""