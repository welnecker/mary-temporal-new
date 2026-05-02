import re
import streamlit as st
import requests

st.title("Teste Mary Mínimo - Estado + Filtro")

# ==========================================================
# 1) ESTADO REAL
# ==========================================================

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
    }

state = st.session_state.mary_state_minimo

state.setdefault("personagem", "Mary")
state.setdefault("timeline", "universitaria_creator")
state.setdefault("local", "quarto")
state.setdefault("tempo", "noite")
state.setdefault("interlocutor", "Janio Donisete")
state.setdefault("mary_acao", "sentada na beira da cama")
state.setdefault("estado_emocional", "confiante")
state.setdefault("modo", "privado")
state.setdefault("turno", 0)


# ==========================================================
# 2) CONTEXTO PARA O MODELO
# ==========================================================

def montar_prompt_para_modelo(state: dict, fala_usuario: str) -> str:
    return f"""
Você escreve SOMENTE como Mary.

[ESTADO REAL DA CENA - NÃO ALTERAR]
Local: {state["local"]}
Tempo: {state["tempo"]}
Interlocutor ativo: {state["interlocutor"]}
Ação atual de Mary: {state["mary_acao"]}
Estado emocional de Mary: {state["estado_emocional"]}
Modo de interação: {state["modo"]}

[REGRAS ABSOLUTAS]
- Não mude o local.
- Não mude o interlocutor.
- Não reinicie a cena.
- Não narre ações do usuário que ele não declarou.
- Mary só controla o próprio corpo, fala e reação.
- Continue a partir da ação atual de Mary.
- Responda de forma natural em PT-BR.

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()


# ==========================================================
# 3) SIMULAÇÃO DE MODELO
# Depois trocamos esta função por OpenRouter/OpenAI.
# ==========================================================

def gerar_resposta_llm(prompt_modelo: str, model: str = "google/gemini-3-flash-preview") -> str:
    api_key = st.secrets.get("OPENROUTER_API_KEY", "")

    if not api_key:
        return "ERRO: OPENROUTER_API_KEY não encontrada no secrets.toml."

    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://mary-temporal-new.streamlit.app",
        "X-Title": "Mary Temporal Test",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Você é Mary. Responda apenas como Mary, em PT-BR, sem explicar regras.",
            },
            {
                "role": "user",
                "content": prompt_modelo,
            },
        ],
        "temperature": 0.7,
        "max_tokens": 350,
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
        ) or "ERRO: resposta vazia do modelo."

    except Exception as e:
        return f"ERRO OpenRouter: {type(e).__name__}: {e}"


# ==========================================================
# 4) FILTRO DE VIOLAÇÃO
# ==========================================================
# ==========================================================
# 4) FILTRO DE VIOLAÇÃO
# ==========================================================

def _tem_padrao(texto: str, padroes: list[str]) -> bool:
    return any(re.search(p, texto, flags=re.IGNORECASE) for p in padroes)


def resposta_viola_estado(resposta: str, state: dict) -> dict:
    texto = (resposta or "").lower()

    resultado = {
        "bloqueios": [],
        "alertas": [],
    }

    local = str(state.get("local", "") or "").lower()
    interlocutor = str(state.get("interlocutor", "") or "").lower()

    # ----------------------------------------------------------
    # 1) Mudança indevida de local
    # ----------------------------------------------------------
    locais_proibidos = ["sala", "rua", "banheiro", "cozinha", "varanda", "carro"]

    for loc in locais_proibidos:
        if loc != local and re.search(rf"\b{re.escape(loc)}\b", texto):
            resultado["bloqueios"].append(f"Mudança indevida de local: {loc}")

    # ----------------------------------------------------------
    # 2) Interlocutor ativo
    # Agora é alerta leve, não bloqueio.
    # ----------------------------------------------------------
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

    # ----------------------------------------------------------
    # 3) Autoria indevida do usuário
    # Bloqueia quando o modelo narra ação nova do usuário.
    # Permite quando Mary apenas percebe/reage ao que o usuário declarou.
    # ----------------------------------------------------------

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
        r"\bjanio\s+(sorri|sorriu|se aproxima|se aproximou|toca|tocou|beija|beijou|senta|sentou|levanta|levantou)\b",
        r"\bvocê\s+(sorri|sorriu|me toca|tocou em mim|me beija|beijou|senta|sentou|levanta|levantou)\b",
        r"\bvoce\s+(sorri|sorriu|me toca|tocou em mim|me beija|beijou|senta|sentou|levanta|levantou)\b",
    ]

    if _tem_padrao(texto, padroes_autoria_usuario):
        if not _tem_padrao(texto, padroes_permitidos_percepcao):
            resultado["bloqueios"].append("Possível autoria indevida do usuário.")

    # ----------------------------------------------------------
    # 4) Mary abandonando a ação atual
    # Só alerta, porque pode ser variação narrativa aceitável.
    # ----------------------------------------------------------
    mary_acao = str(state.get("mary_acao", "") or "").lower()

    if mary_acao and mary_acao not in texto:
        resultado["alertas"].append("A resposta não mencionou claramente a ação atual de Mary.")

    return resultado


def corrigir_resposta_se_necessario(resposta: str, state: dict, validacao: dict) -> str:
    bloqueios = validacao.get("bloqueios", [])

    if not bloqueios:
        return resposta

    return (
        f"Mary continua {state['mary_acao']}, no {state['local']}, "
        f"mantendo o foco em {state['interlocutor']}.\n\n"
        "— Calma. Eu continuo aqui."
    )


# ==========================================================
# 5) INTERFACE
# ==========================================================

fala_usuario = st.text_area("Fala/Ação do usuário")

if st.button("Processar turno"):
    state["turno"] += 1

    prompt_modelo = montar_prompt_para_modelo(state, fala_usuario)
    resposta_bruta = gerar_resposta_llm(prompt_modelo)

    validacao = resposta_viola_estado(resposta_bruta, state)
    resposta_final = corrigir_resposta_se_necessario(resposta_bruta, state, validacao)

    st.markdown("### Prompt enviado ao modelo")
    st.code(prompt_modelo, language="text")

    st.markdown("### Resposta bruta")
    st.write(resposta_bruta)

    st.markdown("### Validação")
    if validacao["bloqueios"]:
        st.error({"bloqueios": validacao["bloqueios"]})
    elif validacao["alertas"]:
        st.warning({"alertas": validacao["alertas"]})
    else:
        st.success("Nenhuma violação detectada.")

    st.markdown("### Resposta final")
    st.write(resposta_final)

st.markdown("---")
st.subheader("Estado real salvo")
st.json(state)

if st.button("Resetar teste"):
    del st.session_state.mary_state_minimo
    st.rerun()
