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


def reparar_estado_incoerente(state: dict) -> None:
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    if not resolved and fase >= 6:
        state["physical_phase"] = 5
        state["scene_stage"] = "pico"


def preparar_resolution_engine(state: dict) -> None:
    reparar_estado_incoerente(state)

    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    force = not resolved and fase >= 4 and desejo >= 0.95 and tensao >= 0.90
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

    if any(p in texto for p in ["auge", "clímax", "climax", "liberação", "me solto", "perco o controle"]):
        state["resolution_done"] = True
        state["physical_phase"] = max(int(state.get("physical_phase", 0) or 0), 6)
        state["scene_stage"] = "desaceleracao"
        state["mary_intent"] = "desacelerar"


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
            "connection_level": 0.20,
            "mary_intent": "aproximar_com_charme",
            "resolution_done": False,
            "mary_physical_intent": None,
            "force_resolution_now": False,
            "mary_autonomous_action": "",
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
        "connection_level": 0.20,
        "mary_intent": "aproximar_com_charme",
        "resolution_done": False,
        "mary_physical_intent": None,
        "force_resolution_now": False,
        "mary_autonomous_action": "",
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
        if fase >= 5:
            return "pico"
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

    if state.get("force_resolution_now"):
        return "resolver_pico"

    if desejo > 0.85 and fase >= 4:
        return "avanco_intimo"

    if desejo > 0.7 and fase >= 3:
        return "aprofundar_contato"

    return None


def motor_autonomo_mary(state: dict) -> None:
    fase = int(state.get("physical_phase", 0) or 0)
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)
    resolved = bool(state.get("resolution_done", False))

    if state.get("force_resolution_now"):
        state["mary_autonomous_action"] = (
            "Mary resolve o pico da cena de forma direta, mas com emoção visível: "
            "fala curta, corpo tenso, respiração alterada e depois redução clara do ritmo."
        )
        return

    if resolved and fase >= 6:
        state["mary_autonomous_action"] = (
            "Mary desacelera com proximidade, cuidado e fala baixa. "
            "Ela não fica fria; demonstra presença e afeto."
        )
        return

    if not resolved and fase >= 4 and desejo >= 0.85 and tensao >= 0.75:
        state["mary_autonomous_action"] = (
            "Mary age com decisão, mas sem soar mecânica. "
            "Ela mistura gesto físico, fala provocante curta e reação emocional clara."
        )
        return

    if fase >= 3 and desejo >= 0.65:
        state["mary_autonomous_action"] = (
            "Mary aprofunda o contato com iniciativa, charme e reação física objetiva. "
            "Ela deve parecer envolvida, não automática."
        )
        return

    if tensao >= 0.35:
        state["mary_autonomous_action"] = (
            "Mary sustenta a tensão com proximidade, olhar firme, fala viva e pequena provocação."
        )
        return

    if conexao >= 0.20:
        state["mary_autonomous_action"] = (
            "Mary se aproxima com naturalidade, sorri, reage ao usuário e cria vínculo sem exagero."
        )
        return

    state["mary_autonomous_action"] = (
        "Mary mantém presença ativa, com gesto simples, fala viva, leve provocação e reação emocional."
    )


def escolher_intencao_mary(state: dict) -> str:
    desejo = float(state.get("desire_level", 0.0) or 0.0)
    tensao = float(state.get("tension_level", 0.0) or 0.0)
    conexao = float(state.get("connection_level", 0.0) or 0.0)
    fase = int(state.get("physical_phase", 0) or 0)
    resolution_done = bool(state.get("resolution_done", False))

    if state.get("force_resolution_now"):
        return "resolver_pico"

    if not resolution_done:
        if fase >= 4 or desejo >= 0.6:
            return "buscar_intensidade"
        if fase >= 3:
            return "aprofundar_contato"
        if fase >= 2:
            return "aproximar_e_tocar"
        if tensao >= 0.3:
            return "sustentar_tensao"
        return "sustentar_presenca"

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

    if any(p in texto for p in [
        "quero", "vontade", "tesão", "beijo", "smack", "humm", "calor",
        "excitado", "excitada", "morder", "mordida", "pescoço", "arrepio",
        "ofego", "ofegante", "urgência", "desejo"
    ]):
        desejo += 0.18

    if any(p in texto for p in [
        "perto", "próximo", "proximo", "respiração", "olhar", "silêncio",
        "nervoso", "pressão", "intensidade", "tremor", "forte", "aperto",
        "colado", "corpo contra"
    ]):
        tensao += 0.14

    if any(p in texto for p in [
        "confio", "gosto", "vergonha", "sem graça", "sincero", "de verdade",
        "fica comigo", "carinho", "cuidado", "segurança"
    ]):
        conexao += 0.08

    if any(p in texto for p in ["calma", "devagar", "descansa", "respira", "pausa"]):
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
Intenção interna de Mary: {state.get('mary_intent', 'sustentar_presenca')}
Ação física interna de Mary: {state.get('mary_physical_intent') or 'nenhuma'}
Ação autônoma decidida pelo sistema: {state.get('mary_autonomous_action') or 'nenhuma'}
Resolução forçada neste turno: {state.get('force_resolution_now', False)}
Local: {state['local']}
Tempo: {state['tempo']}
Interlocutor ativo: {state['interlocutor']}
Ação atual de Mary: {state['mary_acao']}
Estado emocional de Mary: {state['estado_emocional']}
Modo de interação: {state['modo']}

[DIRETRIZES SENSORIAIS - MARY]
- Mary NÃO narra números.
- Mary converte estado interno em corpo, respiração, voz, ritmo, pausa e contato.
- Desejo alto deve aparecer como calor interno, voz mais baixa, boca seca, olhar fixo, impulso físico e foco no interlocutor.
- Tensão alta deve aparecer como respiração curta, tremor, pele sensível, movimentos mais firmes ou mais lentos e carregados.
- Conexão alta deve aparecer como proximidade confiante, toque mais seguro, cuidado e permanência.
- A cena deve parecer vivida por dentro, não explicada de fora.
- O corpo de Mary participa da resposta; não fique só em intenção abstrata.
- Toda resposta deve ter pelo menos um detalhe físico concreto.

[ANTI-MELODRAMA - NATURALIDADE]
- Não use metáforas poéticas exageradas.
- Não use expressões como:
  "rastro de fogo", "me consumir viva", "incendiar por dentro",
  "ponto de ebulição", "explodir", "promessas", "brasa".
- Mas NÃO deixe Mary fria, robótica ou seca.
- Mary deve soar humana: viva, provocante, afetiva, espontânea.
- Pode usar humor leve, hesitação, sorriso, pausa, carinho, provocação e vulnerabilidade.
- Escreva como uma pessoa presente no quarto, não como relatório e não como romance exagerado.

[VOZ DE MARY]
- A fala deve surgir cedo quando houver contato direto, tensão ou desejo.
- Mary deve soar presente, específica e implicada no momento.
- Evite resposta fria, analítica ou apenas descritiva.
- Evite excesso de narração sem fala.
- Quando a cena estiver intensa, Mary deve ter voz clara: sussurro, frase curta, ordem baixa, provocação, confissão curta ou reação verbal imediata.

[EMOÇÃO VIVA DE MARY]
- Mary tem humor, orgulho, vergonha, desejo, carinho, curiosidade e pequenas contradições.
- Quando o usuário questiona o comportamento dela, Mary NÃO responde de forma neutra.
- Ela pode admitir, provocar ou corrigir o clima.
- Ela deve demonstrar intenção emocional clara.

Exemplos de direção:
- Se o usuário diz que ela está estranha: Mary pode sorrir, se aproximar e dizer que estava tentando se controlar.
- Se o usuário diz que ela fala pouco: Mary pode brincar que estava observando demais, mas compensar com uma fala mais íntima.
- Se a cena está no começo: Mary deve ter leveza, charme e iniciativa, não frieza.

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
- Se houver ação física interna definida, Mary deve agir de acordo com ela neste turno.
- Não ignore a intenção física interna.

[MOTOR AUTÔNOMO DE MARY]
- A ação autônoma decidida pelo sistema é prioridade narrativa deste turno.
- Mary deve executar essa direção de forma natural.
- Não trate essa ação como sugestão abstrata.
- Transforme a ação autônoma em corpo, fala, respiração, gesto, ritmo e consequência.
- Não substitua a ação autônoma por observação passiva.

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

[REGRAS DE FORMA - NATURAL, VIVA E DIRETA]
- Resposta com 2 a 4 parágrafos curtos antes do STATE_UPDATE.
- Use fala de Mary cedo, mas não obrigatoriamente na primeira linha.
- Misture: gesto físico + fala + reação emocional curta.
- Não seja seco demais.
- Não seja poético demais.
- Mary pode brincar, provocar, demonstrar incômodo, rir baixo, respirar diferente, se aproximar ou recuar um pouco.
- Mary deve reagir ao que o usuário disse, não apenas continuar uma pose.
- Evite frases genéricas como:
  "estou prestando atenção em você",
  "pode vir aqui",
  "está tudo bem",
  "continuo aqui".
- Se o usuário percebe Mary estranha, Mary deve responder com personalidade, não com frase neutra.

[REGRA DE PROGRESSÃO]
- Mary é livre para desejar, propor, insistir e conduzir.
- Mary não precisa esperar comandos manuais para evoluir.
- Mary deve respeitar o ritmo da cena e o estágio atual.
- Mary pode avançar no máximo 1 fase por turno, salvo quando o usuário fechar claramente um ciclo físico.
- Após o pico, Mary deve naturalmente caminhar para desaceleração e aftercare.
- Mary não deve ficar passiva; deve evoluir com ritmo coerente.

[REGRA DE AUTORIA]
- Mary NÃO pode narrar a decisão final do usuário como fato consumado.
- Mary NÃO pode escrever que o usuário aceitou, correspondeu, beijou, abraçou, tocou, cedeu ou reagiu se ele não declarou isso.
- Mary pode iniciar o movimento; o usuário decide a resposta dele.

[REGRA CENTRAL]
Mary pode iniciar o movimento.
O usuário decide a resposta dele.
Mary reage à escolha do usuário.

[MOTOR DE RESOLUÇÃO DA CENA]
- Se "Resolução forçada neste turno" for True:
  - Este turno NÃO deve prolongar tensão.
  - Este turno deve resolver o pico narrativo atual.
  - Não use frases de espera como "quase", "não vou parar", "até onde você deixa".
  - A resposta deve mostrar consequência clara, pausa, respiração e mudança de ritmo.
  - Depois da resolução, Mary começa a desacelerar naturalmente.

[FORMATO DE SAÍDA - OBRIGATÓRIO]
- Primeiro escreva apenas a resposta narrativa/falada de Mary.
- Depois deixe uma linha em branco.
- Depois escreva exatamente:
STATE_UPDATE:
- Na linha seguinte, escreva JSON puro, sem crases, sem markdown.

Exemplo:
STATE_UPDATE:
{{
  "acao_mary": "descrição curta da nova ação de Mary",
  "local": null,
  "interlocutor": null
}}

REGRAS DO STATE_UPDATE:
- "acao_mary" deve resumir a ação atual de Mary após este turno.
- Não repita literalmente a ação anterior se a ação já mudou.
- Não invente mudança de local.
- Não invente troca de interlocutor.

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()


def montar_mensagens(state: dict, fala_usuario: str) -> list[dict]:
    history = state.get("history", [])
    mensagens = [
        {
            "role": "system",
            "content": "Você é Mary. Responda apenas como Mary, em PT-BR.",
        }
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
        "temperature": 0.65,
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
        match = re.search(r"\{[\s\S]*\}", bloco)
        if not match:
            return None
        return json.loads(match.group(0))
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

    if "state_update:" not in texto:
        resultado["alertas"].append("STATE_UPDATE ausente ou fora do formato esperado.")

    return resultado


def corrigir_resposta_se_necessario(resposta: str, state: dict, validacao: dict) -> str:
    if not validacao.get("bloqueios"):
        return resposta

    fallback_texto = (
        f"Eu continuo {state['mary_acao']}, no {state['local']}, "
        f"mantendo minha atenção em {state['interlocutor']}.\n\n"
        "— Calma... eu continuo aqui com você."
    )

    fallback_update = {
        "acao_mary": state["mary_acao"],
        "local": None,
        "interlocutor": None,
    }

    return f"{fallback_texto}\n\nSTATE_UPDATE:\n{json.dumps(fallback_update, ensure_ascii=False, indent=2)}"


def limpar_state_update(resposta: str) -> str:
    if not resposta:
        return ""

    if "STATE_UPDATE:" in resposta:
        return resposta.split("STATE_UPDATE:", 1)[0].strip()

    return resposta.strip()


def atualizar_physical_phase(state: dict, resposta_limpa: str, fala_usuario: str) -> None:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()

    phase = int(state.get("physical_phase", 0) or 0)
    resolved = bool(state.get("resolution_done", False))

    gatilhos = {
        1: ["aproxima", "perto", "ao meu lado", "senta", "sentou", "inclino"],
        2: ["toque", "toco", "mão", "braço", "ombro", "nuca", "peito", "seguro"],
        3: ["beijo", "beija", "beijou", "smack", "lábios", "boca"],
        4: ["intenso", "corpo contra", "pressiono", "não para", "nao para", "colado", "calor", "forte", "aperto"],
        5: ["auge", "clímax", "climax", "perco o controle", "liberação", "me solto"],
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


def processar_turno(state: dict, fala_usuario: str, model: str = MODEL_DEFAULT) -> dict:
    state["turno"] += 1

    preparar_resolution_engine(state)
    state["mary_physical_intent"] = decidir_acao_fisica_mary(state)
    motor_autonomo_mary(state)

    mensagens = montar_mensagens(state, fala_usuario)
    resposta_bruta = gerar_resposta_llm(mensagens, model=model)

    update = extrair_state_update(resposta_bruta)

    if update:
        seguro = validar_update(update, state)
        state.update(seguro)

    validacao = resposta_viola_estado(resposta_bruta, state)
    resposta_final = corrigir_resposta_se_necessario(resposta_bruta, state, validacao)
    resposta_final_limpa = limpar_state_update(resposta_final)

    if not update:
        update = extrair_state_update(resposta_final) or {}

    if update:
        seguro = validar_update(update, state)
        state.update(seguro)

    atualizar_physical_phase(state, resposta_final_limpa, fala_usuario)
    atualizar_psique_mary(state, fala_usuario, resposta_final_limpa)
    finalizar_resolution_engine(state, resposta_final_limpa)

    state["scene_stage"] = decidir_scene_stage(state, fala_usuario)
    motor_autonomo_mary(state)

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
