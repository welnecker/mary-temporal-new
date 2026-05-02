import re
import streamlit as st

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

def gerar_resposta_mock(state: dict, fala_usuario: str) -> str:
    fala = (fala_usuario or "").strip()

    if not fala:
        return (
            f"Mary permanece {state['mary_acao']}, em silêncio por um instante, "
            f"mantendo a atenção em {state['interlocutor']}."
        )

    return (
        f"Mary continua {state['mary_acao']}, no {state['local']}, "
        f"olhando para {state['interlocutor']} com {state['estado_emocional']}.\n\n"
        f"— {fala}... entendi."
    )


# ==========================================================
# 4) FILTRO DE VIOLAÇÃO
# ==========================================================

def resposta_viola_estado(resposta: str, state: dict) -> list[str]:
    texto = (resposta or "").lower()
    violacoes = []

    local = str(state.get("local", "")).lower()
    interlocutor = str(state.get("interlocutor", "")).lower()

    locais_proibidos = ["sala", "rua", "banheiro", "cozinha", "varanda", "carro"]
    for loc in locais_proibidos:
        if loc != local and re.search(rf"\b{re.escape(loc)}\b", texto):
            violacoes.append(f"Possível mudança indevida de local: {loc}")

    if interlocutor and interlocutor not in texto:
        violacoes.append("A resposta pode ter perdido o interlocutor ativo.")

    acoes_proibidas = [
        "janio sorri",
        "janio se aproxima",
        "janio toca",
        "janio beija",
        "você sorri",
        "você se aproxima",
        "você toca",
        "você beija",
    ]

    for acao in acoes_proibidas:
        if acao in texto:
            violacoes.append(f"Possível autoria indevida do usuário: {acao}")

    return violacoes


def corrigir_resposta_se_necessario(resposta: str, state: dict, violacoes: list[str]) -> str:
    if not violacoes:
        return resposta

    return (
        f"Mary continua {state['mary_acao']}, no {state['local']}, "
        f"mantendo o foco em {state['interlocutor']}.\n\n"
        "— Repete isso pra mim com calma."
    )


# ==========================================================
# 5) INTERFACE
# ==========================================================

fala_usuario = st.text_area("Fala/Ação do usuário")

if st.button("Processar turno"):
    state["turno"] += 1

    prompt_modelo = montar_prompt_para_modelo(state, fala_usuario)
    resposta_bruta = gerar_resposta_mock(state, fala_usuario)

    violacoes = resposta_viola_estado(resposta_bruta, state)
    resposta_final = corrigir_resposta_se_necessario(resposta_bruta, state, violacoes)

    st.markdown("### Prompt enviado ao modelo")
    st.code(prompt_modelo, language="text")

    st.markdown("### Resposta bruta")
    st.write(resposta_bruta)

    st.markdown("### Violações detectadas")
    if violacoes:
        st.error(violacoes)
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
