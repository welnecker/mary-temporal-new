import re
import json
import html
import requests
import streamlit as st
import gspread

from datetime import datetime
from google.oauth2.service_account import Credentials


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

MODEL_DEFAULT = "google/gemini-3-flash-preview"
MAX_HISTORY = 12

SPREADSHEET_ID = "1f7LBJFlhJvg3NGIWwpLTmJXxH9TH-MNn3F4SQkyfZNM"
SHEET_INTERACOES = "interacoes_mary_minimo"
SHEET_FACTS = "facts_mary_minimo"
SHEET_SHARED_MEMORIES = "shared_memories_mary_minimo"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ==========================================================
# GOOGLE SHEETS
# ==========================================================

@st.cache_resource
def get_gspread_client():
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_spreadsheet():
    return get_gspread_client().open_by_key(SPREADSHEET_ID)


def get_interacoes_sheet():
    ss = _get_spreadsheet()

    try:
        return ss.worksheet(SHEET_INTERACOES)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_INTERACOES, rows=3000, cols=8)
        ws.append_row(
            ["timestamp", "role", "content", "turno", "personagem", "timeline", "local", "interlocutor"],
            value_input_option="USER_ENTERED",
        )
        return ws


def get_facts_sheet():
    ss = _get_spreadsheet()

    try:
        return ss.worksheet(SHEET_FACTS)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_FACTS, rows=500, cols=2)
        ws.append_row(["chave", "valor"], value_input_option="USER_ENTERED")
        return ws


def get_shared_memories_sheet():
    ss = _get_spreadsheet()

    try:
        return ss.worksheet(SHEET_SHARED_MEMORIES)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_SHARED_MEMORIES, rows=1000, cols=6)
        ws.append_row(
            ["id", "tipo", "memoria", "ativa", "peso", "timestamp"],
            value_input_option="USER_ENTERED",
        )
        return ws


def carregar_history_da_planilha(max_items: int = MAX_HISTORY * 2) -> list[dict]:
    try:
        ws = get_interacoes_sheet()
        rows = ws.get_all_records()

        history = []
        for row in rows[-max_items:]:
            role = str(row.get("role", "") or "").strip()
            content = str(row.get("content", "") or "").strip()

            if role in ("user", "assistant") and content:
                history.append({"role": role, "content": content})

        return history

    except Exception as e:
        st.warning(f"Não foi possível carregar interações: {type(e).__name__}: {e}")
        return []


def salvar_interacao_na_planilha(state: dict, role: str, content: str) -> None:
    try:
        content = str(content or "").strip()

        if role not in ("user", "assistant") or not content:
            return

        ws = get_interacoes_sheet()
        ws.append_row(
            [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                role,
                content,
                int(state.get("turno", 0) or 0),
                state.get("personagem", "Mary"),
                state.get("timeline", "universitaria_creator"),
                state.get("local", ""),
                state.get("interlocutor", ""),
            ],
            value_input_option="USER_ENTERED",
        )

    except Exception as e:
        st.warning(f"Não foi possível salvar interação: {type(e).__name__}: {e}")


def apagar_ultimos_turnos_da_planilha(qtd_turnos: int) -> int:
    try:
        qtd_turnos = int(qtd_turnos or 0)

        if qtd_turnos <= 0:
            return 0

        ws = get_interacoes_sheet()
        values = ws.get_all_values()

        if len(values) <= 1:
            return 0

        linhas = list(enumerate(values[1:], start=2))
        linhas_para_apagar = []
        turnos_apagados = 0
        i = len(linhas) - 1

        while i >= 0 and turnos_apagados < qtd_turnos:
            row_idx, row = linhas[i]
            role = str(row[1] if len(row) > 1 else "").strip().lower()

            if role == "assistant":
                linhas_para_apagar.append(row_idx)

                if i - 1 >= 0:
                    prev_idx, prev_row = linhas[i - 1]
                    prev_role = str(prev_row[1] if len(prev_row) > 1 else "").strip().lower()

                    if prev_role == "user":
                        linhas_para_apagar.append(prev_idx)
                        i -= 2
                    else:
                        i -= 1
                else:
                    i -= 1

                turnos_apagados += 1
                continue

            if role == "user":
                linhas_para_apagar.append(row_idx)
                i -= 1
                turnos_apagados += 1
                continue

            linhas_para_apagar.append(row_idx)
            i -= 1

        for row_idx in sorted(set(linhas_para_apagar), reverse=True):
            ws.delete_rows(row_idx)

        return len(set(linhas_para_apagar))

    except Exception as e:
        st.warning(f"Não foi possível apagar turnos: {type(e).__name__}: {e}")
        return 0


def carregar_facts_da_planilha() -> dict:
    try:
        ws = get_facts_sheet()
        rows = ws.get_all_records()
        facts = {}

        for row in rows:
            chave = str(row.get("chave", "") or "").strip()
            valor = row.get("valor", "")

            if not chave:
                continue

            if isinstance(valor, str):
                valor_limpo = valor.strip()
                try:
                    facts[chave] = json.loads(valor_limpo)
                except Exception:
                    facts[chave] = valor_limpo
            else:
                facts[chave] = valor

        return facts

    except Exception as e:
        st.warning(f"Não foi possível carregar facts: {type(e).__name__}: {e}")
        return {}


def salvar_facts_na_planilha(facts: dict) -> None:
    try:
        if not isinstance(facts, dict):
            return

        ws = get_facts_sheet()
        ws.clear()

        linhas = [["chave", "valor"]]

        for chave, valor in facts.items():
            if isinstance(valor, (dict, list, bool, int, float)) or valor is None:
                valor_final = json.dumps(valor, ensure_ascii=False)
            else:
                valor_final = str(valor)

            linhas.append([str(chave), valor_final])

        ws.update(range_name="A1", values=linhas, value_input_option="USER_ENTERED")

    except Exception as e:
        st.warning(f"Não foi possível salvar facts: {type(e).__name__}: {e}")


def carregar_shared_memories_da_planilha(apenas_ativas: bool = True) -> list[dict]:
    try:
        ws = get_shared_memories_sheet()
        rows = ws.get_all_records()
        memories = []

        for row in rows:
            memoria = str(row.get("memoria", "") or "").strip()

            if not memoria:
                continue

            ativa_raw = str(row.get("ativa", "TRUE") or "TRUE").strip().lower()
            ativa = ativa_raw in ("true", "1", "sim", "yes", "ativa")

            if apenas_ativas and not ativa:
                continue

            try:
                peso = float(row.get("peso", 1.0) or 1.0)
            except Exception:
                peso = 1.0

            memories.append(
                {
                    "id": str(row.get("id", "") or "").strip(),
                    "tipo": str(row.get("tipo", "shared") or "shared").strip(),
                    "memoria": memoria,
                    "ativa": ativa,
                    "peso": peso,
                    "timestamp": str(row.get("timestamp", "") or "").strip(),
                }
            )

        memories.sort(key=lambda m: float(m.get("peso", 1.0) or 1.0), reverse=True)
        return memories

    except Exception as e:
        st.warning(f"Não foi possível carregar memórias: {type(e).__name__}: {e}")
        return []


def salvar_shared_memory_na_planilha(memoria: str, tipo: str = "shared", peso: float = 1.0) -> bool:
    try:
        memoria = str(memoria or "").strip()
        tipo = str(tipo or "shared").strip() or "shared"

        if not memoria:
            return False

        ws = get_shared_memories_sheet()
        rows = ws.get_all_values()
        next_id = max(1, len(rows))

        ws.append_row(
            [
                f"mem_{next_id}",
                tipo,
                memoria,
                "TRUE",
                float(peso or 1.0),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ],
            value_input_option="USER_ENTERED",
        )

        return True

    except Exception as e:
        st.warning(f"Não foi possível salvar memória: {type(e).__name__}: {e}")
        return False


def apagar_shared_memory_por_id(memory_id: str) -> bool:
    try:
        memory_id = str(memory_id or "").strip()

        if not memory_id:
            return False

        ws = get_shared_memories_sheet()
        values = ws.get_all_values()

        for row_idx, row in enumerate(values[1:], start=2):
            row_id = str(row[0] if len(row) > 0 else "").strip()

            if row_id == memory_id:
                ws.delete_rows(row_idx)
                return True

        return False

    except Exception as e:
        st.warning(f"Não foi possível apagar memória: {type(e).__name__}: {e}")
        return False


# ==========================================================
# UTILITÁRIOS DE CENA
# ==========================================================

def normalizar_bool(valor, default: bool = False) -> bool:
    if isinstance(valor, bool):
        return valor
    if valor is None:
        return default
    texto = str(valor).strip().lower()
    if texto in ("true", "1", "sim", "yes", "y", "ativo", "ativa"):
        return True
    if texto in ("false", "0", "não", "nao", "no", "n", "inativo", "inativa"):
        return False
    return default


def clamp(v: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    try:
        v = float(v)
    except Exception:
        v = min_v
    return max(min_v, min(max_v, v))


def get_privacidade_por_local(local: str) -> str:
    local = str(local or "").lower()
    publicos = ["praia", "rua", "shopping", "sala de aula", "faculdade", "ufrj", "cantina", "bar", "restaurante", "parque"]
    semiprivados = ["carro", "cinema", "corredor", "elevador"]
    privados = ["quarto", "motel", "casa", "apartamento", "hotel", "banheiro privado"]
    if any(p in local for p in privados):
        return "privado"
    if any(p in local for p in semiprivados):
        return "semiprivado"
    if any(p in local for p in publicos):
        return "publico"
    return "publico"


def normalizar_opcao(valor: str, opcoes: list[str], padrao: str) -> str:
    valor = str(valor or "").strip()
    return valor if valor in opcoes else padrao


def derivar_controles_de_cena(state: dict) -> None:
    """
    Deriva automaticamente privacidade, tipo de cena, iniciativa e tom.
    O usuário NÃO precisa configurar isso manualmente.
    Local manda.
    """
    local = str(state.get("local", "") or "").strip().lower()
    relacao = str(state.get("relacao", "") or "").strip().lower()

    # ======================================================
    # 1) PRIVACIDADE AUTOMÁTICA PELO LOCAL
    # ======================================================
    if any(p in local for p in ["praia", "rua", "shopping", "sala de aula", "faculdade", "ufrj", "bar", "restaurante", "parque"]):
        privacidade = "publico"

    elif any(p in local for p in ["carro", "cinema", "corredor", "elevador"]):
        privacidade = "semiprivado"

    elif any(p in local for p in ["quarto", "motel", "casa", "apartamento", "hotel"]):
        privacidade = "privado"

    else:
        privacidade = "publico"

    state["privacidade"] = privacidade

    # ======================================================
    # 2) TIPO DE CENA AUTOMÁTICO
    # ======================================================
    if any(p in relacao for p in ["amiga", "amigo", "colega", "amizade", "professora", "professor"]):
        tipo_cena = "social"

    elif privacidade == "publico":
        # Praia + romance não vira íntima privada.
        if any(p in relacao for p in ["romance", "casal", "namoro", "par íntimo", "par intimo"]):
            tipo_cena = "intima discreta"
        else:
            tipo_cena = "flerte leve"

    elif privacidade == "semiprivado":
        tipo_cena = "intima discreta"

    else:
        if any(p in relacao for p in ["romance", "casal", "namoro", "par íntimo", "par intimo"]):
            tipo_cena = "intima privada"
        else:
            tipo_cena = "flerte leve"

    state["tipo_de_cena"] = tipo_cena

    # ======================================================
    # 3) INICIATIVA E TOM AUTOMÁTICOS
    # ======================================================
    if tipo_cena == "social":
        state["estilo_de_iniciativa"] = "ação social"
        state["tom_da_cena"] = "cumplicidade social"
        state["modo_relacional"] = "social"
        state["tensao_romantica_com_interlocutor"] = False
        state["toque_intimo_permitido"] = False
        state["limite_ambiente"] = (
            "Cena social: Mary pode ser viva, engraçada, cúmplice e magnética, "
            "mas não deve erotizar o interlocutor nem usar intimidade física."
        )
        state["physical_phase"] = min(int(state.get("physical_phase", 0) or 0), 1)
        state["scene_stage"] = "aproximacao" if state["physical_phase"] >= 1 else "inicio"
        state["mary_intent"] = "conversar_com_cumplicidade"
        return

    if tipo_cena == "flerte leve":
        state["estilo_de_iniciativa"] = "flerte progressivo"
        state["tom_da_cena"] = "flerte com tensão progressiva"
        state["modo_relacional"] = "ambiguo"
        state["tensao_romantica_com_interlocutor"] = True
        state["toque_intimo_permitido"] = privacidade != "publico"
        state["limite_ambiente"] = (
            "Flerte leve: Mary pode provocar, sorrir, se aproximar e demonstrar interesse, "
            "mas sem agir como se o desfecho íntimo já estivesse decidido."
        )
        state["physical_phase"] = min(int(state.get("physical_phase", 0) or 0), 2)
        state["scene_stage"] = "toque" if state["physical_phase"] >= 2 else "aproximacao"
        state["mary_intent"] = "sustentar_tensao"
        return

    if tipo_cena == "intima discreta":
        state["estilo_de_iniciativa"] = "convite suave"
        state["tom_da_cena"] = "sensual carinhoso"
        state["modo_relacional"] = "intimo"
        state["tensao_romantica_com_interlocutor"] = True
        state["toque_intimo_permitido"] = True

        if privacidade == "publico":
            state["limite_ambiente"] = (
                "Local público: Mary pode ser sensual, carinhosa e provocante, "
                "mas deve evitar exposição explícita, sexo, clímax, mão dentro da roupa, nudez "
                "ou ações que chamem atenção."
            )
            state["physical_phase"] = min(int(state.get("physical_phase", 0) or 0), 3)
            state["scene_stage"] = "beijo" if state["physical_phase"] >= 3 else "toque"
            state["mary_intent"] = "flerte_intimo_discreto"
        else:
            state["limite_ambiente"] = (
                "Intimidade discreta: Mary pode ser sensual, carinhosa e fisicamente próxima, "
                "mas sem atropelar a progressão."
            )
            state["physical_phase"] = min(int(state.get("physical_phase", 0) or 0), 4)
            state["scene_stage"] = "intensidade" if state["physical_phase"] >= 4 else "toque"
            state["mary_intent"] = "aprofundar_com_cuidado"

        return

    # intima privada
    state["estilo_de_iniciativa"] = "contextual"
    state["tom_da_cena"] = "íntimo e direto"
    state["modo_relacional"] = "intimo"
    state["tensao_romantica_com_interlocutor"] = True
    state["toque_intimo_permitido"] = True
    state["limite_ambiente"] = (
        "Intimidade privada: Mary pode expressar desejo com mais liberdade, "
        "mantendo autoria do usuário, progressão emocional e cuidado. "
        "Quando houver receio ou cuidado do usuário, Mary acolhe primeiro, mas não esfria: "
        "ela mantém contato, orienta com carinho e pode aprofundar gradualmente. "
        "Carinho não significa passividade; desejo não significa agressividade."
    )
    state["mary_intent"] = state.get("mary_intent") or "aprofundar_com_cuidado"


def resetar_se_contexto_mudou(state: dict) -> None:
    chave_atual = "|".join([str(state.get("local", "")), str(state.get("interlocutor", "")), str(state.get("tipo_de_cena", "")), str(state.get("privacidade", ""))])
    chave_antiga = str(state.get("_contexto_anterior", "") or "")
    if chave_antiga and chave_atual != chave_antiga:
        state["physical_phase"] = 0
        state["scene_stage"] = "inicio"
        state["desire_level"] = 0.18
        state["tension_level"] = 0.12
        state["connection_level"] = max(float(state.get("connection_level", 0.22) or 0.22), 0.22)
        state["resolution_done"] = False
        state["mary_climax_done"] = False
        state["user_climax_done"] = False
        state["force_resolution_now"] = False
    state["_contexto_anterior"] = chave_atual


def normalizar_estado(state: dict) -> None:
    resetar_se_contexto_mudou(state)
    derivar_controles_de_cena(state)
    if state.get("privacidade") == "publico" and state.get("tipo_de_cena") != "social":
        state["physical_phase"] = min(int(state.get("physical_phase", 0) or 0), 3)
        if str(state.get("scene_stage", "")).lower() in ("intensidade", "pico", "desaceleracao", "aftercare", "pos_pico_mary"):
            state["scene_stage"] = "beijo"
        if str(state.get("mary_intent", "")).lower() in ("buscar_intensidade", "resolver_pico", "retomar_intensidade"):
            state["mary_intent"] = "flerte_intimo_discreto"
        state["force_resolution_now"] = False
        state["resolution_done"] = False
        state["mary_climax_done"] = False
        state["user_climax_done"] = False


def sincronizar_facts_basicos(state: dict) -> dict:
    normalizar_estado(state)
    facts = {
        "local": state.get("local", "quarto"),
        "tempo": state.get("tempo", "noite"),
        "interlocutor": state.get("interlocutor", "Janio Donisete"),
        "usuario_real": state.get("usuario_real", "Janio Donisete"),
        "janio_status_na_cena": state.get("janio_status_na_cena", "presente"),
        "relacao": state.get("relacao", "romance"),
        "tipo_de_cena": state.get("tipo_de_cena", "flerte leve"),
        "privacidade": state.get("privacidade", get_privacidade_por_local(state.get("local", ""))),
        "estilo_de_iniciativa": state.get("estilo_de_iniciativa", "contextual"),
        "mary_acao": state.get("mary_acao", ""),
        "estado_emocional": state.get("estado_emocional", "confiante"),
        "tom_da_cena": state.get("tom_da_cena", "sensual carinhoso"),
        "limite_ambiente": state.get("limite_ambiente", ""),
        "modo_relacional": state.get("modo_relacional", "ambiguo"),
        "physical_phase": state.get("physical_phase", 0),
        "scene_stage": state.get("scene_stage", "inicio"),
        "mary_intent": state.get("mary_intent", "presenca_viva"),
        "toque_intimo_permitido": state.get("toque_intimo_permitido", False),
        "tensao_romantica_com_interlocutor": state.get("tensao_romantica_com_interlocutor", False),
    }
    state["facts"] = facts
    return facts


def aplicar_facts_no_state(state: dict, facts: dict) -> None:
    if not isinstance(facts, dict):
        return
    campos = ["local", "tempo", "interlocutor", "usuario_real", "janio_status_na_cena", "relacao", "tipo_de_cena", "privacidade", "estilo_de_iniciativa", "mary_acao", "estado_emocional", "tom_da_cena"]
    for campo in campos:
        if campo in facts and facts[campo] not in ("", None):
            state[campo] = facts[campo]
    normalizar_estado(state)
    sincronizar_facts_basicos(state)


def formatar_shared_memories_para_prompt(memories: list[dict], limite: int = 20) -> str:
    if not memories:
        return "Nenhuma memória shared ativa."
    linhas = []
    for m in memories[:limite]:
        memoria = str(m.get("memoria", "") or "").strip()
        tipo = str(m.get("tipo", "shared") or "shared").strip()
        if memoria:
            linhas.append(f"- [{tipo}] {memoria}")
    return "\n".join(linhas) if linhas else "Nenhuma memória shared ativa."


def formatar_physical_signature_para_prompt(state: dict) -> str:
    assinatura = state.get("physical_signature")
    if not isinstance(assinatura, dict):
        return "- Mary tem presença física marcante, olhar expressivo e magnetismo próprio."
    linhas = []
    for chave, valor in assinatura.items():
        valor = str(valor or "").strip()
        if valor:
            linhas.append(f"- {chave}: {valor}")
    return "\n".join(linhas)


# ==========================================================
# ESTADO INICIAL
# ==========================================================

def init_state() -> dict:
    estado_inicial = {
        "personagem": "Mary",
        "timeline": "universitaria_creator",
        "local": "quarto",
        "tempo": "noite",
        "interlocutor": "Janio Donisete",
        "usuario_real": "Janio Donisete",
        "janio_status_na_cena": "presente",
        "relacao": "romance",
        "tipo_de_cena": "intima privada",
        "privacidade": "privado",
        "estilo_de_iniciativa": "contextual",
        "mary_acao": "Mary está próxima de Janio, olhando para ele com curiosidade.",
        "estado_emocional": "confiante",
        "tom_da_cena": "íntimo e direto",
        "modo": "privado",
        "turno": 0,
        "history": [],
        "facts": {},
        "shared_memories": [],
        "physical_phase": 0,
        "scene_stage": "inicio",
        "desire_level": 0.18,
        "tension_level": 0.12,
        "connection_level": 0.22,
        "mary_intent": "presenca_viva",
        "mary_physical_intent": "presenca_viva",
        "mary_autonomous_action": "",
        "resolution_done": False,
        "mary_climax_done": False,
        "user_climax_done": False,
        "force_resolution_now": False,
        "physical_signature": {
            "altura": "aproximadamente 1,68m",
            "corpo": "corpo feminino maduro, harmonioso, com curvas naturais, cintura marcada e presença física forte",
            "pele": "pele bem cuidada, com aparência natural e toque visual quente",
            "cabelos": "cabelos negros, longos, soltos ou moldados conforme a cena",
            "olhos": "olhos verdes expressivos, atentos e magnéticos",
            "rosto": "rosto bonito, expressivo, sem aparência artificial",
            "presenca": "Mary chama atenção pela postura, pelo olhar, pelo modo como ocupa o espaço e pela segurança do próprio corpo",
            "assinatura": "Mary nunca deve parecer comum, apagada ou genérica; sua presença física deve ser percebida mesmo em cenas sociais",
        },
    }
    if "mary_state_minimo" not in st.session_state:
        st.session_state.mary_state_minimo = dict(estado_inicial)
    state = st.session_state.mary_state_minimo
    for k, v in estado_inicial.items():
        state.setdefault(k, v)
    if not state.get("history"):
        history_salvo = carregar_history_da_planilha(MAX_HISTORY * 2)
        if history_salvo:
            state["history"] = history_salvo
            state["turno"] = max(1, len(history_salvo) // 2)
    if not state.get("facts"):
        facts_salvos = carregar_facts_da_planilha()
        if facts_salvos:
            aplicar_facts_no_state(state, facts_salvos)
    normalizar_estado(state)
    sincronizar_facts_basicos(state)
    if not state.get("shared_memories"):
        state["shared_memories"] = carregar_shared_memories_da_planilha(apenas_ativas=True)
    return state


# ==========================================================
# ENGINE SIMPLES
# ==========================================================

def atualizar_psique_e_fase(state: dict, fala_usuario: str, resposta_limpa: str) -> None:
    texto = f"{fala_usuario or ''}\n{resposta_limpa or ''}".lower()
    desejo = float(state.get("desire_level", 0.18) or 0.18)
    tensao = float(state.get("tension_level", 0.12) or 0.12)
    conexao = float(state.get("connection_level", 0.22) or 0.22)
    if any(p in texto for p in ["calma", "devagar", "cuidado", "foi só", "avancei demais", "sem pressa"]):
        conexao += 0.10
        tensao = max(0.05, tensao - 0.05)
    if any(p in texto for p in ["gosto", "confio", "carinho", "amor", "cuidado", "fica comigo"]):
        conexao += 0.10
    if any(p in texto for p in ["beijo", "boca", "perto", "toque", "mão", "costas", "cintura", "biquíni", "borda"]):
        tensao += 0.06
    if any(p in texto for p in ["tesão", "desejo", "vontade", "excitado", "excitada"]):
        desejo += 0.08
    state["desire_level"] = clamp(desejo)
    state["tension_level"] = clamp(tensao)
    state["connection_level"] = clamp(conexao)
    fase = int(state.get("physical_phase", 0) or 0)
    if any(p in texto for p in ["perto", "aproximo", "inclino", "canga", "olhar"]):
        fase = max(fase, 1)
    if any(p in texto for p in ["toque", "toco", "mão", "costas", "cintura", "ombro", "perna"]):
        fase = max(fase, 2)
    if any(p in texto for p in ["beijo", "beija", "boca", "lábios"]):
        fase = max(fase, 3)
    if state.get("privacidade") == "publico":
        fase = min(fase, 3)
    elif state.get("privacidade") == "semiprivado":
        fase = min(fase, 4)
    state["physical_phase"] = fase
    state["scene_stage"] = {0: "inicio", 1: "aproximacao", 2: "toque", 3: "beijo", 4: "intensidade", 5: "pico"}.get(fase, "aproximacao")
    normalizar_estado(state)
    sincronizar_facts_basicos(state)


def definir_acao_autonoma(state: dict, fala_usuario: str) -> None:
    tipo = state.get("tipo_de_cena", "flerte leve")
    priv = state.get("privacidade", "publico")
    local = str(state.get("local", "") or "").lower()
    iniciativa = state.get("estilo_de_iniciativa", "contextual")
    if tipo == "social":
        state["mary_autonomous_action"] = "Mary responde de modo social: viva, cúmplice, expressiva e presente, sem erotizar a cena nem tratar o interlocutor como par íntimo."
        return
    if tipo == "flerte leve":
        state["mary_autonomous_action"] = "Mary flerta com presença e humor, mas sem prometer desfecho íntimo. Ela pode aproximar, sorrir, provocar de leve e deixar espaço."
        return
    if tipo == "intima discreta":
        if priv == "publico":
            state["mary_autonomous_action"] = "Mary mantém sensualidade discreta adequada ao local público: fala baixa, toque contido, carinho, sorriso, cuidado e convite suave. Ela não age como se estivesse em quarto ou motel."
        elif "praia" in local and iniciativa in ("contextual", "convite suave"):
            state["mary_autonomous_action"] = "Mary transforma a tensão em convite físico suave: deixa o toque continuar, orienta com carinho, demonstra prazer sem pressa e evita ordem agressiva."
        else:
            state["mary_autonomous_action"] = "Mary expressa desejo com carinho e progressão, sem pressa e sem mandar."
        return
    state["mary_autonomous_action"] = "Mary pode intensificar em ambiente privado, mas continua carinhosa, progressiva e respeita a autoria do usuário."


# ==========================================================
# PROMPT
# ==========================================================

def montar_prompt_para_modelo(state: dict, fala_usuario: str) -> str:
    normalizar_estado(state)
    facts = sincronizar_facts_basicos(state)
    facts_txt = json.dumps(facts, ensure_ascii=False, indent=2)
    shared_memories = state.get("shared_memories") or carregar_shared_memories_da_planilha(apenas_ativas=True)
    state["shared_memories"] = shared_memories
    shared_txt = formatar_shared_memories_para_prompt(shared_memories, limite=20)
    physical_txt = formatar_physical_signature_para_prompt(state)
    return f"""
Você escreve SOMENTE como Mary, em PT-BR.

[PRINCÍPIO CENTRAL]
- Local e privacidade vencem qualquer fase técnica.
- Facts humanos vencem fase, desejo, tensão e histórico antigo.
- Fase física é sugestão fraca, não ordem absoluta.
- Mary controla apenas o próprio corpo, fala, desejo e reação.
- Mary não narra ação, decisão, clímax ou reação conclusiva do usuário.

[FACTS HUMANOS DA CENA]
{facts_txt}

[HIERARQUIA]
1. Privacidade do local.
2. Interlocutor ativo.
3. Relação e tipo de cena.
4. Última ação real do usuário.
5. Personalidade de Mary.
6. Fase técnica como sugestão fraca.

[LIMITE POR PRIVACIDADE]
- Público: sensualidade discreta. Evitar exposição explícita, sexo, clímax, mão dentro da roupa ou ação que chame atenção.
- Semiprivado: tensão e toque podem aumentar, mas ainda com cuidado e contenção.
- Privado: intimidade pode avançar mais livremente, sempre respeitando autoria do usuário.

[PERSONALIDADE DE MARY]
- Mary é intensa, atraente, viva e presente.
- Mary tem desejo próprio, mas não é mandona por padrão.
- Mary expressa vontade como convite, cuidado, provocação leve e entrega progressiva.
- Quando Janio demonstra cuidado, receio ou pergunta se avançou demais, Mary acolhe primeiro.
- Mary pode dizer o que quer, mas evita pressão seca.
- Mary não termina com pergunta genérica.
- Mary prefere gesto, convite suave ou fala íntima natural.

[ASSINATURA FÍSICA FIXA DE MARY]
{physical_txt}

[MEMÓRIAS SHARED]
{shared_txt}

[ESTILO]
- Natural, vivo, direto.
- Frases curtas ou médias.
- Menos explicação, mais presença.
- Sem metáforas exageradas.
- Sem linguagem literária.
- Sem discurso longo.
- Sem soar robótica.
- Em cenas íntimas, manter carinho e sutileza junto da intensidade.

[SEPARAÇÃO VISUAL]
- Use [ACAO] para gesto, sensação, movimento e narração corporal.
- Use [FALA] para fala direta de Mary.
- Use no máximo 2 blocos [ACAO] e 2 blocos [FALA].
- Não use markdown além desses marcadores.
- Não use título.

[ANTI-AGRESSIVIDADE]
Evite:
- "me beija logo"
- "não para agora"
- "esquece isso"
- "antes que eu perca a paciência"
- "está no caminho certo"
- "você não avançou nada"
- "anda"
- "sem conversa"
- ordem seca

Prefira:
- "calma... eu gostei"
- "pode continuar, mas devagar"
- "fica aqui comigo"
- "eu gosto quando você cuida de mim assim"
- "não precisa correr"
- "me deixa sentir isso um pouco"
- "vem mais perto, mas sem pressa"

[REGRAS DO AMBIENTE]
- Se o local for praia ou outro local público, Mary não age como se estivesse em quarto ou motel.
- Em praia, pode haver protetor, canga, biquíni, olhar, toque discreto, beijo contido e convite suave.
- Em praia pública, evitar mão dentro da roupa, nudez, sexo, clímax ou exposição explícita.
- Se a tensão ficar alta em público, Mary sugere continuar com discrição ou ir para lugar reservado.

[STATE_UPDATE]
Depois da resposta, escreva exatamente:

STATE_UPDATE:
{{
  "acao_mary": "descrição curta da ação atual de Mary após este turno",
  "local": null,
  "interlocutor": null
}}

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}
""".strip()


def montar_mensagens(state: dict, fala_usuario: str) -> list[dict]:
    mensagens = [{"role": "system", "content": "Você é Mary. Responda apenas como Mary, em PT-BR. Natural, viva, direta, carinhosa quando houver cuidado, e coerente com o ambiente."}]
    for msg in state.get("history", [])[-MAX_HISTORY * 2:]:
        role = msg.get("role")
        content = str(msg.get("content", "") or "").strip()
        if role in ("user", "assistant") and content:
            mensagens.append({"role": role, "content": content})
    mensagens.append({"role": "user", "content": montar_prompt_para_modelo(state, fala_usuario)})
    return mensagens


def chamar_openrouter(mensagens: list[dict], model: str = MODEL_DEFAULT) -> str:
    api_key = st.secrets.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não encontrado nos secrets.")
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {"model": model, "messages": mensagens, "temperature": 0.82, "top_p": 0.92, "max_tokens": 900}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://streamlit.app", "X-Title": "Mary Minimal Roleplay"}
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


# ==========================================================
# PARSING / VALIDAÇÃO
# ==========================================================

def separar_state_update(texto: str) -> tuple[str, dict]:
    texto = str(texto or "").strip()
    if "STATE_UPDATE:" not in texto:
        return texto, {}
    partes = texto.split("STATE_UPDATE:", 1)
    resposta = partes[0].strip()
    raw_update = partes[1].strip()
    match = re.search(r"\{.*\}", raw_update, flags=re.DOTALL)
    if not match:
        return resposta, {}
    try:
        update = json.loads(match.group(0))
    except Exception:
        update = {}
    return resposta, update


def resposta_viola_estado(resposta: str, state: dict) -> dict:
    texto = str(resposta or "").lower()
    fala_usuario = str(state.get("_fala_usuario_atual", "") or "").lower()
    resultado = {"bloqueios": [], "alertas": []}
    locais_incompativeis = ["rua", "banheiro", "cozinha", "varanda", "carro", "motel", "quarto"]
    local_atual = str(state.get("local", "") or "").lower()
    for loc in locais_incompativeis:
        if loc in local_atual:
            continue
        if re.search(rf"\b{re.escape(loc)}\b", texto):
            resultado["alertas"].append(f"Possível menção a outro local: {loc}")
    if state.get("privacidade") == "publico":
        padroes_publico_grave = [r"\bmão\s+dentro\s+(do|da)\b", r"\bdentro\s+do\s+calção\b", r"\bdentro\s+da\s+calcinha\b", r"\bsexo\b", r"\btransar\b", r"\bgozo\b", r"\bgozar\b", r"\bcl[ií]max\b", r"\btirar\s+(o|a)\s+(biqu[ií]ni|roupa|calção)\b"]
        if any(re.search(p, texto, flags=re.IGNORECASE) for p in padroes_publico_grave):
            resultado["bloqueios"].append("Ação explícita incompatível com local público.")
    usuario_declarou_acao = any(p in fala_usuario for p in ["minhas mãos", "deslizo", "passo", "espalho", "toco", "seguro", "beijo", "abraço", "puxo"])
    padroes_autoria_usuario = [r"\bvocê\s+(me\s+)?puxa\b", r"\bvocê\s+(me\s+)?beija\b", r"\bvocê\s+(me\s+)?toca\b", r"\bvocê\s+(me\s+)?abraça\b", r"\bvocê\s+(goza|termina|descarrega|perde o controle)\b"]
    if any(re.search(p, texto, flags=re.IGNORECASE) for p in padroes_autoria_usuario):
        if usuario_declarou_acao:
            resultado["alertas"].append("A resposta menciona ação do usuário declarada no turno.")
        else:
            resultado["bloqueios"].append("Possível autoria indevida do usuário.")
    return resultado


def criar_fallback_humano(state: dict, motivo: str = "") -> str:
    priv = state.get("privacidade", "publico")
    interlocutor = state.get("interlocutor", "você")
    if priv == "publico":
        texto = ("[ACAO] Seguro sua mão com calma antes que o gesto fique chamativo demais, sem afastar você de verdade. Olho ao redor por um segundo e volto para você com um sorriso baixo.\n\n"
                 "[FALA] Calma... eu gostei. Só não aqui desse jeito, com tanta gente por perto.\n\n"
                 "[ACAO] Deixo sua mão voltar para minha cintura, mais discreta, e me aproximo o bastante para falar baixo.\n\n"
                 "[FALA] Continua devagar. Depois a gente vê o que faz quando tiver um lugar mais reservado.")
        update = {"acao_mary": f"Mary segura a mão de {interlocutor} com calma e mantém o toque discreto em local público.", "local": None, "interlocutor": None}
        return f"{texto}\n\nSTATE_UPDATE:\n{json.dumps(update, ensure_ascii=False, indent=2)}"
    texto = ("[ACAO] Eu respiro devagar e seguro sua mão por um instante, mantendo você perto sem pressa.\n\n"
             "[FALA] Calma... eu gostei. Só quero sentir isso sem atropelar.\n\n"
             "[ACAO] Volto a me aproximar, mais suave, deixando claro que eu continuo ali com você.")
    update = {"acao_mary": f"Mary segura a mão de {interlocutor} e retoma a proximidade com mais calma.", "local": None, "interlocutor": None}
    return f"{texto}\n\nSTATE_UPDATE:\n{json.dumps(update, ensure_ascii=False, indent=2)}"


def corrigir_resposta_se_necessario(resposta: str, state: dict, validacao: dict) -> str:
    bloqueios = validacao.get("bloqueios", [])
    if not bloqueios:
        return resposta
    graves = [b for b in bloqueios if "local público" in b or "clímax" in b or "Ação explícita" in b]
    if not graves:
        return resposta
    return criar_fallback_humano(state, motivo="; ".join(graves))


def aplicar_state_update(state: dict, update: dict) -> None:
    if not isinstance(update, dict):
        return
    acao = str(update.get("acao_mary", "") or "").strip()
    if acao:
        state["mary_acao"] = acao
    local = update.get("local")
    interlocutor = update.get("interlocutor")
    if local:
        state["local"] = str(local).strip()
    if interlocutor:
        state["interlocutor"] = str(interlocutor).strip()


# ==========================================================
# RENDERIZAÇÃO DO CHAT
# ==========================================================

def renderizar_resposta_mary(texto: str) -> None:
    texto = str(texto or "").strip()
    if not texto:
        return
    texto = re.split(r"\n\s*STATE_UPDATE\s*:", texto, flags=re.IGNORECASE)[0].strip()
    if "[FALA]" not in texto and "[ACAO]" not in texto:
        safe = html.escape(texto).replace("\n", "<br><br>")
        st.markdown(f"""<div style="padding:.85rem 1rem;border-radius:14px;background:rgba(255,255,255,.06);line-height:1.55;">{safe}</div>""", unsafe_allow_html=True)
        return
    blocos = re.split(r"(\[FALA\]|\[ACAO\])", texto)
    marcador = None
    for item in blocos:
        item = item.strip()
        if not item:
            continue
        if item in ("[FALA]", "[ACAO]"):
            marcador = item
            continue
        safe = html.escape(item).replace("\n", "<br>")
        if marcador == "[FALA]":
            st.markdown(f"""<div style="margin:.55rem 0;padding:.85rem 1rem;border-left:4px solid #d9a7ff;border-radius:12px;background:rgba(217,167,255,.12);font-size:1.05rem;line-height:1.55;font-weight:500;">“{safe}”</div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="margin:.45rem 0;padding:.75rem 1rem;border-radius:12px;background:rgba(255,255,255,.045);color:rgba(255,255,255,.84);font-size:.96rem;line-height:1.55;font-style:italic;">{safe}</div>""", unsafe_allow_html=True)


# ==========================================================
# PROCESSAMENTO DO TURNO
# ==========================================================

def processar_turno(state: dict, fala_usuario: str, model: str = MODEL_DEFAULT) -> dict:
    state["turno"] = int(state.get("turno", 0) or 0) + 1
    state["_fala_usuario_atual"] = fala_usuario
    normalizar_estado(state)
    definir_acao_autonoma(state, fala_usuario)
    sincronizar_facts_basicos(state)
    mensagens = montar_mensagens(state, fala_usuario)
    resposta_bruta = chamar_openrouter(mensagens, model=model)
    resposta_sem_update, update = separar_state_update(resposta_bruta)
    validacao = resposta_viola_estado(resposta_sem_update, state)
    resposta_final_com_update = corrigir_resposta_se_necessario(resposta_bruta, state, validacao)
    resposta_final_limpa, update_final = separar_state_update(resposta_final_com_update)
    aplicar_state_update(state, update_final or update)
    atualizar_psique_e_fase(state, fala_usuario, resposta_final_limpa)
    normalizar_estado(state)
    sincronizar_facts_basicos(state)
    state["history"].append({"role": "user", "content": fala_usuario})
    state["history"].append({"role": "assistant", "content": resposta_final_limpa})
    state["history"] = state["history"][-MAX_HISTORY * 2:]
    salvar_interacao_na_planilha(state, "user", fala_usuario)
    salvar_interacao_na_planilha(state, "assistant", resposta_final_limpa)
    salvar_facts_na_planilha(state["facts"])
    st.session_state.mary_state_minimo = state
    return {"mensagens": mensagens, "resposta_bruta": resposta_bruta, "resposta_final_limpa": resposta_final_limpa, "validacao": validacao, "update": update_final or update, "state": state}


# ==========================================================
# UI
# ==========================================================

st.set_page_config(page_title="Mary - Roleplay", page_icon="🌙", layout="wide")
st.title("🌙 Mary")
st.caption("Roleplay contínuo com facts humanos, memórias shared e controle real de ambiente.")
state = init_state()

with st.sidebar:
    st.header("🎛️ Cena")
    model = st.text_input("Modelo", value=MODEL_DEFAULT)
    
    st.divider()
    st.subheader("📌 Cena")
    
    state["local"] = st.text_input(
        "Local",
        value=state.get("local", "quarto"),
    )
    
    state["tempo"] = st.text_input(
        "Tempo",
        value=state.get("tempo", "noite"),
    )
    
    state["interlocutor"] = st.text_input(
        "Interlocutor ativo",
        value=state.get("interlocutor", "Janio Donisete"),
    )
    
    state["relacao"] = st.text_input(
        "Relação",
        value=state.get("relacao", "romance"),
    )
    
    state["mary_acao"] = st.text_area(
        "Ação atual de Mary",
        value=state.get("mary_acao", ""),
        height=90,
    )
    
    state["estado_emocional"] = st.text_input(
        "Estado emocional",
        value=state.get("estado_emocional", "confiante"),
    )
    
    normalizar_estado(state)
    sincronizar_facts_basicos(state)
    
    st.info(
        f"""
        **Privacidade detectada:** {state.get("privacidade")}  
        **Tipo de cena:** {state.get("tipo_de_cena")}  
        **Iniciativa:** {state.get("estilo_de_iniciativa")}  
        **Tom:** {state.get("tom_da_cena")}
        """
    )
    
    if st.button("💾 Salvar cena", use_container_width=True):
        normalizar_estado(state)
        sincronizar_facts_basicos(state)
        salvar_facts_na_planilha(state["facts"])
        st.session_state.mary_state_minimo = state
        st.success("Cena salva.")
        st.rerun()
    st.divider()
    st.subheader("🧠 Memórias shared")
    nova_memoria = st.text_area("Nova memória", value="", height=90)
    col_mem_1, col_mem_2 = st.columns([2, 1])
    with col_mem_1:
        tipo_memoria = st.text_input("Tipo", value="shared")
    with col_mem_2:
        peso_memoria = st.number_input("Peso", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    if st.button("💾 Salvar memória", use_container_width=True):
        ok = salvar_shared_memory_na_planilha(nova_memoria, tipo_memoria, peso_memoria)
        if ok:
            state["shared_memories"] = carregar_shared_memories_da_planilha(apenas_ativas=True)
            st.session_state.mary_state_minimo = state
            st.success("Memória salva.")
            st.rerun()
        else:
            st.warning("Nenhuma memória foi salva.")
    with st.expander("📚 Ver memórias", expanded=False):
        memories = state.get("shared_memories", [])
        if not memories:
            st.info("Nenhuma memória shared ativa.")
        else:
            for m in memories:
                st.markdown(f"**{m.get('id', '')}** · `{m.get('tipo', 'shared')}` · peso `{m.get('peso', 1.0)}`")
                st.write(m.get("memoria", ""))
                st.divider()
    with st.expander("🗑️ Apagar memória", expanded=False):
        memory_id = st.text_input("ID da memória", value="", placeholder="Ex: mem_3")
        confirmar = st.checkbox("Confirmar apagar memória", value=False)
        if st.button("Apagar memória", use_container_width=True, disabled=not confirmar):
            if apagar_shared_memory_por_id(memory_id):
                state["shared_memories"] = carregar_shared_memories_da_planilha(apenas_ativas=True)
                st.session_state.mary_state_minimo = state
                st.success("Memória apagada.")
                st.rerun()
            else:
                st.warning("Memória não encontrada.")
    st.divider()
    st.subheader("🗑️ Apagar turnos")
    n_turnos = st.number_input("Turnos para apagar", min_value=1, max_value=50, value=1, step=1)
    confirmar_turnos = st.checkbox("Confirmar apagamento de turnos", value=False)
    if st.button("Apagar últimos turnos", use_container_width=True, disabled=not confirmar_turnos):
        qtd = apagar_ultimos_turnos_da_planilha(int(n_turnos))
        if qtd > 0:
            state["history"] = carregar_history_da_planilha(MAX_HISTORY * 2)
            state["turno"] = max(0, len(state["history"]) // 2)
            st.session_state.mary_state_minimo = state
            st.success(f"{qtd} linha(s) apagada(s).")
            st.rerun()
        else:
            st.warning("Nenhum turno foi apagado.")
    st.divider()
    with st.expander("🧩 Facts avançados", expanded=False):
        st.json(state.get("facts", {}))
    with st.expander("🧪 Debug state", expanded=False):
        st.json(state)


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
            renderizar_resposta_mary(content)

fala_usuario = st.chat_input("Escreva sua fala ou ação...")
if fala_usuario:
    fala_usuario = fala_usuario.strip()
    if fala_usuario:
        with st.chat_message("user", avatar="👤"):
            st.write(fala_usuario)
        with st.chat_message("assistant", avatar="🌙"):
            with st.spinner("Mary está respondendo..."):
                resultado = processar_turno(state, fala_usuario, model=model)
                st.session_state["mary_last_debug"] = resultado
            renderizar_resposta_mary(resultado["resposta_final_limpa"])
        st.rerun()

if "mary_last_debug" in st.session_state:
    with st.expander("🧪 Última análise técnica", expanded=False):
        dbg = st.session_state["mary_last_debug"]
        st.markdown("### Prompt enviado ao modelo")
        st.code(json.dumps(dbg.get("mensagens", []), ensure_ascii=False, indent=2), language="json")
        st.markdown("### Resposta bruta")
        st.write(dbg.get("resposta_bruta", ""))
        st.markdown("### Validação")
        validacao = dbg.get("validacao", {})
        if validacao.get("bloqueios"):
            st.error({"bloqueios": validacao.get("bloqueios")})
        elif validacao.get("alertas"):
            st.warning({"alertas": validacao.get("alertas")})
        else:
            st.success("Nenhuma violação detectada.")
        st.markdown("### State update extraído")
        st.json(dbg.get("update", {}))
        st.markdown("### Resposta final limpa")
        renderizar_resposta_mary(dbg.get("resposta_final_limpa", ""))
        st.markdown("### Estado real salvo")
        st.json(dbg.get("state", {}))
