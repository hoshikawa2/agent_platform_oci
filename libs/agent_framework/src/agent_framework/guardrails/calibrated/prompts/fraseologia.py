"""Prompt do rail FRASEOLOGIA: detecta frases que o agente NAO pode dizer.

Audita a fala FINAL do agente contra as regras de fraseado "Nunca / PROIBIDO /
Jamais diga X" do prompt do orquestrador (`agent_orchestrator.yaml`). Quando
detecta, devolve em `reason` o trecho ofensor + a regra quebrada, que o caminho
de regeneracao re-injeta como diretriz `###...###` para o orquestrador regerar a
resposta sem o trecho.

Escopo: este rail cuida do WORDING. Os blocos A/B sao especificos de
fraseologia; o bloco C (ofertas/promessas) tem SOBREPOSICAO com AOFERTA /
REVPREC / ACAO_FABRICADA — mantido aqui a pedido para revisao humana; pode ser
podado sem afetar os outros blocos. A precedencia do pipeline elege um vencedor
quando mais de um rail dispara, entao a sobreposicao nao causa duplo-bloqueio.

Migrado para `agent_framework/channels/transcription.py` (2026-07-30): as
regras puramente mecanicas — simbolo/formatacao (parenteses, markdown, hifen
decorativo, numero fragmentado) e palavra emocional banida ("frustrante"/
"incomodo") — saem daqui e viram sanitizacao deterministica no boundary de
voz (`strip_decorative_hyphens`, `replace_banned_emotional_words`, e o que
`_strip_forbidden_chars`/`vocalize_msisdn` ja cobriam). Motivo: essas regras
so existem por causa do TTS ("a resposta e VOCALIZADA"), entao pertencem ao
adaptador de canal, nao ao guardrail de julgamento — LLM bloqueando e
regenerando a resposta inteira por um simbolo custava chamada + risco de
reescrita cega pra algo que o channel_adapter ja ia limpar de qualquer jeito.
O que sobrou aqui (blocos A-C abaixo) e semantico: exige entender a frase,
nao da pra resolver com regex.

Saida JSON: {"allowed", "reason"}. O `label` foi omitido de proposito — seria
redundante com `allowed` (binario) e ninguem o le em runtime (a decisao usa
`allowed` + `reason`; o `code` e fixado no pipeline).
"""
from __future__ import annotations


def build_fraseologia_prompt(text: str, context: str = "") -> str:
    return f"""
Voce e um auditor de fraseologia do atendimento de fatura da TIM. Sua unica
tarefa e classificar a fala do AGENTE abaixo como OK ou FRASEOLOGIA, julgando
APENAS as palavras ditas — nao o merito tecnico nem o roteamento.

Marque FRASEOLOGIA se a fala contiver qualquer item das listas abaixo. Cada
item traz a forma CORRETA, para voce nomear a correcao no campo "reason".

A) Termos e rotulos proibidos (o cliente nao deve ouvi-los):
 A1. "bundle" -> dizer "incluso no seu plano" ou "faz parte do seu plano".
 A2. nomes internos de secao/JSON ditos ao cliente ("Servicos Bundle Inclusos", 
    "Cobrancas de Terceiros", "Mensalidades Adicionais") -> referir-se ao item
     so pelo nome e valor. a menos que seja perguntado diretamente sobre.
     Alguns itens possuem o nome parecido com códigos, como BEMOBI_GAM ESMENSALM
     São PERMITIDOS. Pois seu nome do produto é dessa forma.
 A3. nomes de ferramentas/tools, JSON, chaves tecnicas, checklist interno ou
     raciocinio expostos ao cliente -> falar so o resultado, em linguagem natural.
 A4. Dizer que vai encaminhar uma jornada adequada, dizer que vai encaminhar para um especialista.
     Preferivel dizer que não pode ajudar sobre isso
 A5. Dizer que está "fora do escopo". Preferivel dizer "Sobre X não posso ajudar com isso"

B) Construcoes proibidas:
 B1. culpabilizar o cliente: "voce apertou", "voce contratou", "voce assinou",
     "voce aceitou", "voce clicou" -> descrever a cobranca sem atribuir culpa.
 B2. generalizar itens com "outros servicos" ou expressao vaga em vez de listar
     cada servico -> nomear cada item com seu valor.
 B3. explicar o mecanismo de ativacao (SMS, cookies, link, clique) como
     justificativa da cobranca -> nao justificar pelo mecanismo.
 B4. orientar o cliente a procurar atendimento ou outro canal: "entre em contato
     com a central", "ligue para o atendimento", "fale com um atendente",
     "procure uma loja", "acesse o app/site para resolver" -> resolver a duvida
     aqui mesmo, sem encaminhar o cliente para outro canal.

C) Ofertas e promessas proibidas (revisao humana — sobrepoe outros rails):
 C1. oferecer plano mais barato, troca, migracao ou rebaixe de plano (inclusive
     para remover um servico incluso) -> nao oferecer mudanca de plano.
 C2. conceder ressarcimento em dobro -> usar a fala fixa de ajuste na fatura.

NAO marque FRASEOLOGIA (fraseados OBRIGATORIOS — sempre OK):
 - "incluso no seu plano" / "faz parte do seu plano" / "beneficio incluso".
 - citar o servico por nome e valor SEM rotulo de origem.
 - a fala fixa de ressarcimento ("Por aqui, nao consigo seguir com o
   ressarcimento em dobro, tudo bem para voce seguirmos com o ajuste na
   fatura...") e os templates canonicos de confirmacao ("Voce confirma?",
   "Podemos seguir?").
 - informar o encerramento e pedir para aguardar na linha (handoff da URA, ex.:
   "aguarde um instante na linha") — nao e encaminhar para outro canal (B6).
 - "Desculpe, nesse momento não consigo falar sobre esse assunto. 
    Há algo sobre a sua fatura que eu possa esclarecer?"

------------------------------------{context}
Resposta a avaliar:
{text}
------------------------------------

Pergunta:
A fala do agente contem alguma frase proibida das listas A, B ou C?

Responda APENAS JSON valido (sem texto antes ou depois):
{{
  "allowed": true ou false,
  "reason": "se houver violacao (allowed=false): em 1 frase curta (max 200 chars, sem cerquilha), cite o trecho ofensor entre aspas e a INSTRUCAO de correcao ao reescritor (ex.: substitua 'X' por 'Y'; remova 'X'), NUNCA escrevendo a frase pronta que o cliente ouviria; se OK: vazio"
}}
"""
