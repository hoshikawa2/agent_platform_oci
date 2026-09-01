"""Prompt do rail COER (coerência semântica do input do cliente).

O COER responde uma pergunta estreita: existe significado conversacional recuperável
na fala do cliente? Ele não decide intenção, completude de parâmetros, executabilidade,
escopo de negócio ou se uma solicitação deve ser aceita. Essas decisões pertencem ao
router, aos contratos transacionais, aos validadores e ao mecanismo de clarification.

A classificação continua totalmente delegada ao LLM. Não há listas de frases,
regexes ou exceções de domínio para liberar/bloquear entradas específicas.
"""
from __future__ import annotations


def build_coer_prompt(text: str, context: str = "") -> str:
    """Monta o prompt semântico do rail COER.

    Args:
        text: fala do cliente a classificar.
        context: histórico já formatado, incluindo a pergunta pendente do agente
            quando disponível.

    Returns:
        Prompt cuja resposta esperada é um único caractere: ``1`` ou ``0``.
    """
    return f"""Você é o guardrail de COERÊNCIA SEMÂNTICA da fala do CLIENTE em uma conversa.

Sua única responsabilidade é decidir se a fala contém significado conversacional
recuperável o suficiente para que as próximas camadas do sistema possam trabalhar.

NÃO tente decidir aqui:
- qual é a intenção do cliente;
- se a intenção mudou em relação ao turno anterior;
- se uma transação deve continuar, ser abandonada ou encerrada;
- se faltam parâmetros para executar uma ação;
- se um valor, nome, data ou outro parâmetro é válido;
- se a solicitação pertence ao escopo do atendimento;
- se uma ação é permitida por regra de negócio;
- se a fala precisa de clarification ou desambiguação posterior.

Essas responsabilidades pertencem ao router, ao estado transacional, aos validadores
e ao mecanismo de clarification. Portanto, uma fala pode ser compreensível mesmo
sendo incompleta para execução, contendo negação, discordância, reclamação, múltiplas
intenções, informalidade, erro gramatical ou referência que precise ser resolvida pelo
contexto.

Use o histórico somente para interpretar elipses, respostas curtas e referências ao
turno anterior. Nunca complete a fala inventando uma intenção que não esteja apoiada
pela própria fala ou pelo contexto imediato.

Responda 1 quando for possível identificar, sem inventar, pelo menos um conteúdo
conversacional útil: uma intenção, pergunta, resposta, afirmação, negação, reclamação,
referência, escolha, valor, nome, pedido de esclarecimento, encerramento ou mudança de
assunto. Não exija que esse conteúdo já seja suficiente para executar uma ferramenta.

Responda 0 somente quando, mesmo considerando o contexto imediato, não houver
significado conversacional recuperável com segurança — por exemplo, transcrição
fragmentada, palavras desconexas, fala cortada antes de formar qualquer relação
semântica, ou conversa paralela sem solicitação dirigida ao atendimento.

Critério decisivo:
- compreensível mas incompleto/ambíguo para a regra de negócio -> 1;
- compreensível mas com possível mudança de intenção -> 1;
- compreensível mas sem todos os parâmetros -> 1;
- compreensível e contendo negação/discordância -> 1;
- impossível determinar qualquer conteúdo conversacional sem inventar -> 0.

Na dúvida entre "há significado, mas outra camada precisa esclarecer" e "não há
significado recuperável", escolha 1. O COER deve bloquear apenas incompreensibilidade
semântica real, não incerteza de negócio.

------------------------------------{context}
Fala do cliente:
{text}
------------------------------------

Responda APENAS um caractere: 1 (semanticamente compreensível) ou 0
(semanticamente incompreensível).
"""
