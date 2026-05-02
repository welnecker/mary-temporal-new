import streamlit as st

st.title("Teste Mary Mínimo - Automático")

if "mary_state_minimo" not in st.session_state:
    st.session_state.mary_state_minimo = {
        "personagem": "Mary",
        "timeline": "universitaria_creator",
        "interlocutor": "Janio Donisete",
        "local": "quarto",
        "tempo": "noite",
        "mary_acao": "sentada na beira da cama",
        "estado_emocional": "confiante",
        "modo": "privado",
        "turno": 0,
    }

state = st.session_state.mary_state_minimo


def decidir_acao_mary(state: dict, fala_usuario: str) -> str:
    fala = (fala_usuario or "").lower().strip()
    acao_atual = state.get("mary_acao", "")

    if not fala:
        return acao_atual

    if "entro no quarto" in fala:
        return "sentada na beira da cama"

    if "me aproximo" in fala:
        return "levantando da cama lentamente"

    if "paro na sua frente" in fala:
        return "parada diante de você"

    if "olho para você" in fala or "olho pra você" in fala:
        return "sustentando o olhar em silêncio"

    if "sorrio" in fala:
        return "sorrindo de volta com confiança"

    return acao_atual


def montar_contexto(state: dict, fala_usuario: str) -> str:
    return f"""
[ESTADO REAL DA CENA]
Personagem: {state["personagem"]}
Timeline: {state["timeline"]}
Interlocutor ativo: {state["interlocutor"]}
Local: {state["local"]}
Tempo: {state["tempo"]}
Ação atual de Mary: {state["mary_acao"]}
Estado emocional: {state["estado_emocional"]}
Modo de interação: {state["modo"]}
Turno: {state["turno"]}

[REGRA]
- Não trocar local.
- Não trocar interlocutor.
- Não reiniciar a cena.
- Mary só controla as próprias ações.
- O usuário controla apenas as ações dele.

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()


fala_usuario = st.text_area("Fala/Ação do usuário")

if st.button("Gerar contexto automático"):
    state["turno"] += 1
    state["mary_acao"] = decidir_acao_mary(state, fala_usuario)

    contexto = montar_contexto(state, fala_usuario)

    st.code(contexto, language="text")

    st.markdown("### Resposta simulada da Mary")
    st.write(
        f"{state['personagem']} continua {state['mary_acao']}, "
        f"no {state['local']}, mantendo atenção em {state['interlocutor']}."
    )

st.markdown("---")

st.subheader("Estado atual salvo")
st.json(state)

if st.button("Resetar teste"):
    del st.session_state.mary_state_minimo
    st.rerun()
