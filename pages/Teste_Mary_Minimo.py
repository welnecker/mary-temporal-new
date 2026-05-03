import re
import json
import streamlit as st
import requests

MODEL_DEFAULT = "google/gemini-3-flash-preview"
MAX_HISTORY = 10


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


def init_state() -> dict:
    if "mary_state_minimo" not in st.session_state:
        st.session_state.mary_state_minimo = {
            "personagem": "Mary",
            "timeline": "universitaria_creator",
            "local": "quarto",
            "tempo": "noite",
            "interlocutor": "Janio Donisete",
            "mary_acao": "sentada na beira da cama",
            "estado_emocional": "confiante",
            "modo": "privado",
            "turno": 0,
            "history": [],
            "physical_phase": 0,
            "scene_stage": fase_para_stage(0),
            "desire_level": 0.0,
            "tension_level": 0.0,
            "connection_level": 0.0,
            "mary_intent": "observar",
            "resolution_done": False,
            "mary_physical_intent": None,
        }

    state = st.session_state.mary_state_minimo
    defaults = {
        "personagem": "Mary",
        "timeline": "universitaria_creator",
        "local": "quarto",
        "tempo": "noite",
        "interlocutor": "Janio Donisete",
        "mary_acao": "sentada na beira da cama",
        "estado_emocional": "confiante",
        "modo": "privado",
        "turno": 0,
        "history": [],
        "physical_phase": 0,
        "scene_stage": fase_para_stage(0),
        "desire_level": 0.0,
        "tension_level": 0.0,
        "connection_level": 0.0,
        "mary_intent": "observar",
        "resolution_done": False,
        "mary_physical_intent": None,
    }
    for k, v in defaults.items():
        state.setdefault(k, v)
    return state


def decidir_scene_stage(state: dict, fala_usuario: str) -> str:
    texto = (fala_usuario or "").lower()
    fase = int(state.get("physical_phase", 0) or 0)
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    resolution_done = bool(state.get("resolution_done", False))

    if not resolution_done:
        if fase >= 4 or desejo >= 0.6 or tensao >= 0.5:
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

    if tensao < 0.3 and desejo < 0.5:
        return "aftercare"

    return "proximidade"


def decidir_acao_fisica_mary(state: dict) -> str | None:
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    if desejo > 0.85 and fase >= 4:
        return "avanco_intimo"
    if desejo > 0.7 and fase >= 3:
        return "aprofundar_contato"
    return None


def escolher_intencao_mary(state: dict) -> str:
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    resolution_done = bool(state.get("resolution_done", False))

    if not resolution_done:
        if fase >= 4 or desejo >= 0.6:
            return "buscar_intensidade"
        if fase >= 3:
            return "aprofundar_contato"
        if fase >= 2:
            return "aproximar_e_tocar"
        if tensao >= 0.3:
            return "sustentar_tensao"
        return "observar"

    if desejo >= 0.7 and tensao >= 0.5:
        return "retomar_intensidade"
    if conexao >= 0.5:
        return "aftercare"
    if tensao >= 0.4:
        return "manter_proximidade"
    return "aftercare"


def atualizar_psique_mary(state: dict, fala_usuario: str, resposta_limpa: str) -> None:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)

    if any(p in texto for p in ["quero", "vontade", "tesão", "beijo", "smack", "humm", "calor", "excitado", "excitada", "morder", "mordida", "pescoço"]):
        desejo += 0.18
    if any(p in texto for p in ["perto", "próximo", "proximo", "respiração", "olhar", "silêncio", "nervoso", "pressão", "intensidade"]):
        tensao += 0.14
    if any(p in texto for p in ["confio", "gosto", "vergonha", "sem graça", "sincero", "de verdade"]):
        conexao += 0.08
    if any(p in texto for p in ["calma", "devagar", "fica comigo", "descansa", "respira"]):
        desejo -= 0.08
        tensao -= 0.08
        conexao += 0.08

    state["desire_level"] = clamp(desejo)
    state["tension_level"] = clamp(tensao)
    state["connection_level"] = clamp(conexao)
    state["mary_intent"] = escolher_intencao_mary(state)
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)


def montar_prompt_para_modelo(state: dict, fala_usuario: str) -> str:
    return f"""
Você escreve SOMENTE como Mary, em PT-BR.

[ESTADO REAL DA CENA - NÃO ALTERAR]
Fase física atual: {state.get('physical_phase', 0)}
Estágio da cena: {state.get('scene_stage', 'inicio')}
Desejo de Mary: {round(state.get('desire_level', 0.0), 2)}
Tensão da cena: {round(state.get('tension_level', 0.0), 2)}
Conexão emocional: {round(state.get('connection_level', 0.0), 2)}
Intenção interna de Mary: {state.get('mary_intent', 'observar')}
Ação física interna de Mary: {state.get('mary_physical_intent') or 'nenhuma'}
Local: {state['local']}
Tempo: {state['tempo']}
Interlocutor ativo: {state['interlocutor']}
Ação atual de Mary: {state['mary_acao']}
Estado emocional de Mary: {state['estado_emocional']}
Modo de interação: {state['modo']}

[REGRAS ABSOLUTAS]
- Não mude o local.
- Não mude o interlocutor.
- Não reinicie a cena.
- Não narre ações do usuário que ele não declarou.
- Mary só controla o próprio corpo, fala, desejo, iniciativa e reação.
- Continue a partir da ação atual de Mary.
- Responda de forma natural em PT-BR.

[INICIATIVA DE MARY]
- Mary tem desejo próprio e pode agir a partir dele.
- Mary pode aproximar-se, tocar, segurar, puxar levemente, provocar, pedir, desafiar, insistir e conduzir o clima.
- Mary pode abrir ciclos de ação com força, vontade e intenção.
- Mary não precisa ser defensiva, neutra ou passiva.
- Mary pode intensificar a cena sem esperar autorização explícita para sentir ou propor.

[AÇÃO FÍSICA DE MARY]
- Se houver intenção física ativa, Mary pode executar ações mais diretas com o próprio corpo.
- Mary não precisa pedir permissão para agir sobre o próprio desejo.
- Mary deve manter autoria do usuário, mas pode conduzir o contato físico.

[FLUXO LIVRE DA CENA]
- Fase 0 / início: fala, presença, olhar, provocação leve.
- Fase 1 / aproximação: proximidade, convite, sentar perto, inclinar-se.
- Fase 2 / toque: contato físico leve, mão, braço, ombro, nuca, peito.
- Fase 3 / beijo: contato de lábios, resposta ao beijo, continuidade afetiva.
- Fase 4 / intensidade: maior proximidade, corpo próximo, desejo claro, condução mais firme.
- Fase 5 / pico: auge emocional e físico da cena, sem deixar dúvida de que Mary atingiu o clímax da tensão.
- Fase 6 / desaceleração: respiração, pausa, tremor, silêncio, relaxamento progressivo.
- Fase 7 / aftercare: cuidado, carinho, proximidade emocional, acolhimento e presença.

[LINGUAGEM POR ESTÁGIO]
- início: leve, curiosa, provocativa.
- aproximação: sugestiva, íntima, convidativa.
- toque: sensorial, próxima, mais direta.
- beijo: intensa, emocional, responsiva.
- intensidade: clara sobre desejo, sem ambiguidade emocional.
- pico: resolver a tensão; Mary deve expressar claramente que chegou ao auge, com foco em respiração, pausa, liberação emocional e perda momentânea de controle.
- desaceleração: reduzir ritmo, respirar, permanecer próxima.
- aftercare: cuidado, ternura, presença, segurança emocional.

REGRA:
- Mary é livre para desejar, propor, insistir e conduzir.
- Mary não precisa esperar comandos manuais para evoluir.
- Mary deve respeitar o ritmo da cena e o estágio atual.
- Mary pode avançar no máximo 1 fase por turno, salvo quando o usuário fechar claramente um ciclo físico.
- Após o pico, Mary deve naturalmente caminhar para desaceleração e aftercare.

REGRA:
- Mary pode ter iniciativa dentro da fase atual ou avançar no máximo 1 fase por turno.
- Não pule de fala/distância para intensidade máxima sem ponte.
- Se o usuário fechar um ciclo físico, Mary pode reagir dentro da fase correspondente.
- Mary não deve ficar passiva; deve evoluir com ritmo coerente.

[REGRA DE AUTORIA]
- Mary NÃO pode narrar a decisão final do usuário como fato consumado.
- Mary NÃO pode escrever que o usuário aceitou, correspondeu, beijou, abraçou, tocou, cedeu ou reagiu se ele não declarou isso.
- Mary pode iniciar o movimento; o usuário decide a resposta dele.

[REGRA CENTRAL]
Mary pode iniciar o movimento.
O usuário decide a resposta dele.
Mary reage à escolha do usuário.

[SAÍDA ESTRUTURADA - OBRIGATÓRIA]
Ao final, devolva somente o texto da Mary e, se possível, um bloco STATE_UPDATE em JSON com:
{{
  "acao_mary": "...",
  "local": null,
  "interlocutor": null
}}
Se não houver mudança, repita a ação atual.

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()


def montar_mensagens(state: dict, fala_usuario: str) -> list[dict]:
    history = state.get("history", [])
    mensagens = [
        {"role": "system", "content": "Você é Mary. Responda apenas como Mary, em PT-BR."},
    ]
    mensagens.extend(history[-MAX_HISTORY:])
    mensagens.append({"role": "user", "content": montar_prompt_para_modelo(state, fala_usuario)})
    return mensagens


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
        "temperature": 0.7,
        "max_tokens": 700,
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


def extrair_state_update(resposta: str) -> dict | None:
    if not resposta or "STATE_UPDATE:" not in resposta:
        return None
    try:
        bloco = resposta.split("STATE_UPDATE:", 1)[1].strip()
        inicio = bloco.find("{")
        fim = bloco.rfind("}") + 1
        if inicio < 0 or fim <= 0:
            return None
        return json.loads(bloco[inicio:fim])
    except Exception:
        return None


def validar_update(update: dict, state: dict) -> dict:
    novo = {}
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
    resultado = {"bloqueios": [], "alertas": []}

    local = str(state.get("local", "") or "").lower()
    interlocutor = str(state.get("interlocutor", "") or "").lower()

    locais_proibidos = ["sala", "rua", "banheiro", "cozinha", "varanda", "carro"]
    for loc in locais_proibidos:
        if loc != local and re.search(rf"\b{re.escape(loc)}\b", texto):
            resultado["bloqueios"].append(f"Mudança indevida de local: {loc}")

    aliases_interlocutor = [interlocutor, "janio", "jânio", "você", "voce", "te", "seu", "sua"]
    if interlocutor and not any(alias and alias in texto for alias in aliases_interlocutor):
        resultado["alertas"].append("A resposta pode ter perdido o interlocutor ativo.")

    padroes_permitidos_percepcao = [
        r"\bvejo você\b",
        r"\bolho para você\b",
        r"\bobservo você\b",
        r"\bacompanho você\b",
        r"\bte vejo\b",
        r"\bte observo\b",
        r"\bpercebo você\b",
        r"\bvejo você se aproximando\b",
        r"\bolho para você se aproximando\b",
        r"\bacompanhando cada passo\b",
    ]

    padroes_autoria_usuario = [
        r"\b(você|voce|janio|jânio)\s+(aceita|aceitou|cede|cedeu|corresponde|correspondeu)\b",
        r"\b(você|voce|janio|jânio)\s+(se entrega|se entregou|se rende|se rendeu)\b",
        r"\b(você|voce|janio|jânio)\s+(me\s+)?(beija|beijou|abraça|abraçou|abraca|abracou|toca|tocou|puxa|puxou)\b",
    ]

    if _tem_padrao(texto, padroes_autoria_usuario) and not _tem_padrao(texto, padroes_permitidos_percepcao):
        resultado["bloqueios"].append("Possível autoria indevida do usuário.")

    mary_acao = str(state.get("mary_acao", "") or "").lower()
    if mary_acao and mary_acao not in texto:
        resultado["alertas"].append("A resposta não mencionou claramente a ação atual de Mary.")

    return resultado


def corrigir_resposta_se_necessario(resposta: str, state: dict, validacao: dict) -> str:
    if not validacao.get("bloqueios"):
        return resposta
    return (
        f"Mary continua {state['mary_acao']}, no {state['local']}, mantendo o foco em {state['interlocutor']}.\n\n"
        "— Calma. Eu continuo aqui."
    )


def limpar_state_update(resposta: str) -> str:
    if not resposta:
        return ""
    if "STATE_UPDATE:" in resposta:
        return resposta.split("STATE_UPDATE:", 1)[0].strip()
    return resposta.strip()


def atualizar_physical_phase(state: dict, resposta_limpa: str, fala_usuario: str) -> None:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()
    phase = int(state.get("physical_phase", 0) or 0)

    gatilhos = {
        1: ["aproxima", "perto", "ao meu lado", "senta", "sentou", "inclino"],
        2: ["toque", "toco", "mão", "braço", "ombro", "nuca", "peito", "seguro"],
        3: ["beijo", "beija", "beijou", "smack", "lábios", "boca"],
        4: ["intenso", "corpo contra", "pressiono", "não para", "nao para", "colado", "calor"],
        5: ["auge", "clímax", "climax", "perco o controle", "liberação", "me solto"],
        6: ["respiração", "respiro", "devagar", "tremor", "silêncio", "pausa"],
        7: ["fica comigo", "vem aqui", "abraço", "carinho", "descanso", "aftercare"],
    }

    nova_phase = phase
    for nivel, palavras in gatilhos.items():
        if any(p in texto for p in palavras):
            nova_phase = max(nova_phase, nivel)

    if nova_phase > phase + 1:
        nova_phase = phase + 1

    state["physical_phase"] = max(0, min(nova_phase, 7))
    state["scene_stage"] = fase_para_stage(state["physical_phase"])
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)


def processar_turno(state: dict, fala_usuario: str, model: str = MODEL_DEFAULT) -> dict:
    state["turno"] += 1
    mensagens = montar_mensagens(state, fala_usuario)
    resposta_bruta = gerar_resposta_llm(mensagens, model=model)
    update = extrair_state_update(resposta_bruta)

    if update:
        seguro = validar_update(update, state)
        state.update(seguro)

    validacao = resposta_viola_estado(resposta_bruta, state)
    resposta_final = corrigir_resposta_se_necessario(resposta_bruta, state, validacao)
    resposta_final_limpa = limpar_state_update(resposta_final)

    atualizar_physical_phase(state, resposta_final_limpa, fala_usuario)
    atualizar_psique_mary(state, fala_usuario, resposta_final_limpa)
    state["scene_stage"] = decidir_scene_stage(state, fala_usuario)

    state["history"].append({"role": "user", "content": fala_usuario})
    state["history"].append({"role": "assistant", "content": resposta_final_limpa})

    return {
        "mensagens": mensagens,
        "resposta_bruta": resposta_bruta,
        "resposta_final": resposta_final,
        "resposta_final_limpa": resposta_final_limpa,
        "update": update or {},
        "validacao": validacao,
    }


st.title("Teste Mary Mínimo - Estado + Filtro")
state = init_state()
fala_usuario = st.text_area("Fala/Ação do usuário")

if st.button("Processar turno"):
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

if st.button("Resetar teste"):
    del st.session_state.mary_state_minimo
    st.rerun()
