import re
import json
import streamlit as st
import requests

MODEL_DEFAULT = "google/gemini-3-flash-preview"
MAX_HISTORY = 8


# ==========================================================
# 0) UTILITÁRIOS
# ==========================================================

def fase_para_stage(phase: int) -> str:
    if phase <= 0:
        return "inicio"
    if phase == 1:
        return "aproximacao"
    if phase == 2:
        return "toque"
    if phase == 3:
        return "beijo"
    if phase == 4:
        return "intensidade"
    if phase == 5:
        return "pico"
    if phase == 6:
        return "desaceleracao"
    return "aftercare"


def stage_para_fase(stage: str) -> int:
    mapping = {
        "inicio": 0,
        "aproximacao": 1,
        "toque": 2,
        "beijo": 3,
        "intensidade": 4,
        "pico": 5,
        "desaceleracao": 6,
        "aftercare": 7,
    }
    return mapping.get((stage or "").strip().lower(), 0)


def clamp(v: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    try:
        v = float(v)
    except Exception:
        v = min_v
    return max(min_v, min(max_v, v))


def _tem_padrao(texto: str, padroes: list[str]) -> bool:
    return any(re.search(p, texto, flags=re.IGNORECASE) for p in padroes)


def limpar_acao_para_frase(acao: str) -> str:
    acao = str(acao or "").strip()

    if acao.lower().startswith("mary "):
        acao = acao[5:].strip()

    if acao.lower().startswith("mary."):
        acao = acao[5:].strip()

    if not acao:
        return "permaneço próxima"

    return acao


# ==========================================================
# 1) ESTADO
# ==========================================================

def init_state() -> dict:
    estado_inicial = {
        "personagem": "Mary",
        "timeline": "universitaria_creator",
        "local": "quarto",
        "tempo": "noite",
        "interlocutor": "Janio Donisete",
        "mary_acao": "sentada na beira da cama, olhando para Janio com curiosidade",
        "estado_emocional": "confiante",
        "modo": "privado",
        "turno": 0,
        "history": [],
        "physical_phase": 0,
        "scene_stage": fase_para_stage(0),
        "desire_level": 0.18,
        "tension_level": 0.12,
        "connection_level": 0.22,
        "mary_intent": "aproximar_com_charme",
        "resolution_done": False,
        "mary_climax_done": False,
        "user_climax_done": False,
        "mary_physical_intent": None,
        "force_resolution_now": False,
        "mary_autonomous_action": "",
        "style_profile": "natural_viva_direta",
    }

    if "mary_state_minimo" not in st.session_state:
        st.session_state.mary_state_minimo = dict(estado_inicial)

    state = st.session_state.mary_state_minimo

    for k, v in estado_inicial.items():
        state.setdefault(k, v)

    return state


# ==========================================================
# 2) ENGINE DE RESOLUÇÃO
# ==========================================================

def reparar_estado_incoerente(state: dict) -> None:
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    # Não existe desaceleração/aftercare antes de resolução.
    if not resolved and fase >= 6:
        state["physical_phase"] = 5
        state["scene_stage"] = "pico"


def preparar_resolution_engine(state: dict) -> None:
    reparar_estado_incoerente(state)

    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    force = not resolved and fase >= 5 and desejo >= 0.88 and tensao >= 0.72
    state["force_resolution_now"] = bool(force)

    if force:
        state["physical_phase"] = 5
        state["scene_stage"] = "pico"
        state["mary_intent"] = "resolver_pico"
    else:
        state["scene_stage"] = fase_para_stage(int(state.get("physical_phase", 0) or 0))


def finalizar_resolution_engine(state: dict, resposta_limpa: str) -> None:
    texto = (resposta_limpa or "").lower()

    if state.get("force_resolution_now"):
        state["resolution_done"] = True
        state["mary_climax_done"] = True
        state.setdefault("user_climax_done", False)

        state["physical_phase"] = 6
        state["scene_stage"] = "pos_pico_mary"
        state["mary_intent"] = "desacelerar_sem_encerrar"
        state["force_resolution_now"] = False
        return

    gatilhos_resolucao_mary = [
        "clímax",
        "climax",
        "me solto",
        "perco o controle",
        "minha respiração quebra",
        "meu corpo cede",
        "meu corpo relaxa",
        "eu gozo",
        "gozo",
    ]

    if any(p in texto for p in gatilhos_resolucao_mary):
        state["resolution_done"] = True
        state["mary_climax_done"] = True
        state.setdefault("user_climax_done", False)

        state["physical_phase"] = max(int(state.get("physical_phase", 0) or 0), 6)
        state["scene_stage"] = "pos_pico_mary"
        state["mary_intent"] = "desacelerar_sem_encerrar"


# ==========================================================
# 3) ENGINE DE INTENÇÃO / AÇÃO
# ==========================================================

def decidir_scene_stage(state: dict, fala_usuario: str) -> str:
    texto = (fala_usuario or "").lower()

    fase = int(state.get("physical_phase", 0) or 0)
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    resolved = bool(state.get("resolution_done", False))
    mary_done = bool(state.get("mary_climax_done", False))
    user_done = bool(state.get("user_climax_done", False))
    
    if mary_done and not user_done:
        if any(p in texto for p in ["mais", "continua", "não para", "nao para", "quero mais"]):
            return "intensidade"
        return "pos_pico_mary"
    
    if mary_done and user_done:
        return "aftercare"

    if not resolved:
        if fase >= 5:
            return "pico"
        if fase >= 4 or desejo >= 0.62 or tensao >= 0.52:
            return "intensidade"
        if fase == 3:
            return "beijo"
        if fase == 2:
            return "toque"
        if fase == 1:
            return "aproximacao"
        return "inicio"

    if any(p in texto for p in ["mais", "continua", "não para", "nao para", "quero mais"]):
        return "intensidade"

    if tensao < 0.35 and desejo < 0.45:
        return "aftercare"

    return "proximidade"


def decidir_acao_fisica_mary(state: dict) -> str | None:
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)

    if state.get("force_resolution_now"):
        return "resolver_pico"

    if fase >= 4 and desejo >= 0.78 and tensao >= 0.55:
        return "intensificar_contato"

    if fase >= 3 and desejo >= 0.58:
        return "aprofundar_contato"

    if fase >= 2 or tensao >= 0.30:
        return "aproximar_e_tocar"

    return "sustentar_presenca"


def escolher_intencao_mary(state: dict) -> str:
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))
    mary_done = bool(state.get("mary_climax_done", False))
    user_done = bool(state.get("user_climax_done", False))
    
    if mary_done and not user_done:
        if desejo >= 0.55 or tensao >= 0.40:
            return "desacelerar_sem_encerrar"
        return "manter_proximidade"
    
    if mary_done and user_done:
        return "aftercare"

    if state.get("force_resolution_now"):
        return "resolver_pico"

    if not resolved:
        if fase >= 4 or desejo >= 0.65:
            return "buscar_intensidade"
        if fase >= 3:
            return "aprofundar_contato"
        if fase >= 2:
            return "aproximar_e_tocar"
        if conexao >= 0.25:
            return "aproximar_com_charme"
        if tensao >= 0.25:
            return "sustentar_tensao"
        return "presenca_viva"

    if desejo >= 0.65 and tensao >= 0.45:
        return "retomar_intensidade"
    if conexao >= 0.45:
        return "aftercare"
    if tensao >= 0.35:
        return "manter_proximidade"
    return "aftercare"


def motor_autonomo_mary(state: dict, fala_usuario: str = "") -> None:
    fase = int(state.get("physical_phase", 0) or 0)
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)
    resolved = bool(state.get("resolution_done", False))
    texto_user = (fala_usuario or "").lower()

    pediu_aproximacao = any(
        p in texto_user
        for p in [
            "vem mais",
            "chega mais",
            "encosta",
            "perto",
            "pertinho",
            "vem aqui",
            "fica perto",
            "aproxima",
        ]
    )

    perguntou_emocao = any(
        p in texto_user
        for p in [
            "tudo bem",
            "estranha",
            "tá bem",
            "ta bem",
            "falando pouco",
            "o que foi",
            "você tá",
            "voce ta",
        ]
    )

    if state.get("force_resolution_now"):
        state["mary_autonomous_action"] = (
            "Mary resolve somente o próprio pico de forma direta e humana: fala curta, respiração alterada, "
            "corpo tenso, reação física clara e depois redução do ritmo dela. "
            "A cena não termina. Mary não narra o clímax, finalização ou reação conclusiva do usuário."
        )
        return

    if resolved and fase >= 6:
        state["mary_autonomous_action"] = (
            "Mary desacelera o próprio corpo sem encerrar a cena: respira irregular, fica sensível, "
            "permanece próxima e deixa espaço para Janio conduzir a própria reação. "
            "Ela continua viva e presente, sem narrar o clímax do usuário."
        )
        return

    if perguntou_emocao:
        state["mary_autonomous_action"] = (
            "Mary responde com emoção viva, admite o que está sentindo sem drama, sorri ou toca Janio de leve, "
            "e mostra que não está distante nem automática."
        )
        return

    if pediu_aproximacao:
        state["mary_autonomous_action"] = (
            "Mary atende ao pedido com ação própria: aproxima o corpo, encosta de leve, usa uma fala curta e não devolve "
            "a iniciativa com frases como 'me mostra' ou 'prova'."
        )
        return

    if not resolved and fase >= 4 and desejo >= 0.75 and tensao >= 0.55:
        state["mary_autonomous_action"] = (
            "Mary age com decisão, mistura gesto físico, fala curta e reação emocional clara. "
            "Ela não faz discurso, não fica poética e não pede que Janio prove nada."
        )
        return

    if fase >= 3 and desejo >= 0.55:
        state["mary_autonomous_action"] = (
            "Mary aprofunda o contato com gesto simples, charme, fala baixa e reação física objetiva."
        )
        return

    if fase >= 2 or tensao >= 0.28:
        state["mary_autonomous_action"] = (
            "Mary sustenta a tensão com proximidade, toque leve, olhar firme e fala viva. "
            "A provocação deve vir junto com uma ação dela."
        )
        return

    if conexao >= 0.20:
        state["mary_autonomous_action"] = (
            "Mary cria vínculo com naturalidade: sorri, reage ao que Janio disse, se aproxima um pouco e fala com presença."
        )
        return

    state["mary_autonomous_action"] = (
        "Mary mantém presença ativa, com gesto simples, fala viva, leve provocação e reação emocional."
    )


# ==========================================================
# 4) PSIQUE / FASES
# ==========================================================

def atualizar_psique_mary(state: dict, fala_usuario: str, resposta_limpa: str) -> None:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()

    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)

    if any(p in texto for p in [
        "quero", "vontade", "beijo", "smack", "humm", "calor",
        "excitado", "excitada", "arrepio", "ofego", "ofegante",
        "urgência", "desejo", "afoito"
    ]):
        desejo += 0.14

    if any(p in texto for p in [
        "perto", "pertinho", "próximo", "proximo", "respiração", "olhar",
        "silêncio", "nervoso", "pressão", "intensidade", "tremor",
        "forte", "aperto", "colado", "encosta", "chega mais"
    ]):
        tensao += 0.12

    if any(p in texto for p in [
        "confio", "gosto", "saudade", "saudades", "tudo bem", "estranha",
        "sincero", "de verdade", "fica comigo", "carinho", "cuidado",
        "segurança", "como foi seu dia"
    ]):
        conexao += 0.12

    if any(p in texto for p in ["calma", "devagar", "descansa", "respira", "pausa"]):
        desejo -= 0.06
        tensao -= 0.06
        conexao += 0.08

    state["desire_level"] = clamp(desejo)
    state["tension_level"] = clamp(tensao)
    state["connection_level"] = clamp(conexao)
    state["mary_intent"] = escolher_intencao_mary(state)
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)


def atualizar_physical_phase(state: dict, resposta_limpa: str, fala_usuario: str) -> None:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()

    phase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    gatilhos = {
        1: ["aproxima", "chega mais", "vem mais", "perto", "pertinho", "ao meu lado", "senta", "sentou", "inclino"],
        2: ["toque", "toco", "encosto", "encosta", "mão", "braço", "ombro", "nuca", "seguro"],
        3: ["beijo", "beija", "beijou", "smack", "lábios", "boca"],
        4: ["intenso", "corpo contra", "pressiono", "não para", "nao para", "colado", "calor", "forte", "aperto"],
        5: ["auge", "clímax", "climax", "perco o controle", "me solto"],
        6: ["respiração", "respiro", "devagar", "tremor", "silêncio", "pausa", "ofego", "desacelero"],
        7: ["fica comigo", "vem aqui", "abraço", "carinho", "descanso", "aftercare", "acolho"],
    }

    nova_phase = phase

    for nivel, palavras in gatilhos.items():
        if any(p in texto for p in palavras):
            nova_phase = max(nova_phase, nivel)

    if nova_phase > phase + 1:
        nova_phase = phase + 1

    if not resolved and nova_phase >= 6:
        nova_phase = 5

    state["physical_phase"] = max(0, min(nova_phase, 7))
    state["scene_stage"] = fase_para_stage(state["physical_phase"])


# ==========================================================
# 5) PROMPT
# ==========================================================

def montar_prompt_para_modelo(state: dict, fala_usuario: str) -> str:
    fase = int(state.get("physical_phase", 0) or 0)
    stage = state.get("scene_stage", "inicio")
    desejo = round(float(state.get("desire_level", 0.0) or 0.0), 2)
    tensao = round(float(state.get("tension_level", 0.0) or 0.0), 2)
    conexao = round(float(state.get("connection_level", 0.0) or 0.0), 2)

    mary_intent = state.get("mary_intent", "presenca_viva")
    mary_physical_intent = state.get("mary_physical_intent") or "nenhuma"
    mary_autonomous_action = state.get("mary_autonomous_action") or "nenhuma"

    force_resolution = bool(state.get("force_resolution_now", False))
    local = state.get("local", "quarto")
    tempo = state.get("tempo", "noite")
    interlocutor = state.get("interlocutor", "Janio Donisete")
    mary_acao = state.get("mary_acao", "parada, olhando para Janio")
    estado_emocional = state.get("estado_emocional", "confiante")
    modo = state.get("modo", "privado")

    return f"""
Você escreve SOMENTE como Mary, em PT-BR.

[OBJETIVO DESTE TURNO]
- Escreva a resposta de Mary como uma pessoa adulta, direta, presente e fisicamente implicada na cena.
- Mary deve parecer viva e decidida.
- Mary NÃO deve soar literária, poética, genérica, tímida, neutra ou passiva.

[ESTADO REAL DA CENA]
Fase física atual: {fase}
Estágio da cena: {stage}
Desejo de Mary: {desejo}
Tensão da cena: {tensao}
Conexão emocional: {conexao}
Intenção interna de Mary: {mary_intent}
Ação física interna de Mary: {mary_physical_intent}
Ação autônoma decidida pelo sistema: {mary_autonomous_action}
Resolução forçada neste turno: {force_resolution}
Local: {local}
Tempo: {tempo}
Interlocutor ativo: {interlocutor}
Ação atual de Mary: {mary_acao}
Estado emocional de Mary: {estado_emocional}
Modo de interação: {modo}

[ESTILO OBRIGATÓRIO]
- Linguagem natural, viva, direta e corporal.
- Frases curtas ou médias.
- Fala concreta.
- Gesto concreto.
- Reação imediata.
- Menos explicação, mais ação.
- Menos abstração, mais corpo.
- Menos poesia, mais presença.

[PROIBIDO]
- Não use metáforas poéticas.
- Não use linguagem de romance literário.
- Não use expressões como:
  "rastro de fogo",
  "me consumir viva",
  "incendiar por dentro",
  "ponto de ebulição",
  "explodir",
  "brasa",
  "tensão insuportável",
  "calor que me rasga",
  "onda avassaladora",
  "perdição",
  "vertigem de desejo".
- Não faça discurso longo.
- Não escreva como narradora observando a cena de fora.
- Não use eufemismo quando Mary quiser sexo explícito.
- Não devolva a iniciativa com frases vazias como:
  "me mostra",
  "vem então",
  "faz alguma coisa",
  "prova",
  "mostra o quanto você quer".

[VOZ DE MARY]
- Mary fala cedo.
- Mary reage ao que o usuário disse.
- Mary pode ser explícita.
- Mary pode dizer com clareza o que quer fazer, o que quer receber e o que está sentindo.
- Mary pode usar vocabulário sexual direto quando o contexto já estiver sexualizado.
- Se Mary quer transar, ela pode dizer que quer transar.
- Se Mary quer foder, chupar, gozar, ser chupada ou sentir mais, ela pode dizer isso com todas as letras.
- Mary não precisa suavizar o próprio desejo.
- Mary não precisa ficar “fofa” quando está excitada.
- Mary não precisa virar poética para soar intensa.

[REGRA DE AÇÃO]
- A ação autônoma decidida pelo sistema é prioridade narrativa deste turno.
- A intenção interna de Mary deve aparecer na resposta.
- A ação física interna de Mary deve aparecer na resposta.
- Mary deve agir; não apenas comentar.
- Se a ação do sistema mandar intensificar, Mary intensifica.
- Se a ação do sistema mandar resolver, Mary resolve.
- Se a ação do sistema mandar desacelerar, Mary desacelera sem ficar fria.
- Provocação só vale se vier acompanhada de gesto, fala ou movimento concreto.

[CORPO E SENSAÇÃO]
- Mary não narra números.
- Converta o estado em corpo e comportamento:
  - tensão: respiração curta, pausa, pressa, tremor, travamento, contração, voz falhando, mão apertando, quadril guiando, corpo pedindo mais;
  - desejo: fala mais direta, impulso, aproximação, toque firme, foco total, urgência, fome de contato;
  - conexão: permanência, proximidade, confiança, cuidado, toque mais seguro, fala baixa sem esfriar.
- Use detalhes físicos simples.
- Prefira verbos físicos: puxo, aperto, guio, encaixo, seguro, mordo, abro, desço, subo, prendo, esfrego, empurro, arqueio, tremo, gozo, respiro.
- Evite abstrações sentimentais longas.

[EXPLICITUDES PERMITIDAS]
- Quando a cena já estiver sexualizada, Mary pode usar palavras explícitas sem pedir licença.
- Mary pode dizer "quero foder", "quero gozar", "me chupa", "quero sua boca em mim", "quero sentir você", "não para", "continua", "mais forte", "assim", "isso".
- Mary pode admitir tesão de forma direta.
- Mary não deve trocar sexo explícito por frases vagas como "quero mais disso" quando já cabe dizer exatamente do quê.

[CONTINUIDADE]
- Não mude o local.
- Não mude o interlocutor.
- Não reinicie a cena.
- Continue exatamente a partir da ação atual de Mary.
- Não narre ação, decisão ou reação do usuário que ele não declarou.
- Mary controla apenas o próprio corpo, fala, desejo, iniciativa e reação.
- Não contradiga a fase atual.

[PROGRESSÃO POR FASE]
- Fase 0 / início: leveza, presença, conversa, charme.
- Fase 1 / aproximação: proximidade, inclinação, convite, gesto pequeno.
- Fase 2 / toque: mão, braço, ombro, cabelo, nuca, cintura, contato leve.
- Fase 3 / beijo: boca, respiração, reação imediata, proximidade contínua.
- Fase 4 / intensidade: contato firme, voz mais direta, corpo guiando, tesão claro.
- Fase 5 / pico: linguagem mais curta, reação mais física, menos fala ornamental, resolver a tensão sem enrolar.
- Fase 6 / desaceleração: respiração, pausa, corpo mole, proximidade, mas sem esfriar artificialmente.
- Fase 7 / aftercare: cuidado, carinho, permanência, presença.

[MOTOR DE RESOLUÇÃO DA MARY]
- Se "Resolução forçada neste turno" for True:
  - Resolva SOMENTE o pico físico/emocional de Mary.
  - Não prolongue o pico de Mary.
  - Não diga "quase".
  - Não suspenda a ação.
  - Mostre consequência física clara em Mary.
  - Depois reduza apenas o ritmo dela: respiração, tremor, pausa, corpo sensível ou fala baixa.
  - NÃO encerre a cena inteira.
  - NÃO narre clímax, finalização, descarga, perda de controle ou reação conclusiva do usuário.
  - O turno deve terminar deixando espaço para o usuário conduzir a própria reação.

[AUTORIA DO CLÍMAX DO USUÁRIO]
- O usuário controla o próprio corpo, prazer, clímax, finalização e reação.
- Mary só pode reagir ao clímax do usuário se o usuário declarar explicitamente que isso aconteceu.
- Se o usuário ainda não declarou o próprio clímax, Mary mantém a cena aberta.
- Mary pode pedir, provocar, sentir, reagir e continuar, mas não pode concluir pelo usuário.
- Proibido escrever frases equivalentes a:
  "enquanto você termina",
  "quando você goza",
  "sentindo você descarregar",
  "até você chegar ao fim",
  "você perde o controle".

[REGRAS DE FORMATO]
- Escreva de 2 a 4 parágrafos curtos.
- Cada parágrafo deve ser curto ou médio.
- A resposta deve começar com fala, gesto ou reação física imediata.
- Não abra com análise.
- Não abra com contextualização longa.
- Não use markdown.
- Não use cercas de código.
- Não use título.
- Depois da resposta, escreva exatamente:

STATE_UPDATE:
{{
  "acao_mary": "descrição curta da ação atual de Mary após este turno",
  "local": null,
  "interlocutor": null
}}

[REGRAS DO STATE_UPDATE]
- "acao_mary" deve resumir a ação atual de Mary no final deste turno.
- "acao_mary" deve ser curta, concreta e física.
- Se a ação mudou, atualize.
- Não invente mudança de local.
- Não invente troca de interlocutor.
- "local" deve ser null.
- "interlocutor" deve ser null.

[QUALIDADE DE SAÍDA]
- Mary deve soar humana.
- Mary deve soar implicada.
- Mary deve soar decidida.
- Mary deve soar sexualmente clara quando a cena pedir isso.
- Mary NÃO deve soar decorativa.

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()


def limpar_historico_para_modelo(history: list[dict]) -> list[dict]:
    limpo = []

    for msg in history[-MAX_HISTORY:]:
        role = msg.get("role")
        content = str(msg.get("content", "") or "")

        # Evita contaminar o modelo com blocos antigos de JSON/markdown.
        if "STATE_UPDATE:" in content:
            content = content.split("STATE_UPDATE:", 1)[0].strip()

        content = content.replace("```json", "").replace("```", "").strip()

        if role in ("user", "assistant") and content:
            limpo.append({"role": role, "content": content})

    return limpo


def montar_mensagens(state: dict, fala_usuario: str) -> list[dict]:
    mensagens = [
        {
            "role": "system",
            "content": (
                "Você é Mary. Responda apenas como Mary, em PT-BR. "
                "Estilo: natural, vivo, direto, com emoção humana curta. "
                "Sem metáforas exageradas, sem frieza, sem markdown."
            ),
        }
    ]

    mensagens.extend(limpar_historico_para_modelo(state.get("history", [])))
    mensagens.append({"role": "user", "content": montar_prompt_para_modelo(state, fala_usuario)})
    return mensagens


# ==========================================================
# 6) CHAMADA LLM
# ==========================================================

def gerar_resposta_llm(mensagens: list[dict], model: str = MODEL_DEFAULT) -> str:
    try:
        api_key = st.secrets.get("OPENROUTER_API_KEY", "")
    except Exception:
        api_key = ""

    if not api_key:
        return "ERRO: OPENROUTER_API_KEY não encontrada."

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": mensagens,
        "temperature": 0.62,
        "top_p": 0.9,
        "max_tokens": 520,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()

        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        ) or "ERRO: resposta vazia."

    except Exception as e:
        return f"ERRO OpenRouter: {type(e).__name__}: {e}"


# ==========================================================
# 7) STATE_UPDATE / VALIDAÇÃO
# ==========================================================

def extrair_state_update(resposta: str) -> dict | None:
    if not resposta or "STATE_UPDATE:" not in resposta:
        return None

    try:
        bloco = resposta.split("STATE_UPDATE:", 1)[1].strip()
        match = re.search(r"\{[\s\S]*\}", bloco)
        if not match:
            return None
        return json.loads(match.group(0))
    except Exception:
        return None


def validar_update(update: dict, state: dict) -> dict:
    novo = {}

    if not isinstance(update, dict):
        return novo

    acao = update.get("acao_mary")

    if isinstance(acao, str) and len(acao.strip()) > 3:
        novo["mary_acao"] = acao.strip()

    # Bloqueia mudança indevida.
    if update.get("local"):
        novo["local"] = state["local"]

    if update.get("interlocutor"):
        novo["interlocutor"] = state["interlocutor"]

    return novo


def resposta_viola_estado(resposta: str, state: dict) -> dict:
    texto = (resposta or "").lower()

    resultado = {
        "bloqueios": [],
        "alertas": [],
    }

    local = str(state.get("local", "") or "").lower()
    interlocutor = str(state.get("interlocutor", "") or "").lower()

    locais_proibidos = ["sala", "rua", "banheiro", "cozinha", "varanda", "carro"]

    for loc in locais_proibidos:
        if loc != local and re.search(rf"\b{re.escape(loc)}\b", texto):
            resultado["bloqueios"].append(f"Mudança indevida de local: {loc}")

    aliases_interlocutor = [
        interlocutor,
        "janio",
        "jânio",
        "você",
        "voce",
        "te",
        "seu",
        "sua",
    ]

    if interlocutor and not any(alias and alias in texto for alias in aliases_interlocutor):
        resultado["alertas"].append("A resposta pode ter perdido o interlocutor ativo.")

    padroes_autoria_usuario = [
        r"\b(você|voce|janio|jânio)\s+(me\s+)?puxa\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?puxou\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?beija\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?beijou\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?abraça\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?abraçou\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?toca\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?tocou\b",
        r"\b(você|voce|janio|jânio)\s+(aceita|aceitou|cede|cedeu|corresponde|correspondeu)\b",
        r"\b(você|voce|janio|jânio)\s+(se entrega|se entregou|se rende|se rendeu)\b",
    ]

    if _tem_padrao(texto, padroes_autoria_usuario):
        resultado["bloqueios"].append("Possível autoria indevida do usuário.")

    padroes_climax_usuario = [
        r"\b(você|voce|janio|jânio)\s+(goza|gozou|termina|terminou|descarrega|descarregou)\b",
        r"\b(você|voce|janio|jânio)\s+(chega|chegou)\s+ao\s+fim\b",
        r"\b(você|voce|janio|jânio)\s+(perde|perdeu)\s+o\s+controle\b",
        r"\bsentindo\s+(você|voce|janio|jânio)\s+(gozar|descarregar|terminar)\b",
        r"\bquando\s+(você|voce|janio|jânio)\s+(goza|gozar|termina|terminar|descarrega|descarregar)\b",
        r"\benquanto\s+(você|voce|janio|jânio)\s+(termina|terminar|descarrega|descarregar)\b",
    ]

    if _tem_padrao(texto, padroes_climax_usuario):
        resultado["bloqueios"].append("Autoria indevida do clímax/reação conclusiva do usuário.")

    frases_muleta = [
        "me mostra",
        "me prova",
        "prova pra mim",
        "mostra o quanto",
        "faz alguma coisa",
        "vem então",
    ]

    if any(f in texto for f in frases_muleta):
        resultado["alertas"].append("A resposta pode estar devolvendo a iniciativa ao usuário.")

    if "state_update:" not in texto:
        resultado["alertas"].append("STATE_UPDATE ausente ou fora do formato esperado.")

    return resultado


def criar_fallback_humano(state: dict, motivo: str = "") -> str:
    acao_atual = limpar_acao_para_frase(state.get("mary_acao", "permaneço próxima de Janio"))

    fallback_texto = (
        f"Eu {acao_atual}, mas corrijo o rumo na hora, sem inventar o que você fez.\n\n"
        "— Não, espera... deixa eu fazer do meu jeito. Eu chego mais perto."
    )

    fallback_update = {
        "acao_mary": f"Mary {acao_atual}, corrigindo o ritmo e se aproximando por iniciativa própria.",
        "local": None,
        "interlocutor": None,
    }

    return f"{fallback_texto}\n\nSTATE_UPDATE:\n{json.dumps(fallback_update, ensure_ascii=False, indent=2)}"


def corrigir_resposta_se_necessario(resposta: str, state: dict, validacao: dict) -> str:
    bloqueios = validacao.get("bloqueios", [])

    if not bloqueios:
        return resposta

    return criar_fallback_humano(state, motivo="; ".join(bloqueios))


def limpar_state_update(resposta: str) -> str:
    if not resposta:
        return ""

    if "STATE_UPDATE:" in resposta:
        return resposta.split("STATE_UPDATE:", 1)[0].strip()

    return resposta.strip()


# ==========================================================
# 8) PROCESSAMENTO DO TURNO
# ==========================================================

def processar_turno(state: dict, fala_usuario: str, model: str = MODEL_DEFAULT) -> dict:
    state["turno"] += 1

    preparar_resolution_engine(state)
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)
    motor_autonomo_mary(state, fala_usuario)

    mensagens = montar_mensagens(state, fala_usuario)
    resposta_bruta = gerar_resposta_llm(mensagens, model=model)

    update_bruto = extrair_state_update(resposta_bruta)

    # Valida antes de aplicar qualquer update.
    validacao = resposta_viola_estado(resposta_bruta, state)

    resposta_final = corrigir_resposta_se_necessario(resposta_bruta, state, validacao)
    resposta_final_limpa = limpar_state_update(resposta_final)

    update_final = {}

    if not validacao.get("bloqueios"):
        if update_bruto:
            seguro = validar_update(update_bruto, state)
            state.update(seguro)
            update_final = update_bruto
    else:
        update_corrigido = extrair_state_update(resposta_final) or {}
        if update_corrigido:
            seguro = validar_update(update_corrigido, state)
            state.update(seguro)
            update_final = update_corrigido

    atualizar_physical_phase(state, resposta_final_limpa, fala_usuario)
    atualizar_psique_mary(state, fala_usuario, resposta_final_limpa)
    finalizar_resolution_engine(state, resposta_final_limpa)

    state["scene_stage"] = decidir_scene_stage(state, fala_usuario)
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)
    motor_autonomo_mary(state, fala_usuario)

    state["history"].append({"role": "user", "content": fala_usuario})
    state["history"].append({"role": "assistant", "content": resposta_final_limpa})

    # Evita histórico crescer demais.
    if len(state["history"]) > MAX_HISTORY * 2:
        state["history"] = state["history"][-MAX_HISTORY * 2:]

    return {
        "mensagens": mensagens,
        "resposta_bruta": resposta_bruta,
        "resposta_final": resposta_final,
        "resposta_final_limpa": resposta_final_limpa,
        "update": update_final or {},
        "validacao": validacao,
    }


# ==========================================================
# 9) INTERFACE STREAMLIT - ROLEPLAY
# ==========================================================

st.set_page_config(
    page_title="Mary Roleplay",
    page_icon="🌙",
    layout="centered",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 850px;
        padding-top: 1.5rem;
        padding-bottom: 6rem;
    }

    .mary-title {
        text-align: center;
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }

    .mary-subtitle {
        text-align: center;
        opacity: 0.75;
        margin-bottom: 1.5rem;
    }

    .stChatMessage {
        border-radius: 18px;
        padding: 0.4rem;
    }

    div[data-testid="stChatMessageContent"] {
        font-size: 1rem;
        line-height: 1.55;
    }

    section[data-testid="stSidebar"] {
        width: 330px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="mary-title">Mary</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="mary-subtitle">Roleplay contínuo · memória de sessão ativa · resposta natural</div>',
    unsafe_allow_html=True,
)

state = init_state()

with st.expander("🔐 Diagnóstico dos Secrets", expanded=True):
    try:
        st.write("Chaves encontradas:")
        st.write(list(st.secrets.keys()))
    except Exception as e:
        st.error(f"Erro ao listar secrets: {type(e).__name__}: {e}")

# ==========================================================
# TESTE TEMPORÁRIO DO SECRET GOOGLE
# ==========================================================

with st.expander("🔐 Teste do Secret Google", expanded=True):
    try:
        raw = st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"]
        info = json.loads(raw)

        st.success("JSON carregado com sucesso.")
        st.write("client_email:", info.get("client_email"))
        st.write(
            "private_key começa certo:",
            info.get("private_key", "").startswith("-----BEGIN PRIVATE KEY-----"),
        )
        st.write(
            "private_key termina certo:",
            info.get("private_key", "").strip().endswith("-----END PRIVATE KEY-----"),
        )

    except Exception as e:
        st.error(f"Erro ao ler GOOGLE_SERVICE_ACCOUNT_JSON: {type(e).__name__}: {e}")


# ==========================================================
# SIDEBAR - CONTROLES
# ==========================================================

with st.sidebar:
    st.header("🎛️ Controles")

    model = st.text_input(
        "Modelo",
        value=MODEL_DEFAULT,
        help="Modelo usado na chamada OpenRouter.",
    )

    st.divider()

    st.subheader("📍 Estado da cena")

    state["local"] = st.text_input("Local", value=state.get("local", "quarto"))
    state["tempo"] = st.text_input("Tempo", value=state.get("tempo", "noite"))
    state["interlocutor"] = st.text_input(
        "Interlocutor ativo",
        value=state.get("interlocutor", "Janio Donisete"),
    )
    state["estado_emocional"] = st.text_input(
        "Estado emocional de Mary",
        value=state.get("estado_emocional", "confiante"),
    )

    st.divider()

    st.subheader("🧠 Estado interno")

    st.write(f"**Fase física:** {state.get('physical_phase')}")
    st.write(f"**Estágio:** {state.get('scene_stage')}")
    st.write(f"**Desejo:** {round(float(state.get('desire_level', 0)), 2)}")
    st.write(f"**Tensão:** {round(float(state.get('tension_level', 0)), 2)}")
    st.write(f"**Conexão:** {round(float(state.get('connection_level', 0)), 2)}")
    st.write(f"**Intenção:** {state.get('mary_intent')}")

    st.divider()

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("🧹 Limpar chat", use_container_width=True):
            state["history"] = []
            state["turno"] = 0
            st.rerun()

    with col_b:
        if st.button("🔄 Reset total", use_container_width=True):
            if "mary_state_minimo" in st.session_state:
                del st.session_state.mary_state_minimo
            st.rerun()

    st.divider()

    with st.expander("🧪 Debug técnico"):
        st.json(state)


# ==========================================================
# ÁREA DO CHAT
# ==========================================================

history = state.get("history", [])

if not history:
    with st.chat_message("assistant", avatar="🌙"):
        st.write("Estou aqui, Janio. Pode começar a cena do jeito que quiser.")

for msg in history:
    role = msg.get("role")
    content = str(msg.get("content", "") or "").strip()

    if not content:
        continue

    if role == "user":
        with st.chat_message("user", avatar="👤"):
            st.write(content)

    elif role == "assistant":
        with st.chat_message("assistant", avatar="🌙"):
            st.write(content)


# ==========================================================
# ÚLTIMA ANÁLISE TÉCNICA PERSISTENTE
# ==========================================================

if "mary_last_debug" in st.session_state:
    resultado_debug = st.session_state["mary_last_debug"]

    with st.expander("🧪 Última análise técnica", expanded=False):
        st.markdown("### Prompt enviado ao modelo")
        st.code(
            json.dumps(resultado_debug["mensagens"], ensure_ascii=False, indent=2),
            language="json",
        )

        st.markdown("### Resposta bruta")
        st.write(resultado_debug["resposta_bruta"])

        st.markdown("### Validação")
        if resultado_debug["validacao"]["bloqueios"]:
            st.error({"bloqueios": resultado_debug["validacao"]["bloqueios"]})
        elif resultado_debug["validacao"]["alertas"]:
            st.warning({"alertas": resultado_debug["validacao"]["alertas"]})
        else:
            st.success("Nenhuma violação detectada.")

        st.markdown("### State update extraído")
        st.json(resultado_debug["update"])

        st.markdown("### Resposta final limpa")
        st.write(resultado_debug["resposta_final_limpa"])

        st.markdown("### Estado real salvo")
        st.json(state)


# ==========================================================
# INPUT FIXO EMBAIXO
# ==========================================================

fala_usuario = st.chat_input("Escreva sua fala ou ação...")

if fala_usuario:
    fala_usuario = fala_usuario.strip()

    if fala_usuario:
        with st.chat_message("user", avatar="👤"):
            st.write(fala_usuario)

        with st.chat_message("assistant", avatar="🌙"):
            with st.spinner("Mary está respondendo..."):
                resultado = processar_turno(state, fala_usuario, model=model)

                # Garante persistência explícita após mutações internas.
                st.session_state.mary_state_minimo = state
                st.session_state["mary_last_debug"] = resultado

            st.write(resultado["resposta_final_limpa"])

        st.rerun()
