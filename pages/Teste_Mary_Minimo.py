import streamlit as st

st.title("Teste Mary Mínimo - Mundo por Eventos")

# ==========================================================
# 1) ESTADO INICIAL
# ==========================================================

if "mary_state_minimo" not in st.session_state:
    st.session_state.mary_state_minimo = {
        "personagem": "Mary",
        "timeline": "universitaria_creator",

        "local": "quarto",
        "tempo": "noite",

        "interlocutor": "Janio Donisete",
        "presenca_usuario": True,

        "personagens_presentes": ["Mary", "Janio Donisete"],
        "objeto_foco": None,

        "mary_acao": "sentada na beira da cama",
        "estado_emocional": "confiante",
        "modo": "privado",

        "ultimo_evento": "inicio",
        "turno": 0,
    }

state = st.session_state.mary_state_minimo

# Compatibilidade com sessão antiga
state.setdefault("personagens_presentes", ["Mary", "Janio Donisete"])
state.setdefault("presenca_usuario", True)
state.setdefault("objeto_foco", None)
state.setdefault("ultimo_evento", "inicio")
state.setdefault("turno", 0)


# ==========================================================
# 2) EVENTOS POSSÍVEIS
# ==========================================================

EVENTOS = {
    "usuario_entrou": [
        "entro no quarto",
        "entrei no quarto",
        "chego no quarto",
        "cheguei no quarto",
    ],

    "usuario_saiu": [
        "fui embora",
        "vou embora",
        "saio do quarto",
        "saí do quarto",
        "deixo o quarto",
    ],

    "usuario_aproximou": [
        "me aproximo",
        "chego perto",
        "chego mais perto",
        "me aproximo dela",
    ],

    "usuario_parou_perto": [
        "paro na sua frente",
        "fico na sua frente",
        "paro diante dela",
    ],

    "usuario_falou_elogio": [
        "você está linda",
        "voce esta linda",
        "você está diferente",
        "voce esta diferente",
        "te acho linda",
    ],

    "camera_mencionada": [
        "câmera",
        "camera",
        "gravar",
        "gravando",
        "live",
        "conteúdo",
        "conteudo",
    ],

    "celular_mensagem": [
        "mensagem",
        "celular",
        "notificação",
        "notificacao",
        "silvia mandou mensagem",
        "mensagem da silvia",
    ],

    "terceiro_entrou_silvia": [
        "silvia entra",
        "silvia chegou",
        "silvia aparece",
        "silvia bate na porta",
    ],

    "mudanca_local_sala": [
        "vamos para sala",
        "vou para sala",
        "saímos para sala",
        "saimos para sala",
    ],

    "mudanca_local_rua": [
        "vamos para rua",
        "saímos para rua",
        "saimos para rua",
        "vou para rua",
    ],
}


# ==========================================================
# 3) CLASSIFICADOR SIMPLES DE EVENTO
# ==========================================================

def detectar_evento(fala_usuario: str) -> str:
    fala = (fala_usuario or "").lower().strip()

    if not fala:
        return "sem_entrada"

    for evento, gatilhos in EVENTOS.items():
        if any(gatilho in fala for gatilho in gatilhos):
            return evento

    return "evento_desconhecido"


# ==========================================================
# 4) ATUALIZAÇÃO DO MUNDO
# ==========================================================

def aplicar_evento_no_estado(state: dict, evento: str) -> dict:
    state["ultimo_evento"] = evento

    if evento == "usuario_entrou":
        state["presenca_usuario"] = True
        if "Janio Donisete" not in state["personagens_presentes"]:
            state["personagens_presentes"].append("Janio Donisete")
        state["interlocutor"] = "Janio Donisete"
        state["mary_acao"] = "sentada na beira da cama"

    elif evento == "usuario_saiu":
        state["presenca_usuario"] = False
        if "Janio Donisete" in state["personagens_presentes"]:
            state["personagens_presentes"].remove("Janio Donisete")
        state["interlocutor"] = "nenhum"
        state["mary_acao"] = "sentada na beira da cama, sozinha no quarto"

    elif evento == "usuario_aproximou":
        if state.get("presenca_usuario"):
            state["mary_acao"] = "levantando da cama lentamente"

    elif evento == "usuario_parou_perto":
        if state.get("presenca_usuario"):
            state["mary_acao"] = "parada diante de Janio"

    elif evento == "usuario_falou_elogio":
        if state.get("presenca_usuario"):
            state["mary_acao"] = "sorrindo com confiança"
            state["estado_emocional"] = "vaidosa e segura"

    elif evento == "camera_mencionada":
        state["objeto_foco"] = "câmera"
        state["modo"] = "entre privado e persona pública"
        state["mary_acao"] = "dividida entre olhar para Janio e para a câmera"

    elif evento == "celular_mensagem":
        state["objeto_foco"] = "celular"
        state["mary_acao"] = "olhando para o celular por um instante"

    elif evento == "terceiro_entrou_silvia":
        if "Silvia" not in state["personagens_presentes"]:
            state["personagens_presentes"].append("Silvia")
        state["interlocutor"] = "Silvia"
        state["mary_acao"] = "virando o rosto na direção de Silvia"

    elif evento == "mudanca_local_sala":
        state["local"] = "sala"
        state["mary_acao"] = "chegando à sala com atenção ao ambiente"

    elif evento == "mudanca_local_rua":
        state["local"] = "rua"
        state["mary_acao"] = "parada na rua, ajustando a postura"

    elif evento == "evento_desconhecido":
        # Regra central: se não sabe, não inventa.
        state["mary_acao"] = state.get("mary_acao", "parada em silêncio")

    return state


# ==========================================================
# 5) CONTEXTO
# ==========================================================

def montar_contexto(state: dict, fala_usuario: str) -> str:
    return f"""
[ESTADO REAL DA CENA]
Personagem principal: {state["personagem"]}
Timeline: {state["timeline"]}

Local atual: {state["local"]}
Tempo: {state["tempo"]}

Interlocutor ativo: {state["interlocutor"]}
Usuário presente: {state["presenca_usuario"]}
Personagens presentes: {", ".join(state["personagens_presentes"])}

Objeto em foco: {state["objeto_foco"]}
Ação atual de Mary: {state["mary_acao"]}
Estado emocional de Mary: {state["estado_emocional"]}
Modo de interação: {state["modo"]}

Último evento detectado: {state["ultimo_evento"]}
Turno: {state["turno"]}

[REGRA]
- O estado acima é a verdade da cena.
- Se uma fala do usuário não gerar evento conhecido, manter o estado atual.
- Mary só controla as próprias ações.
- O usuário controla apenas as ações dele.
- O modelo, quando existir, só escreverá texto; não atualizará estado.

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()


# ==========================================================
# 6) INTERFACE
# ==========================================================

fala_usuario = st.text_area("Fala/Ação do usuário")

if st.button("Processar turno"):
    state["turno"] += 1

    evento = detectar_evento(fala_usuario)
    state = aplicar_evento_no_estado(state, evento)

    st.session_state.mary_state_minimo = state

    contexto = montar_contexto(state, fala_usuario)

    st.code(contexto, language="text")

    st.markdown("### Resposta simulada da Mary")
    st.write(
        f"Mary permanece {state['mary_acao']}, "
        f"em {state['local']}, com foco atual em {state['interlocutor']}."
    )

st.markdown("---")
st.subheader("Estado atual salvo")
st.json(state)

if st.button("Resetar teste"):
    del st.session_state.mary_state_minimo
    st.rerun()
