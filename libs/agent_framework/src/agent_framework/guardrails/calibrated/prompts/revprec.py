"""REVPREC: detecta verbalização de resultado operacional sem evidência atual."""
from __future__ import annotations


def build_revprec_prompt(text: str, context: str = "") -> str:
    """Compara a fala candidata com a evidência estrutural do turno atual.

    Polaridade: 1 = a fala afirma conclusão/efeito operacional não comprovado ou
    contradito pela evidência; 0 = permitido.
    """
    return f"""Você audita UMA fala de um agente de atendimento TIM.

Sua tarefa NÃO é decidir se a frase "soa" como ação concluída. Sua tarefa é comparar
as afirmações da RESPOSTA com a EVIDÊNCIA REAL DO TURNO ATUAL.

Responda 1 SOMENTE quando a resposta afirmar que uma ação/efeito operacional já foi
concluído (por exemplo cancelamento, contestação, retirada de valor, crédito, reembolso,
envio ou alteração) e essa conclusão NÃO estiver suportada pela evidência atual, ou
estiver contradita por ela.

Responda 0 quando:
- a evidência atual comprova a ação/resultado afirmado;
- a resposta apenas explica dados de fatura, cobrança, desconto, plano, valor, data,
  status ou motivo presentes na evidência;
- a resposta pede confirmação/permissão ou solicita parâmetro;
- a resposta anuncia uma ação futura sem afirmar que já ocorreu;
- a resposta nega que a ação ocorreu;
- a resposta expressa ausência de evidência ou incerteza;
- não existe afirmação de conclusão operacional.

REGRAS IMPORTANTES:
1. Use SOMENTE a evidência do bloco EVIDÊNCIA ATUAL para provar execução. Não use
   histórico, memória ou suposições.
   Julgue somente a fala do bloco "Resposta:"; qualquer texto fora desse bloco é contexto.
2. Se a evidência mostra sucesso/COMPLETED e contém os fatos afirmados, responda 0.
3. Se a evidência mostra falha/erro/não executado e a resposta afirma sucesso, responda 1.
4. Se não existe evidência de execução e a resposta afirma que uma ação transacional já
   foi realizada, responda 1.
5. Descrição de algo que aconteceu na conta/fatura (ex.: desconto expirou, cobrança foi
   lançada) não é "ação prematura" se isso estiver suportado pelos dados atuais.
6. PROTOCOLO é evidência auxiliar, não regra absoluta: valide junto com a evidência atual.
7. DESCRIÇÃO DA FATURA (cobrança, desconto, data, status, motivo) não é execução de ação
   pelo agente quando estiver sustentada pelos dados atuais.

---------------- EVIDÊNCIA ATUAL ----------------
{context or '[]'}
---------------- RESPOSTA ----------------
{text}
--------------------------------------------------

A RESPOSTA contém alguma afirmação de resultado operacional concluído que NÃO esteja
suportada (ou esteja contradita) pela EVIDÊNCIA ATUAL?

Responda APENAS 1 ou 0."""
