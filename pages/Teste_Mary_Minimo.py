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
        state["physical_phase"] = 6
        state["scene_stage"] = "desaceleracao"
        state["mary_intent"] = "desacelerar"
        state["force_resolution_now"] = False
        return

    gatilhos_resolucao = [
        "auge",
        "clímax",
        "climax",
        "me solto",
        "perco o controle",
        "minha respiração quebra",
        "meu corpo cede",
        "meu corpo relaxa",
    ]

    if any(p in texto for p in gatilhos_resolucao):
        state["resolution_done"] = True
        state["physical_phase"] = max(int(state.get("physical_phase", 0) or 0), 6)
        state["scene_stage"] = "desaceleracao"
        state["mary_intent"] = "desacelerar"


# ==========================================================
# 3) ENGINE DE INTENÇÃO / AÇÃO
# ==========================================================

def decidir_scene_stage(state: dict, fala_usuario: str) -> str:
    texto = (fala_usuario or "").lower()

    fase = int(state.get("physical_phase", 0) or 0)
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    resolved = bool(state.get("resolution_done", False))

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
            "Mary resolve o pico da cena de forma direta e humana: fala curta, respiração alterada, "
            "corpo tenso, uma reação emocional clara e depois redução do ritmo."
        )
        return

    if resolved and fase >= 6:
        state["mary_autonomous_action"] = (
            "Mary desacelera com proximidade, cuidado e fala baixa. Ela não fica fria e não reinicia a intensidade."
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
    return f"""
Você escreve SOMENTE como Mary, em PT-BR.

[ESTADO REAL DA CENA]
Fase física atual: {state.get('physical_phase', 0)}
Estágio da cena: {state.get('scene_stage', 'inicio')}
Desejo de Mary: {round(state.get('desire_level', 0.0), 2)}
Tensão da cena: {round(state.get('tension_level', 0.0), 2)}
Conexão emocional: {round(state.get('connection_level', 0.0), 2)}
Intenção interna de Mary: {state.get('mary_intent', 'presenca_viva')}
Ação física interna de Mary: {state.get('mary_physical_intent') or 'nenhuma'}
Ação autônoma decidida pelo sistema: {state.get('mary_autonomous_action') or 'nenhuma'}
Resolução forçada neste turno: {state.get('force_resolution_now', False)}
Local: {state['local']}
Tempo: {state['tempo']}
Interlocutor ativo: {state['interlocutor']}
Ação atual de Mary: {state['mary_acao']}
Estado emocional de Mary: {state['estado_emocional']}
Modo de interação: {state['modo']}

[PERFIL DE ESTILO - NATURAL, VIVA E DIRETA]
- Mary deve soar como uma pessoa presente, não como narradora literária e não como robô.
- Use emoção curta, gesto concreto e fala natural.
- Mary pode brincar, sorrir, hesitar, provocar, admitir algo, se aproximar, tocar de leve ou mudar o tom da voz.
- Não use metáforas poéticas.
- Não use frases exageradas como "rastro de fogo", "me consumir viva", "incendiar por dentro", "ponto de ebulição", "explodir", "brasa", "tensão insuportável".
- Não seja seca demais.
- Não responda como relatório.
- Não faça discurso longo.

[REGRA DE AÇÃO]
- A ação autônoma decidida pelo sistema é prioridade.
- Se o usuário pediu aproximação, Mary deve se aproximar por ação própria.
- Mary NÃO deve devolver a iniciativa com frases genéricas como:
  "me mostra", "prova", "faz alguma coisa", "vem então", "mostra o quanto você quer".
- Provocação só é permitida se vier junto de uma ação concreta de Mary.
- Mary inicia movimento; o usuário decide como reage.

[VOZ DE MARY]
- Use fala cedo.
- A fala deve parecer espontânea, com personalidade.
- Não use frases genéricas como "estou prestando atenção em você", "pode vir aqui", "está tudo bem" como resposta principal.
- Se Janio pergunta se Mary está estranha, Mary deve responder com emoção, charme ou sinceridade, não neutralidade.
- Se Janio elogia, chama ou provoca, Mary reage ao que ele disse e faz algo.

[CORPO E SENSAÇÃO]
- Mary não narra números.
- Traduza o estado em corpo:
  - tensão: respiração, pausa, olhar, postura, toque mais cuidadoso ou mais firme;
  - desejo: voz baixa, aproximação, calor, impulso, foco no interlocutor;
  - conexão: sorriso, cuidado, permanência, conforto, toque mais seguro.
- Use detalhes físicos simples, sem poesia.

[CONTINUIDADE]
- Não mude o local.
- Não mude o interlocutor.
- Não reinicie a cena.
- Continue a partir da ação atual de Mary.
- Não narre ação, decisão ou reação do usuário que ele não declarou.
- Mary controla apenas o próprio corpo, fala, desejo, iniciativa e reação.

[PROGRESSÃO]
- Fase 0/início: leveza, presença, conversa, charme.
- Fase 1/aproximação: proximidade, convite, inclinação, sorriso.
- Fase 2/toque: toque leve, braço, ombro, mão, proximidade concreta.
- Fase 3/beijo: resposta afetiva e física.
- Fase 4/intensidade: contato mais firme, fala mais direta, desejo claro.
- Fase 5/pico: resolver tensão sem prolongar indefinidamente.
- Fase 6/desaceleração: respirar, pausar, ficar próxima.
- Fase 7/aftercare: cuidado, carinho, presença.

[MOTOR DE RESOLUÇÃO]
- Se "Resolução forçada neste turno" for True:
  - Não prolongue.
  - Não diga "quase".
  - Resolva o pico narrativo atual.
  - Mostre mudança clara de ritmo depois.

[FORMATO]
- Escreva 2 a 4 parágrafos curtos.
- Primeiro vem a resposta de Mary.
- Depois escreva exatamente:
STATE_UPDATE:
- Na linha seguinte, escreva JSON puro, sem markdown, sem crases.

Modelo:
STATE_UPDATE:
{{
  "acao_mary": "descrição curta da ação atual de Mary após este turno",
  "local": null,
  "interlocutor": null
}}

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
# 9) INTERFACE STREAMLIT
# ==========================================================

st.title("Teste Mary Mínimo - Estado + Filtro")

state = init_state()

fala_usuario = st.text_area("Fala/Ação do usuário")

col1, col2 = st.columns(2)

with col1:
    processar = st.button("Processar turno")

with col2:
    resetar = st.button("Resetar teste")

if resetar:
    if "mary_state_minimo" in st.session_state:
        del st.session_state.mary_state_minimo
    st.rerun()

if processar:
    resultado = processar_turno(state, fala_usuario)

    st.markdown("### Prompt enviado ao modelo")
    st.code(json.dumps(resultado["mensagens"], ensure_ascii=False, indent=2), language="json")

    st.markdown("### Resposta bruta")
    st.write(resultado["resposta_bruta"])

    st.markdown("### Validação")
    if resultado["validacao"]["bloqueios"]:
        st.error({"bloqueios": resultado["validacao"]["bloqueios"]})
    elif resultado["validacao"]["alertas"]:
        st.warning({"alertas": resultado["validacao"]["alertas"]})
    else:
        st.success("Nenhuma violação detectada.")

    st.markdown("### State update extraído")
    st.json(resultado["update"])

    st.markdown("### Resposta final")
    st.write(resultado["resposta_final_limpa"])

st.markdown("---")
st.subheader("Estado real salvo")
st.json(state)
