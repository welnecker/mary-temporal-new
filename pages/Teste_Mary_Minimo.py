import streamlit as st

st.title("Teste Mary Mínimo")

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
    }

state = st.session_state.mary_state_minimo

fala_usuario = st.text_area("Fala/Ação do usuário")

if st.button("Gerar contexto"):
    contexto = f"""
[ESTADO REAL DA CENA]
Personagem: {state["personagem"]}
Timeline: {state["timeline"]}
Interlocutor ativo: {state["interlocutor"]}
Local: {state["local"]}
Tempo: {state["tempo"]}
Ação atual de Mary: {state["mary_acao"]}
Estado emocional: {state["estado_emocional"]}
Modo de interação: {state["modo"]}

[REGRA]
- Não trocar local.
- Não trocar interlocutor.
- Não reiniciar a cena.
- Mary só controla as próprias ações.
- O usuário controla apenas as ações dele.

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()

    st.code(contexto, language="text")

    # SIMULA RESPOSTA (SEM IA AINDA)
    st.markdown("### Resposta simulada da Mary")
    st.write(f"{state['personagem']} continua {state['mary_acao']}, olhando para você.")

nova_acao = st.text_input("Nova ação manual de Mary")
if st.button("Atualizar ação"):
    if nova_acao.strip():
        state["mary_acao"] = nova_acao.strip()
        st.success("Ação atualizada.")
