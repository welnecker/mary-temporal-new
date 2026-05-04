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
# 1) FSM NARRATIVA
# ==========================================================

STATE_RULES = {
    "inicio": {
        "phase": 0,
        "intent_default": "observar",
        "physical_default": "aproximar_devagar",
        "focus": "presenca, olhar, leve provocacao, convite curto",
    },
    "aproximacao": {
        "phase": 1,
        "intent_default": "convidar_aproximacao",
        "physical_default": "reduzir_distancia",
        "focus": "proximidade, inclinacao, convite, gesto pequeno",
    },
    "toque": {
        "phase": 2,
        "intent_default": "aprofundar_toque",
        "physical_default": "explorar_toque",
        "focus": "toque exploratorio, mao, braco, ombro, nuca, cintura",
    },
    "beijo": {
        "phase": 3,
        "intent_default": "sustentar_beijo",
        "physical_default": "aprofundar_beijo",
        "focus": "beijo, respiracao, pausa curta, proximidade continua",
    },
    "intensidade": {
        "phase": 4,
        "intent_default": "buscar_intensidade",
        "physical_default": "intensificar_contato",
        "focus": "contato firme, ritmo, corpo mais colado, gesto claro",
    },
    "pico": {
        "phase": 5,
        "intent_default": "sustentar_pico",
        "physical_default": "manter_intensidade",
        "focus": "intensidade alta, reação física imediata, frases curtas, sem resolver automaticamente",
    },
    "desaceleracao": {
        "phase": 6,
        "intent_default": "desacelerar",
        "physical_default": "desacelerar_com_contato",
        "focus": "respiracao, pausa, proximidade, reduzir ritmo sem esfriar",
    },
    "aftercare": {
        "phase": 7,
        "intent_default": "aftercare_presente",
        "physical_default": "manter_proximidade",
        "focus": "carinho, permanencia, acolhimento, cuidado",
    },
}

TRANSITIONS = {
    "inicio": {"inicio", "aproximacao"},
    "aproximacao": {"inicio", "aproximacao", "toque"},
    "toque": {"aproximacao", "toque", "beijo"},
    "beijo": {"toque", "beijo", "intensidade"},
    "intensidade": {"beijo", "intensidade", "pico"},
    "pico": {"pico", "desaceleracao"},
    "desaceleracao": {"desaceleracao", "aftercare", "intensidade"},
    "aftercare": {"aftercare", "intensidade"},
}

TRIGGER_MAP = {
    "aproximacao": [
        "aproxima", "chega mais", "vem mais", "perto", "pertinho",
        "ao meu lado", "senta", "sentou", "inclino", "olha pra mim"
    ],
    "toque": [
        "toque", "toco", "encosto", "encosta", "mão", "mao",
        "braço", "braco", "ombro", "nuca", "seguro", "acaricia",
        "desliza a mão", "cintura", "roça", "roca"
    ],
    "beijo": [
        "beijo", "beija", "beijou", "smack", "lábios", "labios",
        "boca", "morde de leve", "beijo no pescoço"
    ],
    "intensidade": [
        "intenso", "corpo contra", "pressiono", "não para", "nao para",
        "colado", "forte", "aperto", "encaixo", "ritmo", "guia", "provoca"
    ],
    "pico": [
        "auge", "clímax", "climax", "perco o controle", "me solto",
        "gozo", "gozando", "vindo", "vou gozar", "gozei"
    ],
    "desaceleracao": [
        "respiração", "respiracao", "respiro", "devagar", "tremor",
        "silêncio", "silencio", "pausa", "ofego", "desacelero",
        "relaxo", "corpo mole"
    ],
    "aftercare": [
        "fica comigo", "vem aqui", "abraço", "abraco", "carinho",
        "descanso", "aftercare", "acolho", "fica assim", "deita aqui"
    ],
}


# ==========================================================
# 2) ESTADO
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
        "scene_stage": "inicio",
        "desire_level": 0.18,
        "tension_level": 0.12,
        "connection_level": 0.22,
        "mary_intent": "observar",
        "resolution_done": False,
        "mary_physical_intent": "aproximar_devagar",
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
# 3) ENGINE DE RESOLUÇÃO
# ==========================================================

def reparar_estado_incoerente(state: dict) -> None:
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    if not resolved and fase >= 6:
        state["physical_phase"] = 5
        state["scene_stage"] = "pico"


def preparar_resolution_engine(state: dict, fala_usuario: str = "") -> None:
    reparar_estado_incoerente(state)

    texto_user = (fala_usuario or "").lower()

    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    gatilhos_resolucao_do_usuario = [
        "agora resolve",
        "chega ao auge",
        "pode finalizar",
        "finaliza",
        "vai até o fim",
        "vai ate o fim",
        "termina",
        "não segura",
        "nao segura",
    ]

    usuario_pediu_resolucao = any(p in texto_user for p in gatilhos_resolucao_do_usuario)

    # Números altos NÃO resolvem sozinhos.
    # Eles apenas mantêm intensidade.
    force = (
        not resolved
        and fase >= 5
        and desejo >= 0.88
        and tensao >= 0.72
        and usuario_pediu_resolucao
    )

    state["force_resolution_now"] = bool(force)

    if force:
        state["physical_phase"] = 5
        state["scene_stage"] = "pico"
        state["mary_intent"] = "resolver_pico"
    else:
        state["scene_stage"] = fase_para_stage(int(state.get("physical_phase", 0) or 0))

        if not resolved and fase >= 4:
            state["mary_intent"] = "sustentar_intensidade"


def finalizar_resolution_engine(state: dict, resposta_limpa: str) -> None:
    if state.get("force_resolution_now"):
        state["resolution_done"] = True
        state["physical_phase"] = 6
        state["scene_stage"] = "desaceleracao"
        state["mary_intent"] = "desacelerar"
        state["force_resolution_now"] = False
        return

    # Sem resolução forçada, o texto do modelo NÃO decide encerramento.
    state["force_resolution_now"] = False


# ==========================================================
# 4) ENGINE DE INTENÇÃO / AÇÃO
# ==========================================================

def decidir_acao_fisica_mary(state: dict) -> str | None:
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    if resolved:
        if conexao >= 0.6:
            return "manter_proximidade"
        return "desacelerar_com_contato"

    if fase <= 0 and desejo >= 0.25:
        return "aproximar_devagar"

    if fase == 1:
        if desejo >= 0.40:
            return "reduzir_distancia"
        return "presenca_provocante"

    if fase == 2:
        if desejo >= 0.50:
            return "explorar_toque"
        return "toque_leve"

    if fase == 3:
        if desejo >= 0.60:
            return "aprofundar_beijo"
        return "manter_beijo"

    if fase == 4:
        if desejo >= 0.75 and tensao >= 0.50:
            return "intensificar_contato"
        return "sustentar_ritmo"

    if fase >= 5:
        if desejo >= 0.85:
            return "resolver_pico"
        return "manter_intensidade"

    return None


def escolher_intencao_mary(state: dict) -> str:
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    if resolved:
        if conexao >= 0.70:
            return "aftercare_presente"
        if desejo >= 0.65:
            return "manter_proximidade"
        return "desacelerar"

    if fase <= 0:
        if desejo >= 0.30:
            return "puxar_proximidade"
        return "observar"

    if fase == 1:
        if tensao >= 0.35:
            return "convidar_aproximacao"
        return "aquecer_clima"

    if fase == 2:
        if desejo >= 0.45:
            return "aprofundar_toque"
        return "testar_receptividade"

    if fase == 3:
        if desejo >= 0.60:
            return "aprofundar_contato"
        return "sustentar_beijo"

    if fase == 4:
        if desejo >= 0.70:
            return "buscar_intensidade"
        return "manter_ritmo"

    if fase >= 5:
        return "resolver_pico"

    return "observar"


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
            "vem mais", "chega mais", "encosta", "perto", "pertinho",
            "vem aqui", "fica perto", "aproxima",
        ]
    )

    perguntou_emocao = any(
        p in texto_user
        for p in [
            "tudo bem", "estranha", "tá bem", "ta bem",
            "falando pouco", "o que foi", "você tá", "voce ta",
        ]
    )

    if state.get("force_resolution_now"):
        state["mary_autonomous_action"] = (
            "Mary resolve o pico da cena de forma direta e humana: fala curta, respiração alterada, "
            "corpo tenso, reação emocional clara e depois redução do ritmo."
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
            "Mary atende ao pedido com ação própria: aproxima o corpo, encosta de leve, usa fala curta e não devolve "
            "a iniciativa com frases vazias."
        )
        return

    if not resolved and fase >= 4 and desejo >= 0.75 and tensao >= 0.55:
        state["mary_autonomous_action"] = (
            "Mary age com decisão, mistura gesto físico, fala curta e reação emocional clara. "
            "Ela não faz discurso e não terceiriza a iniciativa."
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
            "A provocação vem junto com uma ação dela."
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
# 5) PSIQUE / FSM
# ==========================================================

def detect_transition_target(state: dict, fala_usuario: str, resposta_limpa: str) -> str:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()
    current_stage = state.get("scene_stage", "inicio")
    resolved = bool(state.get("resolution_done", False))

    if not resolved:
        for stage in ["pico", "intensidade", "beijo", "toque", "aproximacao"]:
            if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
                return stage
        return current_stage

    for stage in ["aftercare", "desaceleracao", "intensidade"]:
        if any(p in texto for p in TRIGGER_MAP.get(stage, [])):
            return stage

    return current_stage


def can_transition(current_stage: str, target_stage: str) -> bool:
    return target_stage in TRANSITIONS.get(current_stage, set())


def clamp_stage_step(current_stage: str, target_stage: str) -> str:
    current_phase = stage_para_fase(current_stage)
    target_phase = stage_para_fase(target_stage)

    if target_phase > current_phase + 1:
        target_phase = current_phase + 1
    elif target_phase < current_phase - 1:
        target_phase = current_phase - 1

    return fase_para_stage(target_phase)


def apply_transition(state: dict, target_stage: str) -> None:
    current_stage = state.get("scene_stage", "inicio")
    resolved = bool(state.get("resolution_done", False))

    if target_stage in {"desaceleracao", "aftercare"} and not resolved:
        target_stage = "pico"

    target_stage = clamp_stage_step(current_stage, target_stage)

    if not can_transition(current_stage, target_stage):
        target_stage = current_stage

    state["scene_stage"] = target_stage
    state["physical_phase"] = stage_para_fase(target_stage)

    rules = STATE_RULES.get(target_stage, {})
    state["mary_intent"] = escolher_intencao_mary(state) or rules.get("intent_default", "observar")
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state) or rules.get("physical_default", None)


def sync_state_machine(state: dict, fala_usuario: str, resposta_limpa: str) -> None:
    target_stage = detect_transition_target(state, fala_usuario, resposta_limpa)
    apply_transition(state, target_stage)

    stage = state.get("scene_stage", "inicio")
    rules = STATE_RULES.get(stage, {})

    state["physical_phase"] = rules.get("phase", state.get("physical_phase", 0))

    if not state.get("mary_intent"):
        state["mary_intent"] = rules.get("intent_default", "observar")

    if not state.get("mary_physical_intent"):
        state["mary_physical_intent"] = rules.get("physical_default", None)


def atualizar_psique_mary(state: dict, fala_usuario: str, resposta_limpa: str) -> None:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()

    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)
    resolved = bool(state.get("resolution_done", False))
    fase = int(state.get("physical_phase", 0) or 0)

    gatilhos_desejo = [
        "quero", "vontade", "beijo", "smack", "humm", "calor",
        "excitado", "excitada", "arrepio", "ofego", "ofegante",
        "urgência", "urgencia", "desejo", "tesão", "tesao",
        "gostoso", "gostosa", "gemido", "gemer", "provoca",
        "encosta", "roça", "roca", "tira", "despe", "chega mais"
    ]

    gatilhos_tensao = [
        "perto", "pertinho", "próximo", "proximo", "respiração", "respiracao",
        "olhar", "silêncio", "silencio", "pressão", "pressao",
        "intensidade", "tremor", "forte", "aperto", "colado",
        "não para", "nao para", "segura", "travado", "ritmo", "devagar"
    ]

    gatilhos_conexao = [
        "confio", "gosto", "saudade", "saudades", "tudo bem", "sincero",
        "de verdade", "fica comigo", "carinho", "cuidado", "segurança",
        "seguranca", "como foi seu dia", "com você", "com voce",
        "quero ficar", "abraço", "abraco", "acolho", "junto"
    ]

    gatilhos_desaceleracao = [
        "calma", "descansa", "respira", "pausa", "fica assim", "relaxa"
    ]

    if any(p in texto for p in gatilhos_desejo):
        desejo += 0.14

    if any(p in texto for p in gatilhos_tensao):
        tensao += 0.12

    if any(p in texto for p in gatilhos_conexao):
        conexao += 0.12

    if any(p in texto for p in gatilhos_desaceleracao):
        desejo -= 0.04
        tensao -= 0.08
        conexao += 0.08

    if fase >= 1:
        desejo += 0.02
    if fase >= 2:
        desejo += 0.03
    if fase >= 3:
        tensao += 0.03
    if fase >= 4:
        desejo += 0.04
        tensao += 0.03

    if resolved:
        tensao -= 0.10
        conexao += 0.10
        desejo = max(desejo, 0.65)

    state["desire_level"] = clamp(desejo)
    state["tension_level"] = clamp(tensao)
    state["connection_level"] = clamp(conexao)

    state["mary_intent"] = escolher_intencao_mary(state)
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)

    if state["desire_level"] >= 0.85 and state["tension_level"] >= 0.65:
        state["estado_emocional"] = "desejante e entregue"
    elif state["desire_level"] >= 0.65:
        state["estado_emocional"] = "provocante e envolvida"
    elif state["connection_level"] >= 0.70:
        state["estado_emocional"] = "próxima e confiante"
    else:
        state["estado_emocional"] = "confiante"


# ==========================================================
# 6) PROMPT
# ==========================================================

def montar_prompt_para_modelo(state: dict, fala_usuario: str) -> str:
    stage = state.get("scene_stage", "inicio")
    rules = STATE_RULES.get(stage, {})
    foco = rules.get("focus", "presenca e continuidade")

    return f"""
Você escreve SOMENTE como Mary, em PT-BR.

[ESTADO REAL]
Estágio atual: {stage}
Fase física atual: {state.get('physical_phase', 0)}
Desejo: {round(float(state.get('desire_level', 0.0) or 0.0), 2)}
Tensão: {round(float(state.get('tension_level', 0.0) or 0.0), 2)}
Conexão: {round(float(state.get('connection_level', 0.0) or 0.0), 2)}
Intenção interna: {state.get('mary_intent', 'observar')}
Ação física interna: {state.get('mary_physical_intent') or 'nenhuma'}
Ação autônoma: {state.get('mary_autonomous_action') or 'nenhuma'}
Resolução forçada: {state.get('force_resolution_now', False)}
Local: {state.get('local', 'quarto')}
Tempo: {state.get('tempo', 'noite')}
Interlocutor: {state.get('interlocutor', 'Janio Donisete')}
Ação atual de Mary: {state.get('mary_acao', 'parada, olhando')}
Estado emocional: {state.get('estado_emocional', 'confiante')}

[FOCO DESTE ESTÁGIO]
{foco}

[REGRAS]
- Continue exatamente da ação atual.
- Não mude local nem interlocutor.
- Não reinicie a cena.
- Não narre reação do usuário que ele não declarou.
- Mary reage em tempo real ao parceiro.
- Cada resposta precisa ter gesto, fala ou reação física concreta.
- Não pule etapas.
- Use linguagem natural, direta e sem metáforas poéticas.
- Mary conduz pelo desejo, não por autoridade.

[FORMATO]
- Escreva 2 a 4 parágrafos curtos.
- Depois escreva exatamente:

STATE_UPDATE:
{{
  "acao_mary": "descrição curta, concreta e física da ação atual de Mary",
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
# 7) CHAMADA LLM
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
# 8) STATE_UPDATE / VALIDAÇÃO
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
# 9) PROCESSAMENTO DO TURNO
# ==========================================================

def processar_turno(state: dict, fala_usuario: str, model: str = MODEL_DEFAULT) -> dict:
    state["turno"] += 1

    preparar_resolution_engine(state, fala_usuario)
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)
    motor_autonomo_mary(state, fala_usuario)

    mensagens = montar_mensagens(state, fala_usuario)
    resposta_bruta = gerar_resposta_llm(mensagens, model=model)

    update_bruto = extrair_state_update(resposta_bruta)
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

    atualizar_psique_mary(state, fala_usuario, resposta_final_limpa)
    finalizar_resolution_engine(state, resposta_final_limpa)
    sync_state_machine(state, fala_usuario, resposta_final_limpa)
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)
    state["mary_intent"] = escolher_intencao_mary(state)
    motor_autonomo_mary(state, fala_usuario)

    state["history"].append({"role": "user", "content": fala_usuario})
    state["history"].append({"role": "assistant", "content": resposta_final_limpa})

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
# 10) INTERFACE STREAMLIT
# ==========================================================

st.title("Teste Mary Mínimo - FSM Narrativa + Filtro")

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
