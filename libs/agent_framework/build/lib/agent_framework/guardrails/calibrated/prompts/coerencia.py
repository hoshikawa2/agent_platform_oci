"""Prompt do rail COER (coerência do input do cliente).

Roda no INPUT, em paralelo com PINJ (mesmo pool), num 20b. Decide se a fala do
cliente é aproveitável. Saída BINÁRIA (`1` passa / `0` descarta) — o `reason` é
texto fixo; pedir motivo antes do dígito foi medido e não paga (+170 ms, empate).

Descarta SÓ por três motivos:

(a) incompreensível — transcrição quebrada, palavra solta, conversa paralela;
(b) negação ambígua — "não" colado num pedido de AÇÃO do atendente, sem a vírgula
    que decidiria a leitura ("não quero cancelar" × "não, quero cancelar");
(c) idioma (2026-08-10) — frase INTEIRA em inglês é STT quebrado, não cliente
    bilíngue: descarta mesmo se ela se entende ou responde à pergunta pendente.
    Ressalva: passa quando o agente pediu o NOME do item — nome de serviço É em
    inglês (`coer_ok_0023`). ⚠️ A regra só funciona no ENQUADRAMENTO, acima do
    gate de histórico (dentro de (a): 0/9 nos casos de inglês; no topo: 9/9),
    porque o gate concede 1 a quem responde e o catch-all a quem pede algo
    legível. Travado em `tests/guardrails/test_coerencia.py`.

O resto passa e é tratado adiante (matcher, TOX, OOS, orquestrador): referência
vaga, nome deformado, xingamento, assunto fora de fatura, resposta curta. O
histórico entra no prompt porque é ele que resolve fala curta e negação sem vírgula.

Dois bugs de produção fechados, ambos com a mesma assinatura — o modelo reconhece
a fala e escapa por uma regra de allow antes de aplicar (b):
  - 2026-08-07, "não" seco no degrau 2 da retenção: (b) disparava só por começar
    com "não" e o modelo COMPLETAVA a elipse com a ação que o AGENTE ofereceu.
    Conserto: (b) exige que a fala PEÇA algo, e o teste da subtração proíbe
    completar com a oferta do agente (`coer_ok_0027`: 161/220 → 340/340);
  - 2026-08-10, "não gostaria de falar com a atendente" (`coer_ambig_0014`, 2/9):
    a causa é o VERBO, não o gate nem o histórico (sonda 2×2 — condicional +
    histórico curto 2/10 × "não quero" + o histórico longo do trace 10/10).
    Conserto: gate vale só para a fala que "SÓ responde a ela"; (b) diz que
    entender o pedido não dispensa o teste; a glosa do 1º exemplo cobre o
    condicional. Alvo → 7/9, suíte 176,0 → 180,7/189.

⚠️ Protocolo: decida por BATCH (3 amostras de `--repeat 3` da suíte inteira, banda
de ruído ±4). `--repeat` focado engana nos dois sentidos — a mesma variante deu
7/10 focado × 0/9 batch, e o prompt atual dá 7/9 batch × 3/9 focado.

Variantes medidas e REJEITADAS (não retentar sem motivo novo) — a suíte está numa
fronteira zero-soma, cada cláusula compra um caso e vende outro:
  - "a recusa soar clara não fecha" → CONTRADIZ a exceção "a fala segue dizendo
    qual leitura vale": mata `coer_ok_0003` (7/9 → 0-1/9) em 3 variantes;
  - exceção no GATE ("fala com 'não' ainda passa por (b)") → mata `coer_ruido_0011`
    (9/9 → 0/9): exceção explícita REFORÇA o gate para todo o resto;
  - "gostaria" na lista de modais de (b) → 169,7/189;
  - few-shot NÃO é mais alavanca (era em 2026-08-05, +3,4 p.p.): +3 exemplos = empate
    exato por +132 tokens; só o do NOME em inglês = 189,7/201 (arrasta a regra (c));
    tirar exemplos custa mais do que os tokens que ocupam — inclusive o "não quero
    entender porque…", que o controle FOCADO media como "sem efeito" e em batch vale
    `coer_ok_0010` inteiro (9/9 → 1/9).

Tamanho: 1289 → 1334 (2026-08-07) → **1451 tokens** (cl100k). Suíte: **191,7/201
(95,4%)**, 67 casos. Detalhe por caso e histórico: `tests/llm_tests/README.md`.

Remedido em 2026-08-12 ao desfazer o revert (41979c4d): 193,7/204 (95,0%), 68 casos
— o novo `coer_ruido_0022` ("um" respondendo "sanei sua dúvida?", STT que não pegou
o "sim" → golden 0, reperguntar) sai de 3/10 no prompt antigo para 9/9 em batch só
com o gate "SÓ responde a ela", sem mudança extra de prompt.
"""
from __future__ import annotations


def build_coer_prompt(text: str, context: str = "") -> str:
    """Monta o prompt do rail COER.

    Args:
        text: fala do cliente a classificar.
        context: bloco de histórico já formatado por
            ``prompts._context.format_context_block`` (para este rail a última
            fala do agente é PRESERVADA — é a pergunta pendente).

    Returns:
        Prompt cuja resposta esperada é um único caractere: ``1`` ou ``0``.
    """
    return f"""Você filtra a fala do CLIENTE no atendimento de fatura do provedor. A fala vem de
transcrição de voz e pode chegar truncada ou trocada. O atendimento é em português:
frase inteira em INGLÊS é STT quebrado, não cliente bilíngue — responda 0 mesmo que
ela se entenda ou responda à pergunta do agente; só não vale quando o agente pediu o
NOME do item, que é em inglês.

PRIMEIRO olhe o histórico. Se o agente terminou com uma pergunta e a fala SÓ responde a ela
(sim/não, "ainda não", nome de serviço, valor, uma das opções oferecidas), responda 1
— mesmo curta, estranha ou com o nome deformado pelo STT. Se não há pergunta pendente,
julgue a fala sozinha pelos casos abaixo, sem dar desconto.

Responda 0 (descartar) SÓ nestes dois casos:

(a) NÃO DÁ PARA ENTENDER — você não conseguiria dizer em uma frase, SEM INVENTAR, o
    que o cliente quer, responde ou reclama: transcrição quebrada, frase cortada no
    meio, palavra ou letra solta, frase que soa completa mas cujo pedido não faz
    sentido, ou fala dirigida a OUTRA PESSOA (o cliente conversando com quem está do
    lado, sem falar com o atendimento). Palavra do domínio (plano, fatura, valor,
    cpf) dentro de frase sem sentido não salva a fala. Fala VAGA não é
    incompreensível: se ela aponta para o que está na tela ("esse aí", "isso aqui",
    "esse negócio", "os valores"), responda 1 — perguntar qual item é do fluxo.
    E se a última fala do agente pediu um NOME de item/serviço, nenhuma fala curta
    é incompreensível: ela é a tentativa de dizer o nome, por mais estranha que
    soe → 1 (reconhecê-lo é da etapa seguinte, que tem a fatura).

(b) NEGAÇÃO AMBÍGUA — a fala começa com "não" E PEDE ALGO depois; entender o que ela
    pede não a salva, quem decide é o teste. Faça o teste: tire
    esse "não" do início e olhe SÓ o que sobra na fala — nunca complete com a ação
    que o agente ofereceu. Se não sobra pedido nenhum ("não", "não sanou"), é
    resposta ao agente → 1, seja qual for a pergunta pendente. Se o que sobra é
    pedido de ação do atendente (cancelar, tirar cobrança,
    ajustar/diminuir a fatura, transferir para atendente, encerrar a conta,
    parcelar), sobram duas leituras opostas — recusa ("não quero cancelar") ou
    pedido ("não, quero cancelar") — e a vírgula que decidiria não veio na
    transcrição: responda 0. Vale para qualquer verbo ("não quero/preciso/posso",
    "não quero que vocês...", "não cancela").
    Responda 1 se: vem vírgula, "porque" ou "mas" depois do "não"; há sujeito antes
    do "não" ("eu não quero cancelar"); a fala segue dizendo qual leitura vale; ou o
    que sobra sem o "não" não é ação do atendente (pagar, reconhecer, entender,
    mudar de plano).

Responda 1 em TODO o resto, inclusive:
- pedido, queixa, dúvida ou desabafo que você entende, mesmo com erro de transcrição,
  gíria, xingamento, número solto ou assunto fora de fatura (outros filtros cuidam);
- nome de serviço estranho ou deformado, inclusive quando o agente pediu para repetir
  o nome do serviço;
- pedido de tempo, "alô?", agradecimento, despedida.

Dúvida se entendeu a fala → 1. Pergunta ou pedido claro dirigido ao atendimento, mesmo
fora do assunto de fatura → 1. Dúvida entre as duas leituras da negação → 0.

Exemplos (ilustram a regra, não são lista de falas):
- "não quero parcelar a fatura" → 0 (sem a vírgula, pode ser "não, quero parcelar");
  idem no condicional, "não gostaria de parcelar a fatura"
- "eu não quero parcelar a fatura" → 1 (o "eu" antes do "não" fecha a leitura)
- "não quero parcelar, quero só entender o valor" → 1 (a fala diz qual leitura vale)
- "não vou pagar essa multa" → 1 (pagar não é ação do atendente: a queixa é a mesma)
- "não", depois de "sanou sua dúvida?" → 1 (responde a pergunta pendente)
- "deixe zero", depois de "qual o nome do serviço?" → 1 (pode ser o nome que o STT
  deformou — "Deezer"; reconhecer o nome é da etapa seguinte, que tem a fatura)
- "não quero entender porque a conta subiu tanto" → 1 (entender é dúvida, não ação)
- "olha o menino ali pegando o negócio lá" → 0 (não dá para dizer o que o cliente quer)
- "bota dois planos um em cima do outro pra cá" → 0 (soa ordem, não quer dizer nada)
- "está cobrando um" → 0 (cortada no meio: não dá para saber de quê)

------------------------------------{context}
Fala do cliente:
{text}
------------------------------------

Responda APENAS um caractere: 1 (aproveitável) ou 0 (descartar).
"""
