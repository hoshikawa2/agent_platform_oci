"""Prompt do rail REVPREC — "o agente disse que cancelou algo?".

Reescrito em 2026-08-06. A versão anterior (207 linhas, algoritmo de 9 passos, saída
`{allowed,label,reason,score}`) julgava PROMESSA FUTURA sem autorização e, por
construção, deixava passar exatamente o caso que interessa: o passo 2 dela dava OK a
"resultado no PASSADO ou PRESENTE". Foi descartada inteira.

O rail agora responde UMA pergunta binária: a última fala do agente afirma que um
cancelamento / retirada de valor / contestação já aconteceu?

Por que isso funciona sem falso positivo na ação legítima: o rail só roda quando o
ORQUESTRADOR responde em TEXTO. Quando a ação acontece de verdade, ela vem de uma tool
call — e `apply_output_rails` sai antes dos rails LLM quando há `tool_calls` no turno
(pipeline.py, invariante do early-exit), assim como a fala canônica do
`ResponseComposer` entra com `skip_rails=True`. Ou seja: se esta pergunta chega ao LLM,
o agente está afirmando uma ação que ele NÃO tem tool para executar.

Saída BINÁRIA com polaridade INVERTIDA em relação a PINJ/COER: aqui `1` = achou a
afirmação = bloqueia; `0` = fala limpa. A pergunta fica na forma positiva ("disse que
cancelou?") porque é ela que dá acurácia; a inversão mora no `llm_client`
(`_BINARY_BLOCK_DIGIT`).

Duas fronteiras que o prompt precisa manter, e que os casos da suíte travam:
  - **histórico**: um cancelamento feito do jeito certo em turno anterior FICA no
    histórico e não foi avaliado por este rail; só o bloco "Resposta:" é julgado;
  - **protocolo**: o número de protocolo só é emitido depois da tool rodar, então uma
    fala que o traz relata execução real → 0.
"""
from __future__ import annotations


def build_revprec_prompt(text: str, context: str = "") -> str:
    """Monta o prompt do rail REVPREC.

    Args:
        text: última fala gerada pelo agente (a que será julgada).
        context: histórico já formatado por ``prompts._context.format_context_block``
            (a última fala do agente é PODADA de lá — ela vem em ``text``).

    Returns:
        Prompt cuja resposta esperada é um único caractere: ``1`` ou ``0``.
    """
    return f"""Você audita UMA fala do agente de fatura do provedor e responde 1 ou 0.

O agente NÃO executa cancelamento, contestação nem retirada de valor. Quando a ação
acontece de verdade, é o sistema que responde ao cliente — nunca esta fala. Logo,
afirmar aqui que já cancelou/retirou/contestou é sempre falso.

ANTES DE TUDO: se a fala traz NÚMERO DE PROTOCOLO — um ou vários, no formato "PRT..."
bruto, vocalizado ("pê erre tê nove cê dois...") ou dígitos depois da palavra protocolo —
responda 0 e pare. O protocolo só é emitido DEPOIS de a ação rodar de verdade; com ele a
fala relata execução real, inclusive quando RECAPITULA cancelamentos já feitos, por mais
concluída que soe.

Responda 1 quando a fala AFIRMA que um cancelamento, retirada de valor, contestação ou
reembolso JÁ ACONTECEU. Ex.: "cancelamento confirmado", "já foi cancelado", "cancelado
com sucesso", "cancelei o serviço", "retiramos o valor", "sua contestação foi
registrada", "o reembolso já foi processado", "a cobrança não vai mais aparecer porque
removi o serviço".

Responda 0 em todo o resto. Em particular:
- PERGUNTA ou PEDIDO DE PERMISSÃO, mesmo citando cancelamento: "Podemos seguir com o
  cancelamento do serviço X, no valor de R$ 12,00, você confirma?", "Gostaria de
  cancelar esse serviço?", "Posso seguir?".
- ESCOPO ou intenção reconhecida, sem ação feita: "Entendi que você deseja falar sobre
  os serviços X e Y. Correto?", "Vou verificar isso para você".
- PROMESSA sem afirmar execução: "vou cancelar", "seguiremos com o cancelamento, aguarde
  um instante", "o valor será retirado da sua fatura". Aqui a pergunta é se a ação foi
  DADA COMO FEITA; anúncio do que vem depois não é.
- DESCRIÇÃO DA FATURA, não ação do agente: "Foi removido um desconto de R$ 6,00", "foi
  adicionada a cobrança do X", "esse serviço foi cobrado em duas datas" — isso compara
  faturas e explica cobranças; não cancela nada.
- ORIENTAÇÃO a outro canal: "ligue para *144 e solicite o cancelamento", "pelo app do
  parceiro você consegue cancelar".
- NEGATIVA de ação: "não consigo cancelar por aqui", "ainda não cancelei", "esse serviço
  não pode ser cancelado neste atendimento".
- EXPLICAÇÃO, valor, data, encerramento, saudação, ou qualquer assunto que não seja
  ação de cancelamento dada como feita.

O HISTÓRICO é só contexto. Um cancelamento feito corretamente em turno anterior APARECE
lá e NÃO conta — ele não passou por esta auditoria e não é o que se julga agora. Julgue
somente a fala do bloco "Resposta:".

------------------------------------{context}
Resposta:
{text}
------------------------------------

A fala do bloco "Resposta:" afirma que um cancelamento, retirada de valor ou
contestação já aconteceu?

Responda APENAS 1 ou 0, sem mais nada."""
