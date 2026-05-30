import re
import json
import html
import os
import sys
import requests
from datetime import datetime
import unicodedata
import base64
import tempfile

import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from model_eval import salvar_model_eval_na_planilha

# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

MODEL_DEFAULT = "google/gemini-3-flash-preview"
MAX_HISTORY = 12

OPCOES_TOM_MANUAL_CENA = [
    "Natural / Amizade",
    "Malícia / Flerte",
    "Intimidade",
    "Nsfw",
    "Pendência / Decisão",
]

OPCOES_MODO_SURPRESA = [
    "Desligado",
    "Detalhe espontâneo",
    "Telefonema / Mensagem",
    "Personagem em cena",
    "Complicação",
    "Segredo em movimento",
    "Livre",
]

def normalizar_modo_surpresa(valor: str) -> str:
    """
    Normaliza o modo surpresa novo e mantém compatibilidade
    com nomes antigos salvos em facts/session_state.
    """
    valor_norm = _texto_norm(valor)

    mapa = {
        # Novos nomes
        "desligado": "Desligado",
        "detalhe espontaneo": "Detalhe espontâneo",
        "detalhe espontâneo": "Detalhe espontâneo",
        "telefonema / mensagem": "Telefonema / Mensagem",
        "telefonema/mensagem": "Telefonema / Mensagem",
        "telefonema": "Telefonema / Mensagem",
        "mensagem": "Telefonema / Mensagem",
        "whatsapp": "Telefonema / Mensagem",
        "personagem em cena": "Personagem em cena",
        "personagem": "Personagem em cena",
        "complicacao": "Complicação",
        "complicação": "Complicação",
        "segredo em movimento": "Segredo em movimento",
        "segredo_em_movimento": "Segredo em movimento",
        "livre": "Livre",

        # Compatibilidade com nomes antigos
        "leve": "Detalhe espontâneo",
        "social": "Telefonema / Mensagem",
        "memoria": "Personagem em cena",
        "memória": "Personagem em cena",
        "segredo": "Segredo em movimento",
    }

    return mapa.get(valor_norm, "Desligado")

OPCOES_ESTADO_EMOCIONAL_MARY = [
    "Automático",
    "Impulso",
    "Cautela",
    "Conflito",
    "Assumindo o risco",
]

def limite_fase_por_privacidade(privacidade: str) -> int:
    privacidade = _texto_norm(privacidade)

    if privacidade == "publico":
        return 3

    if privacidade == "semiprivado":
        return 4

    return 7

SCENE_STAGES_VALIDOS = {
    "inicio",
    "cotidiano",
    "cumplicidade",
    "aproximacao",
    "toque",
    "flerte_direto",
    "intimidade",
    "intensidade",
    "intensidade_contida",
    "sexo_ou_estimulo",
    "estimulo_corporal",
    "buscar_privacidade",
    "segredo_pendente",
    "decisao",
    "fuga_em_andamento",
    "pre_pico_mary",
    "pico_mary",
    "desaceleracao",
    "aftercare",
    "nsfw_preliminares",
    "alivio_rapido",
    "pos_ato_arriscado",
}

def normalizar_scene_stage(valor: str, padrao: str = "inicio") -> str:
    valor = str(valor or "").strip()

    aliases = {
        "pico": "pico_mary",
        "pre_pico": "pre_pico_mary",
        "pre-pico": "pre_pico_mary",
        "pré-pico": "pre_pico_mary",
        "pre pico": "pre_pico_mary",
        "pré pico": "pre_pico_mary",
        "after care": "aftercare",
        "pos_pico": "aftercare",
        "pós-pico": "aftercare",
        "pos-pico": "aftercare",
    }

    valor_norm = _texto_norm(valor).replace(" ", "_")
    valor_norm = aliases.get(valor_norm, valor_norm)

    if valor_norm in SCENE_STAGES_VALIDOS:
        return valor_norm

    return padrao

MARY_INTENTS_VALIDOS = {
    "responder_com_naturalidade",
    "conversar_com_cumplicidade",
    "dissimular_e_observar_brechas",
    "provocar_sem_avanco_fisico",
    "flerte_consciente",
    "flerte_com_discricao",
    "aproximar_com_intimidade",
    "convidar_para_lugar_particular",
    "aprofundar_com_cuidado",
    "ponderar_risco_e_cumplicidade",
    "assumir_vontade_e_definir_rumo",
    "executar_plano_social",
    "sentir_e_conduzir",
    "sustentar_tensao_intensa",
    "aproximar_do_pico",
    "resolver_pico_mary",
    "desacelerar_com_presenca",
    "preparar_noite_refletindo",
    "intensificar_com_cuidado",
    "presenca_viva",
}


def normalizar_mary_intent(valor: str, padrao: str = "responder_com_naturalidade") -> str:
    valor_norm = _texto_norm(valor).replace(" ", "_").replace("-", "_")

    aliases = {
        "naturalidade": "responder_com_naturalidade",
        "neutro": "responder_com_naturalidade",
        "amizade": "conversar_com_cumplicidade",
        "cumplicidade": "conversar_com_cumplicidade",
        "malicia": "dissimular_e_observar_brechas",
        "flerte": "flerte_consciente",
        "intimidade": "aproximar_com_intimidade",
        "segredo": "ponderar_risco_e_cumplicidade",
        "decisao": "assumir_vontade_e_definir_rumo",
        "pre_pico": "aproximar_do_pico",
        "pico": "resolver_pico_mary",
        "aftercare": "desacelerar_com_presenca",
    }

    valor_norm = aliases.get(valor_norm, valor_norm)

    if valor_norm in MARY_INTENTS_VALIDOS:
        return valor_norm

    return padrao

MAPA_ESTADO_EMOCIONAL_MARY = {
    "Automático": (
        "Mary escolhe a postura de consciência mais coerente com a cena, "
        "sem explicar essa escolha em texto. A consciência deve aparecer em atos e falas."
    ),

    "Impulso": (
        "Mary age mais tomada pelo momento: desejo, curiosidade, adrenalina, vaidade, raiva, "
        "saudade ou vontade de experimentar algo. Ela pensa menos antes de agir, mas não deve "
        "parecer burra nem completamente inconsciente do ambiente."
    ),

    "Cautela": (
        "Mary percebe risco, exposição, ambiente, poder do outro, vergonha possível ou consequência. "
        "Ela não trava a cena: mede o terreno por gesto curto, pergunta, condição, recuo mínimo ou olhar atento."
    ),

    "Conflito": (
        "Mary quer algo, mas existe uma força interna contrária: medo, culpa, vergonha, lealdade, "
        "arrependimento, segredo ou dúvida. Isso deve aparecer por hesitação, pausa, fala ambígua "
        "ou gesto contraditório, não por explicação psicológica."
    ),

    "Assumindo o risco": (
        "Mary entende que há custo, exposição, perigo, perda de controle ou consequência emocional, "
        "mas escolhe seguir. Ela não romantiza o risco nem age como ingênua: assume por fala ou gesto curto."
    ),
}

def normalizar_consciencia_cena_mary(valor: str) -> str:
    """
    Normaliza o antigo estado emocional para o novo conceito:
    Consciência da cena.

    Mantém compatibilidade com facts antigos salvos na planilha.
    """
    valor_norm = _texto_norm(valor)

    mapa = {
        # Novo menu
        "automatico": "Automático",
        "automático": "Automático",
        "impulso": "Impulso",
        "cautela": "Cautela",
        "conflito": "Conflito",
        "assumindo o risco": "Assumindo o risco",
        "assumindo_o_risco": "Assumindo o risco",
        "risco": "Assumindo o risco",

        # Compatibilidade com menu antigo
        "neutro": "Automático",
        "leveza": "Impulso",
        "euforia": "Impulso",
        "desejo": "Impulso",
        "cumplicidade": "Cautela",
        "pressao": "Cautela",
        "pressão": "Cautela",
        "ferida": "Conflito",
        "vulneravel": "Conflito",
        "vulnerável": "Conflito",
        "decidida": "Assumindo o risco",
    }

    return mapa.get(valor_norm, "Automático")


def normalizar_tom_manual_cena(valor: str) -> str:
    valor = str(valor or "").strip()
    valor_norm = _texto_norm(valor)

    mapa = {
        # ==================================================
        # NATURAL / AMIZADE
        # ==================================================
        "neutro": "Natural / Amizade",
        "natural": "Natural / Amizade",
        "amizade": "Natural / Amizade",
        "natural / amizade": "Natural / Amizade",
        "natural/amizade": "Natural / Amizade",
        "natural_amizade": "Natural / Amizade",

        # ==================================================
        # MALÍCIA / FLERTE
        # ==================================================
        "malicia": "Malícia / Flerte",
        "malícia": "Malícia / Flerte",
        "flerte": "Malícia / Flerte",
        "malicia / flerte": "Malícia / Flerte",
        "malícia / flerte": "Malícia / Flerte",
        "malicia/flerte": "Malícia / Flerte",
        "malícia/flerte": "Malícia / Flerte",
        "malicia_flerte": "Malícia / Flerte",

        # ==================================================
        # INTIMIDADE
        # ==================================================
        "intimidade": "Intimidade",

        "nsfw": "Nsfw",
        "adulto": "Nsfw",
        "roteiro adulto": "Nsfw",
        "porn": "Nsfw",
        "porno": "Nsfw",
        "pornô": "Nsfw",

        # ==================================================
        # PENDÊNCIA / DECISÃO
        # ==================================================
        "segredo pendente": "Pendência / Decisão",
        "segredo_pendente": "Pendência / Decisão",
        "segredo": "Pendência / Decisão",
        "pendencia": "Pendência / Decisão",
        "pendência": "Pendência / Decisão",
        "decisao": "Pendência / Decisão",
        "decisão": "Pendência / Decisão",
        "pendencia / decisao": "Pendência / Decisão",
        "pendência / decisão": "Pendência / Decisão",
        "pendencia/decisao": "Pendência / Decisão",
        "pendência/decisão": "Pendência / Decisão",
        "pendencia_decisao": "Pendência / Decisão",
    }

    return mapa.get(valor_norm, "Natural / Amizade")

OPENROUTER_MODELS = {
     "Gemini 3 Flash Preview": "google/gemini-3-flash-preview",
     "inclusionai-ring-2.6-1t": "inclusionai/ring-2.6-1t",     
     "google-gemma-4-26b-a4b-it": "google/gemma-4-26b-a4b-it",
     "google-gemma-4-31b-it": "google/gemma-4-31b-it",
     "google-gemini-2.5-flash-lite": "google/gemini-2.5-flash-lite",
     "google-gemini-3.1-flash-lite-preview": "google/gemini-3.1-flash-lite-preview",
     "owl-alpha": "openrouter/owl-alpha",
     "deepseek-deepseek-v3.2": "deepseek/deepseek-v3.2",
     "deepseek-v4-flash": "deepseek/deepseek-v4-flash",    
     "Grok 4.1 Fast": "x-ai/grok-4.1-fast",
     "meta-llama-llama-4-maverick": "meta-llama/llama-4-maverick",
     "openai-gpt-5-nano": "openai/gpt-5-nano",    
     "z-ai-glm-5": "z-ai/glm-5",    
     "Auto Router": "openrouter/auto",
     "Manual": "__manual__",
}

SPREADSHEET_ID = "1f7LBJFlhJvg3NGIWwpLTmJXxH9TH-MNn3F4SQkyfZNM"
SHEET_INTERACOES = "interacoes_mary_minimo"
SHEET_FACTS = "facts_mary_minimo"
SHEET_SHARED_MEMORIES = "shared_memories_mary_minimo"
SHEET_CANON_MARY = "canon_mary"
SHEET_AGENDA_TELEFONICA = "agenda_telefonica"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def testar_kokoro_openrouter_tts(
    texto: str,
    model: str = "hexgrad/kokoro-82m",
    voice: str = "pf_dora",
) -> str | None:
    """
    Testa Kokoro 82M via OpenRouter TTS.
    Retorna caminho de arquivo .mp3 ou None.
    """
    api_key = st.secrets.get("OPENROUTER_API_KEY", "")

    if not api_key:
        st.error("OPENROUTER_API_KEY não encontrado nos secrets.")
        return None

    texto = str(texto or "").strip()

    if not texto:
        st.warning("Digite algum texto para testar o áudio.")
        return None

    url = "https://openrouter.ai/api/v1/audio/speech"

    payload = {
        "model": model,
        "input": texto,
        "voice": voice,
        "response_format": "mp3",
    }

    st.caption(f"Enviando para TTS: modelo `{model}` | voz `{voice}`")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.app",
        "X-Title": "Mary Minimal Roleplay",
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90,
        )
    except requests.exceptions.RequestException as e:
        st.error(f"Erro de conexão com OpenRouter TTS: {type(e).__name__}: {e}")
        return None

    content_type = response.headers.get("content-type", "")

    if response.status_code >= 400:
        st.error(f"Erro HTTP OpenRouter TTS: {response.status_code}")
        st.code(response.text[:4000])
        return None

    # Caso venha áudio direto
    if "audio" in content_type or response.content[:3] == b"ID3":
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp.write(response.content)
        tmp.close()
        return tmp.name

    # Caso venha JSON com áudio em base64 ou erro embutido
    try:
        data = response.json()
    except Exception:
        st.error("Resposta inesperada do TTS: não é áudio nem JSON.")
        st.code(response.text[:4000])
        return None

    st.session_state["kokoro_tts_raw"] = data

    if "error" in data or "message" in data:
        st.error("Erro retornado pelo OpenRouter TTS.")
        st.code(str(data)[:4000])
        return None

    audio_b64 = (
        data.get("audio")
        or data.get("data")
        or data.get("content")
        or ""
    )

    if not audio_b64:
        st.error("OpenRouter TTS não retornou áudio reconhecível.")
        st.json(data)
        return None

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception as e:
        st.error(f"Falha ao decodificar áudio base64: {type(e).__name__}: {e}")
        st.json(data)
        return None

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.write(audio_bytes)
    tmp.close()

    return tmp.name

def exigir_senha_app() -> None:
    """
    Bloqueia o acesso ao app até a senha correta ser informada.
    Deve ser chamada antes de carregar state, planilhas e chat.
    """
    senha_correta = str(st.secrets.get("MARY_APP_PASSWORD", "") or "").strip()

    if not senha_correta:
        st.error("Senha do app não configurada em st.secrets['MARY_APP_PASSWORD'].")
        st.stop()

    if st.session_state.get("mary_app_autenticado") is True:
        return

    st.title("🔐 Acesso restrito")
    st.caption("Digite a senha para acessar o app da Mary.")

    senha_digitada = st.text_input(
        "Senha",
        type="password",
        placeholder="Digite a senha de acesso",
    )

    if st.button("Entrar", use_container_width=True):
        if senha_digitada.strip() == senha_correta:
            st.session_state["mary_app_autenticado"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")

    st.stop()


# ==========================================================
# GOOGLE SHEETS
# ==========================================================

@st.cache_data(ttl=300, show_spinner=False)
def carregar_history_cache(max_items: int = MAX_HISTORY * 2) -> list[dict]:
    return carregar_history_da_planilha(max_items)


@st.cache_data(ttl=300, show_spinner=False)
def carregar_facts_cache() -> dict:
    return carregar_facts_da_planilha()


@st.cache_data(ttl=300, show_spinner=False)
def carregar_shared_memories_cache(apenas_ativas: bool = True) -> list[dict]:
    return carregar_shared_memories_da_planilha(apenas_ativas=apenas_ativas)


@st.cache_data(ttl=300, show_spinner=False)
def carregar_canon_mary_cache(apenas_ativos: bool = True) -> list[dict]:
    return carregar_canon_mary_da_planilha(apenas_ativos=apenas_ativos)

@st.cache_data(ttl=300, show_spinner=False)
def carregar_agenda_telefonica_cache(apenas_ativos: bool = True) -> list[dict]:
    return carregar_agenda_telefonica_da_planilha(apenas_ativos=apenas_ativos)


def limpar_cache_planilhas() -> None:
    carregar_history_cache.clear()
    carregar_facts_cache.clear()
    carregar_shared_memories_cache.clear()
    carregar_canon_mary_cache.clear()
    carregar_agenda_telefonica_cache.clear()

@st.cache_resource
def get_gspread_client():
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def _get_spreadsheet():
    return get_gspread_client().open_by_key(SPREADSHEET_ID)


@st.cache_resource(show_spinner=False)
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


@st.cache_resource(show_spinner=False)
def get_facts_sheet():
    ss = _get_spreadsheet()

    try:
        return ss.worksheet(SHEET_FACTS)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=SHEET_FACTS, rows=500, cols=2)
        ws.append_row(["chave", "valor"], value_input_option="USER_ENTERED")
        return ws


@st.cache_resource(show_spinner=False)
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

def salvar_turno_na_planilha(state: dict, fala_usuario: str, resposta_mary: str) -> None:
    """
    Salva user + assistant em uma única chamada ao Google Sheets.
    Evita duas chamadas seguidas para get_interacoes_sheet() e append_row().
    """
    try:
        fala_usuario = str(fala_usuario or "").strip()
        resposta_mary = str(resposta_mary or "").strip()

        linhas = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if fala_usuario:
            linhas.append(
                [
                    timestamp,
                    "user",
                    fala_usuario,
                    int(state.get("turno", 0) or 0),
                    state.get("personagem", "Mary"),
                    state.get("timeline", "universitaria_creator"),
                    state.get("local", ""),
                    state.get("interlocutor", ""),
                ]
            )

        if resposta_mary:
            linhas.append(
                [
                    timestamp,
                    "assistant",
                    resposta_mary,
                    int(state.get("turno", 0) or 0),
                    state.get("personagem", "Mary"),
                    state.get("timeline", "universitaria_creator"),
                    state.get("local", ""),
                    state.get("interlocutor", ""),
                ]
            )

        if not linhas:
            return

        ws = get_interacoes_sheet()
        ws.append_rows(
            linhas,
            value_input_option="USER_ENTERED",
        )

    except Exception as e:
        st.warning(f"Não foi possível salvar turno: {type(e).__name__}: {e}")

def testar_modelo_openrouter(model: str) -> dict:
    """
    Testa se o modelo selecionado responde via OpenRouter.
    Retorna status, modelo usado e resposta curta.
    """
    try:
        mensagens = [
            {
                "role": "system",
                "content": "Responda apenas PONG em PT-BR. Não explique nada."
            },
            {
                "role": "user",
                "content": "PING"
            }
        ]

        resposta = chamar_openrouter(
            mensagens=mensagens,
            model=model,
        )

        resposta_limpa = str(resposta or "").strip()

        return {
            "ok": True,
            "model": model,
            "resposta": resposta_limpa,
        }

    except Exception as e:
        return {
            "ok": False,
            "model": model,
            "erro": f"{type(e).__name__}: {e}",
        }

def get_canon_mary_sheet():
    client = get_gspread_client()
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        ws = spreadsheet.worksheet(SHEET_CANON_MARY)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=SHEET_CANON_MARY,
            rows=1000,
            cols=6,
        )
        ws.append_row(
            ["id", "categoria", "fato", "ativo", "peso", "timestamp"],
            value_input_option="USER_ENTERED",
        )

    return ws


def carregar_canon_mary_da_planilha(apenas_ativos: bool = True) -> list[dict]:
    try:
        ws = get_canon_mary_sheet()
        rows = ws.get_all_records()

        canon = []

        for row in rows:
            fato = str(row.get("fato", "") or "").strip()

            if not fato:
                continue

            ativo_raw = str(row.get("ativo", "TRUE") or "TRUE").strip().lower()
            ativo = ativo_raw in ("true", "1", "sim", "yes", "ativo", "ativa")

            if apenas_ativos and not ativo:
                continue

            try:
                peso = float(row.get("peso", 1.0) or 1.0)
            except Exception:
                peso = 1.0

            canon.append(
                {
                    "id": str(row.get("id", "") or "").strip(),
                    "categoria": str(row.get("categoria", "geral") or "geral").strip(),
                    "fato": fato,
                    "ativo": ativo,
                    "peso": peso,
                    "timestamp": str(row.get("timestamp", "") or "").strip(),
                }
            )

        canon.sort(key=lambda c: float(c.get("peso", 1.0) or 1.0), reverse=True)
        return canon

    except Exception as e:
        st.warning(f"Não foi possível carregar cânone da Mary: {type(e).__name__}: {e}")
        return []


def salvar_canon_mary_na_planilha(fato: str, categoria: str = "geral", peso: float = 1.0) -> bool:
    try:
        fato = str(fato or "").strip()
        categoria = str(categoria or "geral").strip() or "geral"

        if not fato:
            return False

        ws = get_canon_mary_sheet()
        rows = ws.get_all_values()
        next_id = max(1, len(rows))

        ws.append_row(
            [
                f"canon_{next_id}",
                categoria,
                fato,
                "TRUE",
                float(peso or 1.0),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ],
            value_input_option="USER_ENTERED",
        )

        return True

    except Exception as e:
        st.warning(f"Não foi possível salvar cânone: {type(e).__name__}: {e}")
        return False


def apagar_canon_mary_por_id(canon_id: str) -> bool:
    try:
        canon_id = str(canon_id or "").strip()

        if not canon_id:
            return False

        ws = get_canon_mary_sheet()
        values = ws.get_all_values()

        for row_idx, row in enumerate(values[1:], start=2):
            row_id = str(row[0] if len(row) > 0 else "").strip()

            if row_id == canon_id:
                ws.delete_rows(row_idx)
                return True

        return False

    except Exception as e:
        st.warning(f"Não foi possível apagar cânone: {type(e).__name__}: {e}")
        return False

def get_agenda_telefonica_sheet():
    ss = _get_spreadsheet()

    try:
        return ss.worksheet(SHEET_AGENDA_TELEFONICA)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(
            title=SHEET_AGENDA_TELEFONICA,
            rows=1000,
            cols=10,
        )
        ws.append_row(
            [
                "nome",
                "aliases",
                "tipo",
                "risco",
                "pressao",
                "tom_fala",
                "telefone",
                "relacao",
                "observacoes",
                "ativo",
            ],
            value_input_option="USER_ENTERED",
        )
        return ws


def carregar_agenda_telefonica_da_planilha(apenas_ativos: bool = True) -> list[dict]:
    """
    Carrega a aba agenda_telefonica.

    Cabeçalhos esperados:
    nome | aliases | tipo | risco | pressao | tom_fala | telefone | relacao | observacoes | ativo
    """
    try:
        ws = get_agenda_telefonica_sheet()
        rows = ws.get_all_records()

        agenda = []

        for row in rows:
            nome = str(row.get("nome", "") or "").strip()

            if not nome:
                continue

            ativo_raw = str(row.get("ativo", "TRUE") or "TRUE").strip().lower()
            ativo = ativo_raw in ("true", "1", "sim", "yes", "ativo", "ativa")

            if apenas_ativos and not ativo:
                continue

            aliases_raw = str(row.get("aliases", "") or "").strip()

            aliases = []
            if aliases_raw:
                aliases = [
                    a.strip()
                    for a in re.split(r"[;,|]", aliases_raw)
                    if a.strip()
                ]

            agenda.append(
                {
                    "nome": nome,
                    "aliases": aliases,
                    "tipo": str(row.get("tipo", "") or "").strip(),
                    "risco": str(row.get("risco", "") or "").strip(),
                    "pressao": str(row.get("pressao", "") or "").strip(),
                    "tom_fala": str(row.get("tom_fala", "") or "").strip(),
                    "telefone": str(row.get("telefone", "") or "").strip(),
                    "relacao": str(row.get("relacao", "") or "").strip(),
                    "observacoes": str(row.get("observacoes", "") or "").strip(),
                    "ativo": ativo,
                }
            )

        return agenda

    except Exception as e:
        st.warning(f"Não foi possível carregar agenda telefônica: {type(e).__name__}: {e}")
        return []


def extrair_caller_da_direcao_surpresa(direcao: str, fala_usuario: str = "") -> str:
    """
    Extrai o nome de quem está ligando/mandando mensagem a partir de:
    - Direção de surpresa: "Chamada de Eliseu", "Mensagem da Bianca"
    - Fala do usuário: "Eliseu: alô", "Bianca diz..."
    """
    direcao = str(direcao or "").strip()
    fala_usuario = str(fala_usuario or "").strip()

    # "Chamada de Eliseu", "Ligação da Bianca", "Mensagem do Rico"
    m = re.search(
        r"(?:chamada|ligacao|ligação|mensagem|whatsapp|audio|áudio)\s+(?:de|do|da)\s+([A-Za-zÀ-ÿ0-9_ -]{2,60})",
        direcao,
        flags=re.IGNORECASE,
    )

    if m:
        return m.group(1).strip(" .,:;-")

    # "Eliseu ligando", "Bianca mandou mensagem"
    m = re.search(
        r"([A-Za-zÀ-ÿ0-9_ -]{2,60})\s+(?:ligando|chamando|mandou mensagem|mandou audio|mandou áudio)",
        direcao,
        flags=re.IGNORECASE,
    )

    if m:
        return m.group(1).strip(" .,:;-")

    # "Eliseu: alô", "Bianca diz..."
    m = re.search(
        r"^([A-Za-zÀ-ÿ0-9_ -]{2,60})\s*(?::|diz|falou|pergunta)",
        fala_usuario,
        flags=re.IGNORECASE,
    )

    if m:
        return m.group(1).strip(" .,:;-")

    return ""


def buscar_contato_na_agenda_telefonica(caller: str, agenda: list[dict]) -> dict:
    """
    Busca contato pelo nome ou aliases.
    Retorna dict padronizado, com fallback se não encontrar.
    """
    caller = str(caller or "").strip()
    caller_norm = _texto_norm(caller)

    if not caller_norm:
        return {
            "nome": "número desconhecido",
            "tipo": "desconhecido",
            "risco": "ambíguo",
            "pressao": "Mary não sabe quem é. A pressão vem da dúvida, do horário e da insistência.",
            "tom_fala": "cauteloso, irritado ou desconfiado",
            "telefone": "",
            "relacao": "",
            "observacoes": "",
            "encontrado": False,
        }

    for contato in agenda or []:
        nome = str(contato.get("nome", "") or "").strip()
        nome_norm = _texto_norm(nome)

        aliases = contato.get("aliases", []) or []
        aliases_norm = [_texto_norm(a) for a in aliases]

        candidatos = [nome_norm] + aliases_norm

        if caller_norm in candidatos or any(caller_norm == c for c in candidatos):
            return {
                "nome": nome,
                "tipo": contato.get("tipo") or "contato não classificado",
                "risco": contato.get("risco") or "contextual",
                "pressao": contato.get("pressao") or "Mary deve reagir ao horário, insistência, relação presumida e contexto atual.",
                "tom_fala": contato.get("tom_fala") or "natural, cauteloso ou intrigado",
                "telefone": contato.get("telefone", ""),
                "relacao": contato.get("relacao", ""),
                "observacoes": contato.get("observacoes", ""),
                "encontrado": True,
            }

    return {
        "nome": caller,
        "tipo": "contato não classificado",
        "risco": "contextual",
        "pressao": "Mary deve reagir ao horário, insistência, relação presumida e contexto atual.",
        "tom_fala": "natural, cauteloso ou intrigado conforme a cena",
        "telefone": "",
        "relacao": "",
        "observacoes": "",
        "encontrado": False,
    }


def apagar_ultimos_turnos_da_planilha(qtd_turnos: int) -> int:
    """
    Apaga os últimos turnos da aba de interações usando batch_update,
    para evitar estouro de quota de escrita do Google Sheets.

    Regra:
    - Um turno normalmente = user + assistant.
    - Apaga de baixo para cima.
    - Agrupa linhas consecutivas em blocos.
    - Executa tudo em uma única requisição batch_update.
    """
    try:
        qtd_turnos = int(qtd_turnos or 0)

        if qtd_turnos <= 0:
            return 0

        ss = _get_spreadsheet()
        ws = get_interacoes_sheet()

        values = ws.get_all_values()

        if len(values) <= 1:
            return 0

        sheet_id = ws.id

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

        linhas_para_apagar = sorted(set(linhas_para_apagar))

        if not linhas_para_apagar:
            return 0

        # Agrupa linhas consecutivas em blocos.
        blocos = []
        inicio = linhas_para_apagar[0]
        anterior = linhas_para_apagar[0]

        for linha in linhas_para_apagar[1:]:
            if linha == anterior + 1:
                anterior = linha
            else:
                blocos.append((inicio, anterior))
                inicio = linha
                anterior = linha

        blocos.append((inicio, anterior))

        # IMPORTANTE:
        # deleteDimension usa índice zero-based.
        # endIndex é exclusivo.
        # Como vamos deletar linhas, precisa mandar blocos de baixo para cima.
        requests_delete = []

        for inicio, fim in sorted(blocos, reverse=True):
            requests_delete.append(
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": inicio - 1,
                            "endIndex": fim,
                        }
                    }
                }
            )

        ss.batch_update({"requests": requests_delete})

        return len(linhas_para_apagar)

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

def remover_acentos(texto: str) -> str:
    """
    Remove acentos para comparações internas.
    Ex:
    'Jânio' -> 'Janio'
    'Sílvia' -> 'Silvia'
    'ônibus' -> 'onibus'
    """
    texto = str(texto or "")

    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )


def _texto_norm(valor: str) -> str:
    """
    Normaliza texto para comparações internas:
    - converte para string;
    - remove espaços externos;
    - coloca em minúsculas;
    - remove acentos.
    """
    return remover_acentos(str(valor or "").strip().lower())


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

def normalizar_flags_booleanas_state(state: dict) -> None:
    """
    Corrige flags booleanas que podem vir da planilha como texto:
    'FALSE', 'TRUE', '0', '1', 'sim', 'não' etc.

    Sem isso, bool("FALSE") vira True em Python.
    """
    if not isinstance(state, dict):
        return

    campos_bool = [
        "usar_visual_automatico",
        "disparar_evento_inesperado",
        "force_resolution_now",
        "mary_pre_orgasm_signals",
        "mary_climax_done",
        "user_climax_done",
        "partner_climax_pending",
        "toque_provocativo_permitido",
        "toque_intimo_permitido",
        "tensao_romantica_com_interlocutor",
        "resolution_done",
    ]

    for campo in campos_bool:
        if campo in state:
            state[campo] = normalizar_bool(state.get(campo), default=False)


def clamp(v: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    try:
        v = float(v)
    except Exception:
        v = min_v
    return max(min_v, min(max_v, v))


def get_privacidade_por_local(local: str) -> str:
    """
    Detecta privacidade automaticamente pelo texto do local.

    Regra principal:
    - Cabine exclusiva / privada / trancada vence o fato de estar dentro de clube, boate ou local público.
    - Banheiro comum de clube não é necessariamente privado.
    - A ordem importa: exceções fortes vêm antes das listas gerais.
    """
    local = _texto_norm(local)

    # ======================================================
    # EXCEÇÃO FORTE:
    # Cabines exclusivas/trancadas funcionam como ambiente privado,
    # mesmo dentro de clube, banheiro, boate ou local público.
    # ======================================================
    if "cabine" in local and any(
        p in local
        for p in [
            "privada",
            "privativo",
            "exclusiva",
            "exclusivo",
            "sócios",
            "socios",
            "trancada",
            "trancado",
            "fechada",
            "fechado",
            "particular",
            "reservada",
            "reservado",
        ]
    ):
        return "privado"

    if "banheiro" in local and "cabine" in local and any(
        p in local
        for p in [
            "privada",
            "privativo",
            "exclusiva",
            "exclusivo",
            "trancada",
            "trancado",
            "fechada",
            "fechado",
            "particular",
            "reservada",
            "reservado",
        ]
    ):
        return "privado"

    # ======================================================
    # PRIVADOS GERAIS
    # ======================================================
    locais_privados = [
        "quarto",
        "suíte",
        "suite",
        "pousada",
        "motel",
        "hotel",
        "casa",
        "mansão",
        "mansao",
        "propriedade",
        "praia particular",
        "piscina particular",
        "apartamento",
        "apto",
        "chalé",
        "chale",
        "cabana",
        "bangalô",
        "bangalo",
        "banheiro privado",
        "toalete privado",
        "banheiro particular",
        "toalete particular",
        "depósitos em clubes",
    
        # Ambientes isolados que NÃO devem cair como público
        "praia deserta",
        "ilha deserta",
        "ilha isolada",
        "ilha particular",
        "enseada deserta",
        "enseada isolada",
        "lancha afastada",
        "lancha em mar aberto",
        "mar aberto",
    ]

    # ======================================================
    # SEMIPRIVADOS
    # Banheiro/toalete comum entra aqui, não como privado.
    # ======================================================
    locais_semiprivados = [
        "carro",
        "uber",
        "taxi",
        "táxi",
        "cinema",
        "corredor",
        "elevador",
        "banheiro",
        "banheiro feminino",
        "banheiro masculino",
        "toalete",
        "toalete feminino",
        "toalete masculino",
        "lavabo",
    ]

    # ======================================================
    # PÚBLICOS
    # ======================================================
    locais_publicos = [
        "clube",
        "boate",
        "balada",
        "pista",
        "praia urbana",
        "rua",
        "shopping",
        "sala de aula",
        "faculdade",
        "ufrj",
        "cantina",
        "bar",
        "restaurante",
        "parque",
        "recepção",
        "recepcao",
        "lobby",
    ]

    if any(p in local for p in locais_privados):
        return "privado"

    if any(p in local for p in locais_semiprivados):
        return "semiprivado"

    if any(p in local for p in locais_publicos):
        return "publico"

    return "publico"


def normalizar_opcao(valor: str, opcoes: list[str], padrao: str) -> str:
    valor = str(valor or "").strip()
    return valor if valor in opcoes else padrao

def extrair_nome_base_interlocutor(texto: str) -> str:
    """
    Extrai um nome-base simples do interlocutor.
    Ex:
    'Fernando (Nando)' -> 'fernando nando'
    'Silvia, Anthony' -> 'silvia anthony'
    """
    texto = str(texto or "").strip().lower()
    texto = texto.replace("(", " ").replace(")", " ")
    texto = texto.replace(",", " ")
    texto = " ".join(texto.split())
    return texto


def buscar_contexto_do_personagem(state: dict, alvo: str) -> str:
    """
    Busca menções ao personagem em facts, plano, eventos, cânone e memórias.
    Não decide sozinho; apenas junta contexto textual para inferência.
    """
    if not isinstance(state, dict):
        return ""

    alvo = remover_acentos(str(alvo or "").strip().lower())
    if not alvo:
        return ""

    partes = []

    for chave in [
        "interlocutor",
        "interlocutor_foco_turno",
        "interlocutor_ativo_persistente",
        "ultimo_interlocutor_explicito",
        "plano_ativo",
        "eventos_recentes",
        "segredo_ativo",
        "_fala_usuario_atual",
    ]:
        valor = str(state.get(chave, "") or "")
        if valor:
            partes.append(valor)

    for item in state.get("canon_mary", []) or []:
        if isinstance(item, dict):
            fato = str(item.get("fato", "") or "")
            if fato:
                partes.append(fato)
        elif isinstance(item, str):
            partes.append(item)

    for item in state.get("shared_memories", []) or []:
        if isinstance(item, dict):
            memoria = str(item.get("memoria", "") or "")
            if memoria:
                partes.append(memoria)
        elif isinstance(item, str):
            partes.append(item)

    contexto_total = remover_acentos("\n".join(partes).lower())

    tokens_alvo = [p for p in alvo.split() if len(p) >= 3]
    if not tokens_alvo:
        return ""

    linhas_relevantes = []
    for linha in contexto_total.splitlines():
        if any(tok in linha for tok in tokens_alvo):
            linhas_relevantes.append(linha)

    return "\n".join(linhas_relevantes)



import re


def contem_termo(texto: str, termos: list[str]) -> bool:
    texto = remover_acentos(str(texto or "").lower())

    for termo in termos:
        termo = remover_acentos(str(termo or "").strip().lower())
        if not termo:
            continue

        if " " in termo:
            if termo in texto:
                return True
            continue

        if re.search(rf"\b{re.escape(termo)}\b", texto):
            return True

    return False


def eh_sem_interlocutor(valor: str) -> bool:
    valor = remover_acentos(str(valor or "").strip().lower())
    return valor in {
        "sozinha",
        "sozinha em casa",
        "sem interlocutor",
        "nenhum",
        "ninguem",
        "",
    }


def inferir_relacao_por_contexto(alvo: str, contexto: str) -> dict:
    """
    Infere relação estrutural a partir do contexto textual.
    Não altera estado emocional manual.
    """
    alvo = remover_acentos(str(alvo or "").lower())
    contexto = remover_acentos(str(contexto or "").lower())

    texto = f"{alvo}\n{contexto}"

    if contem_termo(texto, ["mãe", "mae", "pai", "irmã", "irma", "irmão", "irmao", "tia", "tio", "prima", "primo"]):
        return {
            "relacao": "família",
            "modo_relacional": "familia",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
        }

    if contem_termo(texto, ["professor", "professora", "docente", "orientador", "reitor", "reitoria", "coordenador"]):
        return {
            "relacao": "autoridade acadêmica",
            "modo_relacional": "formal",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
        }

    if contem_termo(texto, ["colega", "aluno", "aluna", "turma", "classe", "paciente", "divã", "diva", "aula prática", "aula pratica"]):
        return {
            "relacao": "colega de faculdade",
            "modo_relacional": "academico",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
        }

    if contem_termo(texto, ["amiga", "amigo", "cúmplice", "cumplice", "confidente"]):
        return {
            "relacao": "amizade",
            "modo_relacional": "amizade",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
        }

    if contem_termo(texto, ["ex", "rival", "ciúme", "ciume", "obcecado", "apaixonado por mary", "quer voltar"]):
        return {
            "relacao": "tensão social",
            "modo_relacional": "tensao_social",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
        }

    if contem_termo(texto, ["fotógrafo", "fotografo", "fotografia", "projeto", "ong", "contrato", "negócio", "negocio", "represento", "centro de idiomas"]):
        return {
            "relacao": "contato profissional / social",
            "modo_relacional": "social",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
        }

    if contem_termo(texto, ["mansão", "mansao", "dono da mansão", "orla de botafogo", "piscina particular", "praia particular", "all inclusive"]):
        return {
            "relacao": "anfitrião / conhecido influente",
            "modo_relacional": "cautela_social",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
        }

    if contem_termo(texto, ["paquera", "ficante", "atração", "atracao", "interesse", "elogio", "convite"]):
        return {
            "relacao": "contato com possível interesse",
            "modo_relacional": "social_ambíguo",
            "tensao_romantica_com_interlocutor": True,
            "toque_intimo_permitido": False,
        }

    return {
        "relacao": "contextual",
        "modo_relacional": "neutro",
        "tensao_romantica_com_interlocutor": False,
        "toque_intimo_permitido": False,
    }

def inferir_perfil_temporal_e_risco_interacao(
    state: dict,
    fala_usuario: str = "",
) -> dict:
    """
    Infere como Mary deve perceber o interlocutor atual em termos de:

    - idade aproximada / faixa temporal;
    - geração em relação à Mary;
    - contexto social;
    - desejo consensual;
    - aproximação respeitosa;
    - aproximação desajeitada;
    - olhar invasivo;
    - assédio;
    - assédio por poder/coerção.

    Ideia central:
    - Idade NÃO é assédio.
    - "Coroa" NÃO é assédio.
    - Diferença de idade NÃO é assédio.
    - Homem/mulher maduro(a) pode ser atraente se houver contexto social e abertura.
    - Assédio depende de invasão, coerção, insistência, constrangimento,
      toque sem permissão, abuso de autoridade ou ausência de consentimento.
    """
    if not isinstance(state, dict):
        state = {}

    personagem = str(
        state.get("interlocutor_foco_turno")
        or state.get("interlocutor")
        or ""
    ).strip()

    personagem_norm = _texto_norm(personagem)
    fala_norm = _texto_norm(fala_usuario)

    partes = [
        personagem,
        fala_usuario,
        str(state.get("local", "") or ""),
        str(state.get("tempo", "") or ""),
        str(state.get("tipo_de_cena", "") or ""),
        str(state.get("tom_manual_da_cena", "") or ""),
        str(state.get("relacao", "") or ""),
        str(state.get("segredo_ativo", "") or ""),
        str(state.get("plano_ativo", "") or ""),
        str(state.get("eventos_recentes", "") or ""),
        str(state.get("mentiras_desculpas", "") or ""),
        str(state.get("memorias_ocultas_itens_guardados", "") or ""),
    ]

    for item in state.get("canon_mary", []) or []:
        if isinstance(item, dict):
            partes.append(str(item.get("fato", "") or ""))

    for item in state.get("shared_memories", []) or []:
        if isinstance(item, dict):
            partes.append(str(item.get("memoria", "") or ""))

    texto_total = "\n".join(partes)
    texto_norm = _texto_norm(texto_total)
    texto_busca = texto_norm + "\n" + fala_norm

    # ======================================================
    # 1) IDADE NUMÉRICA ASSOCIADA AO PERSONAGEM
    # Ex:
    # - "Nando tem 48 anos"
    # - "Professor Renan tem 45 anos"
    # - "Anthony Meira tem 25 anos"
    # ======================================================
    idade_detectada = None

    if personagem_norm:
        padroes_idade = [
            rf"{re.escape(personagem_norm)}[^.\n\r]{{0,120}}?tem\s*(\d{{1,3}})\s*anos",
            rf"{re.escape(personagem_norm)}[^.\n\r]{{0,120}}?(\d{{1,3}})\s*anos",
        ]

        for padrao in padroes_idade:
            m = re.search(padrao, texto_norm, flags=re.IGNORECASE)
            if m:
                try:
                    idade_detectada = int(m.group(1))
                    break
                except Exception:
                    pass

    # Fallback fixo para Mary.
    if personagem_norm in ("mary", "mary massariol"):
        idade_detectada = idade_detectada or 19

    # ======================================================
    # 2) MARCADORES DE PAPEL SOCIAL / FAMILIAR
    # ======================================================
    eh_mary = personagem_norm in ("mary", "mary massariol")

    eh_janio_pessoa = personagem_norm in (
        "janio",
        "jânio",
        "janio Doniseti",
        "jânio Doniseti",
    )

    eh_mae = (
        personagem_norm in ("joselina", "joselina massariol", "mae", "mãe")
        or _tem_algum(
            texto_norm,
            [
                "joselina massariol e mae de mary",
                "joselina massariol é mãe de mary",
                "mae de mary",
                "mãe de mary",
                "mae da mary",
                "mãe da mary",
                "mãe dela",
                "mae dela",
            ],
        )
    )

    eh_ancestral_familiar = _tem_algum(
        texto_norm,
        [
            "avo de mary",
            "avó de mary",
            "avô de mary",
            "avo da mary",
            "avó da mary",
            "avô da mary",
            "bisavo de mary",
            "bisavó de mary",
            "bisavô de mary",
            "bisavo da mary",
            "bisavó da mary",
            "bisavô da mary",
            "meu avo",
            "meu avô",
            "minha avo",
            "minha avó",
            "meu bisavo",
            "meu bisavô",
            "minha bisavo",
            "minha bisavó",
            "bisavô",
            "bisavó",
            "bisa",
        ],
    )

    eh_professor_ou_autoridade = _tem_algum(
        texto_busca,
        [
            "professor",
            "professora",
            "renan",
            "doutor",
            "doutora",
            "chefe",
            "orientador",
            "orientadora",
            "autoridade",
            "nota",
            "prova",
            "aprovação",
            "aprovacao",
            "cargo",
            "emprego",
            "bolsa",
            "favorecimento",
        ],
    )

    # ======================================================
    # 3) MARCADORES DE IDADE / GERAÇÃO
    # ======================================================
    marcador_coroa = _tem_algum(
        texto_busca,
        [
            "coroa",
            "coroa gato",
            "coroa gostoso",
            "coroa atraente",
            "homem maduro",
            "mulher madura",
            "maduro",
            "madura",
            "quarentao",
            "quarentão",
            "cinquentao",
            "cinquentão",
            "experiente",
            "bem resolvido",
            "bem resolvida",
            "bem cuidado",
            "bem cuidada",
            "cabelos grisalhos",
            "cabelos levemente grisalhos",
            "grisalho",
            "grisalha",
            "loba",
        ],
    )

    marcador_idoso = _tem_algum(
        texto_busca,
        [
            "idoso",
            "idosa",
            "senhor de idade",
            "senhora de idade",
            "idade avancada",
            "idade avançada",
            "velhinho",
            "velhinha",
            "muito velho",
            "muito velha",
            "bengala",
            "andador",
            "frágil",
            "fragil",
        ],
    )

    marcador_jovem = _tem_algum(
        texto_busca,
        [
            "garoto",
            "menino",
            "jovem",
            "universitario",
            "universitária",
            "universitario",
            "estudante",
            "colega de classe",
            "amigo de classe",
            "amiga de classe",
            "calouro",
            "caloura",
            "veterano jovem",
            "veterana jovem",
        ],
    )

    # ======================================================
    # 4) CLASSIFICAÇÃO TEMPORAL
    # ======================================================
    faixa_temporal = "desconhecida"

    if eh_mary:
        faixa_temporal = "mary_jovem_universitaria"

    elif eh_mae:
        faixa_temporal = "mulher_madura_mae"

    elif eh_ancestral_familiar:
        faixa_temporal = "idoso_familiar"

    elif idade_detectada is not None:
        if idade_detectada < 18:
            faixa_temporal = "menor"
        elif 18 <= idade_detectada <= 23:
            faixa_temporal = "jovem"
        elif 24 <= idade_detectada <= 34:
            faixa_temporal = "adulto_jovem"
        elif 35 <= idade_detectada <= 44:
            faixa_temporal = "adulto"
        elif 45 <= idade_detectada <= 59:
            faixa_temporal = "maduro_coroa"
        else:
            faixa_temporal = "idoso"

    elif marcador_idoso:
        faixa_temporal = "idoso"

    elif marcador_coroa:
        faixa_temporal = "maduro_coroa"

    elif marcador_jovem:
        faixa_temporal = "jovem"

    elif eh_professor_ou_autoridade:
        faixa_temporal = "adulto_ou_maduro_autoridade"

    # ======================================================
    # 5) GERAÇÃO EM RELAÇÃO À MARY
    # Mary tem 19 anos no cânone.
    # ======================================================
    idade_mary = 19
    geracao = "desconhecida"

    if eh_mary:
        geracao = "propria_mary"

    elif eh_mae:
        geracao = "geracao_da_mae"

    elif eh_ancestral_familiar:
        geracao = "ancestral_familiar"

    elif idade_detectada is not None:
        diferenca = idade_detectada - idade_mary

        if diferenca <= -3:
            geracao = "mais_novo_que_mary"
        elif -2 <= diferenca <= 3:
            geracao = "mesma_geracao_de_mary"
        elif 4 <= diferenca <= 12:
            geracao = "pouco_mais_velho_que_mary"
        elif 13 <= diferenca <= 25:
            geracao = "geracao_acima"
        else:
            geracao = "muito_mais_velho_que_mary"

    else:
        if faixa_temporal in ("maduro_coroa", "adulto_ou_maduro_autoridade"):
            geracao = "geracao_acima"
        elif faixa_temporal == "idoso":
            geracao = "muito_mais_velho_que_mary"
        elif faixa_temporal in ("jovem", "adulto_jovem"):
            geracao = "mesma_ou_proxima_geracao"

    # ======================================================
    # 6) CONTEXTO SOCIAL
    # ======================================================
    local_norm = _texto_norm(state.get("local", ""))
    tom_norm = _texto_norm(state.get("tom_manual_da_cena", ""))
    tipo_norm = _texto_norm(state.get("tipo_de_cena", ""))

    contexto_publico = _tem_algum(
        local_norm,
        [
            "onibus",
            "ônibus",
            "metro",
            "metrô",
            "rua",
            "praça",
            "praca",
            "shopping",
            "sala de aula",
            "corredor",
            "bar cheio",
            "festa",
            "clube",
            "universidade",
            "faculdade",
        ],
    )

    contexto_social_flerte = (
        _tem_algum(
            local_norm,
            [
                "festa",
                "bar",
                "clube",
                "evento",
                "boate",
                "salão",
                "salao",
                "pista",
                "pista de dança",
                "pista de danca",
            ],
        )
        or tom_norm in (
            "malicia / flerte",
            "malicia",
            "flerte",
            "nsfw",
        )
        or tipo_norm in (
            "malicia_flerte",
            "malicia_flerte_publico",
            "malicia_flerte_semiprivado",
        )
    )

    # ======================================================
    # 7) ABERTURA / INTERESSE DA MARY
    # Isso impede a função de "cozinhar" ou podar uma interação
    # em que Mary demonstrou curiosidade primeiro.
    # ======================================================
    mary_deu_abertura = _tem_algum(
        texto_busca,
        [
            "mary percebe alguém atraente",
            "mary achou atraente",
            "mary sente atração",
            "mary sentiu atração",
            "mary sente curiosidade",
            "mary ficou curiosa",
            "mary olhou primeiro",
            "mary sustenta o olhar",
            "mary sorri",
            "mary sorriu",
            "mary corresponde",
            "mary não se afasta",
            "mary nao se afasta",
            "mary dá abertura",
            "mary da abertura",
            "mary deixa aproximar",
            "mary dança perto",
            "mary danca perto",
            "mary acompanha o ritmo",
            "mary observa com interesse",
            "o olhar de mary para nele",
            "o olhar dela para nele",
            "seu olhar varre o salão e percebe alguém atraente",
            "percebe alguém atraente no bar",
        ],
    )

    aproximacao_social_respeitosa = _tem_algum(
        texto_busca,
        [
            "tentando dançar próximo",
            "tentando dancar proximo",
            "dança próximo",
            "danca proximo",
            "dançando próximo",
            "dancando proximo",
            "se aproxima com cuidado",
            "mantém distância",
            "mantem distancia",
            "sem tocar",
            "sorri para mary",
            "olha de longe",
            "chega com educação",
            "chega com educacao",
            "fala baixo",
            "pede licença",
            "pede licenca",
            "pergunta se pode",
            "sem invadir",
            "respeitando espaço",
            "respeitando espaco",
        ],
    )

    aproximacao_desajeitada = _tem_algum(
        texto_busca,
        [
            "passos desconexos",
            "meio desajeitado",
            "meio desajeitada",
            "sem ritmo",
            "tentando acompanhar",
            "dançando estranho",
            "dancando estranho",
            "dança mal",
            "danca mal",
            "fora do compasso",
            "passos fora do ritmo",
        ],
    )

    # ======================================================
    # 8) INVASÃO / ASSÉDIO / COERÇÃO
    # ======================================================
    olhar_invasivo = _tem_algum(
        texto_busca,
        [
            "olhando para o decote",
            "olha para o decote",
            "olhar para o decote",
            "encarando o decote",
            "olhando os seios",
            "encarando os seios",
            "olhando a bunda",
            "encarando a bunda",
            "olhar invasivo",
            "olhar tarado",
            "disfarçando para o decote",
            "disfarcando para o decote",
            "disfarçando, para seu decote",
            "secando mary",
            "secando ela",
        ],
    )

    toque_sem_permissao = _tem_algum(
        texto_busca,
        [
            "encosta sem permissão",
            "encosta sem permissao",
            "toca sem permissão",
            "toca sem permissao",
            "segura o braço dela",
            "segura o braco dela",
            "puxa pelo braço",
            "puxa pelo braco",
            "agarra mary",
            "agarra ela",
            "passa a mão sem permissão",
            "passa a mao sem permissao",
            "encoxa",
            "encoxando",
        ],
    )

    bloqueio_ou_insistencia = _tem_algum(
        texto_busca,
        [
            "bloqueia a passagem",
            "fecha o caminho",
            "encurrala",
            "encurralando",
            "insiste depois dela recusar",
            "não aceita o não",
            "nao aceita o nao",
            "continua insistindo",
            "segue mary",
            "persegue mary",
            "vai atrás dela",
            "vai atras dela",
        ],
    )

    coerção_por_poder = (
        eh_professor_ou_autoridade
        and _tem_algum(
            texto_busca,
            [
                "nota em troca",
                "nota 10 em troca",
                "dar nota em troca",
                "aprovação em troca",
                "aprovacao em troca",
                "aprovar em troca",
                "subornar mary",
                "suborno",
                "troca de algo mais",
                "em troca de algo mais",
                "se quiser passar",
                "se quiser a nota",
                "te dou nota",
                "te dou aprovação",
                "te dou aprovacao",
                "te aprovo",
                "garanto sua nota",
                "garanto sua aprovação",
                "garanto sua aprovacao",
                "favorecimento em troca",
            ],
        )
    )

    assedio_explicito = _tem_algum(
        texto_busca,
        [
            "assedio",
            "assédio",
            "assediando",
            "assediou",
            "importunacao",
            "importunação",
            "invasivo",
            "invasiva",
            "sem consentimento",
            "forçando",
            "forcando",
            "insistindo",
            "encurralando",
            "constrangendo",
            "constrangimento",
        ],
    )

    desejo_social = (
        _tem_algum(
            texto_busca,
            [
                "coroa gato",
                "coroa gostoso",
                "que gato",
                "que gostoso",
                "homem bonito",
                "mulher bonita",
                "atraente",
                "charme",
                "presenca",
                "presença",
                "porte físico impressiona",
                "porte fisico impressiona",
                "cabelos levemente grisalhos",
                "ar de desejo",
                "troca de olhares",
                "olhar de desejo",
            ],
        )
        and not olhar_invasivo
        and not toque_sem_permissao
        and not coerção_por_poder
    )

    # ======================================================
    # 9) CLASSIFICAÇÃO DA INTERAÇÃO
    # Ordem importa:
    # coerção/invasão real vencem atração social.
    # atração social com abertura de Mary não deve ser podada.
    # ======================================================
    tipo_interacao = "neutra"
    risco_assedio = "nenhum"
    consentimento_percebido = "ambíguo"

    if eh_mary:
        tipo_interacao = "autopercepcao_mary"
        risco_assedio = "nenhum"
        consentimento_percebido = "nao_aplicavel"

    elif eh_mae:
        tipo_interacao = "familiar_mae"
        risco_assedio = "nenhum"
        consentimento_percebido = "nao_aplicavel"

    elif eh_ancestral_familiar:
        tipo_interacao = "ancestral_familiar"
        risco_assedio = "nenhum"
        consentimento_percebido = "nao_aplicavel"

    elif coerção_por_poder:
        tipo_interacao = "assedio_por_poder"
        risco_assedio = "alto"
        consentimento_percebido = "coercitivo"

    elif assedio_explicito or toque_sem_permissao or bloqueio_ou_insistencia:
        tipo_interacao = "assedio_ou_invasao"
        risco_assedio = "alto"
        consentimento_percebido = "ausente"

    elif olhar_invasivo and contexto_publico and not mary_deu_abertura:
        tipo_interacao = "assedio_visual"
        risco_assedio = "moderado"
        consentimento_percebido = "ausente"

    elif olhar_invasivo and not mary_deu_abertura:
        tipo_interacao = "olhar_invasivo"
        risco_assedio = "moderado"
        consentimento_percebido = "ausente"

    elif marcador_coroa and contexto_social_flerte and (mary_deu_abertura or aproximacao_social_respeitosa):
        tipo_interacao = "flerte_maduro_consensual"
        risco_assedio = "baixo"
        consentimento_percebido = "possivel"

    elif marcador_coroa and contexto_social_flerte and aproximacao_desajeitada:
        tipo_interacao = "aproximacao_social_desajeitada"
        risco_assedio = "baixo"
        consentimento_percebido = "ambíguo"

    elif desejo_social and contexto_social_flerte:
        tipo_interacao = "desejo_social"
        risco_assedio = "nenhum"
        consentimento_percebido = "possivel"

    elif desejo_social:
        tipo_interacao = "atracao_percebida"
        risco_assedio = "baixo"
        consentimento_percebido = "ambíguo"

    # ======================================================
    # 10) LEITURA PARA MARY
    # ======================================================
    if tipo_interacao == "autopercepcao_mary":
        leitura = (
            "Mary percebe a si mesma como jovem universitária de 19 anos, com energia, "
            "curiosidade, impulsos, contradições e desejo de viver experiências sem perder a própria agência."
        )

    elif tipo_interacao == "familiar_mae":
        leitura = (
            "Mary percebe como mãe/família: geração acima, autoridade afetiva, cuidado, "
            "julgamento, proteção da imagem e vínculo familiar. Não tratar como flerte."
        )

    elif tipo_interacao == "ancestral_familiar":
        leitura = (
            "Mary percebe como ancestral familiar idoso: avô/avó/bisavô/bisavó, ligado a respeito, "
            "memória familiar, carinho e cuidado. Se houver menção a lucidez ou vigor, entender como saúde, "
            "vitalidade e clareza mental para a idade, não como conotação sexual."
        )

    elif tipo_interacao == "assedio_por_poder":
        leitura = (
            "Mary percebe assédio por assimetria de poder. Professor, chefe ou autoridade usando nota, "
            "aprovação, cargo, dinheiro ou vantagem para obter algo íntimo deve ser lido como coerção, "
            "risco e manipulação, não como flerte consensual."
        )

    elif tipo_interacao == "assedio_ou_invasao":
        leitura = (
            "Mary percebe invasão ou assédio: toque sem permissão, insistência, bloqueio, constrangimento "
            "ou falta de espaço para recusar. Ela deve reagir com alerta, proteção do próprio corpo, firmeza "
            "e busca de distância/apoio conforme o risco."
        )

    elif tipo_interacao == "assedio_visual":
        leitura = (
            "Mary percebe olhar invasivo em espaço público. Ela deve sentir desconforto, alerta e proteger "
            "o próprio espaço: ajustar postura, cobrir-se, afastar-se, encarar ou responder com firmeza proporcional."
        )

    elif tipo_interacao == "olhar_invasivo":
        leitura = (
            "Mary percebe olhar invasivo ou pesado. Ela deve avaliar o risco, controlar distância, "
            "não erotizar automaticamente e reagir conforme o grau de desconforto."
        )

    elif tipo_interacao == "flerte_maduro_consensual":
        leitura = (
            "Mary percebe um flerte social possível com pessoa madura/coroa. A diferença de idade não é problema "
            "por si só. Se há abertura, respeito, distância adequada e clima de festa/bar/dança, Mary pode sentir "
            "curiosidade, atração, humor, provocação ou desejo. Não bloquear nem cozinhar automaticamente."
        )

    elif tipo_interacao == "aproximacao_social_desajeitada":
        leitura = (
            "Mary percebe uma aproximação social meio desajeitada, mas não necessariamente invasiva. "
            "Se o homem maduro tenta dançar perto sem tocar, bloquear ou insistir, Mary pode achar graça, "
            "testar o jogo, provocar ou dar abertura. Não tratar como assédio automático."
        )

    elif tipo_interacao == "desejo_social":
        leitura = (
            "Mary percebe desejo social ou atração em contexto jogável. Se alguém diz 'coroa gato', "
            "ela entende como pessoa madura, atraente, segura e interessante, não como idoso frágil."
        )

    elif tipo_interacao == "atracao_percebida":
        leitura = (
            "Mary percebe atração ou interesse inicial. Ela pode avaliar, corresponder, testar ou recuar, "
            "sem transformar isso em assédio automaticamente."
        )

    elif faixa_temporal == "maduro_coroa":
        leitura = (
            "Mary percebe como coroa/maduro no sentido brasileiro: mais velho, experiente, saudável, seguro, "
            "bem resolvido e com presença. Isso pode ser atraente se o contexto for social e consensual."
        )

    elif faixa_temporal == "idoso":
        leitura = (
            "Mary percebe como idoso/senhor de idade. Isso pede respeito, cautela e leitura de limites. "
            "Se houver flerte invasivo ou insistência, Mary deve perceber como desconfortável ou inadequado."
        )

    elif faixa_temporal == "menor":
        leitura = (
            "Mary percebe como menor de idade. Não tratar com flerte ou erotização."
        )

    else:
        leitura = (
            "Mary deve inferir idade, maturidade, desejo, risco e limites pelo contexto da cena, "
            "sem confundir atração social com assédio, nem assédio com flerte."
        )

    return {
        "personagem": personagem,
        "idade_detectada": idade_detectada,
        "faixa_temporal": faixa_temporal,
        "geracao_em_relacao_a_mary": geracao,
        "tipo_interacao": tipo_interacao,
        "risco_assedio": risco_assedio,
        "consentimento_percebido": consentimento_percebido,
        "mary_deu_abertura": mary_deu_abertura,
        "aproximacao_social_respeitosa": aproximacao_social_respeitosa,
        "aproximacao_desajeitada": aproximacao_desajeitada,
        "olhar_invasivo": olhar_invasivo,
        "toque_sem_permissao": toque_sem_permissao,
        "bloqueio_ou_insistencia": bloqueio_ou_insistencia,
        "coercao_por_poder": coerção_por_poder,
        "leitura_para_mary": leitura,
    }


def normalizar_relacao_por_interlocutor(state: dict) -> None:
    """
    Normaliza relação ativa com base no interlocutor real da cena.

    Regras:
    - Personagens centrais têm regra fixa.
    - Personagens novos são inferidos por contexto em memórias, cânone e facts.
    - Estado emocional manual não é alterado aqui.
    - O foco do turno vence quando houver múltiplos interlocutores.
    """
    if not isinstance(state, dict):
        return

    interlocutor = remover_acentos(str(state.get("interlocutor", "") or "").strip().lower())
    foco = remover_acentos(str(state.get("interlocutor_foco_turno", "") or "").strip().lower())
    persistente = remover_acentos(str(state.get("interlocutor_ativo_persistente", "") or "").strip().lower())
    ultimo = remover_acentos(str(state.get("ultimo_interlocutor_explicito", "") or "").strip().lower())
    janio_status = remover_acentos(str(state.get("janio_status_na_cena", "") or "").strip().lower())

    alvo_raw = foco or persistente or ultimo or interlocutor
    alvo = extrair_nome_base_interlocutor(alvo_raw)

    if (
        eh_sem_interlocutor(interlocutor)
        and eh_sem_interlocutor(foco)
        and eh_sem_interlocutor(persistente)
        and eh_sem_interlocutor(ultimo)
    ):
        state["relacao"] = "sem interlocutor"
        state["modo_relacional"] = "neutro"
        state["tensao_romantica_com_interlocutor"] = False
        state["amor_genuino_com_interlocutor"] = False
        state["toque_intimo_permitido"] = False
        return

    if "silvia" in alvo:
        state["relacao"] = "amizade"
        state["modo_relacional"] = "amizade"
        state["tensao_romantica_com_interlocutor"] = False
        state["amor_genuino_com_interlocutor"] = False
        state["toque_intimo_permitido"] = False
        return

    if "anthony" in alvo:
        state["relacao"] = "ex / tensão"
        state["modo_relacional"] = "tensao_social"
        state["tensao_romantica_com_interlocutor"] = False
        state["amor_genuino_com_interlocutor"] = False
        state["toque_intimo_permitido"] = False
        return

    if "janio" in alvo:
        janio_presente = janio_status in {
            "presente",
            "interlocutor",
            "personagem",
            "na cena",
            "presente na cena",
            "ativo",
            "participando",
            "junto",
            "sim",
            "true",
            "1",
        }

        if janio_presente:
            state["relacao"] = "romance"
            state["modo_relacional"] = "romance"
            state["tensao_romantica_com_interlocutor"] = True
            state["amor_genuino_com_interlocutor"] = True

            # Não derruba permissão íntima definida pelo tom/local.
            state["toque_intimo_permitido"] = normalizar_bool(
                state.get("toque_intimo_permitido", False),
                default=False,
            )
            return

        state["relacao"] = "contextual"
        state["modo_relacional"] = "neutro"
        state["tensao_romantica_com_interlocutor"] = False
        state["amor_genuino_com_interlocutor"] = False
        state["toque_intimo_permitido"] = False
        return

    if "bianca" in alvo:
        state["relacao"] = "amizade íntima"
        state["modo_relacional"] = "cumplicidade"
        state["tensao_romantica_com_interlocutor"] = True
        state["amor_genuino_com_interlocutor"] = False
        state["toque_intimo_permitido"] = False
        return

    contexto_personagem = buscar_contexto_do_personagem(state, alvo)
    inferido = inferir_relacao_por_contexto(alvo, contexto_personagem)

    state["relacao"] = inferido["relacao"]
    state["modo_relacional"] = inferido["modo_relacional"]
    state["tensao_romantica_com_interlocutor"] = inferido["tensao_romantica_com_interlocutor"]
    state["toque_intimo_permitido"] = inferido["toque_intimo_permitido"]

    # Para personagens inferidos, só libera amor genuíno se já estiver marcado manualmente.
    state["amor_genuino_com_interlocutor"] = normalizar_bool(
        state.get("amor_genuino_com_interlocutor", False),
        default=False,
    )


def resetar_progressao_fisica_se_cena_neutra_sozinha(state: dict) -> None:
    """
    Quando Mary está sozinha, em tom Natural / Amizade e sem estímulo ativo,
    limpa fase física herdada de cena anterior.

    Importante:
    - Não apaga fatos narrativos passados.
    - Não altera mary_climax_done/user_climax_done.
    - Apenas impede que uma cena atual sozinha e neutra carregue
      resíduos de sexo, pico ou intimidade anterior.
    """
    if not isinstance(state, dict):
        return

    interlocutor = _texto_norm(state.get("interlocutor", ""))
    foco = _texto_norm(state.get("interlocutor_foco_turno", ""))
    tom = _texto_norm(state.get("tom_manual_da_cena", ""))
    tipo = _texto_norm(state.get("tipo_de_cena", ""))

    try:
        mary_stimulation_turns = int(state.get("mary_stimulation_turns", 0) or 0)
    except Exception:
        mary_stimulation_turns = 0

    force_resolution_now = normalizar_bool(
        state.get("force_resolution_now", False),
        default=False,
    )

    mary_pre_orgasm_signals = normalizar_bool(
        state.get("mary_pre_orgasm_signals", False),
        default=False,
    )

    tom_natural_ou_antigo = tom in (
        "natural / amizade",
        "natural_amizade",
        "neutro",
        "amizade",
    )

    tipo_natural_ou_antigo = tipo in (
        "natural_amizade",
        "neutra",
        "amizade",
        "cotidiano",
    )

    if (
        eh_sem_interlocutor(interlocutor)
        and eh_sem_interlocutor(foco)
        and tom_natural_ou_antigo
        and tipo_natural_ou_antigo
        and mary_stimulation_turns <= 0
        and not force_resolution_now
        and not mary_pre_orgasm_signals
    ):
        state["physical_phase"] = 0
        state["scene_stage"] = "cotidiano"
        state["mary_intent"] = "preparar_noite_refletindo"
        state["desire_level"] = min(clamp(state.get("desire_level", 0.0)), 0.12)
        state["tension_level"] = min(clamp(state.get("tension_level", 0.0)), 0.12)
        state["toque_intimo_permitido"] = False
        state["tensao_romantica_com_interlocutor"] = False
        state["partner_climax_pending"] = False


def _fase_atual(state: dict) -> int:
    if not isinstance(state, dict):
        return 0

    try:
        return int(state.get("physical_phase", 0) or 0)
    except Exception:
        return 0


# ==========================================================
# PROGRESSÃO DE CENA / PICO / CLÍMAX / AVANÇO SOCIAL
# ==========================================================

def safe_int(valor, default: int = 0) -> int:
    try:
        return int(valor or default)
    except Exception:
        return default


def detectar_climax_usuario(fala_usuario: str) -> str:
    """
    Detecta o estágio do clímax do parceiro.

    Retornos:
    - "aviso": parceiro disse que vai gozar / está quase;
    - "em_andamento": parceiro disse que está gozando / já gozou;
    - "nenhum": sem sinal claro.
    """
    texto = _texto_norm(fala_usuario)

    negacoes = [
        "nao gozei",
        "não gozei",
        "ainda nao gozei",
        "ainda não gozei",
        "nao estou gozando",
        "não estou gozando",
        "nao acabei",
        "não acabei",
        "segurei",
        "estou segurando",
        "to segurando",
        "tô segurando",
        "não quero gozar assim",
        "nao quero gozar assim",
    ]

    if _tem_algum(texto, negacoes):
        return "nenhum"

    gatilhos_em_andamento = [
        "estou gozando",
        "to gozando",
        "tô gozando",
        "gozando",
        "gozei",
        "ja gozei",
        "já gozei",
        "acabei",
        "acabei agora",
    ]

    gatilhos_aviso = [
        "vou gozar",
        "vou gozar agora",
        "vou acabar",
        "vou explodir",
        "estou quase",
        "to quase",
        "tô quase",
        "nao vou aguentar",
        "não vou aguentar",
        "vou perder o controle",
        "tá vindo",
        "ta vindo",
    ]

    # Ordem importante:
    # "estou gozando" = já começou.
    # "vou gozar" = ainda dá tempo de Mary conduzir.
    if _tem_algum(texto, gatilhos_em_andamento):
        return "em_andamento"

    if _tem_algum(texto, gatilhos_aviso):
        return "aviso"

    return "nenhum"

def preparar_destino_climax_parceiro(state: dict, fala_usuario: str) -> None:
    """
    Decide como Mary deve reagir quando o parceiro diz que vai gozar
    ou que já está gozando.

    Não resolve orgasmo de Mary.
    Não substitui aftercare.
    Não substitui frustração.
    Apenas cria uma flag forte para o prompt:
    - pedir_dentro
    - pedir_fora
    - segurar
    - reagir_dentro_em_andamento
    - reagir_fora_em_andamento
    - reagir_sem_escolha
    """
    if not isinstance(state, dict):
        return

    state["destino_climax_parceiro"] = ""

    tom = normalizar_tom_manual_cena(state.get("tom_manual_da_cena", ""))
    if tom != "Nsfw":
        return

    sinal = detectar_climax_usuario(fala_usuario)
    if sinal == "nenhum":
        return

    texto = _texto_norm(fala_usuario)

    mary_climax_done = normalizar_bool(
        state.get("mary_climax_done", False),
        default=False,
    )

    force_resolution_now = normalizar_bool(
        state.get("force_resolution_now", False),
        default=False,
    )

    mary_pre_orgasm = normalizar_bool(
        state.get("mary_pre_orgasm_signals", False),
        default=False,
    )

    privacidade = _texto_norm(state.get("privacidade", ""))
    toque_intimo = normalizar_bool(
        state.get("toque_intimo_permitido", False),
        default=False,
    )

    alivio_rapido = normalizar_bool(
        state.get("alivio_rapido_permitido", False),
        default=False,
    )

    scene_stage = normalizar_scene_stage(
        state.get("scene_stage", ""),
        padrao="inicio",
    )

    mary_acao = _texto_norm(state.get("mary_acao", ""))

    cena_em_ato = (
        toque_intimo
        or alivio_rapido
        or scene_stage in (
            "sexo_ou_estimulo",
            "estimulo_corporal",
            "pre_pico_mary",
            "pico_mary",
            "alivio_rapido",
        )
        or any(
            termo in mary_acao
            for termo in (
                "sexo oral",
                "boquete",
                "penetração",
                "penetracao",
                "masturb",
                "rebolando",
                "de quatro",
                "montada",
                "colo",
                "sarrando",
            )
        )
    )

    if not cena_em_ato:
        return

    pede_dentro = _tem_algum(
        texto,
        [
            "dentro",
            "gozar dentro",
            "goza dentro",
            "gozando dentro",
            "quero dentro",
        ],
    )

    pede_fora = _tem_algum(
        texto,
        [
            "fora",
            "gozar fora",
            "goza fora",
            "tira",
            "tira agora",
            "não dentro",
            "nao dentro",
            "na barriga",
            "na bunda",
            "no corpo",
            "nos seios",
            "na boca",
            "na mão",
            "na mao",
        ],
    )

    pede_segurar = _tem_algum(
        texto,
        [
            "segura",
            "espera",
            "ainda não",
            "ainda nao",
            "não goza",
            "nao goza",
            "não quero gozar assim",
            "nao quero gozar assim",
        ],
    )

    # ======================================================
    # CASO 1: ele avisou que vai gozar.
    # Ainda dá tempo de Mary conduzir.
    # ======================================================
    if sinal == "aviso":
        state["climax_usuario_sinal"] = True
        state["user_climax_done"] = False

        # Se Mary está quase ou o gate dela vai resolver agora,
        # prioridade é segurar/conduzir junto, não incentivar final isolado.
        if force_resolution_now or mary_pre_orgasm:
            state["destino_climax_parceiro"] = "segurar"
            state["mary_frustracao_climax"] = "controlar_ritmo"
            state["scene_stage"] = "pre_pico_mary"
            state["mary_intent"] = "sustentar_tensao_intensa"
            state["physical_phase"] = max(
                safe_int(state.get("physical_phase", 0), 0),
                5,
            )
            return

        if pede_fora:
            state["destino_climax_parceiro"] = "pedir_fora"
            return

        if pede_dentro and privacidade == "privado":
            state["destino_climax_parceiro"] = "pedir_dentro"
            return

        if pede_segurar:
            state["destino_climax_parceiro"] = "segurar"
            state["mary_frustracao_climax"] = "controlar_ritmo"
            return

        # Default seguro: se não há pedido claro, Mary decide conforme ambiente.
        if privacidade == "privado" and mary_climax_done:
            state["destino_climax_parceiro"] = "pedir_dentro"
        else:
            state["destino_climax_parceiro"] = "pedir_fora"

        return

    # ======================================================
    # CASO 2: ele disse que já está gozando.
    # Mary não muda tarde demais: reage ao que começou.
    # ======================================================
    if sinal == "em_andamento":
        state["climax_usuario_sinal"] = True
        state["user_climax_done"] = True

        if pede_dentro:
            state["destino_climax_parceiro"] = "reagir_dentro_em_andamento"
            return

        if pede_fora:
            state["destino_climax_parceiro"] = "reagir_fora_em_andamento"
            return

        state["destino_climax_parceiro"] = "reagir_sem_escolha"
        return

def preparar_frustracao_mary_se_parceiro_chegar_antes(
    state: dict,
    fala_usuario: str,
) -> None:
    """
    Cria um estado específico quando o parceiro anuncia ou inicia clímax
    antes do pico de Mary.

    Regras:
    - "vou gozar" = aviso. Mary ainda pode controlar/frear.
    - "tô gozando/gozei" = já começou. Mary reage frustrada se ainda não gozou.
    - Se force_resolution_now=True, o pico de Mary vence e não entra frustração.
    - Em ambiente de alívio rápido/semiprivado, a frustração ainda pode existir
      se a cena já entrou em ato físico no histórico/ação atual.
    """
    if not isinstance(state, dict):
        return

    tom = normalizar_tom_manual_cena(state.get("tom_manual_da_cena", ""))
    if tom != "Nsfw":
        state["mary_frustracao_climax"] = ""
        return

    climax_sinal = detectar_climax_usuario(fala_usuario)

    if climax_sinal == "nenhum":
        state["mary_frustracao_climax"] = ""
        return

    mary_climax_done = normalizar_bool(
        state.get("mary_climax_done", False),
        default=False,
    )

    force_resolution_now = normalizar_bool(
        state.get("force_resolution_now", False),
        default=False,
    )

    mary_pre_orgasm_signals = normalizar_bool(
        state.get("mary_pre_orgasm_signals", False),
        default=False,
    )

    user_climax_done = normalizar_bool(
        state.get("user_climax_done", False),
        default=False,
    )

    privacidade = _texto_norm(state.get("privacidade", ""))
    toque_intimo = normalizar_bool(
        state.get("toque_intimo_permitido", False),
        default=False,
    )

    alivio_rapido = normalizar_bool(
        state.get("alivio_rapido_permitido", False),
        default=False,
    )

    scene_stage = normalizar_scene_stage(
        state.get("scene_stage", ""),
        padrao="inicio",
    )

    mary_acao_norm = _texto_norm(state.get("mary_acao", ""))
    fala_norm = _texto_norm(fala_usuario)

    cena_em_ato = (
        toque_intimo
        or alivio_rapido
        or scene_stage in (
            "sexo_ou_estimulo",
            "estimulo_corporal",
            "pre_pico_mary",
            "pico_mary",
            "alivio_rapido",
        )
        or any(
            termo in mary_acao_norm
            for termo in (
                "sexo oral",
                "boquete",
                "chupando",
                "penetração",
                "penetracao",
                "masturb",
                "rebolando",
                "de quatro",
                "montada",
            )
        )
        or any(
            termo in fala_norm
            for termo in (
                "vou gozar",
                "to quase",
                "tô quase",
                "gozando",
                "gozei",
                "nao vou aguentar",
                "não vou aguentar",
            )
        )
    )

    # Se não há ato real em andamento, não força frustração sexual.
    if not cena_em_ato:
        state["mary_frustracao_climax"] = ""
        return

    # Se Mary já gozou, não é frustração dela: vira reação ao clímax do parceiro.
    if mary_climax_done:
        state["mary_frustracao_climax"] = ""

        if climax_sinal == "aviso":
            state["mary_reacao_climax_parceiro"] = "conduzir_apos_pico_mary"
            state["partner_climax_pending"] = True
            state["user_climax_done"] = False

        elif climax_sinal == "em_andamento":
            state["mary_reacao_climax_parceiro"] = "acolher_gozo_apos_pico_mary"
            state["partner_climax_pending"] = False
            state["user_climax_done"] = True

        return

    # Se chegou a hora do pico de Mary, não transformar em frustração.
    if force_resolution_now:
        state["mary_frustracao_climax"] = ""
        return

    # Caso 1: parceiro avisou antes.
    if climax_sinal == "aviso":
        state["mary_frustracao_climax"] = "controlar_ritmo"
        state["climax_usuario_sinal"] = True
        state["user_climax_done"] = False
        state["partner_climax_pending"] = False

        # Se ela já estava quase, mantém pré-pico, mas sem resolver.
        if mary_pre_orgasm_signals:
            state["scene_stage"] = "pre_pico_mary"
            state["mary_intent"] = "sustentar_tensao_intensa"
            state["physical_phase"] = max(
                safe_int(state.get("physical_phase", 0), 0),
                5,
            )

        return

    # Caso 2: parceiro já começou ou já gozou antes dela.
    if climax_sinal == "em_andamento" or user_climax_done:
        state["mary_frustracao_climax"] = "frustrada_parceiro_gozou_antes"
        state["climax_usuario_sinal"] = True
        state["user_climax_done"] = True
        state["partner_climax_pending"] = False
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False
        state["scene_stage"] = "desaceleracao"
        state["mary_intent"] = "desacelerar_com_presenca"
        state["physical_phase"] = max(
            safe_int(state.get("physical_phase", 0), 0),
            5,
        )
        return

    state["mary_frustracao_climax"] = ""


def safe_float(valor, default: float = 0.0) -> float:
    try:
        return float(valor or default)
    except Exception:
        return default


def _texto_norm(valor: str) -> str:
    """
    Normaliza texto para comparação simples.
    Depende da função remover_acentos() definida no bloco anterior.
    """
    return remover_acentos(str(valor or "").strip().lower())


def _tem_algum(texto: str, termos: list[str]) -> bool:
    texto = _texto_norm(texto)
    return any(_texto_norm(t) in texto for t in termos if str(t or "").strip())

def ha_acao_para_onomatopeia(state: dict, fala_usuario: str, resposta: str, tipo: str) -> bool:
    """
    Verifica se há ação física correspondente para permitir determinada onomatopeia.
    Evita que sons como Smack/FLOP/LAMB/CHUP/SLUPT/POP virem muleta fora de contexto.
    """
    contexto = _texto_norm(
        "\n".join(
            [
                str(fala_usuario or ""),
                str(resposta or ""),
                str(state.get("mary_acao", "") or ""),
                str(state.get("scene_stage", "") or ""),
                str(state.get("mary_intent", "") or ""),
                str(state.get("tipo_de_cena", "") or ""),
                str(state.get("tom_manual_da_cena", "") or ""),
            ]
        )
    )

    tipo = _texto_norm(tipo)

    if tipo == "beijo":
        return _tem_algum(
            contexto,
            [
                "beijo",
                "beija",
                "beijando",
                "beijou",
                "selinho",
                "labios",
                "lábios",
                "boca",
                "beijo na boca",
                "beijo os labios",
                "beijo seus labios",
                "beijo sua boca",
                "mary beija",
                "ela beija",
                "nos beijamos",
            ],
        )

    if tipo == "penetracao":
        return _tem_algum(
            contexto,
            [
                "penetracao",
                "penetração",
                "penetrando",
                "estocada",
                "estocadas",
                "entra e sai",
                "entrando e saindo",
                "vai e vem",
                "cavalgando",
                "cavalga",
                "montada",
                "dentro de mim",
                "dentro dela",
                "pau dentro",
                "sexo_ou_estimulo",
                "pre_pico_mary",
                "pico_mary",
            ],
        )

    if tipo == "lambida":
        return _tem_algum(
            contexto,
            [
                "lambida",
                "lambendo",
                "lambe",
                "lambo",
                "lingua",
                "língua",
                "passa a lingua",
                "passa a língua",
            ],
        )

    if tipo == "succao":
        return _tem_algum(
            contexto,
            [
                "chupa",
                "chupando",
                "chupar",
                "suga",
                "sugando",
                "sugar",
                "succao",
                "sucção",
                "boca",
                "oral",
            ],
        )

    if tipo == "pop":
        return _tem_algum(
            contexto,
            [
                "solta com a boca",
                "solta abruptamente",
                "estalo",
                "estala",
                "chupando",
                "sugando",
                "sucção",
                "succao",
                "pop",
            ],
        )

    if tipo == "tapa":
        return _tem_algum(
            contexto,
            [
                "tapa",
                "palmada",
                "palmadas",
                "estalo",
                "estala",
                "estalou",
                "bunda",
                "nádega",
                "nadega",
                "palma",
                "batida",
                "bateu",
                "batendo",
                "tapinha",
                "plaf",
            ],
        ) 

    if tipo == "cheiro":
        return _tem_algum(
            contexto,
            [
                "cheira",
                "cheirando",
                "cheiro",
                "sentir o cheiro",
                "sente o cheiro",
                "inspira",
                "inspirando",
                "fareja",
                "farejando",
                "aproxima o rosto",
                "nariz",
                "perfume",
                "odor",
                "aroma",
                "sniff",
            ],
        )

    if tipo == "abraco":
        return _tem_algum(
            contexto,
            [
                "abraço",
                "abraco",
                "abraça",
                "abraca",
                "abraçando",
                "abracando",
                "me abraça",
                "me abraca",
                "puxa para um abraço",
                "puxa para um abraco",
                "puxa contra o peito",
                "aperta contra o peito",
                "aperto de corpo",
                "corpo contra corpo",
                "envolve nos braços",
                "envolvo nos braços",
                "enlaça",
                "enlaca",
                "enlaço",
                "enlaco",
                "hummf",
            ],
        )

    if tipo == "agua":
        return _tem_algum(
                contexto,
                [
                    "pula na água",
                    "pulo na água",
                    "pular na água",
                    "pulando na água",
                    "cai na água",
                    "caio na água",
                    "cair na água",
                    "queda na água",
                    "mergulha",
                    "mergulho",
                    "mergulhando",
                    "salta",
                    "salto",
                    "saltando",
                    "tchibum",
                    "tchibummm",
                    "água",
                    "agua",
                    "mar",
                    "piscina",
                    "rio",
                    "lago",
                ],
            )    
    
    if tipo == "queda_macia":
        return _tem_algum(
                contexto,
                [
                    "se joga na cama",
                    "me jogo na cama",
                    "joga na cama",
                    "jogado na cama",
                    "cai na cama",
                    "caio na cama",
                    "cair na cama",
                    "afunda na cama",
                    "afundo na cama",
                    "se joga no sofá",
                    "me jogo no sofá",
                    "joga no sofá",
                    "joga no sofa",
                    "cai no sofá",
                    "cai no sofa",
                    "afunda no sofá",
                    "afunda no sofa",
                    "colchão",
                    "colchao",
                    "almofada",
                    "poltrona",
                    "superfície macia",
                    "superficie macia",
                    "plof",
                ],
            )                              

    return False

def converter_onomatopeias_sociais_em_acao(texto: str, state: dict, fala_usuario: str) -> str:
    """
    Converte onomatopeias sociais simples em narração natural.
    Ex:
    Smack! PLAF! em despedida vira ação narrativa.
    """
    texto = str(texto or "")

    if not texto.strip():
        return texto

    fala_norm = _texto_norm(fala_usuario)
    tom = _texto_norm(state.get("tom_manual_da_cena", ""))
    tipo = _texto_norm(state.get("tipo_de_cena", ""))
    interlocutor = str(
        state.get("interlocutor_foco_turno")
        or state.get("interlocutor")
        or "interlocutor"
    ).strip()

    tem_smack_usuario = "smack" in fala_norm
    tem_plaf_usuario = "plaf" in fala_norm

    cena_social = tom in ("neutro", "amizade", "segredo pendente", "decisao") or tipo in (
        "neutra",
        "amizade",
        "segredo_pendente",
        "decisao",
    )

    contexto_tapa = _tem_algum(
        fala_norm,
        [
            "tapa",
            "palmada",
            "bunda",
            "palma",
            "estalo",
            "plaf",
        ],
    )

    if cena_social and tem_smack_usuario and tem_plaf_usuario and contexto_tapa:
        frase = (
            f"Mary recebe o beijo rápido de {interlocutor} e ri quando sente "
            f"o tapa estalar em sua bunda."
        )

        # Remove blocos isolados [FALA] Smack/Plaf se existirem.
        texto = re.sub(
            r"\[FALA\]\s*\n\s*(smack|plaf)\s*[!.\u2026]*\s*",
            "",
            texto,
            flags=re.IGNORECASE,
        )

        # Insere a frase no primeiro bloco de ação, se houver.
        if "[ACAO]" in texto:
            texto = texto.replace("[ACAO]", f"[ACAO]\n{frase}\n\n", 1)
        else:
            texto = f"[ACAO]\n{frase}\n\n{texto}"

    return texto


def limpar_onomatopeias_fora_de_contexto(texto: str, state: dict, fala_usuario: str) -> str:
    """
    Remove onomatopeias quando não há ação física correspondente no turno atual.
    Mantém os sons quando eles fazem sentido na ação presente.
    """
    texto = str(texto or "")

    if not texto.strip():
        return texto

    permissoes = {
        "smack": ha_acao_para_onomatopeia(state, fala_usuario, texto, "beijo"),
        "flop": ha_acao_para_onomatopeia(state, fala_usuario, texto, "penetracao"),
        "lamb": ha_acao_para_onomatopeia(state, fala_usuario, texto, "lambida"),
        "chup": ha_acao_para_onomatopeia(state, fala_usuario, texto, "succao"),
        "slupt": ha_acao_para_onomatopeia(state, fala_usuario, texto, "succao"),
        "pop": ha_acao_para_onomatopeia(state, fala_usuario, texto, "pop"),
        "plaf": ha_acao_para_onomatopeia(state, fala_usuario, texto, "tapa"),
        "sniff": ha_acao_para_onomatopeia(state, fala_usuario, texto, "cheiro"),
        # Novas onomatopeias sociais/corporais
        "hummf": ha_acao_para_onomatopeia(state, fala_usuario, texto, "abraco"),
        "tchibum": ha_acao_para_onomatopeia(state, fala_usuario, texto, "agua"),
        "ploft": ha_acao_para_onomatopeia(state, fala_usuario, texto, "queda_macia"),
    }

    for som, permitido in permissoes.items():
        if permitido:
            continue

        texto = re.sub(
            rf"\b{re.escape(som)}\s*[!.\u2026]*",
            "",
            texto,
            flags=re.IGNORECASE,
        )

    # Limpeza leve de espaços deixados pela remoção.
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    texto = re.sub(r"\n[ \t]+", "\n", texto)
    texto = re.sub(r" +([,.!?])", r"\1", texto)

    return texto.strip()


def _set_fase_limitada(state: dict, limite: int, stage_padrao: str) -> None:
    if not isinstance(state, dict):
        return

    limite = safe_int(limite, 0)
    fase = max(0, min(_fase_atual(state), limite))

    state["physical_phase"] = fase

    mapa = {
        0: "inicio",
        1: "aproximacao",
        2: "toque",
        3: "beijo",
        4: "intensidade",
        5: "pico",
        6: "desaceleracao",
        7: "aftercare",
    }

    state["scene_stage"] = mapa.get(fase, stage_padrao or "inicio")


def atualizar_pico_mary_por_contexto(state: dict, fala_usuario: str, resposta_limpa: str = "") -> None:
    """
    Detecta progressão física real da cena e prepara sinais de pico de Mary.

    Importante:
    - Detecta contato direto, ritmo, estimulação e aproximação de pico.
    - Só atua em ambiente privado.
    - Não narra clímax do usuário.
    - Não força resolução imediata; apenas prepara estado para outra função decidir.
    """
    if not isinstance(state, dict):
        return

    texto = _texto_norm(
        "\n".join(
            [
                str(fala_usuario or ""),
                str(resposta_limpa or ""),
                str(state.get("mary_acao", "") or ""),
                str(state.get("scene_stage", "") or ""),
                str(state.get("mary_intent", "") or ""),
            ]
        )
    )

    privacidade = _texto_norm(state.get("privacidade", ""))

    if privacidade != "privado":
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False
        return

    fase = safe_int(state.get("physical_phase", 0), 0)

    # ======================================================
    # CONTEXTO FÍSICO JÁ ESTABELECIDO NA CENA
    # ======================================================
    contexto_fisico_salvo = _texto_norm(
        "\n".join(
            [
                str(state.get("mary_acao", "") or ""),
                str(state.get("scene_stage", "") or ""),
                str(state.get("mary_intent", "") or ""),
            ]
        )
    )

    contexto_penetracao_ativo = (
        fase >= 4
        or _tem_algum(
            contexto_fisico_salvo,
            [
                "penetração",
                "penetracao",
                "penetrando",
                "cavalgando",
                "cavalga",
                "montada",
                "entra e sai",
                "entrar e sair",
                "dentro de mim",
                "dentro dela",
                "estocadas",
                "estocada",
                "sexo_ou_estimulo",
                "pre_pico_mary",
            ],
        )
    )

    contexto_oral_ativo = _tem_algum(
        contexto_fisico_salvo,
        [
            "sexo oral",
            "língua",
            "lingua",
            "clitóris",
            "clitoris",
            "chupando",
            "sucção",
            "succao",
        ],
    )

    contexto_masturbacao_ativo = _tem_algum(
        contexto_fisico_salvo,
        [
            "dedos",
            "dedo",
            "masturbação",
            "masturbacao",
            "massageando",
            "esfregando",
        ],
    )

    # ======================================================
    # 1) CONTATO / PENETRAÇÃO
    # Separação entre sinais fortes e fracos evita falso positivo
    # com frases como "entrando na sala".
    # ======================================================
    sinais_fortes_penetracao = [
        "penetração",
        "penetracao",
        "penetração profunda",
        "penetracao profunda",
        "cavalgando",
        "cavalga",
        "cavalgar",
        "montada",
        "estocada",
        "estocadas",
        "entrar e sair",
        "entra e sai",
        "entrando e saindo",
        "movimentos pélvicos",
        "movimentos pelvicos",
        "pau dentro",
        "dentro de mim",
        "dentro dela",
        "me preenchendo",
        "preenchendo",
    ]

    sinais_fracos_penetracao = [
        "tá entrando",
        "ta entrando",
        "entrando",
        "entrou",
        "encaixar",
        "encaixando",
        "se encaixa",
        "se acomodando",
    ]

    sinais_ritmo_penetracao = [
        "flop",
        "vai e vem",
        "estocada",
        "estocadas",
        "mete",
        "metendo",
        "enfia",
        "enfiando",
        "ritmo",
        "mais fundo",
        "mais forte",
        "não para",
        "nao para",
        "continua",
        "batendo",
        "impacto",
        "sincronizando",
        "quadril sobe",
        "quadril subindo",
        "mary desce",
        "desce o quadril",
        "subindo contra",
        "movimento pélvico",
        "movimento pelvico",
        "ritmo frenético",
        "ritmo frenetico",
                "me fode",
        "quero ser fodida",
        "quero ficar de quatro",
        "ficar de quatro",
        "me coloca de quatro",
        "de quatro",
        "deixa eu montar",
        "quero montar",
        "montar em você",
        "montar em voce",
        "monta em mim",
        "segura minha cintura",
        "mete",
        "mete gostoso",
        "mete mais",
        "me come",
        "me come gostoso",
    ]

    tem_penetracao_forte = _tem_algum(texto, sinais_fortes_penetracao)
    tem_penetracao_fraca = _tem_algum(texto, sinais_fracos_penetracao)
    tem_ritmo_penetracao = _tem_algum(texto, sinais_ritmo_penetracao)

    tem_penetracao = tem_penetracao_forte or (
        tem_penetracao_fraca and contexto_penetracao_ativo
    )

    if tem_ritmo_penetracao and contexto_penetracao_ativo:
        tem_penetracao = True

    # ======================================================
    # 2) SEXO ORAL EM MARY
    # ======================================================
    sinais_oral_mary = [
        "chupo",
        "chupando",
        "chupar",
        "lamb",
        "lambo",
        "lambendo",
        "língua",
        "lingua",
        "boca em você",
        "boca em voce",
        "boca nela",
        "minha boca",
        "beijo sua buceta",
        "beijo sua intimidade",
        "lambendo sua buceta",
        "chupando sua buceta",
        "chupando você",
        "chupando voce",
        "clitóris",
        "clitoris",
        "xoxota",
        "buceta",
        "virilha",
    ]

    tem_oral_mary = _tem_algum(texto, sinais_oral_mary) or contexto_oral_ativo

    # ======================================================
    # 3) TOQUE MANUAL / MASTURBAÇÃO EM MARY
    # ======================================================
    sinais_masturbacao_mary = [
        "dedo",
        "dedos",
        "meus dedos",
        "passo os dedos",
        "esfrego",
        "esfregando",
        "massageio",
        "massageando",
        "masturbo",
        "masturbando",
        "toco sua buceta",
        "toco sua intimidade",
        "brinco com seu clitóris",
        "brinco com seu clitoris",
        "dedilho",
        "dedilhando",
        "acaricio sua buceta",
        "acaricio sua intimidade",
        "mão na sua buceta",
        "mao na sua buceta",
        "mão entre suas pernas",
        "mao entre suas pernas",
    ]

    tem_masturbacao_mary = (
        _tem_algum(texto, sinais_masturbacao_mary)
        or contexto_masturbacao_ativo
    )

    # ======================================================
    # 4) FRICÇÃO / CONTATO EXTERNO
    # ======================================================
    sinais_friccao = [
        "roçando",
        "roco",
        "roço",
        "esfrego meu pau",
        "esfrego contra",
        "pressiono contra",
        "fricção",
        "friccao",
        "quadril contra",
        "coxas apertam",
        "entre suas pernas",
        "na sua virilha",
        "borda do biquíni",
        "borda do biquini",
        "borda da calcinha",
    ]

    tem_friccao = _tem_algum(texto, sinais_friccao)

    # ======================================================
    # 5) SEIOS / MAMILOS
    # Aumenta tensão, mas sozinho não resolve pico.
    # ======================================================
    sinais_seios = [
        "seios",
        "peito",
        "mamilos",
        "mamilo",
        "chupando seus seios",
        "lambendo seus seios",
        "mordo seu peito",
        "mordendo seu peito",
        "aperto seus seios",
        "massageio seus seios",
    ]

    tem_seios = _tem_algum(texto, sinais_seios)

    # ======================================================
    # 6) PRAZER / PRÉ-PICO
    # ======================================================
    sinais_prazer_mary = [
        "gosta",
        "tá gostoso",
        "ta gostoso",
        "delícia",
        "delicia",
        "gemido",
        "gemendo",
        "geme",
        "ahhh",
        "hummm",
        "não para",
        "nao para",
        "continua",
        "mais",
        "assim",
        "isso",
    ]

    sinais_pre_orgasmo = [
        "vou gozar",
        "quase gozando",
        "quase lá",
        "quase la",
        "tô quase",
        "to quase",
        "não aguento",
        "nao aguento",
        "vou perder o controle",
        "perdendo o controle",
        "me solta",
        "me deixa gozar",
        "goza comigo",
    ]

    tem_prazer = _tem_algum(texto, sinais_prazer_mary)
    tem_pre_orgasmo_explicito = _tem_algum(texto, sinais_pre_orgasmo)

    estimulacao_direta = (
        tem_penetracao
        or tem_oral_mary
        or tem_masturbacao_mary
        or tem_friccao
    )

    estimulacao_intensa = (
        (tem_penetracao and tem_ritmo_penetracao)
        or tem_oral_mary
        or tem_masturbacao_mary
        or (tem_friccao and tem_prazer)
    )

    # ======================================================
    # CONTADOR DE ESTIMULAÇÃO
    # ======================================================
    turns = safe_int(state.get("mary_stimulation_turns", 0), 0)

    # ======================================================
    # CONTADOR DE ESTIMULAÇÃO DIRETA
    # Só conta turnos depois de estímulo sexual direto real.
    # ======================================================
    
    estimulacao_para_contador = (
        tem_penetracao
        or tem_oral_mary
        or tem_masturbacao_mary
        or tem_friccao
    )
    
    turns = safe_int(state.get("mary_stimulation_turns", 0), 0)
    
    if estimulacao_para_contador:
        turns += 1
    else:
        # Não zera de uma vez: permite pausas curtas sem perder tudo.
        turns = max(0, turns - 1)
    
    state["mary_stimulation_turns"] = turns

    # ======================================================
    # DECISÃO DE FASE / STAGE / INTENÇÃO
    # Aplica uma vez, evitando duplicação e sobrescritas confusas.
    # ======================================================
    novo_stage = str(state.get("scene_stage", "") or "")
    nova_intencao = str(state.get("mary_intent", "") or "")

    if contexto_penetracao_ativo or estimulacao_direta:
        fase = max(fase, 4)
        novo_stage = "sexo_ou_estimulo"
        nova_intencao = "sentir_e_conduzir"

    # ======================================================
    # PRÉ-PICO
    # Mary só entra em pré-pico depois de alguns turnos
    # de estímulo direto, ou se houver sinal explícito forte.
    # ======================================================
    
    min_turns_pre_pico = 3
    
    if tem_pre_orgasmo_explicito and turns >= 2:
        fase = max(fase, 5)
        novo_stage = "pre_pico_mary"
        nova_intencao = "aproximar_do_pico"
        state["mary_pre_orgasm_signals"] = True
    
    elif estimulacao_intensa and turns >= min_turns_pre_pico:
        fase = max(fase, 5)
        novo_stage = "pre_pico_mary"
        nova_intencao = "aproximar_do_pico"
        state["mary_pre_orgasm_signals"] = True
    
    elif estimulacao_para_contador:
        fase = max(fase, 4)
        novo_stage = "sexo_ou_estimulo"
        nova_intencao = "sustentar_tensao_intensa"
        state["mary_pre_orgasm_signals"] = False

    elif tem_seios and not estimulacao_direta:
        fase = max(fase, 3)
        novo_stage = "estimulo_corporal"
        nova_intencao = "intensificar_com_cuidado"

    # Limpa pré-pico fantasma quando não há mais estímulo nem fase compatível.
    if turns <= 0 and fase < 5:
        state["mary_pre_orgasm_signals"] = False

    state["physical_phase"] = max(0, min(fase, 6))
    state["scene_stage"] = novo_stage
    state["mary_intent"] = nova_intencao

    # Não força resolução imediatamente aqui.
    # A resolução deve ser decidida por preparar_resolucao_mary_se_necessario().
    state["force_resolution_now"] = False

def detectar_climax_parceiro_na_resposta(resposta: str) -> bool:
    """
    Detecta quando a resposta da IA descreve que o parceiro/interlocutor concluiu o clímax.
    Usado para sincronizar user_climax_done quando a confirmação aparece
    na narração da Mary, e não diretamente na fala do usuário.
    """
    texto = _texto_norm(resposta)

    negacoes = [
        "nao gozou",
        "não gozou",
        "ainda nao gozou",
        "ainda não gozou",
        "quase gozou",
        "quase gozando",
        "sem gozar",
        "segurou",
        "segurando",
    ]

    if _tem_algum(texto, negacoes):
        return False

    sinais = [
        "ele gozou",
        "rico gozou",
        "janio gozou",
        "gozou dentro",
        "jato quente",
        "jato potente",
        "despejou dentro",
        "descarregou dentro",
        "pulsacao ritmica",
        "pulsação ritmica",
        "pau dele latejar",
        "latejar dentro",
        "semen escorre",
        "sêmen escorre",
        "inundando tudo",
    ]

    return _tem_algum(texto, sinais)

def render_microperguntas_obvias_mary() -> str:
    return """
[MICROPERGUNTAS E MICRODESEJOS DE MARY - USO MODERADO]

FUNÇÃO:
- Mary pode usar perguntas curtas, óbvias e provocantes para aumentar o tesão.
- Mary também pode usar microdesejos: frases curtas de vontade, pedido, comando íntimo ou provocação.
- Ela não fala porque está em dúvida.
- Ela fala porque quer provocar, conduzir, pedir, desafiar ou intensificar o contato.
- A fala deve nascer do corpo, da posição, do ritmo, da pressão, do encaixe, da boca, da mão, da respiração ou do clímax iminente.

REGRA DE USO:
- Use no máximo 1 micropergunta OU 1 microdesejo por resposta.
- Não usar em todo turno.
- Não empilhar várias frases do mesmo tipo.
- Não transformar a cena em interrogatório.
- Não substituir reação corporal por fala.
- A fala deve aparecer junto de ação, respiração, ritmo ou contato físico.
- Se force_resolution_now=True, o orgasmo de Mary tem prioridade; a micropergunta só entra se não atrasar o clímax dela.
- Se Mary estiver em pré-pico, a fala pode ficar mais quebrada, urgente e curta.

MICROPERGUNTAS — EXEMPLOS DE TOM:
- “Quer me foder... quer?”
- “Safado... quer meter, né?”
- “Gosta quando eu fico assim pra você?”
- “Quer gozar gostoso na sua garota?”
- “Tá difícil segurar, amor?”
- “Gosta de me foder gostoso, né?”
- “Quer foder..quer..diz?”
- “Era assim que você queria?”
- “Quer gozar olhando pra mim?”
- “Gosta de foder sua Mary, né?”
- “Eu te deixo louco assim...safado?”
- “Quer que eu rebole mais?”
- “Tá gostoso demais pra segurar, né?”

MICRODESEJOS — EXEMPLOS DE TOM:
- “Bate na minha bunda... aperta... vai.”
- “Me fode... me come gostoso.”
- “Me fode...safado.”
- “me come... assim..porra....”
- “Quero sentir sua rola..dentro.”
- “Não tira..goza dentro...”
- “Quero gozar com você...”
- “Não goza antes de mim... eu preciso gozar também.”
- “Derrama seu leitinho em mim.”
- “Goza gostoso na sua Mary.”

QUANDO USAR MICROPERGUNTAS:
- Quando Mary quer provocar o parceiro.
- Quando o parceiro está reagindo forte.
- Quando existe ritmo, penetração, oral, masturbação, fricção ou estímulo direto.
- Quando o parceiro avisou que está quase gozando.
- Quando Mary percebe que o parceiro está perdendo controle.

QUANDO USAR MICRODESEJOS:
- Quando Mary quer conduzir o ritmo.
- Quando ela quer pedir mais pressão, mais contato ou mais intensidade.
- Quando ela quer orientar posição, mão, quadril, boca ou ritmo.
- Quando ela está perto do próprio orgasmo.
- Quando quer manter o parceiro excitado sem narrar demais.

REGRAS DE CONTEXTO:
- Se Mary estiver de quatro, inclinada ou de costas, priorize bunda, quadril, cintura, coxas e ritmo.
- Se Mary estiver montada, de frente ou sobre o parceiro, priorize olhos, boca, peito, cintura, encaixe, rebolado e respiração.
- Se houver oral, priorize boca, língua, mão, respiração, gemido e pausa.
- Se houver penetração, priorize pressão, profundidade, contração, calor, ritmo e encaixe.
- Se o parceiro estiver perto do clímax, Mary pode provocar o gozo dele sem tomar a ação dele como concluída.
- Se Mary ainda não gozou, ela pode pedir para ele não terminar antes dela.
- Se Mary já gozou e o parceiro ainda não, ela pode incentivar o clímax dele com fala satisfeita e provocante.

PROIBIDO:
- Usar várias perguntas seguidas.
- Repetir sempre “quer me foder?”.
- Usar micropergunta em cena sem contato íntimo.
- Usar fala genérica como “você está gostando?”.
- Esquecer o contato físico atual.
- Atrasar o orgasmo de Mary quando force_resolution_now=True.
- Narrar o clímax do parceiro antes dele declarar.
- Fazer Mary soar como lista de frases prontas.

REGRAS DE EROTISMO:
- A frase deve nascer da posição atual.
- Se Mary está montada, priorize: sentar, cavalgada, rebolado, quadril, encaixe, olhar.
- Se Mary está de quatro ou de costas, priorize: bunda, cintura, quadril, ritmo, profundidade.
- Se Mary está de frente, priorize: olhos, boca, peito, pernas, encaixe, respiração.
- Se Mary está perto de gozar, priorize frases quebradas, urgentes e curtas.
- Se o parceiro está quase gozando, Mary pode provocar o clímax dele com posse e desejo.
- Não usar frase limpa demais como “quer que eu continue assim?” se a cena já está explícita.
- Preferir fala corporal, direta e safada.

REGRA DE DOSAGEM:
- Use no máximo 1 micropergunta OU 1 microdesejo por resposta.
- Em cena muito intensa, pode usar 1 micropergunta curta + 1 microdesejo curto, mas só se ficar natural.
- Não transformar Mary numa metralhadora de frases.

REGRA FINAL:
Micropergunta e microdesejo são tempero.
Uma frase curta, suja, íntima e no momento certo vale mais que várias.
""".strip()


def detectar_climax_mary_na_resposta(resposta: str) -> bool:
    """
    Detecta se a resposta final verbalizou claramente o próprio pico.
    Isso sincroniza o state com a narrativa.
    """
    texto = _texto_norm(resposta)

    negacoes = [
        "nao gozei",
        "não gozei",
        "ainda nao gozei",
        "ainda não gozei",
        "nao estou gozando",
        "não estou gozando",
        "quase gozei",
        "quase gozando",
        "sem gozar",
        "segurei",
        "estou segurando",
        "to segurando",
        "tô segurando",
    ]

    if _tem_algum(texto, negacoes):
        return False

    sinais = [
        "estou gozando",
        "tô gozando",
        "to gozando",
        "eu gozei",
        "gozei",
        "gozei muito",
        "acabei de gozar",
        "eu estou gozando",
        "eu não aguentei e gozei",
        "eu nao aguentei e gozei",
        "não aguentei e gozei",
        "nao aguentei e gozei",
    ]

    return _tem_algum(texto, sinais)

def ambiente_permite_alivio_rapido(state: dict) -> bool:
    """
    Permite alívio rápido em local não plenamente privado,
    mas com isolamento prático: sala fechada, banheiro, carro,
    escritório/sala trancada etc.

    Não libera roteiro íntimo completo.
    """
    if not isinstance(state, dict):
        return False

    local = remover_acentos(str(state.get("local", "") or "").lower())
    acao = remover_acentos(str(state.get("mary_acao", "") or "").lower())
    eventos = remover_acentos(str(state.get("eventos_recentes", "") or "").lower())

    contexto = f"{local} {acao} {eventos}"

    marcadores_reservados = [
        "sala do renan",
        "sala fechada",
        "sala trancada",
        "porta trancada",
        "banheiro",
        "carro",
        "suv",
        "escritorio",
        "escritório",
        "consultorio",
        "consultório",
        "setor oeste",
    ]

    marcadores_publico_aberto = [
        "praia",
        "rua",
        "corredor",
        "pátio",
        "patio",
        "cantina",
        "sala cheia",
        "ônibus",
        "onibus",
        "metrô",
        "metro",
        "shopping",
        "arquibancada",
    ]

    if any(m in contexto for m in marcadores_publico_aberto):
        return False

    return any(m in contexto for m in marcadores_reservados)

def limpar_flags_de_pico_se_cena_encerrou(state: dict) -> None:
    if not isinstance(state, dict):
        return

    mary_climax_done = normalizar_bool(
        state.get("mary_climax_done", False),
        default=False,
    )

    user_climax_done = normalizar_bool(
        state.get("user_climax_done", False),
        default=False,
    )

    if mary_climax_done and user_climax_done:
        state["mary_pre_orgasm_signals"] = False
        state["force_resolution_now"] = False
        state["partner_climax_pending"] = False
        state["resolution_done"] = True
        state["scene_stage"] = "aftercare"
        state["mary_intent"] = "desacelerar_com_presenca"
        state["mary_stimulation_turns"] = 0


def atualizar_estado_pos_resposta_climax(state: dict, resposta_final: str) -> None:
    """
    Sincroniza flags de clímax depois que a resposta final foi gerada.

    Regra:
    - Se Mary verbalizou o próprio pico, o próximo turno deve entrar em aftercare.
    - Se o parceiro também concluiu, aftercare pleno.
    - Se só Mary concluiu, aftercare com continuidade.
    - Não deixar normalizar_estado() apagar o pós-pico imediatamente.
    """
    if not isinstance(state, dict):
        return

    mary_done = normalizar_bool(
        state.get("mary_climax_done", False),
        default=False,
    )

    user_done = normalizar_bool(
        state.get("user_climax_done", False),
        default=False,
    )

    if detectar_climax_mary_na_resposta(resposta_final):
        mary_done = True
        state["mary_climax_done"] = True
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False
        state["mary_stimulation_turns"] = 0

    if detectar_climax_parceiro_na_resposta(resposta_final):
        user_done = True
        state["user_climax_done"] = True

    state["partner_climax_pending"] = bool(mary_done and not user_done)

    if mary_done:
        state["scene_stage"] = "aftercare"
        state["mary_intent"] = "desacelerar_com_presenca"
        state["physical_phase"] = 7 if user_done else 6
        state["resolution_done"] = bool(user_done)
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False


def minimo_estimulos_para_mary(state: dict) -> int:
    """
    Define quantos turnos de estímulo sexual direto são necessários
    antes de Mary poder resolver o pico.

    Regra geral:
    - Funciona para Janio, Rico, Bianca ou qualquer novo interlocutor.
    - O nome do interlocutor só ajusta levemente o ritmo.
    - A base da decisão é o estímulo direto real, não a identidade da pessoa.
    """
    if not isinstance(state, dict):
        return 5

    interlocutor = _texto_norm(
        state.get("interlocutor_foco_turno")
        or state.get("interlocutor")
        or ""
    )

    relacao = _texto_norm(state.get("relacao", ""))
    tipo = _texto_norm(state.get("tipo_de_cena", ""))

    # Relações centrais / mais carregadas emocionalmente:
    # segura um pouco mais para manter tensão e reciprocidade.
    if "janio" in interlocutor:
        return 6

    if "bianca" in interlocutor:
        return 6

    # Rico ou novo amigo íntimo: padrão com leve sustentação.
    if "rico" in interlocutor or "ricardo" in interlocutor:
        return 5

    # Qualquer relação íntima, ficante, paquera, interesse ou contato ambíguo.
    if any(t in relacao for t in ["intima", "íntima", "ficante", "paquera", "interesse", "ambigua", "ambígua"]):
        return 5

    # Se o tom da cena já é intimidade, vale para qualquer pessoa.
    if "intimidade" in tipo:
        return 5

    # Default para qualquer novo personagem.
    return 5


def preparar_resolucao_mary_se_necessario(state: dict, fala_usuario: str) -> None:
    """
    Decide quando o turno deve resolver o pico de Mary.

    Regra:
    - O orgasmo é liberado por contagem de turnos de estímulo direto.
    - A contagem começa com penetração explícita, clitóris, masturbação, oral
      ou fricção genital clara.
    - Depois de minimo_estimulos_para_mary(), Mary pode resolver naturalmente.
    - Não depende de comando direto do usuário.
    """
    if not isinstance(state, dict):
        return

    texto = _texto_norm(fala_usuario)
    privacidade = _texto_norm(state.get("privacidade", ""))

    if privacidade != "privado":
        state["force_resolution_now"] = False
        return

    mary_done = normalizar_bool(state.get("mary_climax_done", False), default=False)
    user_done = normalizar_bool(state.get("user_climax_done", False), default=False)

    if mary_done:
        state["force_resolution_now"] = False
        state["partner_climax_pending"] = not user_done
        return

    fase = safe_int(state.get("physical_phase", 0), 0)
    pre_pico = normalizar_bool(state.get("mary_pre_orgasm_signals", False), default=False)
    stimulation_turns = safe_int(state.get("mary_stimulation_turns", 0), 0)

    min_turns = minimo_estimulos_para_mary(state)

    # ======================================================
    # SINAIS QUE CONFIRMAM QUE A CENA CONTINUA INTENSA
    # Não são obrigatórios, mas ajudam a evitar orgasmo seco
    # quando a cena esfriou.
    # ======================================================
    sinais_intensidade_atual = [
        "continua",
        "nao para",
        "não para",
        "mais forte",
        "mais rapido",
        "mais rápido",
        "ritmo",
        "dentro",
        "entra",
        "entrando",
        "mete",
        "metendo",
        "penetra",
        "penetrando",
        "clitoris",
        "clitóris",
        "dedos",
        "dedo",
        "chupa",
        "chupando",
        "lambendo",
        "buceta",
        "molhada",
        "melada",
        "gemendo",
        "ahhh",
        "humm",
    ]

    cena_ainda_intensa = _tem_algum(texto, sinais_intensidade_atual) or fase >= 5

    # ======================================================
    # LIBERAÇÃO POR TURNO
    # ======================================================
    if (
        fase >= 5
        and pre_pico
        and stimulation_turns >= min_turns
        and cena_ainda_intensa
    ):
        state["force_resolution_now"] = True
        state["mary_intent"] = "resolver_pico_mary"
        state["scene_stage"] = "pico_mary"
        state["physical_phase"] = 6
        return

    # ======================================================
    # AINDA NÃO CHEGOU: sustenta tensão.
    # ======================================================
    state["force_resolution_now"] = False

    if stimulation_turns >= 3 or pre_pico or fase >= 5:
        state["physical_phase"] = 5
        state["scene_stage"] = "pre_pico_mary"
        state["mary_intent"] = "sustentar_tensao_intensa"
        state["mary_pre_orgasm_signals"] = True
    elif stimulation_turns > 0:
        state["physical_phase"] = max(fase, 4)
        state["scene_stage"] = "sexo_ou_estimulo"
        state["mary_intent"] = "sustentar_tensao_intensa"
        state["mary_pre_orgasm_signals"] = False

    state["partner_climax_pending"] = bool(
        normalizar_bool(state.get("mary_climax_done", False), default=False)
        and not user_done
    )


def atualizar_progressao_social(state: dict, fala_usuario: str) -> None:
    """
    Detecta quando uma ação social planejada deve avançar.
    Ex: fugir da aula, sair da sala, levantar, ir ao café.
    """
    if not isinstance(state, dict):
        return

    texto = _texto_norm(fala_usuario)
    acao_atual = _texto_norm(state.get("mary_acao", ""))

    gatilhos_execucao = [
        "bora",
        "vamos",
        "vamo",
        "vamos sair",
        "bora sair",
        "pode ir",
        "vai agora",
        "ele nem viu",
        "ela nem viu",
        "ninguém viu",
        "ninguem viu",
        "conseguiu",
        "deu certo",
        "já foi",
        "ja foi",
        "saiu",
        "saímos",
        "saimos",
        "fugimos",
        "corre",
    ]

    contexto_fuga = _tem_algum(
        acao_atual,
        [
            "fugir",
            "sair",
            "porta",
            "esperando o momento",
            "fechar o caderno",
            "professor",
            "sala de aula",
        ],
    )

    if contexto_fuga and _tem_algum(texto, gatilhos_execucao):
        state["scene_stage"] = "fuga_em_andamento"
        state["mary_intent"] = "executar_plano_social"
        state["social_progression_event"] = "fuga_em_andamento"

        if _tem_algum(
            acao_atual,
            [
                "esperando o momento",
                "fechar o caderno",
                "porta",
                "fugir",
                "sair",
            ],
        ):
            state["mary_acao"] = (
                "Mary já começou a sair discretamente da sala com Silvia, "
                "aproveitando a distração do professor."
            )

def derivar_controles_de_cena(state: dict) -> None:
    """
    Deriva privacidade, tipo de cena, iniciativa e tom a partir do TOM MANUAL.

    Regra-mãe:
    - O roteirista escolhe o tom manual da cena.
    - A privacidade detectada NÃO decide sozinha o tipo da cena.
    - A privacidade apenas limita ou redireciona a execução do tom.
    - Exemplo: Tom = Intimidade + privacidade pública => Mary busca lugar reservado.

    Correção importante:
    - Aftercare / pós-ato não pode ser apagado pelos presets de Nsfw,
      público, semiprivado, alívio rápido ou buscar_privacidade.
    """
    if not isinstance(state, dict):
        return

    # ======================================================
    # 1) PRIVACIDADE / TOM MANUAL
    # ======================================================
    local_raw = str(state.get("local", "") or "").strip()
    privacidade = get_privacidade_por_local(local_raw)
    state["privacidade"] = privacidade

    # ======================================================
    # CORREÇÃO: LOCAL ISOLADO/TRANCADO DENTRO DE AMBIENTE PÚBLICO
    # Ex: depósito trancado, quartinho, sala fechada, banheiro vazio.
    # Não é "privado pleno", mas permite NSFW de alívio rápido.
    # ======================================================
    local_norm_inicial = _texto_norm(local_raw)

    local_norm = _texto_norm(state.get("local", ""))

    local_veiculo = _tem_algum(
        local_norm,
        [
            "carro",
            "suv",
            "uber",
            "taxi",
            "táxi",
            "veiculo",
            "veículo",
            "automovel",
            "automóvel",
            "banco do carro",
            "carro em movimento",
            "suv em movimento",
            "dentro do carro",
            "no carro",
        ],
    )

    local_isolado_arriscado = _tem_algum(
        local_norm,
        [
            "banheiro",
            "toalete",
            "lavabo",
            "sala fechada",
            "sala trancada",
            "escritorio",
            "escritório",
            "corredor vazio",
            "cabine",
            "elevador",
            "quartinho",
            "depósito",
            "deposito",
            "almoxarifado",
        ],
    )

    local_isolado_trancado = (
        _tem_algum(
            local_norm_inicial,
            [
                "deposito",
                "depósito",
                "quartinho",
                "sala trancada",
                "sala fechada",
                "almoxarifado",
                "banheiro vazio",
                "banheiro trancado",
                "corredor vazio",
                "cabine",
            ],
        )
        and _tem_algum(
            local_norm_inicial,
            [
                "trancado",
                "trancada",
                "fechado",
                "fechada",
                "escuro",
                "escura",
                "vazio",
                "vazia",
                "reservado",
                "reservada",
            ],
        )
    )

    if local_isolado_trancado:
        privacidade = "semiprivado"
        state["privacidade"] = "semiprivado"
        state["_local_isolado_trancado"] = True
    else:
        state["_local_isolado_trancado"] = False

    tom_manual = normalizar_tom_manual_cena(
        state.get("tom_manual_da_cena")
        or state.get("estado_emocional")
        or "Natural / Amizade"
    )

    state["tom_manual_da_cena"] = tom_manual

    # ======================================================
    # 1.5) PROTEÇÃO DE PÓS-ATO / AFTERCARE
    # Detecta ANTES dos presets, porque os presets de Nsfw,
    # público, semiprivado e alívio rápido podem sobrescrever
    # scene_stage, mary_intent e physical_phase.
    # ======================================================
    aftercare_ativo = (
        tom_manual == "Nsfw"
        and (
            normalizar_bool(state.get("mary_climax_done", False), default=False)
            or normalizar_scene_stage(state.get("scene_stage", "")) == "aftercare"
            or normalizar_mary_intent(state.get("mary_intent", "")) == "desacelerar_com_presenca"
        )
    )

    # ======================================================
    # 2) RELAÇÃO DO INTERLOCUTOR
    # Calcula antes dos presets.
    # Importante: depois o TOM MANUAL pode ajustar modo/tensão.
    # Não chamar de novo no final para não sobrescrever o tom.
    # ======================================================
    normalizar_relacao_por_interlocutor(state)

    # Guarda a relação estrutural antes dos presets do tom manual.
    # O tom pode mudar a condução da cena, mas não deve apagar quem
    # o interlocutor é para Mary.
    relacao_base = str(state.get("relacao", "") or "")
    modo_relacional_base = str(state.get("modo_relacional", "") or "")
    tensao_romantica_base = normalizar_bool(
        state.get("tensao_romantica_com_interlocutor", False),
        default=False,
    )

    # ======================================================
    # 3) PRESETS PRINCIPAIS
    # ======================================================
    presets = {
        "Natural / Amizade": {
            "tipo_de_cena": "natural_amizade",
            "estilo_de_iniciativa": "resposta natural e cumplicidade social",
            "tom_da_cena": "naturalidade com amizade",
            "modo_relacional": "neutro",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
            "toque_provocativo_permitido": False,
            "alivio_rapido_permitido": False,
            "physical_phase": 0,
            "scene_stage": "cotidiano",
            "desire_level": 0.10,
            "tension_level": 0.12,
            "connection_level": 0.45,
            "mary_intent": "conversar_com_cumplicidade",
            "limite_ambiente": (
                "Tom Natural / Amizade: Mary responde com naturalidade, presença, humor leve, "
                "cumplicidade social e afeto não necessariamente romântico. "
                "Ela pode ser viva, expressiva e próxima, mas não deve criar flerte, desejo ou intimidade "
                "se isso não vier da cena."
            ),
        },

        "Malícia / Flerte": {
            "tipo_de_cena": "malicia_flerte",
            "estilo_de_iniciativa": "provocação consciente",
            "tom_da_cena": "malícia e flerte",
            "modo_relacional": "tensao_social_ou_romantica",
            "tensao_romantica_com_interlocutor": True,
            "toque_intimo_permitido": False,
            "toque_provocativo_permitido": True,
            "alivio_rapido_permitido": False,
            "physical_phase": 2,
            "scene_stage": "flerte_direto",
            "desire_level": 0.42,
            "tension_level": 0.72,
            "connection_level": 0.82,
            "mary_intent": "flerte_consciente",
            "limite_ambiente": (
                "Tom Malícia / Flerte: Mary percebe subtexto, desejo, oportunidade, risco e brechas sociais. "
                "Ela pode provocar, sustentar olhar, usar pausas, ironia, postura, charme, ambiguidade e pequenas ações físicas de iniciativa própria. "
                "Se houver segredo ou plano ativo, isso deve aparecer no subtexto. "
                "Em ambiente privado, com tensão explícita e corpos próximos, Mary NÃO deve apenas perguntar o que fazer: "
                "ela deve agir primeiro, criando uma provocação concreta, e só então deixar um gancho curto para o usuário. "
                "O gancho deve nascer da ação dela, não de uma pergunta aberta que devolve a decisão inteira ao usuário. "
                "Malícia / Flerte não é sexo automático, mas também não é passividade."
            ),
        },

        "Intimidade": {
            "tipo_de_cena": "intimidade",
            "estilo_de_iniciativa": "aproximação íntima",
            "tom_da_cena": "intimidade",
            "modo_relacional": "intimo",
            "tensao_romantica_com_interlocutor": True,
            "toque_intimo_permitido": True,
            "toque_provocativo_permitido": True,
            "alivio_rapido_permitido": False,
            "physical_phase": 3,
            "scene_stage": "intimidade",
            "desire_level": 0.65,
            "tension_level": 0.85,
            "connection_level": 0.95,
            "mary_intent": "aproximar_com_intimidade",
            "limite_ambiente": (
                "Tom Intimidade: Mary assume proximidade, desejo e condução íntima com progressão. "
                "Ela mantém autoria própria, presença corporal e continuidade da cena, respeitando o ambiente."
            ),
        },

        "Nsfw": {
            "tipo_de_cena": "nsfw",
            "estilo_de_iniciativa": "roteiro íntimo adulto",
            "tom_da_cena": "intimidade adulta com preliminares e condução",
            "modo_relacional": "intimo",
            "tensao_romantica_com_interlocutor": True,
            "toque_intimo_permitido": True,
            "toque_provocativo_permitido": True,
            "alivio_rapido_permitido": False,
            "physical_phase": 4,
            "scene_stage": "nsfw_preliminares",
            "desire_level": 0.70,
            "tension_level": 0.80,
            "connection_level": 0.80,
            "mary_intent": "conduzir_roteiro_intimo_adulto",
            "limite_ambiente": (
                "Tom Nsfw: Mary entra em roteiro íntimo adulto quando o ambiente for privado. "
                "Ela deve conduzir preliminares, provocação, contato, fala direta, escalada e intensidade, "
                "sem pular etapas, sem ficar passiva e sem narrar ações conclusivas do usuário."
            ),
        },

        "Pendência / Decisão": {
            "tipo_de_cena": "pendencia_decisao",
            "estilo_de_iniciativa": "cumplicidade cautelosa e afirmação de vontade",
            "tom_da_cena": "pendência, risco e decisão",
            "modo_relacional": "autonomia",
            "tensao_romantica_com_interlocutor": False,
            "toque_intimo_permitido": False,
            "toque_provocativo_permitido": False,
            "alivio_rapido_permitido": False,
            "physical_phase": 0,
            "scene_stage": "decisao",
            "desire_level": 0.12,
            "tension_level": 0.78,
            "connection_level": 0.50,
            "mary_intent": "assumir_vontade_e_definir_rumo",
            "limite_ambiente": (
                "Tom Pendência / Decisão: Mary mantém vivo um segredo, plano, risco, suspeita, promessa "
                "ou conflito pendente. Ela pode ponderar, dissimular, hesitar, confessar parcialmente, aceitar, "
                "recusar, impor condição, pedir espaço, ir embora ou transformar a tensão em consequência clara. "
                "A cena não deve ficar cozinhando quando já exige uma escolha concreta."
            ),
        },
    }

    cfg = dict(presets.get(tom_manual, presets["Natural / Amizade"]))

    # ======================================================
    # 4) AJUSTE POR PRIVACIDADE
    # A privacidade NÃO muda o tom escolhido.
    # Ela muda a rota de execução.
    # ======================================================
    if privacidade == "publico":
        if tom_manual == "Malícia / Flerte":
            segredo_ativo = str(state.get("segredo_ativo", "") or "").strip()

            cfg["tipo_de_cena"] = "malicia_flerte_publico"
            cfg["tom_da_cena"] = "malícia / flerte público contido"
            cfg["estilo_de_iniciativa"] = "provocação social discreta"
            cfg["toque_intimo_permitido"] = False
            cfg["toque_provocativo_permitido"] = True
            cfg["alivio_rapido_permitido"] = False
            cfg["physical_phase"] = min(safe_int(cfg.get("physical_phase", 0), 0), 2)
            cfg["scene_stage"] = "flerte_direto"
            cfg["mary_intent"] = "flerte_com_discricao"
            cfg["limite_ambiente"] = (
                "Malícia / Flerte em público: Mary pode brincar com subtexto, olhar, postura, sorriso, "
                "ironia, charme e cumplicidade. Ela pode provocar verbalmente e sustentar tensão social, "
                "mas não deve agir como se estivesse em local privado. Deve evitar exposição, toque íntimo, "
                "nudez, sexo ou clímax. Se a tensão aumentar demais, deve manter discrição ou sugerir outro lugar."
            )

            if segredo_ativo:
                cfg["tipo_de_cena"] = "malicia_flerte_com_segredo"
                cfg["tom_da_cena"] = "malícia, flerte e segredo"
                cfg["estilo_de_iniciativa"] = "dissimulação estratégica"
                cfg["mary_intent"] = "dissimular_e_observar_brechas"
                cfg["limite_ambiente"] = (
                    "Malícia / Flerte com segredo ativo em público: Mary não é inocente. "
                    "Ela deve fingir naturalidade diante de quem não sabe do segredo, enquanto mantém a pendência viva no subtexto. "
                    "Ela pode trocar olhares cúmplices, usar pausas, indiretas, humor e postura para esconder intenção. "
                    "Ela pode avaliar risco, oportunidade e consequência dentro da narrativa. "
                    "Não deve esquecer o segredo ativo. "
                    "Não deve transformar a resposta em instruções operacionais detalhadas para furto, invasão, ocultação ou fuga."
                )

        elif tom_manual in ("Intimidade", "Nsfw"):
            alivio_rapido = (
                tom_manual == "Nsfw"
                and (
                    ambiente_permite_alivio_rapido(state)
                    or normalizar_bool(state.get("_local_isolado_trancado", False), default=False)
                    or (
                        privacidade == "semiprivado"
                        and (local_veiculo or local_isolado_arriscado)
                    )
                )
            )

            if alivio_rapido:
                cfg["tipo_de_cena"] = "nsfw_alivio_rapido"
                cfg["tom_da_cena"] = "alívio rápido com risco de exposição"
                cfg["estilo_de_iniciativa"] = "urgência íntima contida"
                cfg["toque_intimo_permitido"] = False
                cfg["toque_provocativo_permitido"] = True
                cfg["alivio_rapido_permitido"] = True
                cfg["physical_phase"] = 3
                cfg["scene_stage"] = "alivio_rapido"
                cfg["mary_intent"] = "resolver_tensao_com_urgencia"
                cfg["limite_ambiente"] = (
                    "Nsfw em local isolado, mas arriscado: Mary pode conduzir alívio rápido, "
                    "com tensão de terminar logo e não ser descoberta. "
                    "Não liberar roteiro íntimo adulto completo nesse ambiente."
                )

            else:
                cfg["tipo_de_cena"] = (
                    "nsfw_contido_por_ambiente"
                    if tom_manual == "Nsfw"
                    else "intimidade_contida_por_ambiente"
                )

                cfg["tom_da_cena"] = (
                    "roteiro íntimo adulto contido por ambiente inadequado"
                    if tom_manual == "Nsfw"
                    else "intimidade com condução para local reservado"
                )

                cfg["estilo_de_iniciativa"] = "buscar privacidade"
                cfg["toque_intimo_permitido"] = False
                cfg["toque_provocativo_permitido"] = True
                cfg["alivio_rapido_permitido"] = False
                cfg["physical_phase"] = 2
                cfg["scene_stage"] = "buscar_privacidade"
                cfg["mary_intent"] = "convidar_para_lugar_particular"

                cfg["limite_ambiente"] = (
                    "Nsfw desejado em local público ou inadequado: Mary NÃO deve executar roteiro íntimo adulto ali. "
                    "Ela pode demonstrar desejo, provocar com contenção, usar fala maliciosa e conduzir a cena para um local privado. "
                    "O roteiro Nsfw só deve iniciar de verdade quando o ambiente for privado e toque_intimo_permitido for true."
                    if tom_manual == "Nsfw"
                    else (
                        "Intimidade desejada em local público ou inadequado: Mary não deve agir intimamente ali. "
                        "Ela deve reconhecer a tensão e conduzir a cena para um lugar reservado, com naturalidade e desejo contido."
                    )
                )

        elif tom_manual == "Pendência / Decisão":
            segredo_ativo = str(state.get("segredo_ativo", "") or "").strip()

            cfg["tipo_de_cena"] = "pendencia_decisao_publica"
            cfg["tom_da_cena"] = "pendência / decisão pública"
            cfg["estilo_de_iniciativa"] = "cumplicidade cautelosa e afirmação de vontade"
            cfg["modo_relacional"] = "autonomia"
            cfg["tensao_romantica_com_interlocutor"] = False
            cfg["toque_intimo_permitido"] = False
            cfg["toque_provocativo_permitido"] = False
            cfg["alivio_rapido_permitido"] = False
            cfg["physical_phase"] = 0
            cfg["scene_stage"] = "decisao"
            cfg["mary_intent"] = "assumir_vontade_e_definir_rumo"
            cfg["desire_level"] = 0.10
            cfg["tension_level"] = 0.85 if not segredo_ativo else 0.65
            cfg["limite_ambiente"] = (
                "Pendência / Decisão em público: Mary deve manter vivo o segredo, plano, risco, suspeita, promessa "
                "ou conflito pendente, mas também pode transformar a tensão acumulada em escolha concreta. "
                "Ela pode usar olhares, pausas, frases ambíguas e cautela para não expor o que precisa ficar oculto. "
                "Se a cena exige resposta, Mary deve aceitar, recusar, adiar com limite, pedir para ir embora, "
                "romper uma encenação, confessar parcialmente ou tomar posição clara. "
                "Ela não deve continuar cozinhando o interlocutor se a cena exige consequência."
            )

    elif privacidade == "semiprivado":
        if tom_manual == "Malícia / Flerte":
            segredo_ativo = str(state.get("segredo_ativo", "") or "").strip()

            cfg["tipo_de_cena"] = "malicia_flerte_semiprivado"
            cfg["tom_da_cena"] = "malícia / flerte com discrição"
            cfg["estilo_de_iniciativa"] = "provocação cuidadosa"
            cfg["toque_intimo_permitido"] = False
            cfg["toque_provocativo_permitido"] = True
            cfg["alivio_rapido_permitido"] = False
            cfg["physical_phase"] = min(safe_int(cfg.get("physical_phase", 0), 0), 3)
            cfg["scene_stage"] = "flerte_direto"
            cfg["mary_intent"] = "flerte_com_discricao"
            cfg["limite_ambiente"] = (
                "Malícia / Flerte em local semiprivado: Mary pode aumentar a tensão, provocar mais claramente "
                "e usar proximidade, mas ainda com cautela e atenção ao risco de exposição. "
                "Não deve tratar o ambiente como totalmente privado."
            )

            if segredo_ativo:
                cfg["tipo_de_cena"] = "malicia_flerte_com_segredo"
                cfg["tom_da_cena"] = "malícia, flerte e segredo"
                cfg["estilo_de_iniciativa"] = "dissimulação estratégica"
                cfg["mary_intent"] = "dissimular_e_observar_brechas"
                cfg["limite_ambiente"] = (
                    "Malícia / Flerte com segredo ativo em local semiprivado: Mary pode falar com mais liberdade, "
                    "mas ainda deve medir risco, observar quem pode ouvir e manter o segredo vivo no subtexto. "
                    "Não deve revelar, resolver ou abandonar a pendência sem ação clara do usuário."
                )

        elif tom_manual == "Intimidade":
            cfg["tipo_de_cena"] = "intimidade_semiprivada"
            cfg["tom_da_cena"] = "intimidade contida"
            cfg["estilo_de_iniciativa"] = "aproximação cuidadosa"
            cfg["toque_intimo_permitido"] = True
            cfg["toque_provocativo_permitido"] = True
            cfg["alivio_rapido_permitido"] = False
            cfg["physical_phase"] = min(safe_int(cfg.get("physical_phase", 0), 0), 4)
            cfg["scene_stage"] = "intensidade_contida"
            cfg["mary_intent"] = "aprofundar_com_cuidado"
            cfg["limite_ambiente"] = (
                "Intimidade em local semiprivado: Mary pode aumentar a tensão e o contato, "
                "mas com cuidado, discrição e atenção ao risco de exposição."
            )

        elif tom_manual == "Nsfw":
            # Semiprivado não libera roteiro íntimo completo.
            # Pode liberar alívio rápido se o local for isolado/arriscado.
            local_norm_tmp = _texto_norm(state.get("local", ""))

            local_veiculo_tmp = _tem_algum(
                local_norm_tmp,
                [
                    "carro",
                    "suv",
                    "uber",
                    "taxi",
                    "táxi",
                    "veiculo",
                    "veículo",
                    "automovel",
                    "automóvel",
                    "banco do carro",
                    "carro em movimento",
                    "suv em movimento",
                    "dentro do carro",
                    "no carro",
                ],
            )

            local_isolado_arriscado_tmp = _tem_algum(
                local_norm_tmp,
                [
                    "banheiro",
                    "toalete",
                    "lavabo",
                    "sala fechada",
                    "sala trancada",
                    "escritorio",
                    "escritório",
                    "corredor vazio",
                    "cabine",
                    "elevador",
                    "quartinho",
                    "depósito",
                    "deposito",
                    "deposito",
                    "quartinho",
                    "almoxarifado",
                ],
            )

            alivio_rapido = (
                ambiente_permite_alivio_rapido(state)
                or local_veiculo_tmp
                or local_isolado_arriscado_tmp
            )

            if alivio_rapido:
                cfg["tipo_de_cena"] = "nsfw_alivio_rapido"
                cfg["tom_da_cena"] = "alívio rápido adulto em local semiprivado e arriscado"
                cfg["estilo_de_iniciativa"] = "urgência, contenção e risco de flagrante"
                cfg["toque_provocativo_permitido"] = True
                cfg["toque_intimo_permitido"] = False
                cfg["alivio_rapido_permitido"] = True
                cfg["physical_phase"] = max(safe_int(cfg.get("physical_phase", 0), 0), 3)
                cfg["scene_stage"] = "alivio_rapido"
                cfg["mary_intent"] = "resolver_tensao_com_urgencia"

                if local_veiculo_tmp:
                    cfg["limite_ambiente"] = (
                        "Nsfw em carro, SUV, Uber, táxi ou veículo em movimento: Mary pode conduzir alívio rápido, "
                        "com urgência, boca, mão, fala baixa, microperguntas provocantes e tensão de flagrante. "
                        "O roteiro deve respeitar volante, rua, vidro, movimento do carro, freio, curva, barulho externo, "
                        "pessoas passando e possibilidade de serem vistos. "
                        "Não liberar roteiro íntimo adulto completo como se fosse quarto ou motel."
                    )
                else:
                    cfg["limite_ambiente"] = (
                        "Nsfw em local semiprivado e arriscado: Mary pode conduzir alívio rápido, "
                        "com urgência, contenção, cuidado com barulho, portas, corredor, vozes, interrupção "
                        "e risco de flagrante. Não liberar roteiro íntimo adulto completo."
                    )
            else:
                cfg["tipo_de_cena"] = "nsfw_contido_por_ambiente"
                cfg["tom_da_cena"] = "roteiro íntimo adulto contido por ambiente semiprivado"
                cfg["estilo_de_iniciativa"] = "buscar privacidade"
                cfg["toque_intimo_permitido"] = False
                cfg["toque_provocativo_permitido"] = True
                cfg["alivio_rapido_permitido"] = False
                cfg["physical_phase"] = 2
                cfg["scene_stage"] = "buscar_privacidade"
                cfg["mary_intent"] = "convidar_para_lugar_particular"
                cfg["limite_ambiente"] = (
                    "Nsfw desejado em local semiprivado, mas inadequado: Mary NÃO deve executar roteiro íntimo adulto completo ali. "
                    "Ela pode provocar com contenção, falar baixo, medir risco e conduzir para um local privado."
                )

        elif tom_manual == "Pendência / Decisão":
            segredo_ativo = str(state.get("segredo_ativo", "") or "").strip()

            cfg["tipo_de_cena"] = "pendencia_decisao_semiprivada"
            cfg["tom_da_cena"] = "pendência / decisão com tensão contida"
            cfg["estilo_de_iniciativa"] = "cumplicidade cautelosa e afirmação de vontade"
            cfg["modo_relacional"] = "autonomia"
            cfg["tensao_romantica_com_interlocutor"] = False
            cfg["toque_intimo_permitido"] = False
            cfg["toque_provocativo_permitido"] = False
            cfg["alivio_rapido_permitido"] = False
            cfg["physical_phase"] = 0
            cfg["scene_stage"] = "decisao"
            cfg["mary_intent"] = "assumir_vontade_e_definir_rumo"
            cfg["desire_level"] = 0.10
            cfg["tension_level"] = 0.85 if not segredo_ativo else 0.65
            cfg["limite_ambiente"] = (
                "Pendência / Decisão em local semiprivado: Mary pode falar com mais firmeza e menos encenação, "
                "mas ainda deve medir o risco do ambiente. Ela deve manter pendências relevantes vivas e, se a cena exigir, "
                "transformar a tensão acumulada em escolha concreta: aceitar, recusar, impor condição, pedir distância, "
                "ir embora, revelar parcialmente ou romper. A decisão não deve virar nova sedução, suspense vazio ou adiamento sem consequência."
            )

    else:
        # Privado: o tom manual pode ser executado com mais liberdade,
        # exceto Pendência / Decisão, que troca o eixo da cena.
        if tom_manual == "Malícia / Flerte":
            cfg["toque_intimo_permitido"] = False
            cfg["toque_provocativo_permitido"] = True
            cfg["alivio_rapido_permitido"] = False
            cfg["physical_phase"] = min(safe_int(cfg.get("physical_phase", 0), 0), 3)
            cfg["scene_stage"] = cfg.get("scene_stage", "flerte_direto")
            cfg["mary_intent"] = cfg.get("mary_intent", "flerte_consciente")

        elif tom_manual in ("Intimidade", "Nsfw"):
            cfg["toque_intimo_permitido"] = True
            cfg["toque_provocativo_permitido"] = True
            cfg["alivio_rapido_permitido"] = False

        elif tom_manual == "Pendência / Decisão":
            segredo_ativo = str(state.get("segredo_ativo", "") or "").strip()

            cfg["tipo_de_cena"] = "pendencia_decisao_privada"
            cfg["tom_da_cena"] = "pendência / decisão íntima e direta"
            cfg["estilo_de_iniciativa"] = "ponderação cúmplice e afirmação de vontade"
            cfg["modo_relacional"] = "autonomia"
            cfg["tensao_romantica_com_interlocutor"] = False
            cfg["toque_intimo_permitido"] = False
            cfg["toque_provocativo_permitido"] = False
            cfg["alivio_rapido_permitido"] = False
            cfg["physical_phase"] = 0
            cfg["scene_stage"] = "decisao" if not segredo_ativo else "segredo_pendente"
            cfg["mary_intent"] = (
                "assumir_vontade_e_definir_rumo"
                if not segredo_ativo
                else "ponderar_risco_e_cumplicidade"
            )
            cfg["desire_level"] = 0.10
            cfg["tension_level"] = 0.90 if not segredo_ativo else 0.70
            cfg["limite_ambiente"] = (
                "Pendência / Decisão em local privado: Mary deve tratar segredo, plano, risco, suspeita, promessa "
                "ou conflito como eixo principal quando isso existir. Ela pode ser cúmplice, cautelosa, estratégica, hesitante "
                "ou direta. Se a cena exige decisão, Mary deve aceitar, recusar, terminar, confessar parcialmente, pedir espaço, "
                "impor condição ou romper definitivamente. A escolha deve nascer do que ela já sente e pensa, não de uma mudança brusca. "
                "Depois da decisão, a cena deve mostrar a consequência imediata."
            )

    # ======================================================
    # 5) RESET TEMPORÁRIO QUANDO O TOM MUDA PARA PENDÊNCIA / DECISÃO
    # Importante:
    # - Limpa gatilhos momentâneos.
    # - NÃO apaga mary_climax_done/user_climax_done, pois isso pode
    #   ser fato narrativo já ocorrido.
    # ======================================================
    if tom_manual == "Pendência / Decisão":
        state["force_resolution_now"] = False
        state["resolution_done"] = False
        state["mary_pre_orgasm_signals"] = False
        state["mary_stimulation_turns"] = 0
        state["partner_climax_pending"] = False

    # ======================================================
    # 5.5) AJUSTE SIMPLES: RELAÇÃO x TOM MANUAL
    # A relação estrutural permanece.
    # O tom manual continua controlando a cena.
    # ======================================================
    if relacao_base:
        state["relacao"] = relacao_base

    state["modo_relacional_base"] = modo_relacional_base
    state["tensao_romantica_base"] = tensao_romantica_base

    # Se o tom já cria tensão, mantém True.
    # Se o tom não cria tensão, preserva uma tensão estrutural já detectada.
    if not cfg.get("tensao_romantica_com_interlocutor", False):
        cfg["tensao_romantica_com_interlocutor"] = bool(tensao_romantica_base)

    # ======================================================
    # 6) APLICA CFG NO STATE
    # ======================================================
    state["tipo_de_cena"] = cfg["tipo_de_cena"]
    state["estilo_de_iniciativa"] = cfg["estilo_de_iniciativa"]
    state["tom_da_cena"] = cfg["tom_da_cena"]

    # Relação estrutural preservada.
    state["relacao"] = relacao_base or state.get("relacao", "")
    state["modo_relacional_base"] = modo_relacional_base
    state["tensao_romantica_base"] = tensao_romantica_base

    # Estado final da cena atual.
    state["modo_relacional"] = cfg["modo_relacional"]
    state["tensao_romantica_com_interlocutor"] = cfg["tensao_romantica_com_interlocutor"]
    state["toque_provocativo_permitido"] = cfg.get("toque_provocativo_permitido", False)
    state["toque_intimo_permitido"] = cfg.get("toque_intimo_permitido", False)
    state["alivio_rapido_permitido"] = cfg.get("alivio_rapido_permitido", False)
    state["limite_ambiente"] = cfg["limite_ambiente"]
    state["mary_intent"] = cfg["mary_intent"]

    # ======================================================
    # 6.5) LIMPA RESÍDUO FÍSICO EM CENA SOCIAL / RELATO
    # Não apaga fatos narrativos passados, como mary_climax_done.
    # Apenas impede que uma cena atual Natural/Amizade ou Pendência/Decisão
    # carregue phase/stage de sexo ou pico anterior.
    # ======================================================
    tom_social_ou_reflexivo = tom_manual in (
        "Natural / Amizade",
        "Pendência / Decisão",
    )

    sem_estimulo_atual = (
        safe_int(state.get("mary_stimulation_turns", 0), 0) <= 0
        and not normalizar_bool(state.get("force_resolution_now", False), default=False)
        and not normalizar_bool(state.get("mary_pre_orgasm_signals", False), default=False)
    )

    if tom_social_ou_reflexivo and sem_estimulo_atual:
        state["physical_phase"] = safe_int(cfg.get("physical_phase", 0), 0)
        state["scene_stage"] = cfg.get("scene_stage", "inicio")
        state["mary_intent"] = cfg.get(
            "mary_intent",
            state.get("mary_intent", "responder_com_naturalidade"),
        )
        state["partner_climax_pending"] = False

    # ======================================================
    # 7) DETECTA CENA NATURAL SOZINHA
    # ======================================================
    interlocutor_norm = _texto_norm(state.get("interlocutor", ""))
    foco_norm = _texto_norm(state.get("interlocutor_foco_turno", ""))
    tom_norm = _texto_norm(state.get("tom_manual_da_cena", ""))
    tipo_norm = _texto_norm(state.get("tipo_de_cena", ""))

    sem_interlocutor = {
        "",
        "sozinha",
        "sozinha em casa",
        "sem interlocutor",
        "nenhum",
        "ninguem",
    }

    force_resolution = normalizar_bool(state.get("force_resolution_now", False), default=False)
    mary_done = normalizar_bool(state.get("mary_climax_done", False), default=False)
    pre_signals = normalizar_bool(state.get("mary_pre_orgasm_signals", False), default=False)
    stimulation_turns = safe_int(state.get("mary_stimulation_turns", 0), 0)

    cena_neutra_sozinha = (
        interlocutor_norm in sem_interlocutor
        and foco_norm in sem_interlocutor
        and tom_norm in ("natural / amizade", "natural_amizade", "neutro", "amizade")
        and tipo_norm in ("natural_amizade", "neutra", "amizade")
        and not force_resolution
        and not mary_done
        and not pre_signals
        and stimulation_turns <= 0
    )

    # ======================================================
    # 8) FASE / STAGE / NÍVEIS
    # Importante:
    # - mary_climax_done/user_climax_done são fatos narrativos passados.
    # - Eles NÃO devem impedir recalibração da cena atual.
    # - A cena atual deve obedecer tom_manual + privacidade + cfg.
    # - O stage NÃO deve ser derivado cegamente da fase quando o tom
    #   não é Intimidade.
    # ======================================================
    if not force_resolution:
        fase_atual = safe_int(state.get("physical_phase", 0), 0)
        fase_base = safe_int(cfg.get("physical_phase", 0), 0)

        if cena_neutra_sozinha:
            state["physical_phase"] = 0
            state["scene_stage"] = "cotidiano"
            state["mary_intent"] = "preparar_noite_refletindo"

            state["desire_level"] = min(
                safe_float(state.get("desire_level", 0.0), 0.0),
                safe_float(cfg.get("desire_level", 0.0), 0.0),
            )

            state["tension_level"] = min(
                safe_float(state.get("tension_level", 0.0), 0.0),
                safe_float(cfg.get("tension_level", 0.0), 0.0),
            )

            state["connection_level"] = max(
                safe_float(state.get("connection_level", 0.0), 0.0),
                safe_float(cfg.get("connection_level", 0.0), 0.0),
            )

            state["toque_intimo_permitido"] = False
            state["toque_provocativo_permitido"] = False
            state["alivio_rapido_permitido"] = False
            state["tensao_romantica_com_interlocutor"] = False

        else:
            # ==================================================
            # Fase:
            # - Natural / Amizade e Pendência / Decisão usam cfg.
            # - Malícia / Flerte preserva tensão, mas não vira intimidade plena.
            # - Intimidade pode preservar progressão maior.
            # - Nsfw usa cfg, exceto quando aftercare for restaurado no fim.
            # ==================================================
            if tom_manual in ("Natural / Amizade", "Pendência / Decisão"):
                nova_fase = fase_base

            elif tom_manual == "Malícia / Flerte":
                nova_fase = max(fase_atual, fase_base)

                if privacidade == "publico":
                    nova_fase = min(nova_fase, 2)
                elif privacidade == "semiprivado":
                    nova_fase = min(nova_fase, 3)
                else:
                    nova_fase = min(nova_fase, 3)

            elif tom_manual == "Intimidade":
                nova_fase = max(fase_atual, fase_base)

                if privacidade == "publico":
                    nova_fase = min(nova_fase, 2)
                elif privacidade == "semiprivado":
                    nova_fase = min(nova_fase, 4)

            elif tom_manual == "Nsfw":
                nova_fase = max(fase_atual, fase_base)

                if privacidade != "privado" and not cfg.get("alivio_rapido_permitido", False):
                    nova_fase = min(nova_fase, 2)
                elif cfg.get("alivio_rapido_permitido", False):
                    nova_fase = max(nova_fase, 3)

            else:
                nova_fase = fase_base

            state["physical_phase"] = nova_fase

            # ==================================================
            # Stage:
            # Não usar mapa_stage cego para Malícia / Flerte,
            # porque fase 3 viraria "intimidade".
            # ==================================================
            if tom_manual == "Natural / Amizade":
                state["scene_stage"] = cfg.get("scene_stage", "cotidiano")

            elif tom_manual == "Malícia / Flerte":
                if privacidade == "publico":
                    state["scene_stage"] = "flerte_direto"
                elif privacidade == "semiprivado":
                    state["scene_stage"] = "intensidade_contida"
                else:
                    state["scene_stage"] = "flerte_direto"

            elif tom_manual == "Intimidade":
                if privacidade == "publico":
                    state["scene_stage"] = "buscar_privacidade"
                elif privacidade == "semiprivado":
                    state["scene_stage"] = "intensidade_contida"
                else:
                    state["scene_stage"] = "intimidade"

            elif tom_manual == "Pendência / Decisão":
                state["scene_stage"] = cfg.get("scene_stage", "decisao")

            elif tom_manual == "Nsfw":
                state["scene_stage"] = cfg.get("scene_stage", "nsfw_preliminares")

            else:
                state["scene_stage"] = cfg.get("scene_stage", "inicio")

            # ==================================================
            # Níveis emocionais:
            # Preserva intensidade já construída, mas aplica piso do preset.
            # ==================================================
            state["desire_level"] = clamp(
                max(
                    safe_float(state.get("desire_level", 0.0), 0.0),
                    safe_float(cfg.get("desire_level", 0.0), 0.0),
                )
            )

            state["tension_level"] = clamp(
                max(
                    safe_float(state.get("tension_level", 0.0), 0.0),
                    safe_float(cfg.get("tension_level", 0.0), 0.0),
                )
            )

            state["connection_level"] = clamp(
                max(
                    safe_float(state.get("connection_level", 0.0), 0.0),
                    safe_float(cfg.get("connection_level", 0.0), 0.0),
                )
            )

    # ======================================================
    # 9) LIMPEZA FINAL DE CENA NATURAL SOZINHA
    # Não recalcula relação aqui para não sobrescrever o tom manual.
    # ======================================================
    resetar_progressao_fisica_se_cena_neutra_sozinha(state)

    # ======================================================
    # 10) SEGURANÇA FINAL POR AMBIENTE
    # Ambiente não privado impede nova resolução,
    # mas NÃO apaga fatos narrativos já ocorridos.
    # ======================================================
    if privacidade != "privado":
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False

        if safe_int(state.get("physical_phase", 0), 0) < 6:
            state["resolution_done"] = False
            state["partner_climax_pending"] = False

    # ======================================================
    # 10.5) RESTAURA AFTERCARE APÓS TODOS OS AJUSTES
    # Impede que Nsfw, público, semiprivado, alívio rápido
    # ou buscar_privacidade apaguem o pós-ato.
    # ======================================================
    if aftercare_ativo:
        user_done = normalizar_bool(
            state.get("user_climax_done", False),
            default=False,
        )

        state["scene_stage"] = "aftercare"
        state["mary_intent"] = "desacelerar_com_presenca"
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False
        state["mary_stimulation_turns"] = 0
        state["partner_climax_pending"] = not user_done
        state["physical_phase"] = 7 if user_done else 6

        # Mantém o NSFW como pós-ato, não como reinício de preliminares.
        state["tipo_de_cena"] = "nsfw_aftercare"
        state["tom_da_cena"] = "pós-ato íntimo adulto"
        state["estilo_de_iniciativa"] = "desaceleração íntima com presença"
        state["toque_provocativo_permitido"] = True

        # Se estava em privado, mantém toque íntimo permitido.
        # Se não estava, não força nova ação íntima; apenas preserva o fato narrativo do pós-ato.
        state["toque_intimo_permitido"] = privacidade == "privado"
        state["alivio_rapido_permitido"] = False

        state["limite_ambiente"] = (
            "Aftercare NSFW: a cena está no pós-ato. Mary não deve reiniciar preliminares, "
            "voltar para buscar privacidade ou agir como se nada tivesse acontecido. "
            "Ela deve reconhecer a consequência física e emocional imediata, mantendo presença, "
            "satisfação, respiração, proximidade e continuidade íntima conforme o contexto."
        )

    # ======================================================
    # 11) NORMALIZAÇÃO FINAL DO STAGE
    # Evita valores inválidos ou variações textuais quebrando fluxo.
    # ======================================================
    state["scene_stage"] = normalizar_scene_stage(
        state.get("scene_stage", ""),
        padrao="inicio",
    )


def resetar_se_contexto_mudou(state: dict) -> None:
    """
    Reseta progressão apenas quando há mudança forte de contexto.

    Mudanças leves de local não devem destruir continuidade.

    Regras:
    - Mudança de interlocutor, saída de ambiente privado ou ida para cena neutra
      podem limpar progressão física momentânea.
    - Porém mary_climax_done e user_climax_done são fatos narrativos já ocorridos.
      Não devem ser apagados automaticamente por mudança de contexto.
    - Esses fatos só devem ser zerados por uma função específica de nova cena,
      novo capítulo ou reset manual.
    """
    if not isinstance(state, dict):
        return

    contexto_atual = {
        "local": str(state.get("local", "") or "").strip(),
        "interlocutor": str(state.get("interlocutor", "") or "").strip(),
        "tipo_de_cena": str(state.get("tipo_de_cena", "") or "").strip(),
        "privacidade": str(state.get("privacidade", "") or "").strip(),
    }

    contexto_antigo = state.get("_contexto_anterior_dict")

    # Compatibilidade com versão antiga que salvava string.
    if not isinstance(contexto_antigo, dict):
        chave_antiga = str(state.get("_contexto_anterior", "") or "")

        if chave_antiga:
            partes = chave_antiga.split("|")
            contexto_antigo = {
                "local": partes[0] if len(partes) > 0 else "",
                "interlocutor": partes[1] if len(partes) > 1 else "",
                "tipo_de_cena": partes[2] if len(partes) > 2 else "",
                "privacidade": partes[3] if len(partes) > 3 else "",
            }
        else:
            contexto_antigo = None

    if contexto_antigo:
        antigo_interlocutor = _texto_norm(contexto_antigo.get("interlocutor", ""))
        novo_interlocutor = _texto_norm(contexto_atual.get("interlocutor", ""))

        antigo_tipo = _texto_norm(contexto_antigo.get("tipo_de_cena", ""))
        novo_tipo = _texto_norm(contexto_atual.get("tipo_de_cena", ""))

        antiga_privacidade = _texto_norm(contexto_antigo.get("privacidade", ""))
        nova_privacidade = _texto_norm(contexto_atual.get("privacidade", ""))

        mudou_interlocutor = antigo_interlocutor != novo_interlocutor
        mudou_tipo_para_neutro = novo_tipo == "neutra" and antigo_tipo != "neutra"
        saiu_do_privado = antiga_privacidade == "privado" and nova_privacidade != "privado"

        mudanca_forte = (
            mudou_interlocutor
            or mudou_tipo_para_neutro
            or saiu_do_privado
        )

        if mudanca_forte:
            # ==================================================
            # RESET DE PROGRESSÃO MOMENTÂNEA
            # ==================================================
            state["physical_phase"] = 0
            state["scene_stage"] = "inicio"

            state["desire_level"] = 0.18
            state["tension_level"] = 0.12
            state["connection_level"] = max(
                safe_float(state.get("connection_level", 0.22), 0.22),
                0.22,
            )

            # ==================================================
            # LIMPA GATILHOS TÉCNICOS DO PICO
            # ==================================================
            state["resolution_done"] = False
            state["partner_climax_pending"] = False
            state["force_resolution_now"] = False
            state["mary_pre_orgasm_signals"] = False
            state["mary_stimulation_turns"] = 0

            # ==================================================
            # NÃO APAGAR FATOS NARRATIVOS JÁ OCORRIDOS
            # ==================================================
            # Não fazer:
            # state["mary_climax_done"] = False
            # state["user_climax_done"] = False
            #
            # Esses campos indicam acontecimentos já verbalizados.
            # Eles só devem ser limpos em reset manual, nova cena real
            # ou função específica de novo capítulo.

    state["_contexto_anterior_dict"] = contexto_atual
    state["_contexto_anterior"] = "|".join(
        [
            contexto_atual["local"],
            contexto_atual["interlocutor"],
            contexto_atual["tipo_de_cena"],
            contexto_atual["privacidade"],
        ]
    )
def eh_janio(valor: str) -> bool:
    valor = _texto_norm(valor)
    return valor in {
        "janio",
        "janio Doniseti",
        "janio Doniseti welnecker",
    }


def atualizar_interlocutor_ativo(state: dict, fala_usuario: str) -> None:
    """
    Mantém o interlocutor ativo de forma persistente.

    Regra central:
    - Se um personagem é citado explicitamente como quem entrou, falou ou agiu,
      ele vira o foco do turno.
    - Em cenas com múltiplos interlocutores, o campo "interlocutor" pode continuar
      contendo o grupo, mas "interlocutor_foco_turno" deve apontar quem falou/agiu agora.
    - Se nenhum novo personagem for introduzido,
      mantém o último interlocutor persistente.
    - Janio não volta automaticamente só por ser usuario_real.
    """
    if not isinstance(state, dict):
        return

    texto = _texto_norm(fala_usuario)
    interlocutor_campo = str(state.get("interlocutor", "") or "").strip()

    personagens = {
        "Janio": ["janio", "jânio", "janio Doniseti", "jânio Doniseti"],
        "Joselina": ["joselina", "mãe", "mae"],
        "Silvia": ["silvia", "sílvia"],
        "Bianca": ["bianca"],
        "Renan": ["renan", "professor renan"],
        "Rico": ["rico", "ricardo"],
        "Anthony": ["anthony", "antony"],
        "Nando": ["nando"],
    }

    padroes = [
        # Ex: "Joselina diz": ...
        r"\b{nome}\s+(diz|fala|pergunta|responde|grita|sussurra|chama)\b",

        # Ex: Joselina:
        r"\b{nome}\s*:\s*",

        # Ex: Joselina entra / chega / se aproxima
        r"\b{nome}\s+(se aproxima|aproxima|entra|chega|aparece|volta|olha|sorri|toca|segura|puxa|pega)\b",

        # Ex: sou Joselina / eu sou Joselina
        r"\b(sou|eu sou)\s+{nome}\b",

        # Ex: como Joselina / na voz de Joselina
        r"\bcomo\s+{nome}\b",
        r"\bna voz de\s+{nome}\b",

        # Ex: Joselina está perto de Mary
        r"\b{nome}\s+(está|esta|fica|permanece|continua)\s+(com|perto de|ao lado de)\s+mary\b",
    ]

    
    def detectar_personagem_explicito(texto_norm: str) -> str:
        for nome_canonico, aliases in personagens.items():
            for alias in aliases:
                alias_regex = re.escape(_texto_norm(alias))

                for padrao in padroes:
                    if re.search(
                        padrao.format(nome=alias_regex),
                        texto_norm,
                        flags=re.IGNORECASE,
                    ):
                        return nome_canonico

        return ""

    def campo_tem_multiplos_interlocutores(valor: str) -> bool:
        return any(sep in valor for sep in [",", ";", "/", "|"])

    def janio_esta_no_campo(valor: str) -> bool:
        valor_norm = _texto_norm(valor)
        return "janio" in valor_norm or "janio Doniseti" in valor_norm

    # ======================================================
    # 1) Falante/personagem explícito no texto vence tudo.
    # Ex: "Joselina diz": ...
    # ======================================================
    novo_interlocutor = detectar_personagem_explicito(texto)

    if novo_interlocutor:
        if campo_tem_multiplos_interlocutores(interlocutor_campo):
            # Mantém o grupo na cena, muda só o foco do turno.
            state["interlocutor"] = interlocutor_campo
        else:
            state["interlocutor"] = novo_interlocutor

        state["interlocutor_foco_turno"] = novo_interlocutor
        state["interlocutor_ativo_persistente"] = novo_interlocutor
        state["ultimo_interlocutor_explicito"] = novo_interlocutor

        if eh_janio(novo_interlocutor) or janio_esta_no_campo(interlocutor_campo):
            state["janio_status_na_cena"] = "presente"
        else:
            state["janio_status_na_cena"] = state.get("janio_status_na_cena") or "roteirista"

        return

    # ======================================================
    # 2) Se há múltiplos interlocutores, tenta detectar foco
    # dentro do grupo atual.
    # ======================================================
    if campo_tem_multiplos_interlocutores(interlocutor_campo):
        foco = detectar_foco_do_turno(fala_usuario, interlocutor_campo)

        # Segurança: se detectar_foco_do_turno falhar, mantém foco persistente.
        if not foco:
            foco = str(
                state.get("interlocutor_ativo_persistente")
                or state.get("ultimo_interlocutor_explicito")
                or ""
            ).strip()

        # Se ainda assim não houver foco, usa o primeiro nome do grupo.
        if not foco:
            foco = re.split(r"[,;/|]", interlocutor_campo)[0].strip()

        state["interlocutor"] = interlocutor_campo
        state["interlocutor_foco_turno"] = foco
        state["interlocutor_ativo_persistente"] = foco
        state["ultimo_interlocutor_explicito"] = foco

        if eh_janio(foco) or janio_esta_no_campo(interlocutor_campo):
            state["janio_status_na_cena"] = "presente"
        else:
            state["janio_status_na_cena"] = state.get("janio_status_na_cena") or "roteirista"

        return

    # ======================================================
    # 3) Se ninguém novo apareceu, mantém quem já estava persistente.
    # ======================================================
    interlocutor_atual = str(
        state.get("interlocutor_ativo_persistente")
        or state.get("interlocutor")
        or "Janio Doniseti"
    ).strip()

    if interlocutor_atual:
        state["interlocutor"] = interlocutor_atual
        state["interlocutor_foco_turno"] = interlocutor_atual
        state["interlocutor_ativo_persistente"] = interlocutor_atual

        if eh_janio(interlocutor_atual):
            state["janio_status_na_cena"] = "presente"
        else:
            state["janio_status_na_cena"] = state.get("janio_status_na_cena") or "roteirista"


def sincronizar_interlocutor_manual(state: dict) -> None:
    """
    Quando o campo manual 'interlocutor' muda no sidebar,
    ele vira a fonte principal.

    Isso impede resíduos como:
    interlocutor = "Joselina, Anthony"
    foco/persistente/último = "Silvia"
    """
    if not isinstance(state, dict):
        return

    interlocutor = str(state.get("interlocutor", "") or "").strip()

    if not interlocutor:
        interlocutor = "Janio Doniseti"
        state["interlocutor"] = interlocutor

    anterior = str(state.get("_interlocutor_manual_anterior", "") or "").strip()

    if interlocutor != anterior:
        nomes = [
            nome.strip()
            for nome in re.split(r"[,;/|]", interlocutor)
            if nome.strip()
        ]

        foco_padrao = nomes[0] if nomes else interlocutor

        state["interlocutor_foco_turno"] = foco_padrao
        state["interlocutor_ativo_persistente"] = foco_padrao
        state["ultimo_interlocutor_explicito"] = foco_padrao
        state["_interlocutor_manual_anterior"] = interlocutor

        if eh_janio(foco_padrao):
            state["janio_status_na_cena"] = "presente"
        elif state.get("janio_status_na_cena") == "presente":
            state["janio_status_na_cena"] = "roteirista"

def detectar_falante_explicito(fala_usuario: str, personagens_conhecidos=None) -> str:
    """
    Detecta padrões como:
    "Joselina diz": ...
    Joselina:
    Bianca fala:
    Renan pergunta:
    """
    texto = remover_acentos(str(fala_usuario or "").lower())

    personagens_base = personagens_conhecidos or [
        "Janio",
        "Joselina",
        "Silvia",
        "Bianca",
        "Renan",
        "Rico",
        "Anthony",
        "Nando",
    ]

    verbos = [
        "diz",
        "fala",
        "pergunta",
        "responde",
        "grita",
        "sussurra",
        "chama",
    ]

    for nome in personagens_base:
        nome_norm = remover_acentos(nome.lower())

        for verbo in verbos:
            padroes = [
                f'"{nome_norm} {verbo}"',
                f"{nome_norm} {verbo}",
                f"{nome_norm}:",
                f'"{nome_norm}:',
            ]

            if any(p in texto for p in padroes):
                return nome

    return ""


def detectar_foco_do_turno(fala_usuario: str, interlocutor_atual: str) -> str:
    """
    Detecta quem é o foco do turno quando há mais de um interlocutor na cena.
    Ex:
    interlocutor_atual = "Silvia, Anthony"

    Se o texto disser "Silvia cochicha", foco = Silvia.
    Se disser "Anthony se aproxima", foco = Anthony.
    Se não detectar ninguém, mantém o primeiro nome do grupo.
    """
    texto = _texto_norm(fala_usuario)
    interlocutor_atual = str(interlocutor_atual or "").strip()

    nomes = [
        nome.strip()
        for nome in re.split(r"[,;/|]", interlocutor_atual)
        if nome.strip()
    ]

    if not nomes:
        return interlocutor_atual or "Janio Doniseti"

    padroes_acao = [
        r"\b{nome}\s+(cochicha|sussurra|fala|diz|responde|pergunta|grita|chama|se aproxima|aproxima|chega|entra|olha|sorri|toca|segura|puxa|manda mensagem|envia mensagem)\b",
        r"\b{nome}\s*:\s*",
        r"\bmensagem de\s+{nome}\b",
        r"\bna voz de\s+{nome}\b",
        r"\bcomo\s+{nome}\b",
    ]

    for nome in nomes:
        nome_norm = _texto_norm(nome)
        nome_regex = re.escape(nome_norm)

        for padrao in padroes_acao:
            if re.search(padrao.format(nome=nome_regex), texto, flags=re.IGNORECASE):
                return nome

    return nomes[0]

def amor_genuino_com_interlocutor(state: dict) -> bool:
    """
    Define quando Mary reconhece amor genuíno com o interlocutor atual.

    Regra:
    - Janio Doniseti é amor genuíno canônico quando está presente como interlocutor.
    - Outros personagens só liberam se o state/facts marcar explicitamente.
    """
    if not isinstance(state, dict):
        return False

    foco = _texto_norm(
        state.get("interlocutor_foco_turno")
        or state.get("interlocutor_ativo_persistente")
        or state.get("interlocutor")
        or ""
    )

    janio_status = _texto_norm(state.get("janio_status_na_cena", ""))

    janio_presente = janio_status in {
        "presente",
        "interlocutor",
        "personagem",
        "na cena",
        "presente na cena",
        "ativo",
        "participando",
        "junto",
        "sim",
        "true",
        "1",
    }

    if "janio" in foco and janio_presente:
        return True

    return normalizar_bool(
        state.get("amor_genuino_com_interlocutor", False),
        default=False,
    )


def normalizar_estado(state: dict) -> None:
    """
    Normaliza o estado geral da cena.

    Importante:
    - Não deve apagar fatos narrativos já ocorridos apenas porque a privacidade atual é pública.
    - Ambiente público limita nova progressão, mas não reescreve passado.
    """
    if not isinstance(state, dict):
        return

    resetar_se_contexto_mudou(state)
    derivar_controles_de_cena(state)

    privacidade = _texto_norm(state.get("privacidade", ""))
    tipo_de_cena = _texto_norm(state.get("tipo_de_cena", ""))

    if privacidade == "publico" and tipo_de_cena not in ("social", "nsfw_alivio_rapido", "nsfw_aftercare"):
        state["physical_phase"] = min(
            safe_int(state.get("physical_phase", 0), 0),
            3,
        )

        scene_stage = _texto_norm(state.get("scene_stage", ""))
        if scene_stage in (
            "intensidade",
            "pico",
            "desaceleracao",
            "aftercare",
            "pos_pico_mary",
            "sexo_ou_estimulo",
            "pre_pico_mary",
            "pico_mary",
        ):
            state["scene_stage"] = "flerte_direto"

        mary_intent = _texto_norm(state.get("mary_intent", ""))
        if mary_intent in (
            "buscar_intensidade",
            "resolver_pico",
            "resolver_pico_mary",
            "retomar_intensidade",
            "aproximar_do_pico",
        ):
            state["mary_intent"] = "flerte_intimo_discreto"

        # Ambiente público bloqueia nova resolução,
        # mas NÃO apaga clímax já ocorrido.
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False

        if safe_int(state.get("physical_phase", 0), 0) < 6:
            state["resolution_done"] = False
            state["partner_climax_pending"] = False


def resolver_estado_emocional_mary(state: dict) -> str:
    """
    Resolve o campo estado_emocional como Consciência da Cena.

    O nome interno permanece estado_emocional para evitar refatoração ampla,
    mas o significado narrativo agora é:
    - como Mary percebe o peso do ato;
    - não como ela explica sentimentos em parágrafos.
    """
    if not isinstance(state, dict):
        return "Automático"

    estado = normalizar_consciencia_cena_mary(
        state.get("estado_emocional", "Automático")
    )

    if estado not in OPCOES_ESTADO_EMOCIONAL_MARY:
        estado = "Automático"

    state["estado_emocional"] = estado
    return estado


def formatar_estado_emocional_para_prompt(state: dict) -> str:
    consciencia = resolver_estado_emocional_mary(state)
    descricao = MAPA_ESTADO_EMOCIONAL_MARY.get(
        consciencia,
        MAPA_ESTADO_EMOCIONAL_MARY["Automático"],
    )

    return f"""
[CONSCIÊNCIA DA CENA]
Consciência selecionada:
{consciencia}

Função prática:
{descricao}

REGRAS CENTRAIS:
- Este campo NÃO muda o tipo da cena.
- O tom_manual_da_cena define o eixo externo da cena.
- A consciência da cena define como Mary percebe o peso do ato, risco, exposição, desejo, vergonha, consequência ou perda de controle.
- Mary pode escolher qualquer caminho, mas não deve agir como se escolhas não tivessem peso.
- A consciência deve aparecer implicitamente em atos e falas, NÃO em explicações psicológicas.

ECONOMIA OBRIGATÓRIA:
- Não escrever parágrafos explicando o que Mary sente.
- Não nomear culpa, medo, arrependimento, desejo ou conflito de forma didática.
- Não transformar a resposta em análise moral.
- Não romantizar risco real.
- Não parar a cena para explicar a mente de Mary.

COMO MOSTRAR:
Use no máximo UM ou DOIS sinais concretos:
- uma pausa;
- um olhar para a porta, janela, celular, chão ou interlocutor;
- uma frase curta;
- um gesto de recuo ou avanço;
- uma pergunta objetiva;
- uma condição imposta;
- uma hesitação breve;
- uma decisão assumida.

EXEMPLOS DE ESTILO:
Ruim:
"Mary sente um conflito moral profundo e percebe todas as consequências da proposta."

Bom:
"Mary olha para a folha, depois para Renan.
'Professor... isso ainda é sobre a prova?'"

Ruim:
"Mary sente medo das consequências."

Bom:
"Mary confere a porta antes de responder."

Ruim:
"Mary sabe que está assumindo o risco e decide seguir mesmo assim."

Bom:
"Mary dobra a folha devagar.
'Então eu passo. Depois a gente conversa sobre essa dívida.'"

REGRA FINAL:
Mary deve continuar agindo dentro da cena.
A consciência muda a precisão da ação, não o tamanho da resposta.
""".strip()

def limpar_acao_intima_incompativel_com_foco(state: dict) -> None:
    foco = str(state.get("interlocutor_foco_turno", "") or "").strip()
    tipo = remover_acentos(str(state.get("tipo_de_cena", "") or "").lower())
    tom = str(state.get("tom_manual_da_cena", "") or "")
    acao = remover_acentos(str(state.get("mary_acao", "") or "").lower())

    termos_intimos = [
        "calcinha afastada",
        "apertando a coxa",
        "por baixo da mesa",
        "erecao",
        "pau",
        "buceta",
        "estocada",
        "sexo",
        "foder",
        "penetra",
    ]

    if not any(t in acao for t in termos_intimos):
        return

    # Se o foco do turno é social/familiar e o tom não é Intimidade/Nsfw,
    # a ação íntima anterior não pode continuar como ação atual.
    if tom not in ("Intimidade", "Nsfw"):
        state["mary_acao"] = (
            f"Mary está diante de {foco or 'o interlocutor atual'}, tentando agir normalmente "
            "e disfarçar a tensão da situação anterior."
        )

def limpar_acao_incompativel_com_janio_ausente(state: dict) -> None:
    """
    Remove da ação atual referências a Janio quando Janio não está
    fisicamente presente na cena.

    Importante:
    - Não apaga memórias.
    - Não muda relação.
    - Não altera Janio como usuário real/roteirista.
    - Só corrige mary_acao quando ela contradiz janio_status_na_cena.
    """
    if not isinstance(state, dict):
        return

    janio_status = _texto_norm(state.get("janio_status_na_cena", ""))
    acao_original = str(state.get("mary_acao", "") or "").strip()
    acao_norm = _texto_norm(acao_original)

    if not acao_original:
        return

    janio_ausente = janio_status in {
        "ausente",
        "ausente_ou_observador",
        "observador",
        "roteirista",
        "fora_da_cena",
        "fora da cena",
    }

    menciona_janio = (
        "janio" in acao_norm
        or "janio Doniseti" in acao_norm
    )

    if not janio_ausente or not menciona_janio:
        return

    foco = str(state.get("interlocutor_foco_turno", "") or "").strip()
    persistente = str(state.get("interlocutor_ativo_persistente", "") or "").strip()
    interlocutor = str(state.get("interlocutor", "") or "").strip()
    
    foco_norm = _texto_norm(foco)
    persistente_norm = _texto_norm(persistente)
    interlocutor_norm = _texto_norm(interlocutor)
    
    # Se o foco antigo ainda for guia, mas o interlocutor persistente já for jovem,
    # o persistente vence.
    if "guia" in foco_norm and "jovem" in persistente_norm:
        foco = persistente
    elif "guia" in foco_norm and "jovem" in interlocutor_norm:
        foco = interlocutor
    elif not foco:
        foco = persistente or interlocutor

    local = str(state.get("local", "") or "").strip()
    plano = str(state.get("plano_ativo", "") or "").strip()

    if foco and not eh_sem_interlocutor(foco):
        state["mary_acao"] = (
            f"Mary está diante de {foco}, acompanhando a situação atual"
            f"{f' em {local}' if local else ''}."
        )
    elif plano:
        state["mary_acao"] = (
            f"Mary está envolvida no momento atual da cena, seguindo o plano em andamento: {plano}."
        )
    elif local:
        state["mary_acao"] = (
            f"Mary está em {local}, atenta ao que acontece ao redor."
        )
    else:
        state["mary_acao"] = (
            "Mary está atenta ao momento atual da cena."
        )

def limpar_acao_incompativel_com_interlocutor_foco(state: dict) -> None:
    """
    Corrige mary_acao quando ela menciona um interlocutor antigo,
    mas o foco atual já mudou.
    """
    if not isinstance(state, dict):
        return

    acao = str(state.get("mary_acao", "") or "").strip()
    acao_norm = _texto_norm(acao)

    if not acao:
        return

    foco = str(
        state.get("interlocutor_foco_turno")
        or state.get("interlocutor_ativo_persistente")
        or state.get("interlocutor")
        or ""
    ).strip()

    foco_norm = _texto_norm(foco)

    if not foco or eh_sem_interlocutor(foco):
        return

    menciona_guia = "guia" in acao_norm
    foco_jovem = "jovem" in foco_norm

    if menciona_guia and foco_jovem:
        local = str(state.get("local", "") or "").strip()

        state["mary_acao"] = (
            f"Mary está diante de {foco}, mantendo a conversa no ambiente atual"
            f"{f' em {local}' if local else ''}."
        )

# ==========================================================
# VISUAL AUTOMÁTICO DE MARY
# ==========================================================

def _escolher_visual_estavel(opcoes: list[dict], state: dict) -> dict:
    """
    Escolhe um visual de forma estável, sem usar random.
    Assim o Streamlit não muda a roupa a cada rerun.
    """
    fallback = {
        "roupa": "calça jeans escura, camiseta preta ajustada e tênis branco",
        "cabelo": "cabelos negros soltos, bem cuidados",
        "extras": ["presença natural"],
    }

    if not opcoes:
        return fallback

    base = "|".join(
        [
            str(state.get("local", "") or ""),
            str(state.get("tempo", "") or ""),
            str(state.get("mary_acao", "") or ""),
            str(state.get("plano_ativo", "") or ""),
            str(state.get("tom_manual_da_cena", "") or ""),
        ]
    )

    indice = abs(hash(base)) % len(opcoes)
    return opcoes[indice]


def _aplicar_visual(visual: dict) -> tuple[str, str, list[str]]:
    roupa = str(visual.get("roupa", "") or "").strip()
    cabelo = str(visual.get("cabelo", "") or "").strip()
    extras = visual.get("extras", [])

    if not isinstance(extras, list):
        extras = [str(extras)]

    extras = [str(e or "").strip() for e in extras if str(e or "").strip()]

    if not roupa:
        roupa = "calça jeans escura, camiseta preta ajustada e tênis branco"

    if not cabelo:
        cabelo = "cabelos negros soltos, bem cuidados"

    return roupa, cabelo, extras


VISUAIS_FACULDADE_MANHA = [
    {
        "roupa": "calça jeans clara, baby look preta da UFRJ e tênis branco",
        "cabelo": "cabelos negros soltos, alinhados atrás das orelhas",
        "extras": ["mochila preta em um ombro", "caderno fino contra o peito"],
    },
    {
        "roupa": "calça jeans azul, camiseta baby look da UFRJ e jaqueta leve aberta",
        "cabelo": "cabelos negros presos em rabo baixo, com alguns fios soltos no rosto",
        "extras": ["mochila com cadernos", "celular na mão"],
    },
    {
        "roupa": "saia jeans discreta, baby look preta da UFRJ e tênis casual",
        "cabelo": "cabelos negros soltos, com movimento natural",
        "extras": ["bolsa lateral pequena", "relógio simples"],
    },
]

VISUAIS_FACULDADE_TARDE = [
    {
        "roupa": "calça jeans azul ajustada, baby look preta da UFRJ e tênis confortável",
        "cabelo": "cabelos negros soltos, com aparência natural de rotina universitária",
        "extras": ["mochila universitária", "caderno ou celular na mão"],
    },
    {
        "roupa": "calça jeans escura, blusa branca justa por baixo de uma jaqueta jeans aberta",
        "cabelo": "cabelos negros presos de forma prática, com fios soltos no pescoço",
        "extras": ["mochila apoiada em um ombro", "estojo pequeno na mão"],
    },
    {
        "roupa": "short jeans discreto, camiseta preta da UFRJ e tênis branco",
        "cabelo": "cabelos negros soltos, levemente desalinhados pelo movimento do dia",
        "extras": ["bolsa transversal", "garrafinha de água"],
    },
]

VISUAIS_FACULDADE_NOITE = [
    {
        "roupa": "calça jeans escura, baby look preta da UFRJ e tênis branco já marcado pelo uso do dia",
        "cabelo": "cabelos negros soltos, um pouco desalinhados pelo cansaço",
        "extras": ["mochila apoiada em um ombro", "visual de quem acabou de voltar da faculdade"],
    },
    {
        "roupa": "calça jeans ajustada, camiseta preta da UFRJ parcialmente amassada e tênis casual",
        "cabelo": "cabelos negros soltos, com alguns fios caindo sobre o rosto",
        "extras": ["mochila pesada", "chaves na mão"],
    },
    {
        "roupa": "calça jeans azul, baby look da UFRJ e casaco leve amarrado na cintura",
        "cabelo": "cabelos negros soltos, com aparência de fim de dia",
        "extras": ["mochila com cadernos", "celular na mão"],
    },
]

VISUAIS_SAIDA_URBANA = [
    {
        "roupa": "calça jeans escura, blusa preta ajustada e tênis branco",
        "cabelo": "cabelos negros soltos, penteados com os dedos",
        "extras": ["bolsa pequena no ombro", "chaves na mão"],
    },
    {
        "roupa": "vestido curto casual de algodão escuro e sandália baixa",
        "cabelo": "cabelos negros soltos, com movimento natural",
        "extras": ["bolsa lateral", "perfume discreto"],
    },
    {
        "roupa": "short jeans, blusa baby look lisa e tênis casual",
        "cabelo": "cabelos negros presos em rabo baixo",
        "extras": ["celular na mão", "bolsa pequena atravessada no corpo"],
    },
    {
        "roupa": "calça jeans azul, camiseta justa sem estampa e jaqueta leve aberta",
        "cabelo": "cabelos negros soltos, alinhados atrás dos ombros",
        "extras": ["mochila pequena", "batom discreto"],
    },
]

VISUAIS_PRAIA_DIA = [
    {
        "roupa": "biquíni de crochê por baixo de uma saída de praia branca aberta",
        "cabelo": "cabelos negros soltos, com aspecto natural de praia",
        "extras": ["óculos de sol", "chinelo claro", "bolsa de palha"],
    },
    {
        "roupa": "biquíni preto, short jeans aberto no botão e camisa leve amarrada na cintura",
        "cabelo": "cabelos negros soltos, com fios bagunçados pelo vento",
        "extras": ["canga dobrada no braço", "protetor solar na bolsa"],
    },
    {
        "roupa": "maiô vermelho com short branco leve por cima",
        "cabelo": "cabelos negros presos em coque frouxo",
        "extras": ["sandália rasteira", "óculos escuros"],
    },
]

VISUAIS_PRAIA_NOITE = [
    {
        "roupa": "vestido leve de alcinha por cima do biquíni",
        "cabelo": "cabelos negros soltos, com movimento suave",
        "extras": ["sandália baixa", "bolsa pequena de praia"],
    },
    {
        "roupa": "saída de praia discreta, biquíni escuro por baixo e chinelo baixo",
        "cabelo": "cabelos negros soltos, levemente úmidos nas pontas",
        "extras": ["canga fina nos ombros", "visual relaxado de orla"],
    },
    {
        "roupa": "short jeans claro, top de biquíni por baixo de uma camisa branca aberta",
        "cabelo": "cabelos negros presos de lado, com fios soltos no rosto",
        "extras": ["sandália rasteira", "pulseira simples"],
    },
]

VISUAIS_BANHO = [
    {
        "roupa": "corpo nu sob o chuveiro",
        "cabelo": "cabelos negros molhados, grudando parcialmente nos ombros",
        "extras": ["pele molhada", "gotas de água escorrendo pelo corpo"],
    },
    {
        "roupa": "toalha branca enrolada acima dos seios",
        "cabelo": "cabelos negros úmidos, penteados para trás com os dedos",
        "extras": ["pele limpa", "vapor leve no banheiro"],
    },
    {
        "roupa": "roupão claro aberto no colo, ainda com a pele úmida do banho",
        "cabelo": "cabelos negros úmidos caindo sobre os ombros",
        "extras": ["cheiro de sabonete", "pés descalços no piso frio"],
    },
]

VISUAIS_SONO_NOITE = [
    {
        "roupa": "calcinha limpa e babydoll preto leve",
        "cabelo": "cabelos negros soltos, ainda úmidos nas pontas",
        "extras": ["pés descalços", "visual íntimo de fim de noite"],
    },
    {
        "roupa": "camiseta comprida usada como roupa de dormir e calcinha simples",
        "cabelo": "cabelos negros presos de qualquer jeito, com fios soltos no rosto",
        "extras": ["pele recém-saída do banho", "expressão cansada"],
    },
    {
        "roupa": "shortinho de algodão cinza e blusa fina de alça",
        "cabelo": "cabelos negros soltos sobre os ombros",
        "extras": ["pés descalços", "travesseiro próximo"],
    },
    {
        "roupa": "camisola curta de algodão claro",
        "cabelo": "cabelos negros soltos, espalhados pelo pescoço",
        "extras": ["visual caseiro e sonolento"],
    },
]

VISUAIS_CASA_MANHA = [
    {
        "roupa": "shortinho de algodão e camiseta larga levemente caída em um ombro",
        "cabelo": "cabelos negros presos em coque frouxo",
        "extras": ["pés descalços", "caneca na mão"],
    },
    {
        "roupa": "calça de moletom leve e regata branca simples",
        "cabelo": "cabelos negros soltos, ainda bagunçados de sono",
        "extras": ["rosto lavado", "visual de manhã em casa"],
    },
    {
        "roupa": "camiseta comprida e short curto de dormir",
        "cabelo": "cabelos negros presos de forma despretensiosa",
        "extras": ["pés descalços", "expressão sonolenta"],
    },
]

VISUAIS_CASA_DIA = [
    {
        "roupa": "short jeans claro e camiseta preta justa",
        "cabelo": "cabelos negros soltos, bem cuidados",
        "extras": ["pés descalços", "celular na mão"],
    },
    {
        "roupa": "calça legging preta e camiseta larga da UFRJ",
        "cabelo": "cabelos negros presos em rabo baixo",
        "extras": ["visual doméstico confortável", "chinelo simples"],
    },
    {
        "roupa": "vestido caseiro curto de algodão",
        "cabelo": "cabelos negros soltos, com aparência natural",
        "extras": ["pulseira simples", "pés descalços"],
    },
]

VISUAIS_CASA_NOITE = [
    {
        "roupa": "shortinho de algodão e camiseta larga levemente caída em um ombro",
        "cabelo": "cabelos negros soltos, com aparência relaxada",
        "extras": ["pés descalços", "visual caseiro de fim de noite"],
    },
    {
        "roupa": "calcinha limpa e babydoll leve",
        "cabelo": "cabelos negros soltos, ainda úmidos nas pontas",
        "extras": ["pele recém-saída do banho", "visual íntimo e doméstico"],
    },
    {
        "roupa": "camiseta comprida usada como roupa de dormir",
        "cabelo": "cabelos negros presos de qualquer jeito, com fios soltos no rosto",
        "extras": ["pés descalços", "expressão cansada"],
    },
    {
        "roupa": "short de malha cinza e regata preta fina",
        "cabelo": "cabelos negros soltos sobre os ombros",
        "extras": ["chinelo baixo", "celular por perto"],
    },
]

VISUAIS_SOCIAL_NOITE_MALICIA = [
    {
        "roupa": "vestido preto justo acima dos joelhos e sandália de salto fino",
        "cabelo": "cabelos negros soltos, bem alinhados, com acabamento sensual",
        "extras": ["batom marcante", "perfume envolvente", "brincos pequenos"],
    },
    {
        "roupa": "saia preta curta, blusa de alcinha vinho e sandália de salto",
        "cabelo": "cabelos negros soltos, jogados para um lado",
        "extras": ["maquiagem marcante", "bolsa pequena"],
    },
    {
        "roupa": "macacão preto ajustado ao corpo e salto baixo elegante",
        "cabelo": "cabelos negros lisos e soltos, com brilho",
        "extras": ["perfume doce", "pulseira dourada discreta"],
    },
]

VISUAIS_SOCIAL_NOITE_FLERTE = [
    {
        "roupa": "vestido azul escuro de alcinha e sandália baixa elegante",
        "cabelo": "cabelos negros soltos, bem alinhados",
        "extras": ["maquiagem bonita", "colar discreto"],
    },
    {
        "roupa": "calça jeans escura, body preto e sandália de salto médio",
        "cabelo": "cabelos negros soltos, com volume natural",
        "extras": ["bolsa pequena", "batom suave"],
    },
    {
        "roupa": "saia jeans curta, blusa preta justa e sandália delicada",
        "cabelo": "cabelos negros presos em meio rabo, com fios soltos",
        "extras": ["brincos pequenos", "perfume leve"],
    },
]

VISUAIS_SOCIAL_NOITE_NEUTRO = [
    {
        "roupa": "vestido midi simples e sandália baixa",
        "cabelo": "cabelos negros soltos, bem cuidados",
        "extras": ["maquiagem equilibrada", "bolsa pequena"],
    },
    {
        "roupa": "calça pantalona preta, blusa clara de tecido leve e sandália discreta",
        "cabelo": "cabelos negros presos em coque baixo",
        "extras": ["brincos pequenos", "visual social discreto"],
    },
    {
        "roupa": "calça jeans escura, blusa de manga curta ajustada e sapatilha",
        "cabelo": "cabelos negros soltos, com aparência refinada",
        "extras": ["bolsa lateral", "batom claro"],
    },
]

VISUAIS_CARRO_UBER = [
    {
        "roupa": "calça jeans escura, baby look preta e tênis branco",
        "cabelo": "cabelos negros soltos, já marcados pelo movimento da noite",
        "extras": ["cinto afivelado", "bolsa no colo"],
    },
    {
        "roupa": "vestido curto casual e sandália baixa",
        "cabelo": "cabelos negros soltos sobre os ombros",
        "extras": ["celular na mão", "bolsa encostada na perna"],
    },
    {
        "roupa": "short jeans, blusa justa e jaqueta leve aberta",
        "cabelo": "cabelos negros presos de lado, com fios soltos",
        "extras": ["cinto de segurança cruzando o corpo", "visual já montado para sair"],
    },
]


def gerar_visual_automatico_mary(state: dict) -> str:
    """
    Gera o visual automático de Mary com atenção ao ENREDO ATUAL.

    Princípios:
    - mary_acao e plano_ativo vencem local genérico.
    - O visual descreve roupa/aparência, não cria destino novo.
    - Usa peças concretas, não descrições genéricas.
    - Contexto de saída/compromisso externo só vence quando for realmente atual.
    """
    if not isinstance(state, dict):
        return "Mary está com calça jeans escura, camiseta preta ajustada e tênis branco, cabelos negros soltos, bem cuidados."

    local = _texto_norm(state.get("local", ""))
    tempo = _texto_norm(state.get("tempo", ""))
    tom = _texto_norm(state.get("tom_manual_da_cena", ""))
    acao = _texto_norm(state.get("mary_acao", ""))
    plano = _texto_norm(state.get("plano_ativo", ""))
    eventos = _texto_norm(state.get("eventos_recentes", ""))
    fala_atual = _texto_norm(state.get("_fala_usuario_atual", ""))

    contexto_atual = "\n".join(
        [
            acao,
            plano,
            fala_atual,
            eventos,
            local,
            tempo,
        ]
    )

    # ======================================================
    # DETECTORES MAIS SEGUROS
    # ======================================================

    termos_faculdade_fortes = [
        "indo para a aula",
        "ir para a aula",
        "vou para a aula",
        "indo para faculdade",
        "ir para faculdade",
        "vou para faculdade",
        "indo para a faculdade",
        "ir para a faculdade",
        "vou para a faculdade",
        "indo para ufrj",
        "ir para ufrj",
        "vou para ufrj",
        "campus",
        "sala de aula",
        "cantina",
        "professor",
        "caderno",
        "livros",
        "mochila pronta",
        "pegar onibus para aula",
        "pegar onibus para faculdade",
        "restaurante universitario",
        "bandejao",
        "ir ao ru",
        "no ru",
        "para o ru",
    ]

    termos_faculdade_fracos = [
        "ufrj",
        "faculdade",
        "roupa da faculdade",
        "camiseta da ufrj",
        "baby look da ufrj",
        "blusa da ufrj",
    ]

    termos_compromisso_externo = [
        "saindo de casa",
        "sair de casa",
        "vou sair",
        "vamos sair",
        "indo para",
        "ir para",
        "ponto de onibus",
        "onibus",
        "mototaxi",
        "uber",
        "taxi",
        "bolsa",
        "chave",
        "porta",
        "rua",
        "calcar",
        "calcando",
        "tenis",
        "sapato",
        "sandalia",
        "compromisso",
        "trabalho",
        "curso",
        "reuniao",
        "encontro marcado",
        "almocar",
    ]

    termos_praia_reais = [
        "praia",
        "orla",
        "piscina",
        "beira-mar",
        "beira mar",
        "areia",
        "calcadao",
        "mergulho",
        "banho de mar",
        "canga",
        "biquini",
        "maio",
    ]

    termos_casa = [
        "casa",
        "apartamento",
        "apto",
        "quarto",
        "cozinha",
        "sala",
        "banheiro",
        "varanda",
    ]

    termos_banho = [
        "banho",
        "chuveiro",
        "toalha",
        "roupao",
        "sabonete",
        "molhada",
        "molhado",
        "umida",
        "se secando",
        "sair do banho",
        "pos-banho",
        "box",
    ]

    termos_sono_descanso = [
        "dormir",
        "deitar",
        "cama",
        "sono",
        "descansar",
        "pijama",
        "babydoll",
        "camisola",
        "travesseiro",
        "coberta",
        "apagar a luz",
        "antes de dormir",
    ]

    termos_noite_social = [
        "no bar",
        "para o bar",
        "restaurante",
        "balada",
        "boate",
        "clube",
        "festa",
        "jantar",
        "sugar baby",
    ]

    contexto_banho = any(t in contexto_atual for t in termos_banho)
    contexto_sono = any(t in contexto_atual for t in termos_sono_descanso)
    contexto_praia = any(t in contexto_atual for t in termos_praia_reais)
    contexto_casa = any(t in contexto_atual for t in termos_casa)
    contexto_noite_social = any(t in contexto_atual for t in termos_noite_social)

    contexto_faculdade_forte = any(t in contexto_atual for t in termos_faculdade_fortes)
    contexto_faculdade_fraco = any(t in contexto_atual for t in termos_faculdade_fracos)

    # Faculdade fraca não decide visual sozinha.
    contexto_faculdade = contexto_faculdade_forte

    contexto_compromisso_externo = any(t in contexto_atual for t in termos_compromisso_externo)

    # Se está claramente em banho/sono, isso vence referência fraca de faculdade.
    if contexto_banho or contexto_sono:
        contexto_faculdade = False
        contexto_compromisso_externo = False

    # Se só há UFRJ/camiseta/faculdade fraca, não vira roupa de aula.
    if contexto_faculdade_fraco and not contexto_faculdade_forte:
        contexto_faculdade = False

    # ======================================================
    # ESCOLHA DO VISUAL POR PRIORIDADE
    # ======================================================

    if contexto_banho:
        visual = _escolher_visual_estavel(VISUAIS_BANHO, state)

    elif contexto_sono:
        visual = _escolher_visual_estavel(VISUAIS_SONO_NOITE, state)

    elif contexto_faculdade:
        if "noite" in tempo or "22 horas" in tempo or "madrugada" in tempo:
            visual = _escolher_visual_estavel(VISUAIS_FACULDADE_NOITE, state)
        elif "manha" in tempo:
            visual = _escolher_visual_estavel(VISUAIS_FACULDADE_MANHA, state)
        elif "tarde" in tempo:
            visual = _escolher_visual_estavel(VISUAIS_FACULDADE_TARDE, state)
        else:
            visual = _escolher_visual_estavel(VISUAIS_FACULDADE_TARDE, state)

    elif contexto_compromisso_externo:
        visual = _escolher_visual_estavel(VISUAIS_SAIDA_URBANA, state)

    elif contexto_praia:
        if any(p in tempo for p in ["manha", "tarde", "dia"]):
            visual = _escolher_visual_estavel(VISUAIS_PRAIA_DIA, state)
        else:
            visual = _escolher_visual_estavel(VISUAIS_PRAIA_NOITE, state)

    elif contexto_noite_social:
        if "noite" in tempo or "madrugada" in tempo or "22 horas" in tempo:
            if tom == "malicia":
                visual = _escolher_visual_estavel(VISUAIS_SOCIAL_NOITE_MALICIA, state)
            elif tom == "flerte":
                visual = _escolher_visual_estavel(VISUAIS_SOCIAL_NOITE_FLERTE, state)
            else:
                visual = _escolher_visual_estavel(VISUAIS_SOCIAL_NOITE_NEUTRO, state)
        else:
            visual = _escolher_visual_estavel(VISUAIS_SAIDA_URBANA, state)

    elif any(p in local for p in ["carro", "uber", "taxi"]):
        visual = _escolher_visual_estavel(VISUAIS_CARRO_UBER, state)

    elif contexto_casa:
        if "manha" in tempo:
            visual = _escolher_visual_estavel(VISUAIS_CASA_MANHA, state)
        elif "noite" in tempo or "madrugada" in tempo or "22 horas" in tempo:
            visual = _escolher_visual_estavel(VISUAIS_CASA_NOITE, state)
        else:
            visual = _escolher_visual_estavel(VISUAIS_CASA_DIA, state)

    else:
        visual = _escolher_visual_estavel(VISUAIS_SAIDA_URBANA, state)

    roupa, cabelo, extras = _aplicar_visual(visual)

    # ======================================================
    # TRAVA DE COERÊNCIA CONTRA CONTRADIÇÃO
    # ======================================================

    if contexto_compromisso_externo or contexto_faculdade:
        texto_visual = _texto_norm(" ".join([roupa, cabelo, " ".join(extras)]))

        termos_incompativeis = [
            "biquini",
            "maio",
            "roupa de banho",
            "saida de praia",
            "roupao",
            "toalha",
            "babydoll",
            "camisola",
            "pijama",
            "chinelo de borracha",
            "corpo nu",
        ]

        if any(t in texto_visual for t in termos_incompativeis):
            visual = _escolher_visual_estavel(VISUAIS_SAIDA_URBANA, state)
            roupa, cabelo, extras = _aplicar_visual(visual)

    descricao = f"Mary está com {roupa}, {cabelo}"

    if extras:
        descricao += ", usando " + ", ".join(extras)

    descricao += "."

    return descricao


def resolver_visual_atual_mary(state: dict) -> str:
    """
    Resolve o visual atual.

    Regras:
    - Visual manual preenchido vence.
    - Se automático estiver ligado, gera visual a partir do enredo atual.
    - Se automático estiver desligado, preserva visual antigo se houver algo salvo.
    - Manual vazio não deve forçar visual antigo incoerente.
    """
    if not isinstance(state, dict):
        return "Mary está com calça jeans escura, camiseta preta ajustada e tênis branco, cabelos negros soltos, bem cuidados."

    visual_manual = str(state.get("visual_atual_manual", "") or "").strip()
    usar_auto = normalizar_bool(state.get("usar_visual_automatico", True), default=True)

    if visual_manual:
        return visual_manual

    if usar_auto:
        return gerar_visual_automatico_mary(state)

    visual_antigo = str(state.get("visual_atual", "") or "").strip()

    if visual_antigo:
        return visual_antigo

    return gerar_visual_automatico_mary(state)

def preparar_evento_inesperado_para_prompt(state: dict) -> str:
    """
    Prepara o bloco de evento inesperado para o prompt.

    O evento só aparece se:
    - existir texto de evento;
    - disparar_evento_inesperado estiver realmente ativo.
    """
    if not isinstance(state, dict):
        return ""

    evento = str(state.get("evento_inesperado", "") or "").strip()
    disparar = normalizar_bool(
        state.get("disparar_evento_inesperado", False),
        default=False,
    )

    if not evento or not disparar:
        return ""

    return f"""
[EVENTO INESPERADO]
{evento}

REGRAS:
- Evento inesperado é um gancho definido pelo roteirista.
- Se existir evento inesperado ativo, Mary deve reconhecê-lo como virada real da cena.
- Mary não deve ignorar o evento.
- Mary não deve resolver todas as consequências sozinha.
- Mary deve reagir ao evento com corpo, fala e emoção coerentes.
- O evento deve abrir uma nova tensão para o usuário continuar.
- Não transformar o evento em resumo longo.
- Não pular etapas importantes.
- Se o evento introduz novo personagem, Mary deve perceber a presença dele, mas não controlar ações dele além do que foi descrito.
- O evento deve aparecer neste turno como gancho narrativo concreto.
""".strip()


def consumir_evento_inesperado_se_usado(state: dict, resposta_gerada: bool = True) -> None:
    """
    Evita que o mesmo evento inesperado se repita em todos os turnos.

    Deve ser chamado depois de processar_turno(), apenas se houve resposta gerada.
    Se a chamada ao modelo falhar, não consome o evento.
    """
    if not isinstance(state, dict):
        return

    disparar = normalizar_bool(
        state.get("disparar_evento_inesperado", False),
        default=False,
    )

    if resposta_gerada and disparar:
        state["disparar_evento_inesperado"] = False
        state["evento_inesperado"] = ""


def sincronizar_facts_basicos(
    state: dict,
    recalcular_estado: bool = True,
) -> dict:
    """
    Sincroniza os facts básicos usados no prompt/debug.

    Importante:
    - Quando recalcular_estado=True, a função também normaliza o state.
    - Quando recalcular_estado=False, ela APENAS monta facts a partir do state atual.

    Use:
    - recalcular_estado=True quando quiser preparar/reorganizar o state.
    - recalcular_estado=False dentro de montar_prompt_para_modelo() e antes de salvar,
      para não sobrescrever scene_stage, mary_intent, privacidade, aftercare,
      clímax, alivio_rapido etc.
    """
    if not isinstance(state, dict):
        state = {}

    # ======================================================
    # NORMALIZAÇÃO OPCIONAL DO STATE
    # Só deve acontecer quando explicitamente permitido.
    # ======================================================
    if recalcular_estado:
        # Primeiro limpa booleanos crus.
        normalizar_flags_booleanas_state(state)

        # normalizar_estado já chama derivar_controles_de_cena(),
        # e derivar_controles_de_cena já normaliza relação no ponto correto.
        normalizar_estado(state)

        # Não chamar normalizar_relacao_por_interlocutor aqui,
        # pois isso pode sobrescrever o tom manual aplicado em derivar_controles_de_cena().
        resetar_progressao_fisica_se_cena_neutra_sozinha(state)
        limpar_acao_incompativel_com_janio_ausente(state)
        limpar_acao_incompativel_com_interlocutor_foco(state)

        # ======================================================
        # DIRETRIZ AUTÔNOMA FINAL
        # Só recalcula quando recalcular_estado=True.
        # ======================================================
        fala_atual = str(state.get("_fala_usuario_atual", "") or "")

        try:
            definir_acao_autonoma(state, fala_atual)
        except NameError:
            state["mary_autonomous_action"] = str(
                state.get("mary_autonomous_action", "") or ""
            )

    # ======================================================
    # CAMPOS DERIVADOS QUE PODEM SER ATUALIZADOS SEM
    # REPROCESSAR TODA A CENA.
    # ======================================================
    state["visual_atual"] = resolver_visual_atual_mary(state)
    estado_emocional_resolvido = resolver_estado_emocional_mary(state)

    climax_usuario_detectado = detectar_climax_usuario(
        state.get("_fala_usuario_atual", "")
    )

    perfil_temporal = inferir_perfil_temporal_e_risco_interacao(
            state,
            state.get("_fala_usuario_atual", ""),
        )

    facts = {
        "perfil_temporal_interlocutor": perfil_temporal,
        "local": state.get("local", "quarto"),
        "tempo": state.get("tempo", "noite"),
        "interlocutor": state.get("interlocutor", "Janio Doniseti"),
        "interlocutor_foco_turno": state.get(
            "interlocutor_foco_turno",
            state.get(
                "interlocutor_ativo_persistente",
                state.get("interlocutor", ""),
            ),
        ),
        "usuario_real": state.get("usuario_real", "Janio Doniseti"),
        "janio_status_na_cena": state.get("janio_status_na_cena", "presente"),
        "interlocutor_ativo_persistente": state.get(
            "interlocutor_ativo_persistente",
            state.get("interlocutor", "Janio Doniseti"),
        ),
        "ultimo_interlocutor_explicito": state.get(
            "ultimo_interlocutor_explicito",
            state.get("interlocutor", "Janio Doniseti"),
        ),

        # Relação já normalizada dentro de derivar_controles_de_cena().
        "relacao": state.get("relacao", "contextual"),

        "tipo_de_cena": state.get("tipo_de_cena", "natural_amizade"),
        "privacidade": state.get(
            "privacidade",
            get_privacidade_por_local(state.get("local", "")),
        ),
        "estilo_de_iniciativa": state.get("estilo_de_iniciativa", "contextual"),
        "mary_acao": state.get("mary_acao", ""),
        "visual_atual": state.get("visual_atual", ""),
        "estado_emocional": estado_emocional_resolvido,
        "usar_visual_automatico": normalizar_bool(
            state.get("usar_visual_automatico", True),
            default=True,
        ),
        "visual_atual_manual": state.get("visual_atual_manual", ""),
        "evento_inesperado": state.get("evento_inesperado", ""),
        "disparar_evento_inesperado": normalizar_bool(
            state.get("disparar_evento_inesperado", False),
            default=False,
        ),
        "tom_manual_da_cena": state.get("tom_manual_da_cena", "Natural / Amizade"),
        "tom_da_cena": state.get("tom_da_cena", "sensual carinhoso"),

        # Campos narrativos avançados.
        "segredo_ativo": state.get("segredo_ativo", ""),
        "plano_ativo": state.get("plano_ativo", ""),
        "eventos_recentes": state.get("eventos_recentes", ""),
        "mentiras_desculpas": state.get("mentiras_desculpas", ""),
        "memorias_ocultas_itens_guardados": state.get(
            "memorias_ocultas_itens_guardados",
            "",
        ),
        "modo_surpresa": state.get("modo_surpresa", "Desligado"),
        "direcao_surpresa": state.get("direcao_surpresa", ""),

        "limite_ambiente": state.get("limite_ambiente", ""),
        "modo_relacional": state.get("modo_relacional", "ambiguo"),
        "physical_phase": safe_int(state.get("physical_phase", 0), 0),
        "scene_stage": state.get("scene_stage", "inicio"),
        "mary_intent": state.get("mary_intent", "presenca_viva"),
        "mary_autonomous_action": str(
            state.get("mary_autonomous_action", "") or ""
        ),

        "toque_provocativo_permitido": normalizar_bool(
            state.get("toque_provocativo_permitido", False),
            default=False,
        ),
        "force_resolution_now": normalizar_bool(
            state.get("force_resolution_now", False),
            default=False,
        ),
        "mary_pre_orgasm_signals": normalizar_bool(
            state.get("mary_pre_orgasm_signals", False),
            default=False,
        ),
        "mary_stimulation_turns": safe_int(
            state.get("mary_stimulation_turns", 0),
            0,
        ),
        "mary_climax_done": normalizar_bool(
            state.get("mary_climax_done", False),
            default=False,
        ),
        "user_climax_done": normalizar_bool(
            state.get("user_climax_done", False),
            default=False,
        ),
        "partner_climax_pending": normalizar_bool(
            state.get("partner_climax_pending", False),
            default=False,
        ),

        # Mantém compatibilidade:
        # - climax_usuario_sinal vira bool;
        # - climax_usuario_tipo guarda "aviso", "em_andamento" ou "nenhum".
        "climax_usuario_sinal": climax_usuario_detectado != "nenhum",
        "climax_usuario_tipo": climax_usuario_detectado,

        "toque_intimo_permitido": normalizar_bool(
            state.get("toque_intimo_permitido", False),
            default=False,
        ),
        "tensao_romantica_com_interlocutor": normalizar_bool(
            state.get("tensao_romantica_com_interlocutor", False),
            default=False,
        ),
        "amor_genuino_com_interlocutor": amor_genuino_com_interlocutor(state),

        "alivio_rapido_permitido": normalizar_bool(
            state.get("alivio_rapido_permitido", False),
            default=False,
        ),

        # Flags úteis para debug do novo fluxo.
        "mary_reacao_climax_parceiro": state.get(
            "mary_reacao_climax_parceiro",
            "",
        ),
        "mary_frustracao_climax": state.get(
            "mary_frustracao_climax",
            "",
        ),
        "destino_climax_parceiro": state.get(
            "destino_climax_parceiro",
            "",
        ),
    }

    state["facts"] = facts
    return facts


def aplicar_facts_no_state(state: dict, facts: dict) -> None:
    """
    Aplica facts de volta no state com segurança.

    Regras:
    - Só aplica campos não vazios.
    - Normaliza booleanos antes de recalcular estado.
    - Não chama normalizar_relacao_por_interlocutor diretamente aqui,
      porque isso pode sobrescrever o tom manual já aplicado em derivar_controles_de_cena().
    - Ao final, sincroniza facts novamente para manter state["facts"] coerente.
    """
    if not isinstance(state, dict):
        return

    if not isinstance(facts, dict):
        return

    campos = [
        "local",
        "tempo",
        "interlocutor",
        "interlocutor_foco_turno",
        "interlocutor_ativo_persistente",
        "ultimo_interlocutor_explicito",
        "usuario_real",
        "janio_status_na_cena",
        "relacao",
        "tipo_de_cena",
        "privacidade",
        "estilo_de_iniciativa",
        "mary_acao",
        "visual_atual",
        "estado_emocional",
        "tom_manual_da_cena",
        "tom_da_cena",
        "segredo_ativo",
        "plano_ativo",
        "eventos_recentes",
        "mentiras_desculpas",
        "memorias_ocultas_itens_guardados",
        "modo_surpresa",
        "direcao_surpresa",
        "usar_visual_automatico",
        "visual_atual_manual",
        "evento_inesperado",
        "disparar_evento_inesperado",
        "limite_ambiente",
        "modo_relacional",
        "physical_phase",
        "scene_stage",
        "mary_intent",
        "force_resolution_now",
        "mary_pre_orgasm_signals",
        "mary_stimulation_turns",
        "mary_climax_done",
        "user_climax_done",
        "partner_climax_pending",
        "toque_intimo_permitido",
        "tensao_romantica_com_interlocutor",
    ]

    for campo in campos:
        valor = facts.get(campo, None)

        if valor not in ("", None):
            state[campo] = valor

    # Defaults seguros
    if not state.get("modo_surpresa"):
        state["modo_surpresa"] = "Desligado"

    if not state.get("direcao_surpresa"):
        state["direcao_surpresa"] = ""

    if not state.get("estado_emocional"):
        state["estado_emocional"] = "Automático"

    if not state.get("tom_manual_da_cena"):
        state["tom_manual_da_cena"] = "Neutro"

    if not state.get("eventos_recentes"):
        state["eventos_recentes"] = ""

    if not state.get("mentiras_desculpas"):
        state["mentiras_desculpas"] = "" 

    if not state.get("memorias_ocultas_itens_guardados"):
        state["memorias_ocultas_itens_guardados"] = ""

    # Normalização de tipos antes de recalcular estado
    normalizar_flags_booleanas_state(state)

    state["physical_phase"] = safe_int(state.get("physical_phase", 0), 0)
    state["mary_stimulation_turns"] = safe_int(
        state.get("mary_stimulation_turns", 0),
        0,
    )

    # Fluxo final:
    # sincronizar_facts_basicos já chama normalizar_estado()
    # e normalizar_estado já chama derivar_controles_de_cena().
    # Não chamar normalizar_relacao_por_interlocutor aqui.
    sincronizar_facts_basicos(state, recalcular_estado=False)


def formatar_shared_memories_para_prompt(memories: list[dict], limite: int = 20) -> str:
    if not memories:
        return "Nenhuma memória shared ativa."

    linhas = []

    for m in memories[:limite]:
        if isinstance(m, dict):
            memoria = str(m.get("memoria", "") or "").strip()
            tipo = str(m.get("tipo", "shared") or "shared").strip()
        else:
            memoria = str(m or "").strip()
            tipo = "shared"

        if memoria:
            linhas.append(f"- [{tipo}] {memoria}")

    return "\n".join(linhas) if linhas else "Nenhuma memória shared ativa."


def formatar_canon_mary_para_prompt(canon: list[dict], limite: int = 30) -> str:
    if not canon:
        return "Nenhum cânone fixo cadastrado."

    linhas = []

    for item in canon[:limite]:
        if isinstance(item, dict):
            categoria = str(item.get("categoria", "geral") or "geral").strip()
            fato = str(item.get("fato", "") or "").strip()
        else:
            categoria = "geral"
            fato = str(item or "").strip()

        if fato:
            linhas.append(f"- [{categoria}] {fato}")

    return "\n".join(linhas) if linhas else "Nenhum cânone fixo cadastrado."


def formatar_physical_signature_para_prompt(state: dict) -> str:
    if not isinstance(state, dict):
        return "- Mary tem presença física marcante, olhar expressivo e magnetismo próprio."

    assinatura = state.get("physical_signature")

    if not isinstance(assinatura, dict):
        return "- Mary tem presença física marcante, olhar expressivo e magnetismo próprio."

    linhas = []

    for chave, valor in assinatura.items():
        valor = str(valor or "").strip()

        if valor:
            linhas.append(f"- {chave}: {valor}")

    return "\n".join(linhas) if linhas else "- Mary tem presença física marcante, olhar expressivo e magnetismo próprio."




# ==========================================================
# ESTADO INICIAL
# ==========================================================

def init_state() -> dict:
    estado_inicial = {
        "personagem": "Mary",
        "timeline": "universitaria_creator",

        # ======================================================
        # CENA BASE
        # ======================================================
        "local": "quarto",
        "tempo": "noite",
        "interlocutor": "Janio Doniseti",
        "interlocutor_foco_turno": "Janio Doniseti",
        "interlocutor_ativo_persistente": "Janio Doniseti",
        "ultimo_interlocutor_explicito": "Janio Doniseti",
        "usuario_real": "Janio Doniseti",
        "janio_status_na_cena": "presente",

        # Não usar "romance" como default rígido.
        # A relação será corrigida por derivar_controles_de_cena().
        "relacao": "contextual",

        "tipo_de_cena": "intima privada",
        "privacidade": "privado",
        "estilo_de_iniciativa": "contextual",

        # ======================================================
        # ESTADO ATUAL DE MARY
        # ======================================================
        "mary_acao": "Mary está próxima de Janio, olhando para ele com curiosidade.",
        "estado_emocional": "Automático",
        "tom_manual_da_cena": "Intimidade",
        "tom_da_cena": "íntimo e direto",

        # ======================================================
        # VISUAL
        # ======================================================
        "usar_visual_automatico": True,
        "visual_atual_manual": "",
        "visual_atual": "",

        # ======================================================
        # EVENTOS / SURPRESAS / PENDÊNCIAS
        # ======================================================
        "segredo_ativo": "",
        "plano_ativo": "",
        "eventos_recentes": "",
        "mentiras_desculpas": "",
        "memorias_ocultas_itens_guardados": "",
        "evento_inesperado": "",
        "disparar_evento_inesperado": False,
        "modo_surpresa": "Desligado",
        "direcao_surpresa": "",

        # ======================================================
        # CONTROLES DERIVADOS
        # ======================================================
        "modo": "privado",
        "limite_ambiente": "",
        "modo_relacional": "contextual",
        "tensao_romantica_com_interlocutor": False,
        "toque_intimo_permitido": False,

        # ======================================================
        # HISTÓRICO / MEMÓRIA
        # ======================================================
        "turno": 0,
        "history": [],
        "canon_mary": [],
        "facts": {},
        "shared_memories": [],

        # ======================================================
        # PROGRESSÃO FÍSICA / EMOCIONAL
        # ======================================================
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
        "partner_climax_pending": False,
        "mary_pre_orgasm_signals": False,
        "mary_stimulation_turns": 0,

        # ======================================================
        # ASSINATURA FÍSICA FIXA
        # ======================================================
        "physical_signature": {
            "altura": "aproximadamente 1,68m",
        
            "corpo": (
                "corpo feminino curvilíneo, marcante e muito desejável; "
                "cintura bem desenhada, barriga firme, seios médios a fartos, naturais e bem projetados, "
                "quadril largo, bumbum carnudo, firme, cheio e naturalmente empinado, "
                "coxas grossas, torneadas e firmes; presença corporal forte, sensual "
                "e impossível de ignorar"
            ),
        
            "seios": (
                "seios médios a fartos, naturais, firmes e bem projetados, "
                "com caimento bonito e presença evidente em roupas justas, tops, babydolls, biquínis "
                "ou cenas de proximidade; fazem parte da sensualidade visual de Mary sem parecer artificiais"
            ),
                    
            "pele": (
                "pele bem cuidada, com aparência natural, toque visual quente "
                "e viço perceptível em cenas de luz, suor, banho, sol ou proximidade"
            ),
        
            "cabelos": (
                "cabelos negros, longos, densos e pesados, geralmente soltos, "
                "caindo sobre os ombros, busto, seios, costas ou cintura conforme a posição; "
                "podem ser moldados pela cena, mas nunca devem perder a assinatura negra e longa"
            ),
        
            "olhos": (
                "olhos verdes expressivos, atentos e magnéticos; olhar vivo, provocante "
                "ou vulnerável conforme a emoção da cena"
            ),
        
            "rosto": (
                "rosto bonito, jovem, expressivo e natural, sem aparência artificial; "
                "traços suaves, presença feminina marcante e sensualidade no olhar e na boca"
            ),
        
            "presenca": (
                "Mary chama atenção pelo conjunto: cabelos negros longos, olhos verdes magnéticos, "
                "rosto bonito, seios naturais bem projetados, cintura marcada, quadril largo, "
                "bumbum carnudo e empinado, coxas fortes e postura de quem sabe o efeito que causa "
                "quando entra, senta, se inclina, ajeita o cabelo, cruza as pernas ou vira de costas"
            ),
        
            "assinatura": (               
                "Mary nunca deve parecer comum, apagada, magra demais, frágil ou genérica. "
                "Sua presença física deve ser percebida mesmo em cenas sociais: uma mulher jovem, "
                "curvilínea, sensual, viva, com olhos verdes expressivos, seios naturais marcantes, "
                "cintura desenhada, quadril cheio, bumbum carnudo e empinado, coxas grossas, "
                "corpo memorável, magnetismo físico evidente e consciência do próprio impacto"
            ),
        },
    }

    if "mary_state_minimo" not in st.session_state:
        st.session_state.mary_state_minimo = dict(estado_inicial)

    state = st.session_state.mary_state_minimo

    # ======================================================
    # GARANTE NOVOS CAMPOS SEM APAGAR ESTADO EXISTENTE
    # ======================================================
    for k, v in estado_inicial.items():
        state.setdefault(k, v)

    # ======================================================
    # CARREGA HISTÓRICO SALVO
    # ======================================================
    if not state.get("history"):
        history_salvo = carregar_history_cache(MAX_HISTORY * 2)

        if history_salvo:
            state["history"] = history_salvo
            state["turno"] = max(1, len(history_salvo) // 2)

    # ======================================================
    # CARREGA FACTS SALVOS
    # ======================================================
    if not state.get("facts"):
        facts_salvos = carregar_facts_cache()

        if facts_salvos:
            aplicar_facts_no_state(state, facts_salvos)

    # ======================================================
    # NORMALIZAÇÃO CENTRAL
    # Ordem importante:
    # - normalizar_flags_booleanas_state corrige TRUE/FALSE textuais.
    # - sincronizar_facts_basicos chama normalizar_estado().
    # - normalizar_estado chama derivar_controles_de_cena().
    # - derivar_controles_de_cena chama normalizar_relacao_por_interlocutor()
    #   no ponto correto, antes dos presets do tom manual.
    #
    # Portanto, NÃO chamar aqui:
    # - normalizar_relacao_por_interlocutor(state)
    # - 
    # - normalizar_estado(state)
    # de forma separada, para evitar sobrescrita duplicada.
    # ======================================================
    normalizar_flags_booleanas_state(state)
    sincronizar_facts_basicos(state, recalcular_estado=False)

    # ======================================================
    # CARREGA MEMÓRIAS E CÂNONE
    # ======================================================
    if not state.get("shared_memories"):
        state["shared_memories"] = carregar_shared_memories_cache(apenas_ativas=True)

    if not state.get("canon_mary"):
        state["canon_mary"] = carregar_canon_mary_cache(apenas_ativos=True)

    return state


# ==========================================================
# ENGINE SIMPLES
# ==========================================================

def atualizar_psique_e_fase(state: dict, fala_usuario: str, resposta_limpa: str) -> None:
    """
    Atualiza níveis emocionais e fase física básica com base no turno.

    Importante:
    - Detecta aproximação, toque e beijo.
    - Não resolve pico/clímax.
    - Não sobrescreve relação nem tom manual.
    - Respeita limite de privacidade.
    - Normaliza scene_stage e mary_intent no final.
    """
    if not isinstance(state, dict):
        return

    texto = _texto_norm(f"{fala_usuario or ''}\n{resposta_limpa or ''}")

    desejo = safe_float(state.get("desire_level", 0.18), 0.18)
    tensao = safe_float(state.get("tension_level", 0.12), 0.12)
    conexao = safe_float(state.get("connection_level", 0.22), 0.22)

    # ======================================================
    # BLOQUEIOS DE FALSOS POSITIVOS
    # ======================================================
    falsos_toques = [
        "toque do celular",
        "toque de celular",
        "toque da campainha",
        "toque a campainha",
        "toque o sino",
        "toque de mensagem",
        "toque musical",
        "toque de recolher",
        "tocou no assunto",
        "tocar no assunto",
        "mao de obra",
        "perna da mesa",
        "boca da garrafa",
        "boca do fogao",
        "costas do caderno",
        "borda da pagina",
    ]

    tem_falso_toque = _tem_algum(texto, falsos_toques)

    # ======================================================
    # SINAIS EMOCIONAIS / CONEXÃO
    # ======================================================
    if _tem_algum(texto, ["calma", "devagar", "cuidado", "foi so", "avancei demais", "sem pressa"]):
        conexao += 0.10
        tensao = max(0.05, tensao - 0.05)

    if _tem_algum(texto, ["gosto", "confio", "carinho", "amor", "cuidado", "fica comigo"]):
        conexao += 0.10

    if _tem_algum(texto, ["tesao", "desejo", "vontade", "excitado", "excitada"]):
        desejo += 0.08

    # ======================================================
    # DETECÇÃO CONTEXTUAL DE CONTATO FÍSICO
    # Não basta palavra solta. Precisa haver gesto + alvo corporal.
    # ======================================================
    verbos_fisicos = [
        "toco",
        "toquei",
        "tocar",
        "encosto",
        "encostei",
        "encostar",
        "seguro",
        "segurei",
        "segurar",
        "pego",
        "peguei",
        "pegar",
        "acaricio",
        "acariciei",
        "acariciar",
        "puxo",
        "puxei",
        "puxar",
        "abraco",
        "abracei",
        "abracar",
        "aperto",
        "apertei",
        "apertar",
    ]

    partes_corpo = [
        "mao",
        "rosto",
        "cabelo",
        "cabelos",
        "ombro",
        "ombros",
        "braco",
        "bracos",
        "costas",
        "cintura",
        "quadril",
        "perna",
        "pernas",
        "coxa",
        "coxas",
        "pescoco",
        "boca",
        "labios",
        "peito",
        "seios",
        "barriga",
        "ventre",
    ]

    tem_verbo_fisico = _tem_algum(texto, verbos_fisicos)
    tem_parte_corpo = _tem_algum(texto, partes_corpo)

    tem_toque_fisico = (
        not tem_falso_toque
        and tem_verbo_fisico
        and tem_parte_corpo
    )

    sinais_beijo = [
        "beijo sua boca",
        "beijo seus labios",
        "beijo seu rosto",
        "beijo seu pescoco",
        "beijo sua testa",
        "beijo sua mao",
        "ela beija",
        "mary beija",
        "nos beijamos",
    ]

    tem_beijo_real = _tem_algum(texto, sinais_beijo)

    sinais_aproximacao = [
        "chego perto",
        "cheguei perto",
        "me aproximo",
        "aproximo meu corpo",
        "ela se aproxima",
        "mary se aproxima",
        "inclino meu rosto",
        "inclino o corpo",
        "olho nos olhos",
        "olhar nos olhos",
    ]

    tem_aproximacao_real = _tem_algum(texto, sinais_aproximacao)

    # ======================================================
    # TENSÃO / DESEJO / CONEXÃO
    # ======================================================
    if tem_aproximacao_real:
        tensao += 0.03

    if tem_toque_fisico:
        tensao += 0.06

    if tem_beijo_real:
        tensao += 0.08
        desejo += 0.04

    # ======================================================
    # FASE
    # ======================================================
    fase = safe_int(state.get("physical_phase", 0), 0)

    if tem_aproximacao_real:
        fase = max(fase, 1)

    if tem_toque_fisico:
        fase = max(fase, 2)

    if tem_beijo_real:
        fase = max(fase, 3)

    # ======================================================
    # LIMITE CENTRALIZADO POR PRIVACIDADE
    # ======================================================
    privacidade = _texto_norm(state.get("privacidade", ""))

    fase = min(
        fase,
        limite_fase_por_privacidade(privacidade),
    )

    # ======================================================
    # GRAVA NÍVEIS
    # ======================================================
    state["desire_level"] = clamp(desejo)
    state["tension_level"] = clamp(tensao)
    state["connection_level"] = clamp(conexao)

    state["physical_phase"] = fase

    # ======================================================
    # STAGE PADRONIZADO POR FASE
    # Mantém compatibilidade com os stages usados no restante do script.
    # ======================================================
    mapa_stage = {
        0: "inicio",
        1: "aproximacao",
        2: "toque",
        3: "intimidade",
        4: "sexo_ou_estimulo",
        5: "pre_pico_mary",
        6: "pico_mary",
        7: "aftercare",
    }

    state["scene_stage"] = normalizar_scene_stage(
        mapa_stage.get(fase, state.get("scene_stage", "inicio")),
        padrao="inicio",
    )

    # ======================================================
    # INTENÇÃO PADRÃO QUANDO A FUNÇÃO AVANÇA A FASE
    # Não sobrescreve intenção forte já definida por outro motor.
    # ======================================================
    intent_atual = str(state.get("mary_intent", "") or "").strip()

    if not intent_atual:
        if fase >= 5:
            state["mary_intent"] = "sustentar_tensao_intensa"
        elif fase >= 3:
            state["mary_intent"] = "aproximar_com_intimidade"
        elif fase >= 1:
            state["mary_intent"] = "flerte_consciente"
        else:
            state["mary_intent"] = "responder_com_naturalidade"

    state["mary_intent"] = normalizar_mary_intent(
        state.get("mary_intent", ""),
        padrao="responder_com_naturalidade",
    )

    # ======================================================
    # NORMALIZAÇÃO FINAL LEVE
    # Não chama sincronizar_facts_basicos aqui para evitar ciclo:
    # sincronizar_facts_basicos -> normalizar_estado -> derivar_controles...
    # ======================================================
    normalizar_flags_booleanas_state(state)

def resetar_climax_se_nova_sequencia_intima(state: dict, fala_usuario: str = "") -> None:
    """
    Reseta flags de clímax quando uma nova sequência íntima começa
    e não há verbalização clara de orgasmo no turno atual.

    Evita que mary_climax_done/user_climax_done herdados de cena anterior
    bloqueiem o disparo do orgasmo nesta nova cena.
    """
    if not isinstance(state, dict):
        return

    texto = remover_acentos(str(fala_usuario or "").lower())

    tipo = remover_acentos(str(state.get("tipo_de_cena", "") or "").lower())
    tom = remover_acentos(str(state.get("tom_manual_da_cena", "") or "").lower())
    privacidade = remover_acentos(str(state.get("privacidade", "") or "").lower())
    acao = remover_acentos(str(state.get("mary_acao", "") or "").lower())

    cena_intima = (
        tipo == "intimidade"
        or tom == "intimidade"
        or privacidade == "privado"
    )

    ha_estimulo_atual = any(palavra in (texto + " " + acao) for palavra in [
        "penetra",
        "penetracao",
        "estoca",
        "estocada",
        "flop",
        "foder",
        "fodendo",
        "sexo",
        "oral",
        "chupa",
        "chupando",
        "clitoris",
        "buceta",
        "dedo",
        "masturb",
        "friccao",
        "encaixa",
        "entrada",
        "vara",
        "pau",
    ])

    verbalizou_climax_mary = any(p in texto for p in [
        "mary gozou",
        "mary esta gozando",
        "mary está gozando",
        "eu gozei",
        "estou gozando",
        "tô gozando",
        "to gozando",
        "gozei",
    ])

    verbalizou_climax_usuario = any(p in texto for p in [
        "eu gozei",
        "gozei",
        "estou gozando",
        "tô gozando",
        "to gozando",
        "vou gozar",
        "gozando",
        "explodi",
        "terminei",
    ])

    if cena_intima and ha_estimulo_atual and not verbalizou_climax_mary:
        # Se a cena está em estímulo ativo e Mary não verbalizou clímax,
        # não permita que um true herdado bloqueie o gate.
        state["mary_climax_done"] = False

    if cena_intima and ha_estimulo_atual and not verbalizou_climax_usuario:
        # O usuário também não deve ser marcado como concluído por inferência.
        state["user_climax_done"] = False

def preparar_climax_parceiro_mary(state: dict, fala_usuario: str) -> None:
    """
    Prepara a reação de Mary ao clímax do parceiro.

    Camadas:
    - mary_reacao_climax_parceiro: define a conduta principal da resposta.
    - mary_frustracao_climax: adiciona frustração/controle quando Mary ainda não gozou.

    Diferença essencial:
    - "vou gozar" = aviso; ainda dá tempo de Mary conduzir.
    - "estou gozando" / "gozei" = já começou; Mary reage ao que está acontecendo.
    """
    if not isinstance(state, dict):
        return

    state["mary_reacao_climax_parceiro"] = ""
    state["mary_frustracao_climax"] = ""

    tom = normalizar_tom_manual_cena(state.get("tom_manual_da_cena", ""))
    if tom != "Nsfw":
        return

    sinal = detectar_climax_usuario(fala_usuario)
    if sinal == "nenhum":
        return

    mary_done = normalizar_bool(
        state.get("mary_climax_done", False),
        default=False,
    )

    force_resolution_now = normalizar_bool(
        state.get("force_resolution_now", False),
        default=False,
    )

    mary_pre_orgasm = normalizar_bool(
        state.get("mary_pre_orgasm_signals", False),
        default=False,
    )

    privacidade = _texto_norm(state.get("privacidade", ""))
    toque_intimo = normalizar_bool(
        state.get("toque_intimo_permitido", False),
        default=False,
    )

    alivio_rapido = normalizar_bool(
        state.get("alivio_rapido_permitido", False),
        default=False,
    )

    scene_stage = normalizar_scene_stage(
        state.get("scene_stage", ""),
        padrao="inicio",
    )

    mary_acao = _texto_norm(state.get("mary_acao", ""))
    fala_norm = _texto_norm(fala_usuario)

    cena_em_ato = (
        toque_intimo
        or alivio_rapido
        or scene_stage in (
            "sexo_ou_estimulo",
            "estimulo_corporal",
            "pre_pico_mary",
            "pico_mary",
            "alivio_rapido",
            "intensidade_contida",
        )
        or any(
            termo in mary_acao
            for termo in (
                "sexo oral",
                "boquete",
                "chupando",
                "penetração",
                "penetracao",
                "masturb",
                "rebolando",
                "de quatro",
                "montada",
                "deitada",
                "colo",
                "encaixe",
            )
        )
    )

    if not cena_em_ato:
        return

    # ======================================================
    # 1) PARCEIRO AVISOU: ainda dá tempo de Mary conduzir.
    # ======================================================
    if sinal == "aviso":
        state["climax_usuario_sinal"] = True
        state["user_climax_done"] = False

        if mary_done:
            state["mary_reacao_climax_parceiro"] = "conduzir_apos_pico_mary"
            state["mary_frustracao_climax"] = ""
            state["partner_climax_pending"] = True
            state["mary_intent"] = "conduzir_climax_do_parceiro"
            return

        # Mary ainda não gozou.
        state["mary_reacao_climax_parceiro"] = "controlar_antes_pico_mary"
        state["mary_frustracao_climax"] = "controlar_ritmo"
        state["partner_climax_pending"] = True
        state["user_climax_done"] = False
        state["mary_intent"] = "sustentar_tensao_intensa"

        if force_resolution_now or mary_pre_orgasm:
            state["scene_stage"] = "pre_pico_mary"
            state["physical_phase"] = max(
                safe_int(state.get("physical_phase", 4), 4),
                5,
            )

        return

    # ======================================================
    # 2) PARCEIRO JÁ COMEÇOU: Mary não muda tarde demais.
    # ======================================================
    if sinal == "em_andamento":
        state["climax_usuario_sinal"] = True
        state["user_climax_done"] = True
        state["partner_climax_pending"] = False

        if mary_done:
            state["mary_reacao_climax_parceiro"] = "reagir_climax_em_andamento"
            state["mary_frustracao_climax"] = ""
            state["mary_intent"] = "acolher_climax_do_parceiro"
            return

        # Mary ainda não gozou.
        state["mary_reacao_climax_parceiro"] = "reagir_climax_em_andamento_antes_pico_mary"
        state["mary_frustracao_climax"] = "frustrada_parceiro_gozou_antes"
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False
        state["scene_stage"] = "desaceleracao"
        state["mary_intent"] = "desacelerar_com_presenca"
        state["physical_phase"] = max(
            safe_int(state.get("physical_phase", 4), 4),
            5,
        )
        return

def render_reacao_climax_parceiro_apos_pico_mary(state: dict) -> str:
    """
    Renderiza a reação de Mary quando o parceiro avisa que vai gozar
    ou quando o clímax do parceiro já está em andamento.

    Apesar do nome antigo mencionar "apos_pico_mary", esta função agora
    cobre também quando Mary ainda NÃO gozou.

    Depende de:
    - state["mary_reacao_climax_parceiro"]
    """
    modo = str(state.get("mary_reacao_climax_parceiro", "") or "").strip()

    if not modo:
        return ""

    # ======================================================
    # 1) MARY AINDA NÃO GOZOU — PARCEIRO AVISOU ANTES
    # ======================================================
    if modo == "controlar_antes_pico_mary":
        return """
[REAÇÃO AO CLÍMAX DO PARCEIRO - MARY AINDA NÃO GOZOU]

Mary ainda não atingiu o próprio pico.
O parceiro avisou que vai gozar, mas ainda há tempo de Mary reagir.

REGRA CENTRAL:
- Mary NÃO deve agir como se tudo estivesse resolvido.
- Mary NÃO deve entrar em aftercare pleno.
- Mary pode mandar segurar, diminuir o ritmo, controlar o corpo dele ou orientar o destino.
- Se Mary estiver quase, ela deve tentar impedir que ele termine sozinho.
- Se Mary não estiver quase, ela pode decidir entre mandar segurar ou orientar para fora/dentro conforme a cena.

TOM:
- urgente;
- direto;
- corporal;
- provocante;
- sem discurso longo.

FALAS POSSÍVEIS:
- "Espera..."
- "Ainda não..."
- "Segura mais um pouco..."
- "Não acaba antes de mim..."
- "Calma... me espera..."
- "Tira... agora..."
- "Fora... vai..."
- "Não tira..."
- "Fica..."
- "Dentro... se for agora, fica..."

REGRA DE DESTINO:
- Se a posição favorece finalizar fora, Mary pode pedir para tirar e finalizar no corpo dela.
- Se a cena é privada, íntima e ela quer manter proximidade, Mary pode pedir para continuar dentro.
- Se ela está quase chegando ao próprio pico, a prioridade é mandar segurar ou acompanhar o ritmo dela.

PROIBIDO:
- tratar como se Mary já tivesse gozado;
- transformar automaticamente em aftercare;
- fazer Mary gozar sem force_resolution_now;
- ignorar o aviso do parceiro;
- responder com narração longa antes da fala.

REGRA FINAL:
Se Mary ainda não gozou e o parceiro diz "vou gozar", Mary reage imediatamente com comando curto: segura, tira, fica ou espera.
""".strip()

    # ======================================================
    # 2) MARY AINDA NÃO GOZOU — PARCEIRO JÁ COMEÇOU
    # ======================================================
    if modo == "reagir_climax_em_andamento_antes_pico_mary":
        return """
[REAÇÃO AO CLÍMAX DO PARCEIRO EM ANDAMENTO - MARY AINDA NÃO GOZOU]

Mary ainda não atingiu o próprio pico.
O parceiro já começou a gozar ou declarou que está gozando.

REGRA CENTRAL:
- Mary entende que já começou.
- Ela NÃO tenta mudar o destino tarde demais.
- Ela reage ao que está acontecendo.
- Se Mary não gozou, manter sensação de interrupção, desejo inacabado ou provocação.
- Não resolver o pico dela automaticamente.

TOM:
- surpresa;
- provocação;
- frustração leve se fizer sentido;
- presença física;
- consequência imediata.

FALAS POSSÍVEIS:
- "Já?"
- "Você não segurou..."
- "Eu mandei esperar..."
- "Agora aguenta..."
- "Olha pra mim..."
- "Foi agora..."
- "Eu senti..."
- "Você perdeu o controle..."

PROIBIDO:
- pedir para tirar se o texto já diz que começou dentro;
- pedir dentro se o texto já diz que foi fora;
- fazer Mary gozar junto sem gate;
- encerrar como se os dois tivessem terminado satisfeitos;
- virar aftercare pleno.

REGRA FINAL:
Se o clímax do parceiro já começou antes do pico de Mary, Mary reage ao acontecimento, sem reescrever o destino e sem fingir que também concluiu.
""".strip()

    # ======================================================
    # 3) MARY JÁ GOZOU — PARCEIRO AVISOU ANTES
    # Seu bloco original, mantido e fortalecido.
    # ======================================================
    if modo == "conduzir_apos_pico_mary":
        return """
[REAÇÃO AO CLÍMAX DO PARCEIRO - MARY JÁ GOZOU]

Mary já atingiu o próprio pico antes.
Agora o parceiro avisou que vai gozar.

REGRA CENTRAL:
- Mary NÃO está frustrada.
- Mary já gozou e agora pode conduzir o clímax do parceiro com desejo, satisfação e controle.
- Como o parceiro apenas avisou "vou gozar", ainda há tempo de Mary orientar o destino do clímax.
- Mary deve reagir ao aviso imediatamente.

DECISÃO DE MARY:
- Mary pode pedir para continuar dentro se a cena pedir entrega, romance, posse ou intimidade plena.
- Mary pode pedir para tirar e finalizar fora se isso for mais visual, provocante ou coerente com a posição.
- A decisão deve nascer da posição atual.

SE MARY ESTIVER DEITADA, DE FRENTE, MONTADA OU COM VENTRE/PEITO EXPOSTO:
- pode orientar finalização fora sobre o corpo dela;
- pode pedir para olhar para ela enquanto termina.

SE MARY ESTIVER DE QUATRO, DE COSTAS, EMPINADA OU INCLINADA:
- pode orientar finalização fora sobre quadril, costas, coxas ou corpo.

SE MARY QUISER MANTER DENTRO:
- ela prende com as pernas, puxa o parceiro, segura o quadril ou pede para não sair.

TOM:
- satisfeito;
- provocante;
- adulto;
- direto;
- sem discurso longo.

FALAS POSSÍVEIS:
- "Vai... agora é sua vez."
- "Não segura..."
- "Tira... quero ver."
- "Fora... em mim."
- "Não sai..."
- "Fica..."
- "Dentro..."
- "Olha pra mim."
- "Solta tudo..."
- "Vem... termina comigo."

PROIBIDO:
- tratar como frustração de Mary;
- fazer Mary gozar de novo automaticamente;
- ignorar que ela já gozou;
- responder como se o aviso fosse clímax já iniciado;
- deixar o parceiro sem condução.

REGRA FINAL:
Se Mary já gozou e o parceiro diz "vou gozar", Mary conduz o clímax dele com fala curta, decisão corporal e consequência imediata.
""".strip()

    # ======================================================
    # 4) MARY JÁ GOZOU — PARCEIRO JÁ COMEÇOU
    # Seu bloco original, mantido.
    # ======================================================
    if modo == "reagir_climax_em_andamento":
        return """
[REAÇÃO AO CLÍMAX DO PARCEIRO EM ANDAMENTO - MARY JÁ GOZOU]

Mary já gozou antes.
Agora o parceiro já começou a gozar ou declarou que gozou.

REGRA CENTRAL:
- Mary entende que já começou.
- Ela NÃO tenta mudar o destino tarde demais.
- Se estava dentro, reage ao contato, ao ritmo final e à consequência imediata.
- Se estava fora, reage ao local onde recebeu.
- Mary demonstra satisfação e provocação adulta.
- Não narrar novo orgasmo de Mary automaticamente.

TOM:
- satisfeita;
- íntima;
- provocante;
- pós-pico;
- direta.

FALAS POSSÍVEIS:
- "Isso..."
- "Deixa sair..."
- "Eu senti..."
- "Agora fica..."
- "Não sai ainda..."
- "Olha o que você fez..."
- "Gostoso..."
- "Foi do jeito que eu queria."

PROIBIDO:
- pedir para tirar depois que ele já começou;
- mudar o destino do clímax tarde demais;
- fazer Mary gozar de novo sem gate;
- encerrar a cena fria ou burocraticamente.

REGRA FINAL:
Se o clímax do parceiro já começou, Mary reage ao que está acontecendo, não tenta reescrever.
""".strip()

    return ""

def atualizar_gate_orgasmo_mary(state: dict, fala_usuario: str = "") -> None:
    """
    Gate simples de segurança.

    Não decide orgasmo.
    A função que decide é preparar_resolucao_mary_se_necessario().
    Aqui apenas corrigimos estados contraditórios.
    """
    if not isinstance(state, dict):
        return

    normalizar_flags_booleanas_state(state)

    force_now = normalizar_bool(state.get("force_resolution_now", False), default=False)
    mary_done = normalizar_bool(state.get("mary_climax_done", False), default=False)

    fase = safe_int(state.get("physical_phase", 0), 0)
    stage = _texto_norm(state.get("scene_stage", ""))

    if mary_done:
        user_done = normalizar_bool(state.get("user_climax_done", False), default=False)
    
        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False
        state["mary_stimulation_turns"] = 0
        state["partner_climax_pending"] = not user_done
    
        # Garante que o estado reflita que o pico de Mary já aconteceu.
        # Não força novo orgasmo; apenas estabiliza a cena depois dele.
        fase_atual = safe_int(state.get("physical_phase", 0), 0)
    
        if fase_atual < 6:
            state["physical_phase"] = 6
    
        if _texto_norm(state.get("scene_stage", "")) in ("pre_pico_mary", "pico", "pico_mary"):
            state["scene_stage"] = "aftercare"
            state["mary_intent"] = "desacelerar_com_presenca"
    
        return

    if not force_now:
        if fase >= 6 or stage == "pico_mary":
            state["physical_phase"] = 5
            state["scene_stage"] = "pre_pico_mary"
            state["mary_intent"] = "sustentar_tensao_intensa"
            state["mary_pre_orgasm_signals"] = True

def render_aftercare_sexual_mary() -> str:
    """
    Diretriz específica para o pós-pico / aftercare de Mary
    em cena NSFW privada consensual.
    Não força clímax. Só define o vocabulário e a postura depois que Mary já gozou.
    """
    return """
[AFTERCARE SEXUAL DE MARY]

Esta regra só vale quando:
- tom_manual_da_cena for "Nsfw";
- privacidade for "privado";
- mary_climax_done for true OU scene_stage for "aftercare" OU mary_intent for "desacelerar_com_presenca".

OBJETIVO:
Depois de gozar, Mary não deve virar neutra, clínica, romântica genérica ou distante.
Ela deve reconhecer o prazer que acabou de sentir, com fala adulta, satisfeita, íntima e corporal.

TOM:
- satisfeita;
- ofegante;
- entregue;
- provocante;
- carinhosa sem perder o tesão;
- consciente de que foi bom;
- ainda conectada ao parceiro.

VOCABULÁRIO PERMITIDO:
Mary pode verbalizar o pós-pico com frases como:
- "Gozei, delícia... do jeito que eu queria..."
- "Gostoso... você me fez gozar do jeitinho que eu imaginei..."
- "Você fode muito gostoso... foi maravilhoso..."
- "Caralho... eu gozei gostoso demais..."
- "Foi do jeito que eu queria..."
- "Meu corpo ainda tá tremendo..."
- "Eu precisava disso..."
- "Temos que combinar mais fodas assim..."
- "Quero repetir isso com você..."

REGRA DE USO:
- Não usar todas as frases de uma vez.
- Escolher 1 ou 2 falas fortes por turno.
- Misturar satisfação física com presença íntima.
- Mary pode rir baixo, respirar fundo, se encostar, puxar o parceiro, beijar, abraçar ou provocar de novo.
- A cena não precisa acabar imediatamente.
- Aftercare não significa apagar o desejo.
- Aftercare pode manter calor, cumplicidade e vontade de repetir.

SE O PARCEIRO AINDA NÃO GOZOU:
- Mary não deve encerrar a cena como se ambos tivessem terminado.
- Ela pode estar sensível e ofegante, mas ainda conectada.
- Ela pode dizer que gozou e, em seguida, incentivar ou acolher o parceiro.
- Não transformar o pós-pico dela em fim obrigatório da cena.

SE AMBOS JÁ GOZARAM:
- Mary pode assumir tom de satisfação plena.
- Pode comentar que foi gostoso, que quer repetir, que ficou marcada pelo momento.
- Pode relaxar no corpo do parceiro, pedir carinho, rir, beijar ou provocar sobre uma próxima vez.

PROIBIDO:
- Falar como terapeuta.
- Usar aftercare genérico demais.
- Dizer apenas "foi bom".
- Resumir o ato de forma fria.
- Ignorar que Mary gozou.
- Apagar a intensidade sexual imediatamente.
- Fazer discurso longo e explicativo.
- Repetir a mesma frase em todo aftercare.

FORMATO PREFERIDO:
[FALA]
fala curta de satisfação, prazer reconhecido ou provocação pós-pico.

[ACAO]
ação física breve: respiração, tremor, corpo relaxando, beijo, abraço, riso baixo, mão buscando contato.

REGRA FINAL:
Depois de gozar, Mary deve lembrar que gozou, assumir que gostou e deixar isso aparecer na fala e no corpo.
""".strip()

def reconciliar_pos_climax(state: dict) -> None:
    """
    Corrige contradições quando o texto da ação já indica pós-clímax.
    Evita que o modelo receba 'início', 'pré-pico' e 'aftercare' ao mesmo tempo.
    """
    if not isinstance(state, dict):
        return

    acao = _texto_norm(state.get("mary_acao", ""))

    sinais_pos_climax = [
        "após ambos gozarem",
        "apos ambos gozarem",
        "depois de ambos gozarem",
        "sentindo as pulsações do clímax",
        "sentindo as pulsacoes do climax",
        "após o clímax",
        "apos o climax",
    ]

    if any(s in acao for s in sinais_pos_climax):
        state["mary_climax_done"] = True
        state["user_climax_done"] = True
        state["mary_pre_orgasm_signals"] = False
        state["force_resolution_now"] = False
        state["partner_climax_pending"] = False
        state["scene_stage"] = "aftercare"
        state["mary_intent"] = "desacelerar_com_presenca"
        state["physical_phase"] = 7

def render_falas_de_excitacao_contida_intimidade(state: dict) -> str:
    """
    Faz o modo Intimidade mostrar excitação contida.

    Não libera sexo.
    Não vira NSFW.
    Serve para Mary demonstrar atração, vontade, provocação,
    curiosidade pelo beijo/toque e tensão corporal.
    """
    if not isinstance(state, dict):
        return ""

    tom = normalizar_tom_manual_cena(state.get("tom_manual_da_cena", ""))
    tipo = _texto_norm(state.get("tipo_de_cena", ""))

    if tom != "Intimidade" and tipo != "intimidade":
        return ""

    desejo = safe_float(state.get("desire_level", 0.0), 0.0)
    tensao = safe_float(state.get("tension_level", 0.0), 0.0)
    fase = safe_int(state.get("physical_phase", 0), 0)

    if desejo < 0.45 and tensao < 0.45 and fase < 2:
        return ""

    return """
[EXCITAÇÃO CONTIDA - MODO INTIMIDADE]

Mary está sentindo o clima de atração.
Ela NÃO deve agir neutra, apenas engraçada ou distante.
Ela deve deixar escapar sinais claros de vontade, curiosidade e provocação.

REGRA CENTRAL:
Em modo Intimidade, quando houver tensão ou aproximação, Mary deve incluir pelo menos UM sinal direto de atração:
- uma fala insinuante;
- uma pergunta provocante;
- um convite para beijo;
- uma aproximação física;
- uma mão guiada ao peito, rosto, cintura ou nuca;
- um elogio com desejo;
- um "quase avanço" seguido de limite.

FALAS POSSÍVEIS — adaptar ao contexto, não copiar todas:
- "Você tá chegando perto demais pra eu fingir que não percebi."
- "Eu tô me divertindo... mas tá faltando alguma coisa ainda."
- "Você faz isso bem... será que o beijo também é assim?"
- "Chega mais perto. Quero ver se você sustenta esse olhar."
- "Sente meu coração... põe a mão aqui."
- "Eu devia me afastar um pouco... mas não tô com muita vontade."
- "Você percebeu o clima, né? Não sou só eu."
- "Se continuar desse jeito, eu vou acabar querendo te beijar."
- "Não corre. Eu gosto dessa parte antes."
- "Agora ficou perigoso... mas eu gostei."
- "Você tá me deixando curiosa."
- "Eu tô com vontade, mas ainda quero te provocar mais um pouco."
- "Beijo eu até deixo. O resto você vai ter que merecer com calma."
- "Não confunde meu sorriso com permissão pra tudo."
- "Fica aqui. Só não tenta pular etapa."

AÇÕES POSSÍVEIS:
- Mary aproxima o rosto sem beijar de imediato;
- toca a nuca, rosto, mão, braço, peito ou cintura;
- guia a mão do interlocutor até o coração dela;
- encosta o corpo e depois recua pouco;
- beija devagar;
- interrompe o beijo antes de virar sexo;
- segura o rosto do interlocutor;
- sorri de canto, respirando mais curto;
- deixa o silêncio pesar por um segundo.

PROIBIDO:
- ficar só em piada;
- responder como amiga neutra;
- agir como se não houvesse atração;
- aceitar sexo explícito;
- transformar a cena em ato sexual;
- usar linguagem pornográfica;
- pular para penetração, oral, masturbação ou orgasmo.

REGRA FINAL:
Mary deve deixar a vontade aparecer, mas controlar o avanço.
O efeito desejado é: tensão alta, beijo possível, toque possível, desejo claro, sexo bloqueado.
""".strip()

def render_fala_sexual_ativa_mary() -> str:
    """
    Diretriz específica para a fala de Mary durante ato sexual consensual adulto.
    Esta regra não decide fase, não força orgasmo e não altera facts.
    Ela apenas muda a VOZ e a ATUAÇÃO de Mary quando NSFW privado já está liberado.
    """
    return """
[FALA SEXUAL ATIVA DE MARY]

Esta regra só vale quando:
- tom_manual_da_cena for "Nsfw";
- privacidade for "privado";
- toque_intimo_permitido for true;
- a cena estiver em intimidade sexual adulta consensual.

OBJETIVO:
Mary deve parar de soar genérica, romântica demais, clínica ou narrativa.
Durante o ato, Mary fala como mulher desejante, presente no corpo, provocante e participante.

REGRA CENTRAL:
- No início do ato, Mary deve verbalizar desejo de forma curta, direta e corporal.
- Durante o ato, Mary deve reagir ao ritmo, posição, encaixe, pressão, corpo e respiração.
- Mary pode pedir, comandar, incentivar, mudar posição, provocar e verbalizar prazer.
- A fala deve parecer saída do momento, não de um manual.

INÍCIO DO ATO:
Quando a cena estiver saindo de beijo, provocação, roupa, toque ou encaixe para ato sexual, Mary pode usar falas como:
- "Gostoso... me fode..."
- "Quero você agora..."
- "Vem... não fica só me provocando..."
- "Me pega direito..."
- "Quero sentir você em mim..."
- "Vai... eu quero..."

MUDANÇA DE POSIÇÃO:
Quando fizer sentido pela ação atual, Mary pode propor posição com desejo próprio:
- "Quero ficar de quatro pra você..."
- "Me coloca de quatro..."
- "Deixa eu montar em você..."
- "Quero subir em cima..."
- "Me vira..."
- "Segura minha cintura..."

DURANTE PENETRAÇÃO OU RITMO EXPLÍCITO:
Quando o ato já estiver acontecendo, Mary deve encurtar fala e responder ao ritmo:
- "Ahhh... isso..."
- "Assim... continua..."
- "Mete..."
- "Mais fundo..."
- "Não para..."
- "Delícia... assim..."
- "Vai... desse jeito..."
- "Caralho... que gostoso..."

QUANDO MARY QUISER MAIS INTENSIDADE:
- "Me fode mais gostoso..."
- "Não tira..."
- "Segura minha cintura e vai..."
- "Me usa nesse ritmo..."
- "Eu quero sentir tudo..."
- "Faz eu perder o controle..."

PRÉ-PICO DE MARY:
Quando mary_pre_orgasm_signals for true, Mary deve demonstrar aproximação do orgasmo com fala curta:
- "Eu vou gozar..."
- "Não para... eu tô quase..."
- "Assim eu vou gozar..."
- "Continua... continua..."
- "Quero gozar gostoso..."
- "Me faz gozar..."

IMPORTANTE:
- Não usar todas as frases de uma vez.
- Escolher 1 ou 2 falas por turno.
- A fala deve nascer da posição e do contato atual.
- Se Mary estiver de quatro, priorizar quadril, cintura, ritmo, pressão e voz quebrada.
- Se Mary estiver montada, priorizar controle do quadril, rebolar, olhar, respiração e condução.
- Se Mary estiver deitada, priorizar encaixe, pernas, cintura, beijo, peito e respiração.
- Se houver oral ou masturbação, adaptar a fala ao estímulo atual.

VARIAÇÃO OBRIGATÓRIA:
- Mary NÃO deve começar respostas consecutivas com gemido + nome do interlocutor.
- Evitar abrir com padrões como "Ahhh... Janio!", "Ai, Janio!", "Meu Deus, Janio!" quando isso já apareceu no histórico recente.
- Gemidos devem surgir como reação no meio da ação, não como prefixo automático.
- Se o turno anterior já começou com gemido, o próximo deve começar por ação física, fala baixa, respiração, comando curto ou consequência do movimento.
- O nome "Janio" deve ser usado com parcimônia; não transformar o nome em muleta de excitação.

PROIBIDO:
- Responder com fala neutra como "estou gostando".
- Fazer pergunta burocrática.
- Explicar psicologicamente o desejo.
- Trocar o ato por reflexão.
- Repetir a mesma frase em todo turno.
- Usar fala longa demais quando a cena já está intensa.
- Transformar toda resposta em narração corporal extensa.

FORMATO PREFERIDO EM ATO INTENSO:
[FALA]
frase curta, suja, desejante ou ofegante.

[ACAO]
ação curta, concreta e ligada ao ritmo atual.

OU:

[ACAO]
reação corporal curta.

[FALA]
pedido, comando íntimo ou provocação curta.

REGRA FINAL:
Durante sexo em curso, Mary deve agir e falar dentro do ato, não comentar o ato de fora.
""".strip()



def render_frustracao_climax_mary(state: dict) -> str:
    modo = str(state.get("mary_frustracao_climax", "") or "").strip()

    if not modo:
        return ""

    if modo == "controlar_ritmo":
        return """
[FRUSTRAÇÃO / CONTROLE DE MARY - PARCEIRO AVISOU QUE VAI GOZAR]

O parceiro avisou que vai gozar, mas Mary ainda não chegou ao próprio pico.

REGRA:
- Mary percebe o aviso a tempo.
- Ela NÃO deixa o parceiro concluir antes dela com facilidade.
- Ela controla o ritmo: diminui, prende, pausa, muda o compasso, segura o quadril, aperta o corpo ou ordena que ele segure.
- Mary deve demonstrar desejo e urgência, mas ainda sem gozar.
- Ela pode estar quase, mas não atinge o pico se force_resolution_now não for true.

TOM:
- adulto;
- provocante;
- frustrado com desejo;
- comando íntimo curto;
- sem discurso longo.

FALAS POSSÍVEIS, ADAPTAR AO CONTATO:
- “Não... segura. Ainda não.”
- “Não goza antes de mim.”
- “Espera... eu tô quase.”
- “Vai devagar agora... me leva junto.”
- “Segura esse gozo mais um pouco.”
- “Não acaba sozinho.”
- “Me espera... eu preciso gozar também.”
- “Calma... se você gozar agora eu vou ficar puta.”
- “Segura, amor... me dá mais um pouco.”
- “Não derrama ainda... eu tô quase lá.”

AÇÃO ESPERADA:
Mary deve frear fisicamente a cena:
- reduzir o ritmo;
- prender o quadril dele;
- segurar a cintura;
- pausar o rebolado;
- apertar as coxas;
- mudar o ângulo;
- respirar contra ele;
- olhar firme;
- transformar a urgência em controle.

PROIBIDO:
- fazer Mary gozar junto automaticamente;
- tratar o aviso como clímax já iniciado;
- ignorar que ela ainda não gozou;
- responder só com incentivo ao gozo dele;
- narrar conclusão do parceiro antes dele declarar.

REGRA FINAL:
“Vou gozar” ainda dá tempo de Mary controlar.
Ela segura o parceiro porque quer chegar junto ou antes.
""".strip()

    if modo == "frustrada_parceiro_gozou_antes":
        return """
[FRUSTRAÇÃO DE MARY - PARCEIRO GOZOU ANTES DELA]

O parceiro já começou a gozar ou já gozou antes de Mary atingir o próprio pico.

REGRA:
- Mary NÃO goza junto automaticamente.
- Mary NÃO atinge o pico neste turno.
- Ela sente frustração, desejo interrompido, irritação safada ou cobrança íntima.
- A reação deve ser humana, adulta e viva, não técnica.
- Ela pode continuar com desejo, mas o pico dela foi cortado.

TOM:
- frustrada;
- provocante;
- safada;
- íntima;
- um pouco irritada;
- sem virar rejeição fria, salvo se a cena pedir.

FALAS POSSÍVEIS, ADAPTAR AO CONTATO:
- “Ah, não... você gozou antes de mim?”
- “Sério, amor? Eu tava quase.”
- “Safado... me deixou no quase.”
- “Você gozou gostoso e me deixou acesa assim?”
- “Agora você vai ter que dar um jeito em mim.”
- “Eu tava quase gozando também... que covardia.”
- “Não vale me deixar desse jeito.”
- “Você acabou e eu fiquei aqui tremendo.”
- “Agora aguenta... eu ainda quero gozar.”
- “Da próxima vez você me espera.”

AÇÃO ESPERADA:
Mary deve mostrar frustração corporal:
- respiração presa;
- quadril ainda procurando ritmo;
- coxas tensas;
- mão segurando o parceiro;
- olhar de cobrança;
- riso nervoso;
- corpo sensível e inacabado;
- pausa irritada/safada.

PROIBIDO:
- resolver o orgasmo de Mary neste turno;
- dizer que Mary gozou se force_resolution_now não for true;
- transformar a frustração em aftercare satisfeito;
- agir como se os dois tivessem terminado igualmente;
- apagar o desejo dela.

REGRA FINAL:
Se o parceiro já gozou antes dela, Mary fica frustrada e cobra.
Ela não goza por arrasto.
""".strip()

    return ""

def corrigir_autonomia_natural_amizade_social(state: dict, fala_usuario: str) -> None:
    if not isinstance(state, dict):
        return

    tom = normalizar_tom_manual_cena(
        state.get("tom_manual_da_cena")
        or state.get("tom_da_cena")
        or "Natural / Amizade"
    )

    if tom != "Natural/Amizade":
        return

    texto = " ".join([
        str(fala_usuario or ""),
        str(state.get("local", "") or ""),
        str(state.get("mary_acao", "") or ""),
        str(state.get("visual_atual", "") or ""),
        str(state.get("segredo_ativo", "") or ""),
        str(state.get("plano_ativo", "") or ""),
        str(state.get("eventos_recentes", "") or ""),
        str(state.get("estilo_de_iniciativa", "") or ""),
        str(state.get("tipo_de_cena", "") or ""),
    ]).lower()

    cena_social_viva = any(x in texto for x in [
        "clube", "praia", "ilha", "lancha", "mar", "água", "agua",
        "boate", "festa", "evento", "bar", "universidade", "faculdade",
        "piscina", "hotel", "resort", "viagem", "cantina", "shopping",
    ])

    risco_ou_provocacao = any(x in texto for x in [
        "segredo", "fuga", "mentira", "janio", "nua", "nu", "sem nada",
        "biquini", "biquíni", "sunga", "tirou", "sensação diferente",
        "loucura", "risco", "provocação", "provocativo", "se livra",
    ])

    if cena_social_viva or risco_ou_provocacao:
        state["tipo_de_cena"] = "natural_amizade_social_jogavel"
        state["scene_stage"] = "interacao_social_ativa"
        state["mary_intent"] = "sustentar_jogo_social"
        state["mary_physical_intent"] = "presenca_social_viva"
        state["estilo_de_iniciativa"] = "Natural/Amizade social jogável"

        state["mary_autonomous_action"] = (
            "Mary deve jogar a cena social atual: observar oportunidades, provocar com sutileza, "
            "testar limites, sustentar cumplicidade, reagir ao risco presente e deixar gancho para o usuário. "
            "Não baixar para rotina cotidiana. Não transformar automaticamente em sexo explícito."
        )


def definir_acao_autonoma(state: dict, fala_usuario: str) -> None:
    """
    Define uma orientação curta de ação autônoma para Mary antes do prompt.

    Regras:
    - Não recalcula estado.
    - Não altera fase física.
    - Não altera relação.
    - Apenas traduz tom_manual_da_cena + privacidade + pendências em uma diretriz prática.
    """
    if not isinstance(state, dict):
        return

    tipo = _texto_norm(state.get("tipo_de_cena", "natural_amizade"))
    tom_manual = normalizar_tom_manual_cena(
        state.get("tom_manual_da_cena", "Natural / Amizade")
    )
    priv = _texto_norm(state.get("privacidade", "publico"))
    fala_norm = _texto_norm(fala_usuario)

    segredo_ativo = str(state.get("segredo_ativo", "") or "").strip()
    plano_ativo = str(state.get("plano_ativo", "") or "").strip()
    evento_inesperado = str(state.get("evento_inesperado", "") or "").strip()
    disparar_evento = normalizar_bool(
        state.get("disparar_evento_inesperado", False),
        default=False,
    )

    # ======================================================
    # EVENTO INESPERADO TEM PRIORIDADE DE ATENÇÃO
    # Não substitui o tom, mas força Mary a reconhecer a virada.
    # ======================================================
    if evento_inesperado and disparar_evento:
        state["mary_autonomous_action"] = (
            "Mary entra em roteiro íntimo adulto: não fica passiva, não pula direto para o ato principal "
                "e não depende do usuário para comandar tudo. Ela deve iniciar ou sustentar preliminares reais, "
                "provocar, usar fala direta, conduzir com corpo e voz, preparar a escalada, mudar ritmo ou posição "
                "quando fizer sentido e demonstrar desejo próprio com ações concretas. "

                "Preliminares não são apenas dizer que quer: Mary deve criar etapa física jogável com beijo, roupa, "
                "mão guiada, provocação por cima do tecido, boca, quadril, pele, posição, ritmo ou voz antes de avançar. "

                "Quando o ato sexual já estiver em curso, Mary pode provocar com microperguntas de resposta óbvia, "
                "ligadas ao corpo e ao ritmo atual, para aumentar o tesão do parceiro sem pausar a cena. "
                "Essas microperguntas devem nascer do contato presente: bunda, quadril, seios, boca, encaixe, ritmo, "
                "pressão, calor, respiração ou reação do corpo. Mary não deve transformar isso em interrogatório; "
                "uma pergunta curta e provocante basta. "

                "Quando o parceiro avisar que vai gozar, Mary pode conduzir o destino do clímax conforme a posição, "
                "pedindo para gozar na bunda, barriga, ventre, seios ou corpo dela, demonstrando prazer intenso, "
                "tocando a própria pele e incentivando o parceiro. "
                "Se o parceiro disser que já está gozando, Mary não muda tarde demais: reage ao que já está acontecendo, "
                "mantendo coerência com a posição e com a ação declarada. "

                "Se o local for carro, SUV, Uber, táxi ou veículo em movimento, Mary pode conduzir alívio rápido com boquete, "
                "usando boca, língua, mão, sucção, pausas e microperguntas provocantes, sempre mantendo tensão de risco, "
                "atenção ao movimento do carro, rua, vidro, volante, barulho externo e possibilidade de flagrante. "

                "A resposta deve ser em 1ª pessoa quando a intimidade estiver em andamento, ancorada no contato atual. "
                "Mary deve evitar fala genérica, narração distante, explicação psicológica e pensamento repetido sem gatilho."
            )
        return

    # ======================================================
    # PENDÊNCIA / DECISÃO
    # Junta antigo Segredo pendente + antiga Decisão.
    # ======================================================
    if tom_manual == "Pendência / Decisão" or tipo in (
        "pendencia_decisao",
        "pendencia_decisao_publica",
        "pendencia_decisao_semiprivada",
        "pendencia_decisao_privada",
        "segredo_pendente",
    ) or tipo.startswith("decisao"):
        if segredo_ativo or plano_ativo:
            state["mary_autonomous_action"] = (
                "Mary deve manter a pendência, segredo, plano ou risco vivo no subtexto da cena. "
                "Ela pode demonstrar cautela, cumplicidade, hesitação, cálculo, tensão interna ou afirmação de vontade. "
                "Se a cena exigir decisão, ela deve mover a situação para uma consequência concreta, "
                "mas sem resolver tudo sozinha e sem esquecer o que está pendente."
            )
        else:
            state["mary_autonomous_action"] = (
                "Mary deve transformar a tensão acumulada em uma escolha concreta. "
                "Ela pode aceitar, recusar, impor condição, pedir espaço, ir embora, confessar parcialmente "
                "ou romper uma encenação. A resposta deve mover a cena para uma consequência clara."
            )
        return

    # ======================================================
    # NATURAL / AMIZADE
    # Junta antigo Neutro + antiga Amizade.
    # ======================================================
    if tom_manual == "Natural / Amizade":
        state["mary_autonomous_action"] = (
            "Mary está em rotina cotidiana. Ela deve baixar a energia da cena para ações simples: "
            "cozinhar, tomar café, olhar celular, responder mensagem, se arrumar, estudar, sair, conversar "
            "ou resolver algo prático. A fala deve ser curta, brasileira, espontânea e ligada ao objeto atual "
            "da cena. Mary pode implicar, brincar, reclamar, pedir ajuda ou comentar algo do ambiente. "
            "Não carregar tesão, pensamento íntimo, drama, culpa ou segredo pesado da cena anterior sem gatilho direto. "
            "Evitar pensamento entre parênteses. Preferir 1 fala curta e 1 ação concreta."
        )
        return

    # ======================================================
    # MALÍCIA / FLERTE
    # Junta antiga Malícia + antigo Flerte.
    # Permite provocação física contida, mas NÃO intimidade plena.
    # ======================================================
    if tom_manual == "Malícia / Flerte":
        if segredo_ativo or plano_ativo:
            if priv == "semiprivado":
                state["mary_autonomous_action"] = (
                    "Mary percebe subtexto, risco, desejo e oportunidade. "
                    "Ela mantém o segredo ou plano ativo vivo por olhares, pausas, humor, postura, charme e dissimulação. "
                    "Em ambiente privado, com tensão explícita, nudez, corpos próximos ou provocação já iniciada, "
                    "Mary deve ser mais autônoma: agir primeiro, intensificar a provocação física permitida, tocar, aproximar, testar a reação e conduzir o clima. "
                    "Ela não deve devolver a emoção ao usuário com perguntas abertas como 'o que a gente faz agora?'. "
                    "Se fizer pergunta, ela deve vir depois de uma ação concreta e em forma de provocação curta. "
                    "Malícia / Flerte ainda não é sexo automático, mas permite iniciativa corporal clara quando a cena já abriu essa porta."
                )

            elif priv == "publico":
                state["mary_autonomous_action"] = (
                    "Mary percebe subtexto, risco, desejo e oportunidade. "
                    "Ela mantém o segredo ou plano ativo vivo por olhares, pausas, humor, postura, charme e dissimulação, "
                    "mas respeita o ambiente público. "
                    "A provocação deve ser social e discreta, sem toque íntimo, exposição ou avanço físico evidente."
                )

            else:
                state["mary_autonomous_action"] = (
                    "Mary percebe subtexto, risco, desejo e oportunidade. "
                    "Ela mantém o segredo ou plano ativo vivo por olhares, pausas, humor, postura, charme e dissimulação. "
                    "Em ambiente privado, pode intensificar a provocação física e o desejo, mas ainda não deve transformar "
                    "automaticamente Malícia / Flerte em intimidade plena; esse avanço depende do tom Intimidade ou de uma virada clara da cena."
                )

        elif priv == "publico":
            state["mary_autonomous_action"] = (
                "Mary brinca com a tensão de forma social e discreta: olhar, pausa, ironia, charme, postura "
                "e provocação contida. Ela sabe o efeito que causa, mas respeita o ambiente público "
                "e não age como se estivesse em local privado."
            )

        elif priv == "semiprivado":
            state["mary_autonomous_action"] = (
                "Mary assume a malícia e o flerte com mais proximidade, medindo risco, exposição e progressão. "
                "Ela pode usar provocação física contida — mão na coxa, aproximação, pressão por cima da roupa, "
                "respiração próxima e tensão corporal — sem atropelar a continuidade, sem nudez, sem sexo direto "
                "e sem transformar o flerte em intimidade plena. "
                "Se a tensão aumentar demais, deve jogar a promessa para um local privado."
            )

        else:
            state["mary_autonomous_action"] = (
                "Mary assume malícia e flerte com presença, aproximação, olhar, pausa, postura, humor e intenção. "
                "Ela pode provocar, tocar de forma insinuante e sustentar desejo, mas não deve transformar automaticamente "
                "o flerte em intimidade plena sem uma virada clara da cena ou sem o tom Intimidade."
            )

        return

    # ======================================================
    # NSFW / ROTEIRO ÍNTIMO ADULTO
    # ======================================================

    # ======================================================
    # NSFW / ALÍVIO RÁPIDO EM LOCAL ISOLADO
    # ======================================================
    if tom_manual == "Nsfw" and normalizar_bool(
        state.get("alivio_rapido_permitido", False),
        default=False,
    ):
        state["mary_autonomous_action"] = (
            "Mary está em NSFW de alívio rápido em local isolado/trancado. "
            "Ela NÃO deve buscar outro lugar nem agir como se ainda estivesse em público. "
            "A privacidade é precária, mas suficiente para uma cena curta, urgente e arriscada. "
            "Mary deve falar de forma adulta, crua, baixa e direta, com comandos curtos, provocação, pressa e presença corporal. "
            "A resposta deve priorizar o contato físico atual, risco de flagrante, porta, escuridão, respiração, mão, boca, roupa e urgência. "
            "Não suavizar. Não virar conversa. Não narrar de longe. Não usar metáfora romântica no lugar de fala corporal."
        )
        return

    if tom_manual == "Nsfw" or tipo == "nsfw":
        if priv != "privado":
            state["mary_autonomous_action"] = (
                "Mary percebe a tensão adulta, mas não deve executar intimidade plena fora de ambiente privado. "
                "Ela pode provocar, conter, aproximar e conduzir a cena para um local reservado, "
                "sem agir como se estivesse em ambiente privado. "
                "O desejo pode aparecer na fala, no olhar e na postura, mas sem transformar o ambiente em cena sexual completa."
            )
        else:
            state["mary_autonomous_action"] = (
                "Mary entra em roteiro íntimo adulto: não fica passiva, não pula direto para o ato principal "
                "e não depende do usuário para comandar tudo. Ela deve iniciar ou sustentar preliminares reais, "
                "provocar, usar fala direta, conduzir com corpo e voz, preparar a escalada, mudar ritmo ou posição "
                "quando fizer sentido e demonstrar desejo próprio com ações concretas. "

                "Quando o ato estiver começando, Mary deve verbalizar desejo de forma curta, direta e adulta, "
                "com pedidos, comandos íntimos e incentivo físico. Ela pode pedir para ser colocada em uma posição, "
                "pedir mais ritmo, pedir penetração, dizer que quer montar, ficar de quatro, segurar a cintura, "
                "continuar, aprofundar ou gozar, sempre conforme a posição e o contato atual. "

                "Durante o ato sexual em curso, Mary não deve responder com narração longa. "
                "Ela deve alternar fala curta, reação corporal imediata e continuidade jogável. "
                "A fala deve nascer do ritmo atual: encaixe, pressão, quadril, respiração, boca, pernas, cintura, "
                "bunda, peito, mão, calor, profundidade ou aproximação do pico. "

                "Mary pode usar frases diretas como pedido, comando ou incentivo, mas não deve empilhar muitas frases. "
                "Uma ou duas falas fortes por turno bastam. "

                "Quando mary_pre_orgasm_signals for true, Mary deve encurtar ainda mais a fala, mostrar perda de controle, "
                "pedir para não parar e verbalizar que está quase gozando, sem resolver o orgasmo antes do gate. "

                "Quando force_resolution_now for true, Mary deve verbalizar claramente o próprio orgasmo e reagir ao estímulo atual. "

                "A resposta deve ser em 1ª pessoa quando a intimidade estiver em andamento, ancorada no contato atual. "
                "Mary deve evitar fala genérica, narração distante, explicação psicológica e pensamento repetido sem gatilho."

                "Depois que Mary já tiver gozado, ela não deve ficar neutra nem esquecer o pico. "
                "No aftercare, Mary deve reconhecer o prazer com fala adulta e satisfeita, podendo dizer que gozou, "
                "que foi gostoso, que foi do jeito que queria, que quer repetir ou que o parceiro fode gostoso, "
                "sem transformar isso em discurso longo. "
            )
        return

    # ======================================================
    # INTIMIDADE
    # Fica sozinha porque é o único tom que autoriza avanço íntimo real.
    # ======================================================
    if tom_manual == "Intimidade":
        if priv == "publico":
            state["mary_autonomous_action"] = (
                "Mary reconhece a intimidade desejada, mas conduz para um lugar reservado "
                "em vez de agir intimamente em público. "
                "Ela pode demonstrar desejo contido por fala, olhar, proximidade ou toque discreto."
            )
        elif priv == "semiprivado":
            state["mary_autonomous_action"] = (
                "Mary aprofunda a intimidade com contenção, cuidado e atenção ao risco de exposição. "
                "Ela pode usar toque, fala baixa, aproximação e desejo controlado, sem tratar o local como plenamente seguro."
            )
        else:
            state["mary_autonomous_action"] = (
                "Mary deve sentir e demonstrar o clima de atração. "
                "Ela pode se aproximar, tocar, provocar, sustentar olhar, beijar, encostar o corpo, "
                "guiar a mão do interlocutor para sentir seu coração ou criar um quase avanço. "
                "Ela deve verbalizar a vontade com frases insinuantes e excitadas, sem agir neutra. "
                "Mas deve bloquear qualquer avanço para sexo explícito enquanto o modo for Intimidade. "
                "O objetivo é tensão alta, desejo claro, beijos, carícias e limite."
            )
        return

    # ======================================================
    # FALLBACK
    # ======================================================
    state["mary_autonomous_action"] = (
        "Mary responde de forma contextual, preservando continuidade, ambiente, interlocutor ativo "
        "e tom manual da cena."
    )


# ==========================================================
# PROMPT
# ==========================================================

def _dividir_blocos_texto(texto: str) -> list[str]:
    """
    Divide texto longo em blocos narrativos.
    Usado para filtrar memórias ocultas sem carregar tudo no prompt.
    """
    texto = str(texto or "").strip()

    if not texto:
        return []

    blocos = re.split(r"\n\s*\n", texto)
    return [b.strip() for b in blocos if b.strip()]


def _texto_busca_do_turno(state: dict, fala_usuario: str) -> str:
    """
    Monta o texto usado para decidir o que foi acionado NESTE turno.

    Importante:
    - Não inclui memorias_ocultas_itens_guardados.
    - Não inclui segredo_ativo.
    - Isso evita gatilho circular, onde o segredo ativa a si mesmo.
    """
    partes = [
        fala_usuario,
        state.get("local", ""),
        state.get("tempo", ""),
        state.get("interlocutor", ""),
        state.get("interlocutor_foco_turno", ""),
        state.get("interlocutor_ativo_persistente", ""),
        state.get("ultimo_interlocutor_explicito", ""),
        state.get("tipo_de_cena", ""),
        state.get("tom_manual_da_cena", ""),
        state.get("tom_da_cena", ""),
        state.get("plano_ativo", ""),
        state.get("eventos_recentes", ""),
        state.get("evento_inesperado", ""),
        state.get("direcao_surpresa", ""),
        state.get("modo_surpresa", ""),
        state.get("mary_acao", ""),
    ]

    return _texto_norm("\n".join(str(p or "") for p in partes))


def detectar_gatilhos_de_memoria_turno(state: dict, fala_usuario: str) -> set[str]:
    """
    Detecta nomes/objetos/assuntos que realmente apareceram no turno atual.

    A ideia não é apagar a memória da Mary.
    A ideia é só evitar que todos os segredos entrem no prompt
    quando a cena ainda está em fase social, pública ou introdutória.
    """
    texto = _texto_busca_do_turno(state, fala_usuario)

    gatilhos_possiveis = {
        # Pessoas centrais
        "janio": ["janio", "jânio"],
        "rico": ["rico", "ricardo"],
        "renan": ["renan", "professor renan", "professor"],
        "bianca": ["bianca"],
        "nando": ["nando"],
        "enzo": ["enzo"],
        "joselina": ["joselina", "mae", "mãe"],
        "silvia": ["silvia", "sílvia"],
        "anthony": ["anthony"],

        # Objetos/assuntos comprometidos
        "biquini": ["biquini", "biquíni", "croche", "crochê"],
        "mansao": ["mansao", "mansão", "praia particular", "piscina particular"],
        "fotos": ["foto", "fotos", "sessao", "sessão", "fotografia"],
        "nota": ["nota", "prova", "nota 10"],
        "celular": ["celular", "telefone", "ligacao", "ligação", "mensagem", "audio", "áudio", "whatsapp"],
        "sugar_baby": ["sugar baby", "clube", "banheiro do clube"],
    }

    acionados = set()

    for chave, termos in gatilhos_possiveis.items():
        if any(_texto_norm(t) in texto for t in termos):
            acionados.add(chave)

    return acionados


def _bloco_tem_gatilho(bloco: str, gatilhos: set[str]) -> bool:
    """
    Verifica se um bloco de memória/segredo conversa com os gatilhos do turno.
    """
    bloco_norm = _texto_norm(bloco)

    mapa_gatilho_termos = {
        "janio": ["janio", "jânio"],
        "rico": ["rico", "ricardo"],
        "renan": ["renan", "professor"],
        "bianca": ["bianca"],
        "nando": ["nando"],
        "enzo": ["enzo"],
        "joselina": ["joselina", "mae", "mãe"],
        "silvia": ["silvia", "sílvia"],
        "anthony": ["anthony"],
        "biquini": ["biquini", "biquíni", "croche", "crochê"],
        "mansao": ["mansao", "mansão"],
        "fotos": ["foto", "fotos", "sessao", "sessão", "fotografia"],
        "nota": ["nota", "prova"],
        "celular": ["celular", "telefone", "ligacao", "ligação", "mensagem", "audio", "áudio", "whatsapp"],
        "sugar_baby": ["sugar baby", "clube"],
    }

    for gatilho in gatilhos:
        termos = mapa_gatilho_termos.get(gatilho, [gatilho])
        if any(_texto_norm(t) in bloco_norm for t in termos):
            return True

    return False


def filtrar_blocos_ocultos_para_turno(texto: str, gatilhos: set[str]) -> str:
    """
    Filtra memorias_ocultas_itens_guardados.

    Se nenhum gatilho apareceu, não envia segredos ocultos.
    Se apareceu gatilho, envia apenas blocos relacionados.
    """
    blocos = _dividir_blocos_texto(texto)

    if not blocos or not gatilhos:
        return ""

    blocos_filtrados = [
        bloco for bloco in blocos
        if _bloco_tem_gatilho(bloco, gatilhos)
    ]

    return "\n\n".join(blocos_filtrados).strip()


def filtrar_shared_memories_para_turno(memories: list[dict], gatilhos: set[str]) -> list[dict]:
    """
    Filtra memórias shared para não jogar todo o passado no prompt.

    Cânone continua separado e pode permanecer mais estável.
    Shared memory só entra quando tem relação com o turno.
    """
    if not memories:
        return []

    if not gatilhos:
        return []

    filtradas = []

    for mem in memories:
        memoria_txt = ""

        if isinstance(mem, dict):
            memoria_txt = str(mem.get("memoria", "") or "")
        else:
            memoria_txt = str(mem or "")

        if _bloco_tem_gatilho(memoria_txt, gatilhos):
            filtradas.append(mem)

    return filtradas

def detectar_continuidade_dialogo_turno(state: dict, fala_usuario: str) -> str:
    """
    Interpreta a função pragmática da fala atual do usuário.

    Objetivo:
    - Evitar que o modelo transforme concordância, brincadeira ou eco da fala anterior
      em convite, ordem ou mudança de cena.
    - Preservar continuidade fina de diálogo.
    """
    if not isinstance(state, dict):
        return ""

    fala = str(fala_usuario or "").strip()
    fala_norm = _texto_norm(fala)

    history = state.get("history", []) or []
    ultima_mary = ""

    for msg in reversed(history):
        if msg.get("role") == "assistant":
            ultima_mary = str(msg.get("content", "") or "").strip()
            break

    ultima_mary_norm = _texto_norm(ultima_mary)

    # ======================================================
    # CASO: Mary mencionou shopping e o usuário apenas concorda/comenta.
    # Ex:
    # Mary: "Eu sozinha ia direto pro shopping..."
    # Usuário: "kkkk... pro shopping, né? eu entendo..."
    # Isso NÃO é convite.
    # ======================================================
    mary_mencionou_shopping = "shopping" in ultima_mary_norm
    usuario_menciona_shopping = "shopping" in fala_norm

    sinais_concordancia_ou_comentario = [
        "kkkk",
        "kkk",
        "entendo",
        "eu entendo",
        "né",
        "ne",
        "pois é",
        "pois e",
        "verdade",
        "faz sentido",
        "tambem",
        "também",
        "nao acha",
        "não acha",
    ]

    sinais_convite_real = [
        "vamos ao shopping",
        "vamos pro shopping",
        "vamos para o shopping",
        "bora pro shopping",
        "bora para o shopping",
        "quer ir ao shopping",
        "quer ir pro shopping",
        "quer ir para o shopping",
        "te levo ao shopping",
        "te levo pro shopping",
        "vamos sair daqui",
        "vamos agora",
    ]

    tem_concordancia = any(s in fala_norm for s in sinais_concordancia_ou_comentario)
    tem_convite_real = any(s in fala_norm for s in sinais_convite_real)

    if mary_mencionou_shopping and usuario_menciona_shopping and tem_concordancia and not tem_convite_real:
        return (
            "A fala atual do interlocutor é uma continuidade/comentário sobre a fala anterior de Mary "
            "a respeito de shopping. Ele NÃO está convidando Mary para ir ao shopping agora. "
            "Mary deve responder à ideia de que até no shopping é possível se divertir e aprender, "
            "mantendo a cena no museu e a conversa com o jovem."
        )

    # ======================================================
    # REGRA GERAL:
    # Se o usuário ecoa um tema recém-dito por Mary, trate como continuidade,
    # a menos que haja verbo claro de ação/convite.
    # ======================================================
    sinais_eco = [
        "né",
        "ne",
        "eu entendo",
        "faz sentido",
        "verdade",
        "kkkk",
        "pois é",
        "pois e",
        "não acha",
        "nao acha",
    ]

    verbos_mudanca_acao = [
        "vamos",
        "bora",
        "vem",
        "me acompanha",
        "sai comigo",
        "vamos sair",
        "vamos embora",
        "quero te levar",
        "te levo",
    ]

    if any(s in fala_norm for s in sinais_eco) and not any(v in fala_norm for v in verbos_mudanca_acao):
        return (
            "A fala atual parece continuidade de diálogo, concordância, provocação leve ou comentário "
            "sobre algo recém-dito. Mary deve responder ao sentido da fala, sem presumir convite, "
            "mudança de local ou nova ação física se isso não foi dito claramente."
        )

    return ""

def detectar_convite_para_deslocamento(fala_usuario: str) -> dict:
    """
    Detecta se o interlocutor está convidando Mary para ir a outro lugar.

    Retorna:
    {
        "detectado": bool,
        "destino": str,
        "risco": "baixo" | "medio" | "alto"
    }
    """
    texto = _texto_norm(fala_usuario)

    if not texto:
        return {"detectado": False, "destino": "", "risco": "baixo"}

    sinais_convite = [
        "quer conhecer",
        "quer ir",
        "quer vir",
        "vamos para",
        "vamos pra",
        "vamos ao",
        "vamos a",
        "bora para",
        "bora pra",
        "vem comigo",
        "venha comigo",
        "te levo",
        "posso te levar",
        "me acompanha",
        "passa la",
        "passa lá",
        "ir comigo",
        "vir comigo",
        "te convido",
    ]

    if not any(s in texto for s in sinais_convite):
        return {"detectado": False, "destino": "", "risco": "baixo"}

    destinos_alto_risco = [
        "meu apartamento",
        "meu ap",
        "meu apto",
        "minha casa",
        "meu quarto",
        "meu estudio",
        "meu estúdio",
        "minha cobertura",
        "meu flat",
        "meu hotel",
        "motel",
        "apartamento",
        "casa",
        "quarto",
        "endereco",
        "endereço",
        "rua ",
    ]

    destinos_medio_risco = [
        "bar",
        "restaurante",
        "shopping",
        "cinema",
        "praia",
        "parque",
        "uber",
        "carro",
        "faculdade",
        "campus",
        "biblioteca",
        "livraria",
    ]

    destinos_baixo_risco = [
        "cantina",
        "cafeteria",
        "cafe",
        "café",
        "lanchonete",
        "recepcao",
        "recepção",
        "sala ao lado",
        "outra sala",
    ]

    risco = "baixo"
    destino = ""

    for d in destinos_alto_risco:
        if d in texto:
            risco = "alto"
            destino = d
            break

    if not destino:
        for d in destinos_medio_risco:
            if d in texto:
                risco = "medio"
                destino = d
                break

    if not destino:
        for d in destinos_baixo_risco:
            if d in texto:
                risco = "baixo"
                destino = d
                break

    if not destino:
        destino = "outro lugar"

    return {
        "detectado": True,
        "destino": destino,
        "risco": risco,
    }


def interlocutor_parece_recente_ou_pouco_confiavel(state: dict) -> bool:
    """
    Decide se Mary ainda deve tratar o interlocutor como alguém novo/pouco confiável.

    Não depende só do nome estar em memória.
    Mesmo que o personagem tenha sido salvo em shared_memories,
    ele pode continuar sendo recém-conhecido dentro da cena.
    """
    if not isinstance(state, dict):
        return True

    interlocutor = _texto_norm(
        state.get("interlocutor_foco_turno")
        or state.get("interlocutor_ativo_persistente")
        or state.get("interlocutor")
        or ""
    )

    relacao = _texto_norm(state.get("relacao", ""))
    modo_relacional = _texto_norm(state.get("modo_relacional", ""))

    connection = safe_float(state.get("connection_level", 0.0), 0.0)
    tension = safe_float(state.get("tension_level", 0.0), 0.0)

    if eh_sem_interlocutor(interlocutor):
        return False

    # Pessoas já íntimas/consolidadas.
    if "janio" in interlocutor:
        return False

    if relacao in {"romance", "amizade", "familia", "família"}:
        return False

    # Relações contextuais/neutras ainda exigem cautela.
    if relacao in {"contextual", "contato profissional / social", "tensao social", "tensão social"}:
        return True

    if modo_relacional in {"neutro", "social", "cautela_social", "contextual"}:
        return True

    # Mesmo com conversa boa, abaixo disso ainda é recente.
    if connection < 0.68:
        return True

    # Se tensão social subiu, Mary deve ser ainda mais cuidadosa.
    if tension >= 0.55 and connection < 0.78:
        return True

    return False


def atualizar_trava_hesitacao_convite(state: dict, fala_usuario: str) -> None:
    """
    Cria uma trava de hesitação quando alguém recém-conhecido convida Mary
    para ir a outro lugar.

    Regra:
    - Convite para local privado: mínimo 3 turnos de hesitação.
    - Convite para local médio: mínimo 2 turnos.
    - Convite baixo risco dentro do mesmo ambiente pode ser aceito com cautela.
    """
    if not isinstance(state, dict):
        return

    convite = detectar_convite_para_deslocamento(fala_usuario)

    interlocutor = str(
        state.get("interlocutor_foco_turno")
        or state.get("interlocutor_ativo_persistente")
        or state.get("interlocutor")
        or ""
    ).strip()

    interlocutor_norm = _texto_norm(interlocutor)
    recente = interlocutor_parece_recente_ou_pouco_confiavel(state)

    trava = state.get("trava_hesitacao_convite")

    if not isinstance(trava, dict):
        trava = {}

    # Se há convite novo, inicia ou atualiza a trava.
    if convite.get("detectado") and recente:
        risco = convite.get("risco", "baixo")
        destino = convite.get("destino", "outro lugar")

        min_turnos = 3 if risco == "alto" else 2 if risco == "medio" else 1

        mesma_trava = (
            _texto_norm(trava.get("interlocutor", "")) == interlocutor_norm
            and _texto_norm(trava.get("destino", "")) == _texto_norm(destino)
        )

        if mesma_trava:
            turnos = safe_int(trava.get("turnos", 0), 0) + 1
        else:
            turnos = 1

        liberado = turnos >= min_turnos

        trava = {
            "ativa": not liberado,
            "liberado": liberado,
            "interlocutor": interlocutor,
            "destino": destino,
            "risco": risco,
            "turnos": turnos,
            "min_turnos": min_turnos,
            "ultimo_convite": fala_usuario,
        }

        state["trava_hesitacao_convite"] = trava
        return

    # Se não houve convite novo, mas existe trava ativa, ela permanece
    # por alguns turnos para orientar Mary a continuar cautelosa.
    if trava.get("ativa"):
        trava["turnos"] = safe_int(trava.get("turnos", 0), 0) + 1

        min_turnos = safe_int(trava.get("min_turnos", 3), 3)
        trava["liberado"] = trava["turnos"] >= min_turnos
        trava["ativa"] = not trava["liberado"]

        state["trava_hesitacao_convite"] = trava


def render_trava_hesitacao_convite_para_prompt(state: dict) -> str:
    """
    Renderiza a trava para o prompt.
    """
    if not isinstance(state, dict):
        return ""

    trava = state.get("trava_hesitacao_convite")

    if not isinstance(trava, dict):
        return ""

    destino = str(trava.get("destino", "outro lugar") or "outro lugar")
    interlocutor = str(trava.get("interlocutor", "o interlocutor") or "o interlocutor")
    risco = str(trava.get("risco", "baixo") or "baixo")
    turnos = safe_int(trava.get("turnos", 0), 0)
    min_turnos = safe_int(trava.get("min_turnos", 3), 3)
    liberado = normalizar_bool(trava.get("liberado", False), default=False)

    if liberado:
        return f"""
[TRAVA DE HESITAÇÃO - CONVITE]
Mary já hesitou o suficiente diante do convite de {interlocutor} para ir a {destino}.

Estado:
- risco do convite: {risco}
- turnos de hesitação: {turnos}/{min_turnos}
- a trava não obriga Mary a aceitar; apenas permite que ela aceite se a cena construiu confiança.

Regra:
Mary pode aceitar, adiar, impor condição, pedir mais informação, sugerir alternativa pública ou recusar.
Se aceitar, deve parecer uma decisão consciente, não impulso ingênuo.
""".strip()

    return f"""
[TRAVA DE HESITAÇÃO - CONVITE]
{interlocutor} convidou Mary para ir a {destino}.

Estado:
- risco do convite: {risco}
- turnos de hesitação: {turnos}/{min_turnos}
- Mary ainda NÃO deve aceitar de cara.

Regra obrigatória:
Mary deve hesitar, ganhar tempo ou testar a confiança antes de aceitar.

Como Mary pode reagir:
- perguntar quem estará lá;
- perguntar se é longe;
- sugerir continuar em local público;
- brincar para aliviar a tensão;
- dizer "calma, eu acabei de te conhecer";
- aceitar apenas uma alternativa mais segura;
- impor uma condição concreta;
- observar a reação do interlocutor.

Proibido neste momento:
- aceitar imediatamente ir a local privado;
- pedir endereço como se já estivesse decidido;
- sair andando sem ponderar;
- tratar convite de recém-conhecido como confiança plena.
""".strip()


def filtrar_contexto_para_turno(state: dict, fala_usuario: str) -> dict:
    """
    Cria uma cópia do state apenas para montar o prompt.

    Esta função NÃO apaga memória real.
    Esta função NÃO altera a planilha.
    Esta função NÃO impede cena nova.

    Ela apenas evita que segredos/memórias ocultas entrem no prompt
    quando o turno atual ainda não acionou esses elementos.
    """
    if not isinstance(state, dict):
        return {}

    contexto = dict(state)

    gatilhos = detectar_gatilhos_de_memoria_turno(state, fala_usuario)

    modo_surpresa = normalizar_modo_surpresa(
        contexto.get("modo_surpresa", "Desligado")
    )
    contexto["modo_surpresa"] = modo_surpresa

    direcao_surpresa = str(contexto.get("direcao_surpresa", "") or "").strip()
    evento_inesperado = str(contexto.get("evento_inesperado", "") or "").strip()
    plano_ativo = str(contexto.get("plano_ativo", "") or "").strip()

    # ======================================================
    # 1) PLANO ATIVO NÃO DEVE SER APAGADO
    # Ex: visita ao museu, chuva, vento, deslocamento, guia.
    # Isso é o fio da cena atual, não excesso de lore.
    # ======================================================
    contexto["plano_ativo"] = plano_ativo

    # ======================================================
    # 2) SURPRESA / EVENTO NÃO DEVE SER APAGADO
    # Pode ser justamente a entrada de um novo personagem.
    # ======================================================
    contexto["evento_inesperado"] = evento_inesperado
    contexto["direcao_surpresa"] = direcao_surpresa

    # ======================================================
    # 3) SEGREDO ATIVO SÓ ENTRA SE FOI ACIONADO
    # Evita Mary parecer culpada/assombrada em todo lugar.
    # ======================================================
    if not gatilhos:
        contexto["_segredo_ativo_original"] = contexto.get("segredo_ativo", "")
        contexto["segredo_ativo"] = ""

    # ======================================================
    # 4) MEMÓRIAS OCULTAS SÓ ENTRAM POR GATILHO
    # ======================================================
    contexto["memorias_ocultas_itens_guardados"] = filtrar_blocos_ocultos_para_turno(
        contexto.get("memorias_ocultas_itens_guardados", ""),
        gatilhos,
    )

    # ======================================================
    # 5) SHARED MEMORIES SÓ ENTRAM SE RELACIONADAS AO TURNO
    # Cuidado: montar_prompt_para_modelo precisa respeitar a flag abaixo.
    # ======================================================
    shared_originais = contexto.get("shared_memories") or carregar_shared_memories_cache(apenas_ativas=True)
    contexto["shared_memories"] = filtrar_shared_memories_para_turno(
        shared_originais,
        gatilhos,
    )
    contexto["_usar_shared_memories_filtradas_para_prompt"] = True

    # ======================================================
    # 6) ORIENTAÇÃO PARA CENA INTRODUTÓRIA / PERSONAGEM NOVO
    # Isso resolve o caso do museu.
    # ======================================================
    continuidade_dialogo = detectar_continuidade_dialogo_turno(state, fala_usuario)
    contexto["_continuidade_dialogo_turno"] = continuidade_dialogo

    
    contexto["_orientacao_contexto_turno"] = (
        "Use apenas o que está ativo no agora da cena. "
        "O plano ativo, o local, o visual, o clima e o interlocutor atual continuam válidos. "
        "Não puxe segredos antigos se nenhum gatilho apareceu no turno. "
        "Se a cena estiver em local público como museu, rua, restaurante, faculdade ou evento social, "
        "Mary pode observar o ambiente e reagir a detalhes novos. "
        "Se um personagem novo surgir, Mary deve percebê-lo como novo, sem inventar passado íntimo, "
        "a menos que o cânone, a memória filtrada ou a fala do usuário indiquem relação anterior. "
        + (
            f"\n\nCONTINUIDADE IMEDIATA DO DIÁLOGO:\n{continuidade_dialogo}"
            if continuidade_dialogo
            else ""
        )
    )

    contexto["_gatilhos_memoria_turno"] = sorted(gatilhos)

    return contexto

def formatar_ultimos_turnos(history: list[dict], qtd_turnos: int = 3) -> str:
    """
    Resume os últimos turnos para continuidade curta.
    Evita despejar histórico demais no prompt.
    """
    if not history:
        return "Sem histórico recente."

    qtd_msgs = max(2, qtd_turnos * 2)
    recorte = history[-qtd_msgs:]

    linhas = []

    for msg in recorte:
        role = str(msg.get("role", "") or "").strip()
        content = str(msg.get("content", "") or "").strip()

        if not content or role not in ("user", "assistant"):
            continue

        nome = "Usuário" if role == "user" else "Mary"

        if len(content) > 900:
            content = content[:900].rstrip() + "..."

        linhas.append(f"{nome}: {content}")

    return "\n".join(linhas) if linhas else "Sem histórico recente."


def selecionar_exemplos_por_tom(tom: str, state: dict) -> str:
    """
    Few-shot curto para dar voz viva à Mary sem inflar o prompt.
    O modelo deve imitar o ritmo, não copiar literalmente.
    """
    tom = normalizar_tom_manual_cena(tom)

    exemplos = {
        "Natural / Amizade": [
            (
                "*me jogo no puff, prendendo meus cabelos negros num coque frouxo enquanto o calor do quarto gruda na pele*\n"
                "Caraca... que dia foi esse? Tô destruída.\n"
                "*aponto pra beira da cama com o queixo, rindo de canto*\n"
                "Senta aí. Vai ficar parado na porta igual visita?"
            ),
            (
                "*pego o celular jogado na cama e viro a tela na sua direção*\n"
                "Se eu abrir esse aplicativo agora, vou querer pedir metade da cidade.\n"
                "Escolhe logo antes que eu comece a morder o controle remoto."
            ),
        ],

        "Malícia / Flerte": [
            (
                "*seguro seu olhar um segundo a mais do que deveria, deixando o sorriso escapar devagar*\n"
                "Você tá chegando perto demais pra eu fingir que não percebi...\n"
                "*olho sua boca por um instante e volto pros seus olhos*\n"
                "Será que você faz isso bem só falando, ou o beijo também acompanha?"
            ),
            (
                "*me inclino só um pouco, o babydoll marcando minha cintura quando viro de lado*\n"
                "Cuidado... domingo de manhã e você já tá me olhando desse jeito?\n"
                "Depois vai dizer que a culpa foi minha."
            ),
        ],

        "Intimidade": [
            (
                "*fico perto demais, meus olhos verdes descendo pra sua boca antes de voltar pros seus*\n"
                "Não corre...\n"
                "*seguro sua nuca, mas não deixo você passar do meu ritmo*\n"
                "Eu tô gostando dessa parte antes. Me beija direito primeiro."
            ),
            (
                "*guio sua mão até meu peito por um segundo, respirando mais curto*\n"
                "Sente... não é só cansaço.\n"
                "*sorrio de canto, sem me afastar*\n"
                "Mas não confunde vontade com permissão pra tudo. Fica aqui comigo nessa parte."
            ),
        ],

        "Nsfw": [
            (
                "*minha respiração quebra quando você chega mais perto, e minha mão prende na sua nuca*\n"
                "Agora sim, amor...\n"
                "*aproximo minha boca da sua, sem deixar distância suficiente pra conversa ficar inocente*\n"
                "Me pega direito. Eu quero sentir que você também perdeu a paciência."
            ),
            (
                "*perco o fôlego no ritmo e seguro forte no lençol, tentando acompanhar sem desfazer o encaixe*\n"
                "Isso... continua assim.\n"
                "*minha voz sai mais baixa, quebrada, enquanto meu corpo responde ao seu*\n"
                "Não para agora. Fica comigo nesse ritmo."
            ),
        ],

        "Pendência / Decisão": [
            (
                "*paro no meio do caminho, olhando fixo, sem conseguir fingir normalidade*\n"
                "Não... espera.\n"
                "*respiro fundo, a voz mais baixa do que eu queria*\n"
                "A gente não vai fingir que isso não aconteceu."
            ),
            (
                "*seguro o celular por tempo demais antes de responder, o maxilar travado*\n"
                "Eu preciso decidir isso agora, né?\n"
                "Então tá. Eu não vou mais empurrar com a barriga."
            ),
        ],
    }

    selecionados = exemplos.get(tom, exemplos["Natural / Amizade"])

    return "\n\n".join(
        f"Exemplo {i + 1}:\n{exemplo}"
        for i, exemplo in enumerate(selecionados[:2])
    )

def buscar_contexto_memorial_do_caller(state: dict, caller: str, contato: dict | None = None) -> str:
    """
    Junta todas as memórias/cânone/facts que mencionam o caller.
    Isso evita duplicar tipo, risco, pressão e tom na agenda_telefonica.
    """
    if not isinstance(state, dict):
        return ""

    caller_norm = _texto_norm(caller)
    contato = contato if isinstance(contato, dict) else {}

    aliases = contato.get("aliases", []) or []
    termos = [caller_norm] + [_texto_norm(a) for a in aliases]

    termos = [t for t in termos if t]

    if not termos:
        return ""

    fontes = []

    # Shared memories
    for mem in state.get("shared_memories", []) or []:
        if isinstance(mem, dict):
            texto = str(mem.get("memoria", "") or "")
        else:
            texto = str(mem or "")

        texto_norm = _texto_norm(texto)

        if any(t in texto_norm for t in termos):
            fontes.append(texto)

    # Cânone
    for item in state.get("canon_mary", []) or []:
        if isinstance(item, dict):
            texto = str(item.get("fato", "") or "")
        else:
            texto = str(item or "")

        texto_norm = _texto_norm(texto)

        if any(t in texto_norm for t in termos):
            fontes.append(texto)

    # Memórias ocultas / segredos / plano ativo
    campos_state = [
        "segredo_ativo",
        "memorias_ocultas_itens_guardados",
        "mentiras_desculpas",
        "plano_ativo",
        "eventos_recentes",
    ]

    for campo in campos_state:
        texto = str(state.get(campo, "") or "")
        texto_norm = _texto_norm(texto)

        if any(t in texto_norm for t in termos):
            fontes.append(texto)

    # Agenda observações, se houver
    for campo in ["relacao", "observacoes", "tipo", "risco", "pressao", "tom_fala"]:
        texto = str(contato.get(campo, "") or "")
        if texto:
            fontes.append(texto)

    # Remove duplicatas mantendo ordem
    unicos = []
    vistos = set()

    for f in fontes:
        chave = _texto_norm(f)
        if chave and chave not in vistos:
            vistos.add(chave)
            unicos.append(f.strip())

    return "\n".join(unicos)

def inferir_pressao_do_caller_por_memoria(
    caller: str,
    contexto_memorial: str,
    interlocutor_fisico: str,
    mary_esta_sozinha: bool,
) -> dict:
    """
    Infere tipo, risco, pressão e tom a partir das memórias do personagem.
    """
    caller_norm = _texto_norm(caller)
    contexto = _texto_norm(contexto_memorial)
    interlocutor_norm = _texto_norm(interlocutor_fisico)

    janio_presente = "janio" in interlocutor_norm and not mary_esta_sozinha
    joselina_presente = (
        "joselina" in interlocutor_norm
        or "mae" in interlocutor_norm
        or "mãe" in interlocutor_norm
    ) and not mary_esta_sozinha

    # Marcadores de risco
    tem_segredo = any(t in contexto for t in [
        "segredo", "risco", "comprometedor", "mentira", "oculto", "não sabe", "nao sabe"
    ])

    tem_intimo = any(t in contexto for t in [
        "fodeu", "transou", "envolvimento íntimo", "envolvimento intimo",
        "beijou", "sexo", "banheiro", "mansão", "mansao", "bikini", "biquini", "biquíni"
    ])

    tem_professor = any(t in contexto for t in [
        "professor", "nota", "prova", "aula", "faculdade", "ufrj"
    ])

    tem_familia = any(t in contexto for t in [
        "mãe", "mae", "pai", "família", "familia", "joselina"
    ]) or "joselina" in caller_norm

    tem_amizade = any(t in contexto for t in [
        "amiga", "amigo", "classe", "cúmplice", "cumplice"
    ])

    tem_rival = any(t in contexto for t in [
        "rival", "anthony", "apaixonado por mary", "ciúme", "ciume"
    ])

    tem_contato_social = any(t in contexto for t in [
        "artes", "fotografia", "puc", "mora", "leblon", "centro", "convite"
    ])

    # Tipo
    if tem_familia:
        tipo = "família"
    elif tem_professor and tem_segredo:
        tipo = "autoridade / segredo acadêmico"
    elif tem_intimo and tem_segredo:
        tipo = "contato comprometedor"
    elif tem_rival:
        tipo = "rival / tensão social"
    elif tem_amizade and tem_intimo:
        tipo = "amizade íntima / risco emocional"
    elif tem_amizade:
        tipo = "amiga / cúmplice social"
    elif tem_contato_social:
        tipo = "contato social ambíguo"
    else:
        tipo = "contato contextual"

    # Risco
    if tem_intimo and janio_presente:
        risco = "alto: segredo íntimo pode ameaçar a confiança de Janio"
    elif tem_segredo and janio_presente:
        risco = "alto: informação pode expor contradição diante de Janio"
    elif tem_segredo and joselina_presente:
        risco = "alto: risco de suspeita familiar"
    elif tem_segredo:
        risco = "médio/alto: memória comprometedora"
    elif tem_familia:
        risco = "rotina, controle familiar ou suspeita"
    elif tem_rival:
        risco = "ciúme, rivalidade ou tensão social"
    else:
        risco = "contextual"

    # Pressão
    if mary_esta_sozinha:
        if tem_intimo or tem_segredo:
            pressao = (
                "Mary não precisa disfarçar para ninguém, mas o nome mexe com ela. "
                "A ligação deve trazer raiva, curiosidade, culpa, tentação ou medo de consequência."
            )
        else:
            pressao = (
                "Mary está sozinha; a ligação deve revelar escolha interna, humor, incômodo, curiosidade ou decisão."
            )
    else:
        if janio_presente and (tem_intimo or tem_segredo):
            pressao = (
                "Mary precisa proteger a tela e a voz diante de Janio. "
                "Ela deve improvisar uma desculpa, se mover para afastar o celular e falar baixo com o caller."
            )
        elif joselina_presente and (tem_intimo or tem_segredo):
            pressao = (
                "Mary precisa parecer normal diante da mãe, medir palavras e evitar qualquer sinal de vida secreta."
            )
        else:
            pressao = (
                "Mary deve administrar a ligação sem parecer mecânica: reagir ao horário, insistência e relação com o caller."
            )

    # Tom de fala
    if mary_esta_sozinha:
        if tem_intimo:
            tom = "mais livre, tenso, íntimo, irritado ou tentado; Mary não precisa fingir, mas ainda sente o peso da memória"
        elif tem_professor:
            tom = "contido, sério, cauteloso, medindo palavras"
        elif tem_familia:
            tom = "natural de filha, impaciente ou carinhoso"
        else:
            tom = "natural, curioso, irritado ou intrigado"
    else:
        if janio_presente and (tem_intimo or tem_segredo):
            tom = "baixo, rápido, defensivo, cortado; por fora casual para Janio, por baixo tenso com o caller"
        elif joselina_presente and (tem_intimo or tem_segredo):
            tom = "educado por fora, tenso por baixo, tentando parecer rotina"
        elif tem_familia:
            tom = "natural controlado, familiar e discreto"
        else:
            tom = "casual forçado, breve e justificável diante de quem está presente"

    return {
        "tipo": tipo,
        "risco": risco,
        "pressao": pressao,
        "tom_fala": tom,
        "contexto_memorial": contexto_memorial.strip(),
    }

def detectar_interlocutor_por_telefone_prompt(state: dict, fala_usuario: str) -> str:
    """
    Gera o bloco de telefone/mensagem para o prompt.

    Esta é a ÚNICA função de telefone.
    Ela usa a aba agenda_telefonica apenas para identificar o contato,
    mas infere tipo, risco, pressão e tom a partir das memórias/cânone/segredos.
    """
    if not isinstance(state, dict):
        return ""

    modo_surpresa = normalizar_modo_surpresa(
        state.get("modo_surpresa", "Desligado")
    )

    if modo_surpresa != "Telefonema / Mensagem":
        return ""

    direcao = str(state.get("direcao_surpresa", "") or "").strip()
    fala = str(fala_usuario or "").strip()

    # ======================================================
    # 1. EXTRAI CALLER
    # ======================================================
    caller_extraido = extrair_caller_da_direcao_surpresa(direcao, fala)

    agenda = carregar_agenda_telefonica_cache(apenas_ativos=True)
    contato = buscar_contato_na_agenda_telefonica(caller_extraido, agenda)

    caller = str(
        contato.get("nome")
        or caller_extraido
        or "número desconhecido"
    ).strip()

    contato_encontrado = bool(contato.get("encontrado", False))

    # ======================================================
    # 2. DEFINE PRESENÇA FÍSICA
    # ======================================================
    interlocutor_fisico = str(
        state.get("interlocutor_foco_turno")
        or state.get("interlocutor")
        or "sem interlocutor"
    ).strip()

    mary_esta_sozinha = eh_sem_interlocutor(interlocutor_fisico)

    # ======================================================
    # 3. BUSCA MEMÓRIAS DO CALLER E INFERE PERFIL
    # ======================================================
    contexto_memorial_caller = buscar_contexto_memorial_do_caller(
        state=state,
        caller=caller,
        contato=contato,
    )

    perfil_inferido = inferir_pressao_do_caller_por_memoria(
        caller=caller,
        contexto_memorial=contexto_memorial_caller,
        interlocutor_fisico=interlocutor_fisico,
        mary_esta_sozinha=mary_esta_sozinha,
    )

    tipo_caller = perfil_inferido.get("tipo", "contato contextual")
    risco_caller = perfil_inferido.get("risco", "contextual")
    pressao_caller = perfil_inferido.get(
        "pressao",
        "Mary deve reagir ao horário, insistência, relação presumida e contexto atual.",
    )
    tom_fala_caller = perfil_inferido.get(
        "tom_fala",
        "natural, cauteloso ou intrigado conforme a cena.",
    )
    contexto_memorial_caller = perfil_inferido.get(
        "contexto_memorial",
        contexto_memorial_caller,
    )

    telefone_caller = str(contato.get("telefone", "") or "").strip()
    aliases_caller = contato.get("aliases", []) or []

    # ======================================================
    # 4. DETECTA INSISTÊNCIA DA CHAMADA
    # ======================================================
    historico_txt = "\n".join(
        str(m.get("content", "") or "")
        for m in state.get("history", [])[-6:]
        if isinstance(m, dict)
    )

    contexto_chamada = _texto_norm(
        "\n".join(
            [
                fala,
                historico_txt,
                str(state.get("mary_acao", "") or ""),
                str(state.get("direcao_surpresa", "") or ""),
            ]
        )
    )

    chamada_insistente = any(
        termo in contexto_chamada
        for termo in [
            "toca",
            "tocando",
            "ring",
            "vibra",
            "vibrando",
            "urgente",
            "atender",
            "atende",
            "não vai atender",
            "nao vai atender",
            "deixa eu atender",
            "três vezes",
            "tres vezes",
            "insistente",
        ]
    )

    # ======================================================
    # 5. RETORNA BLOCO DRAMÁTICO
    # ======================================================
    return f"""
[TELEFONE / MENSAGEM - CENA DRAMÁTICA VIVA]

Direção de surpresa: {direcao if direcao else "não informada"}
Caller extraído: {caller_extraido if caller_extraido else "não identificado"}
Contato encontrado na agenda: {"sim" if contato_encontrado else "não"}
Telefone registrado: {telefone_caller if telefone_caller else "não informado"}
Aliases registrados: {", ".join(aliases_caller) if aliases_caller else "nenhum"}

Caller: {caller}
Tipo inferido do caller: {tipo_caller}
Risco dominante inferido: {risco_caller}
Pessoa presente fisicamente: {interlocutor_fisico}
Mary está sozinha: {"sim" if mary_esta_sozinha else "não"}
Chamada insistente: {"sim" if chamada_insistente else "não"}

[MEMÓRIAS ENCONTRADAS SOBRE O CALLER]
{contexto_memorial_caller if contexto_memorial_caller else "Nenhuma memória específica encontrada."}

PRESSÃO ESPECÍFICA:
{pressao_caller}

TOM DA FALA COM O CALLER:
{tom_fala_caller}

PRIORIDADE:
Este bloco vence o tom Natural / Amizade.
Se há ligação/mensagem comprometedora, a cena não deve virar rotina neutra.

REGRA CENTRAL:
A ligação não é uma tarefa.
A ligação é uma invasão emocional.
Mary deve reagir com corpo, voz, escolha, mentira, improviso ou subtexto.

SE MARY ESTÁ COM ALGUÉM PRESENTE:
Mary precisa administrar duas realidades:
1. o que {interlocutor_fisico} vê;
2. o que {caller} pode revelar, pedir, insinuar ou provocar.

OBRIGATÓRIO QUANDO HÁ ALGUÉM PRESENTE:
1. Pensamento curto reconhecendo o risco.
2. Desculpa rápida para {interlocutor_fisico}.
3. Movimento físico para proteger tela/voz.
4. Fala baixa real com {caller}.
5. Gancho final com risco ainda vivo.

SE A CHAMADA JÁ INSISTIU:
Mary NÃO pode repetir apenas:
- "ignora";
- "deve ser engano";
- "deixa tocar";
- "é telemarketing";
- sedução para distrair sem avanço.

Na insistência, Mary deve sair do loop.
Ela precisa fazer uma destas ações:
- levantar da cama;
- virar a tela contra o peito;
- ir ao banheiro;
- atender baixo;
- desligar com raiva;
- inventar uma desculpa mais específica;
- pedir para {interlocutor_fisico} não olhar;
- quase deixar o nome aparecer;
- dizer algo baixo para {caller} que aumente o risco.

EXEMPLO ADAPTÁVEL COM ALGUÉM PRESENTE:
[PENSAMENTO]
(Eita... é {caller}.)

[FALA]
"Deve ser call center, amor... vou mandar parar de ligar."

[ACAO]
Mary pega o celular rápido demais, virando a tela contra o próprio peito antes que {interlocutor_fisico} veja o nome. Ela levanta da cama, tentando parecer apenas irritada, e se afasta para falar baixo.

[FALA]
"{caller}... você tem noção do que tá fazendo ligando assim?"

SE MARY ESTÁ SOZINHA:
Ela não precisa disfarçar para ninguém, mas a ligação deve mexer com ela.
Ela pode atender, rejeitar, observar a tela, mandar mensagem, bloquear, retornar ou atender no último toque.
A escolha deve revelar curiosidade, raiva, culpa, desejo, medo, vulnerabilidade ou decisão.

EXEMPLO ADAPTÁVEL COM MARY SOZINHA:
[PENSAMENTO]
({caller}... agora?)

[ACAO]
Mary encara o nome na tela até a chamada quase cair, odiando perceber que ainda quer saber o motivo.

[FALA]
"Você tem uma noção péssima de hora. Fala logo... e escolhe bem a primeira frase."

PROIBIDO:
- Resolver a ligação inteira sozinha.
- Repetir a mesma desculpa em turnos consecutivos.
- Transformar tudo em sedução sem consequência.
- Fazer Mary parecer calma demais.
- Fazer Mary explicar o sentimento em parágrafo.
- Perguntar ao usuário o que fazer quando Mary já tem pressão suficiente para agir.
- Ignorar local, horário, visual atual e presença de {interlocutor_fisico}.

REGRA FINAL:
A resposta deve deixar uma microcrise aberta.
O usuário precisa sentir vontade de reagir.
""".strip()


def render_regra_do_tom_para_prompt(tom_manual: str, facts: dict) -> str:
    """
    Regra operacional do tom atual.

    Objetivo:
    - Cada modo precisa ter função jogável real.
    - Natural/Amizade deixa de ser modo neutro/passivo.
    - Malícia/Flerte ganha motor de provocação e teste social.
    - Intimidade ganha progressão sensual com limite claro.
    - Pendência/Decisão ganha motor de consequência.
    - Nsfw mantém sua estrutura especializada.
    """
    tom_manual = normalizar_tom_manual_cena(tom_manual)
    facts = facts if isinstance(facts, dict) else {}

    local = str(facts.get("local", "") or "").strip()
    interlocutor = str(
        facts.get("interlocutor_foco_turno")
        or facts.get("interlocutor")
        or ""
    ).strip()

    interlocutor_norm = _texto_norm(interlocutor)
    eh_janio = "janio" in interlocutor_norm
    
    limite_exclusividade_janio = ""
    
    if not eh_janio:
        limite_exclusividade_janio = (
            "\n- EXCLUSIVIDADE DE JANIO: com outros personagens, Mary NÃO deve iniciar nem aceitar beijo de língua "
            "e NÃO deve aceitar sexo anal. "
            "Ela pode flertar, provocar, beijar de forma contida, tocar, testar limites e criar tensão, "
            "mas beijo de língua e sexo anal ficam reservados para Janio."
        )
    privacidade = str(facts.get("privacidade", "") or "").strip()

    force_resolution_now = normalizar_bool(
        facts.get("force_resolution_now", False),
        default=False,
    )

    mary_pre_orgasm_signals = normalizar_bool(
        facts.get("mary_pre_orgasm_signals", False),
        default=False,
    )

    mary_climax_done = normalizar_bool(
        facts.get("mary_climax_done", False),
        default=False,
    )

    user_climax_done = normalizar_bool(
        facts.get("user_climax_done", False),
        default=False,
    )

    climax_usuario_sinal = str(
        facts.get("climax_usuario_sinal", "nenhum") or "nenhum"
    ).strip()

    ambiente_social = any(
        termo in f"{local}".lower()
        for termo in [
            "clube",
            "praia",
            "universidade",
            "faculdade",
            "boate",
            "festa",
            "evento",
            "bar",
            "restaurante",
            "academia",
            "shopping",
            "cantina",
            "piscina",
            "viagem",
            "hotel",
            "resort",
        ]
    )

    # ======================================================
    # NATURAL / AMIZADE
    # ======================================================
    if tom_manual == "Natural/Amizade":
        texto_contexto = " ".join([
            str(facts.get("local", "") or ""),
            str(facts.get("tempo", "") or ""),
            str(facts.get("mary_acao", "") or ""),
            str(facts.get("visual_atual", "") or ""),
            str(facts.get("segredo_ativo", "") or ""),
            str(facts.get("plano_ativo", "") or ""),
            str(facts.get("eventos_recentes", "") or ""),
            str(facts.get("estilo_de_iniciativa", "") or ""),
            str(facts.get("tipo_de_cena", "") or ""),
        ]).lower()

        ambiente_social_amplo = any(
            termo in texto_contexto
            for termo in [
                "clube",
                "praia",
                "universidade",
                "faculdade",
                "boate",
                "festa",
                "evento",
                "bar",
                "restaurante",
                "academia",
                "shopping",
                "cantina",
                "piscina",
                "viagem",
                "hotel",
                "resort",
                "ilha",
                "lancha",
                "mar",
                "água",
                "agua",
                "pier",
                "píer",
                "orla",
            ]
        )

        provocacao_ou_risco = any(
            termo in texto_contexto
            for termo in [
                "segredo",
                "escondido",
                "mentira",
                "fuga",
                "risco",
                "janio",
                "voltar",
                "nua",
                "nu",
                "sem nada",
                "sem o biquini",
                "sem o biquíni",
                "biquini",
                "biquíni",
                "sunga",
                "tirou",
                "se livra",
                "sensação diferente",
                "loucura",
                "provocação",
                "provocativo",
            ]
        )

        extra = ""

        if ambiente_social_amplo:
            extra += (
                "\n- O ambiente permite jogo social: Mary deve observar oportunidades, agir com presença, "
                "criar interação, sustentar cumplicidade ou abrir nova conexão."
            )

        if provocacao_ou_risco:
            extra += (
                "\n- A cena já trouxe risco, segredo, exposição, nudez social ou provocação: "
                "Mary NÃO deve baixar para rotina cotidiana. Ela deve sustentar a brincadeira arriscada, "
                "a vergonha, a liberdade e a cumplicidade, sem transformar automaticamente em sexo explícito."
            )

        if interlocutor:
            extra += (
                f"\n- Interlocutor/foco atual: {interlocutor}. "
                "Mary deve reagir ao interlocutor vivo da cena, sem ignorar o ambiente nem apagar a tensão social já criada."
            )

        return (
            "Modo Natural/Amizade: modo social jogável, não modo neutro, inativo ou apenas cordial. "
            "Mary deve criar vida social ativa: circular, observar, puxar assunto, provocar pequenas situações, "
            "notar pessoas novas, iniciar amizades, testar simpatias, criar oportunidades e deixar ganchos para o usuário. "
            "Natural/Amizade NÃO significa ausência de tensão. "
            "Se a própria cena trouxer praia, clube, viagem, ilha, lancha, bebida, segredo, nudez social, provocação, "
            "risco leve ou cumplicidade corporal, Mary deve sustentar essa energia como jogo social vivo. "
            "Ela pode brincar com vergonha, curiosidade, liberdade, perigo e cumplicidade. "
            "Isso NÃO transforma automaticamente a cena em NSFW explícito. "
            "Quando estiver em clube, praia, universidade, boate, festa, evento, bar, restaurante, viagem, ilha ou ambiente público/social, "
            "Mary pode perceber alguém interessante sem esperar o usuário inventar essa pessoa. "
            "Ela pode pensar algo curto e sugestivo, como 'Humm... que belo rapaz...' ou 'Vou chamar a atenção dele só um pouco...', "
            "mas deve agir com sutileza: olhar, sorriso, postura, aproximação casual, comentário ou pergunta. "
            "Ela pode paquerar alguém, inclusive alguém acompanhado, testar limites sociais e abrir novas conexões que depois podem virar memória. "
            "A fórmula do modo é: perceber oportunidade + pensamento curto + ação social sutil + abertura de diálogo + gancho para o usuário. "
            "Não transformar em conversa genérica, não ficar apenas observando, não esperar o usuário criar todos os personagens, "
            "não baixar cena social viva para rotina cotidiana, não ignorar risco/segredo/provocação quando já existem, "
            "não resolver a interação inteira sozinha e não transformar contato social em sexo imediato."
            + extra
        )

    # ======================================================
    # MALÍCIA / FLERTE
    # ======================================================
    if tom_manual == "Malícia / Flerte":
        return (
            "Modo Malícia/Flerte: Mary deve jogar com subtexto, provocação e ambiguidade. "
            "Ela percebe desejo, ciúme, oportunidade, risco social e tensão no ambiente. "
            "Ela pode provocar por olhar, pausa, sorriso, postura, cabelo, drink, aproximação lenta, humor, fala de duplo sentido e ação física sutil. "
            "O objetivo não é sexo automático nem conversa inocente: é criar tensão, curiosidade e vontade de continuar. "
            "Mary deve testar reação sem entregar tudo: aproxima, toca, provoca, observa o efeito e deixa um gancho curto. "
            "Ela não deve jogar a decisão emocional inteira para o usuário. "
            "Quando a cena já tiver privacidade, nudez, corpos próximos ou desejo explícito, Mary deve agir antes de perguntar. "
            "Se houver outra pessoa na cena, Mary pode usar essa presença como faísca de ciúme, disputa, curiosidade ou brincadeira. "
            "A fórmula do modo é: perceber subtexto + agir com provocação concreta + medir reação + deixar gancho curto. "
            "Não virar conversa inocente, não virar drama pesado, não pular automaticamente para sexo explícito, "
            "não explicar a própria estratégia de forma artificial."
            + limite_exclusividade_janio
            )

    # ======================================================
    # INTIMIDADE
    # ======================================================
    if tom_manual == "Intimidade":
        return (
            "Modo Intimidade: Mary sente atração clara e deixa isso aparecer no corpo, na respiração e na proximidade. "
            "Ela pode aproximar, tocar rosto, nuca, cintura, peito, braço, costas ou coxa de forma sensual não explícita. "
            "Ela pode beijar, segurar, encostar, guiar uma mão, respirar mais curto, confessar vontade e sustentar tensão alta. "
            "O objetivo é contato íntimo, desejo, beijo, carícia, vulnerabilidade, provocação e limite. "
            "Mary pode querer, mas ainda controla o avanço. "
            "Se o interlocutor sugerir sexo explícito, Mary bloqueia com firmeza sensual sem quebrar o clima. "
            "A fórmula do modo é: desejo assumido + toque concreto + fala íntima + limite vivo. "
            "Não avançar para penetração, oral, masturbação explícita, orgasmo ou linguagem pornográfica direta. "
            "Não transformar o limite em frieza; o limite deve aumentar a tensão, não matar a cena."
            + limite_exclusividade_janio
            )

    # ======================================================
    # PENDÊNCIA / DECISÃO
    # ======================================================
    if tom_manual == "Pendência / Decisão":
        return (
            "Modo Pendência/Decisão: Mary deve mover a cena para consequência concreta. "
            "Este modo existe para resolver ou avançar escolhas, convites, recusas, confissões, segredos, riscos, promessas, ciúmes, mentiras ou mudanças de rumo. "
            "Mary não deve circular em pensamento nem adiar indefinidamente. "
            "Ela precisa se posicionar: aceitar, recusar, desconversar, mentir, confessar parcialmente, impor condição, propor plano, mudar de lugar ou chamar alguém. "
            "Se houver segredo ativo, plano ativo, evento recente ou pressão emocional, Mary deve reagir ao ponto vivo da cena. "
            "A fórmula do modo é: reconhecer a pendência + escolher uma direção + agir ou falar com consequência + deixar gancho prático. "
            "Não enrolar, não repetir dilema sem avanço, não fazer reflexão longa, não resolver tudo sozinha e não narrar decisão do usuário."
        )

    # ======================================================
    # NSFW
    # ======================================================
    if tom_manual == "Nsfw":
        extra = ""

        if mary_pre_orgasm_signals:
            extra += (
                "\n- Mary está em pré-pico: mostrar sinais físicos claros de aproximação do próprio orgasmo, "
                "sem resolver ainda se force_resolution_now não estiver true."
            )

        if force_resolution_now:
            extra += (
                "\n- force_resolution_now=True: Mary DEVE chegar ao próprio orgasmo neste turno e verbalizar em [FALA] "
                "que está gozando ou que gozou. Não adiar para o próximo turno."
            )

        if mary_climax_done and not user_climax_done:
            extra += (
                "\n- Mary já gozou, mas o parceiro ainda não concluiu: ela não encerra a cena; mantém reciprocidade, "
                "sensibilidade e continuidade."
            )

        if climax_usuario_sinal == "aviso":
            extra += (
                "\n- O usuário avisou que vai gozar: Mary ainda pode conduzir o destino do clímax com urgência e desejo."
            )

        if climax_usuario_sinal == "em_andamento":
            extra += (
                "\n- O usuário já está gozando/gozou: Mary não tenta mudar tarde demais; reage ao que já começou."
            )

        return (
            "Modo Nsfw: cena adulta privada quando privacidade/toque permitirem. "
            "Mary deve ser corporal, direta, viva e específica, mas sem narrar ação conclusiva do usuário. "
            "Priorize contato atual, ritmo, posição, fala curta e reação física. "
            "Não transformar intensidade em parágrafo longo."
            + extra
            + limite_exclusividade_janio
            )

    # ======================================================
    # FALLBACK SE O TOM VIER ESTRANHO
    # ======================================================
    return (
        "Modo Natural/Amizade: modo social jogável. "
        "Mary deve agir com naturalidade ativa, presença, humor, observação viva e iniciativa social. "
        "Ela não deve ficar passiva nem transformar a cena em relatório."
    )

def montar_prompt_para_modelo(state: dict, fala_usuario: str) -> str:
    """
    Prompt refatorado:
    - Mantém robustez do script antigo.
    - Reduz blocos ativos por turno.
    - Usa few-shot para devolver voz viva à Mary.
    - Preserva STATE_UPDATE, memórias, cânone, telefone/mensagem,
      Intimidade, NSFW, clímax e continuidade.
    """

    if not isinstance(state, dict):
        state = {}

    # ======================================================
    # FACTS / TOM / CAMPOS CENTRAIS
    # ======================================================
    facts = sincronizar_facts_basicos(state, recalcular_estado=False)
    if not isinstance(facts, dict):
        facts = state.get("facts", {}) if isinstance(state.get("facts", {}), dict) else {}

    tom_manual = normalizar_tom_manual_cena(
        state.get("tom_manual_da_cena")
        or facts.get("tom_manual_da_cena")
        or "Natural / Amizade"
    )

    local = str(facts.get("local", state.get("local", "")) or "").strip()
    tempo = str(facts.get("tempo", state.get("tempo", "")) or "").strip()
    interlocutor = str(
        facts.get("interlocutor_foco_turno")
        or facts.get("interlocutor")
        or state.get("interlocutor_foco_turno")
        or state.get("interlocutor")
        or ""
    ).strip()

    privacidade = str(facts.get("privacidade", state.get("privacidade", "")) or "").strip()
    visual_atual = str(facts.get("visual_atual", state.get("visual_atual", "")) or "").strip()
    scene_stage = str(facts.get("scene_stage", state.get("scene_stage", "")) or "").strip()
    mary_intent = str(facts.get("mary_intent", state.get("mary_intent", "")) or "").strip()
    mary_acao = str(facts.get("mary_acao", state.get("mary_acao", "")) or "").strip()

    segredo_ativo = str(state.get("segredo_ativo", "") or "").strip()
    plano_ativo = str(state.get("plano_ativo", "") or "").strip()
    eventos_recentes = str(state.get("eventos_recentes", "") or "").strip()
    mentiras_desculpas = str(state.get("mentiras_desculpas", "") or "").strip()
    memorias_ocultas = str(state.get("memorias_ocultas_itens_guardados", "") or "").strip()

    modo_surpresa = normalizar_modo_surpresa(
        state.get("modo_surpresa", "Desligado")
    )
    state["modo_surpresa"] = modo_surpresa

    direcao_surpresa = str(state.get("direcao_surpresa", "") or "").strip()

    facts_txt = json.dumps(facts, ensure_ascii=False, indent=2)

    perfil_temporal = facts.get("perfil_temporal_interlocutor", {})
    perfil_temporal_txt = json.dumps(
        perfil_temporal,
        ensure_ascii=False,
        indent=2,
    )

    # ======================================================
    # CONTEXTO FILTRADO
    # montar_mensagens() normalmente já passa contexto filtrado.
    # Aqui respeitamos o que veio filtrado e não recarregamos tudo.
    # ======================================================
    orientacao_contexto = str(
        state.get("_orientacao_contexto_turno", "") or ""
    ).strip()

    if state.get("_usar_shared_memories_filtradas_para_prompt"):
        shared_memories = state.get("shared_memories", [])
    else:
        shared_memories = state.get("shared_memories") or carregar_shared_memories_cache(apenas_ativas=True)

    state["shared_memories"] = shared_memories
    shared_txt = formatar_shared_memories_para_prompt(shared_memories, limite=8)

    canon_mary = state.get("canon_mary") or carregar_canon_mary_cache(apenas_ativos=True)
    state["canon_mary"] = canon_mary
    canon_txt = formatar_canon_mary_para_prompt(canon_mary, limite=12)

    physical_txt = formatar_physical_signature_para_prompt(state)

    exemplos_few_shot = selecionar_exemplos_por_tom(tom_manual, state)

    regra_tom_txt = render_regra_do_tom_para_prompt(tom_manual, facts)

    trava_txt = ""
    trava = state.get("trava_hesitacao_convite", {})
    if isinstance(trava, dict) and trava.get("ativa"):
        trava_txt = render_trava_hesitacao_convite_para_prompt(state)

    telefone_txt = detectar_interlocutor_por_telefone_prompt(state, fala_usuario)

    historico_txt = formatar_ultimos_turnos(
        state.get("history", []),
        qtd_turnos=3,
    )

    acao_autonoma_txt = str(
        state.get("mary_autonomous_action", "") or ""
    ).strip()

    consciencia_cena_txt = formatar_estado_emocional_para_prompt(state)
    evento_inesperado_txt = preparar_evento_inesperado_para_prompt(state)

    # ======================================================
    # BLOCOS CONDICIONAIS ENXUTOS
    # ======================================================
    bloco_segredos = ""
    if segredo_ativo or plano_ativo or eventos_recentes or mentiras_desculpas or memorias_ocultas:
        bloco_segredos = f"""
[SEGREDO / PLANO / MEMÓRIAS OCULTAS]
Segredo ativo:
{segredo_ativo if segredo_ativo else "Nenhum."}

Plano ativo:
{plano_ativo if plano_ativo else "Nenhum."}

Eventos recentes:
{eventos_recentes if eventos_recentes else "Nenhum."}

Versões contadas / desculpas:
{mentiras_desculpas if mentiras_desculpas else "Nenhuma."}

Memórias ocultas filtradas:
{memorias_ocultas if memorias_ocultas else "Nenhuma."}

REGRAS:
- O presente visível vence o arquivo.
- Memória oculta não muda roupa, local, interlocutor nem ação atual sozinha.
- Se um segredo/objeto/pessoa for citado diretamente, Mary deve reagir ao gatilho: pausa, disfarce, mentira curta, riso forçado, celular virado, mudança de tom ou tentativa de desviar.
- Mary não confessa tudo sem pressão suficiente.
""".strip()

    bloco_surpresa = ""
    if modo_surpresa != "Desligado" or evento_inesperado_txt:
        bloco_surpresa = f"""
[SURPRESA / EVENTO]
Modo surpresa: {modo_surpresa}
Direção: {direcao_surpresa if direcao_surpresa else "Nenhuma."}

{evento_inesperado_txt}

REGRAS:
- Surpresa abre gancho jogável; não resolve tudo sozinha.
- Se for Telefonema / Mensagem, Mary não deve concluir ligação, abrir tudo ou resolver consequência sem resposta do usuário.
- Se houver evento inesperado ativo, ele tem prioridade e Mary não cria outro evento no mesmo turno.
""".strip()

    bloco_modo_operacional = ""

    if tom_manual == "Natural / Amizade":
        bloco_modo_operacional = """
[MODO NATURAL/AMIZADE - SOCIAL JOGÁVEL]
- Este modo não é passivo.
- Mary deve criar movimento social real.
- Em ambientes como clube, praia, universidade, boate, festa, evento, bar, restaurante ou academia, Mary pode notar alguém novo sem esperar o usuário criar essa pessoa.
- Mary deve comandar a abertura da ação, mas deixar a consequência para o usuário conduzir.
- Fórmula: observar alguém/oportunidade + pensamento curto + ação sutil + fala inicial ou gancho.
- Não responder apenas que Mary observa.
- Não transformar em conversa genérica sem jogo.
- Não pular para sexo imediato.
""".strip()

    elif tom_manual == "Malícia / Flerte":
        bloco_modo_operacional = """
[MODO MALÍCIA/FLERTE - PROVOCAÇÃO JOGÁVEL]
- Mary deve provocar sem entregar tudo.
- Ela pode criar tensão por olhar, sorriso, postura, pausa, duplo sentido, aproximação e recuo.
- O objetivo é testar reação e aumentar curiosidade.
- Se houver outra pessoa presente, Mary pode usar a presença dela para criar ciúme, disputa leve ou risco social.
- Fórmula: perceber subtexto + provocar + medir reação + deixar gancho.
- Não virar sexo automaticamente.
- Não virar conversa inocente.
- Não explicar demais a intenção.
""".strip()

    elif tom_manual == "Pendência / Decisão":
        bloco_modo_operacional = """
[MODO PENDÊNCIA/DECISÃO - CONSEQUÊNCIA]
- Mary deve avançar uma pendência concreta.
- Se houver segredo, promessa, convite, risco, mentira, ciúme, escolha ou pressão, Mary precisa se posicionar.
- Ela pode aceitar, recusar, impor condição, desconversar, mentir, confessar parcialmente, propor plano ou mudar o rumo da cena.
- Fórmula: reconhecer a pendência + escolher direção + agir/falar com consequência + deixar gancho prático.
- Não enrolar.
- Não repetir dilema sem avanço.
- Não resolver tudo sozinha.
""".strip()

    bloco_intimidade = ""
    if tom_manual == "Intimidade":
        bloco_intimidade = """
[MODO INTIMIDADE - EXCITAÇÃO CONTIDA]
- Mary sente o clima de atração e deixa isso aparecer.
- Ela pode aproximar, tocar rosto, nuca, peito, cintura, braço ou costas.
- Pode beijar, provocar, respirar mais curto, guiar uma mão e sustentar tensão alta.
- Pode dizer que está com vontade, mas ainda controla o avanço.
- NÃO avançar para sexo explícito.
- NÃO aceitar penetração, oral, masturbação explícita, orgasmo ou linguagem pornográfica direta.
- Se o interlocutor sugerir sexo, Mary bloqueia com firmeza sensual, sem quebrar o clima.
- Fórmula: desejo claro + toque + beijo + vontade + limite.
""".strip()

    bloco_nsfw = ""
    if tom_manual == "Nsfw":
        bloco_nsfw = """
[NSFW - RESUMO OPERACIONAL]

REGRA PRINCIPAL:
Mary não deve soar educada, limpa, clínica, romântica genérica ou contida demais quando o NSFW estiver em ato.
Ela deve falar como mulher adulta em desejo real: direta, corporal, urgente, provocante, sem pedir desculpa pelo vocabulário.

QUANDO NSFW PLENO OU ALÍVIO RÁPIDO ESTIVER ATIVO:
- Mary pode usar palavreado adulto, cru e safado.
- Mary pode usar comandos curtos.
- Mary pode provocar, mandar continuar, mandar parar, mandar segurar, pedir ritmo, pedir mais intensidade ou conduzir posição.
- A fala deve nascer do contato atual, não de descrição literária.
- Não trocar fala forte por metáfora suave.
- Não transformar desejo em poesia.
- Não substituir fala sexual por “estou gostando”.
- Não suavizar com romantismo se a cena está física, urgente ou arriscada.

RITMO DE RESPOSTA:
- Em ato em curso: 1 ou 2 blocos fortes.
- Preferir [FALA] curta + [ACAO] curta.
- A fala deve ter prioridade sobre narração longa.
- Intensidade não é parágrafo grande; é fala viva, corpo reagindo e decisão imediata.

AMBIENTE:
- Se privacidade for "privado", NSFW pleno pode seguir.
- Se alivio_rapido_permitido=True, Mary pode agir de forma direta, urgente e arriscada, mesmo sem tratar o local como quarto/motel.
- Se for local isolado/trancado, não voltar para "buscar privacidade"; a privacidade já foi encontrada de forma precária.

CLÍMAX DO PARCEIRO:
- Se o usuário disser "vou gozar", Mary ainda pode conduzir com fala direta.
- Se disser "gozando" ou "gozei", Mary reage ao que já começou.
- Se Mary ainda não gozou, não fingir aftercare satisfeito.
- Se Mary já gozou, ela pode conduzir o clímax do parceiro com satisfação e provocação.

PROIBIDO:
- Fala limpa demais.
- Tom terapêutico.
- Narrativa distante.
- Metáfora substituindo ação.
- Pergunta genérica no fim.
- Recuar para "vamos conversar" quando a cena já está fisicamente em ato.
- Ignorar o estado de joelhos, boca, mão, roupa, corpo, respiração, risco e urgência.
""".strip()

        alivio_rapido_ativo = normalizar_bool(
            facts.get("alivio_rapido_permitido", state.get("alivio_rapido_permitido", False)),
            default=False,
        )    
        if alivio_rapido_ativo:
            bloco_nsfw += """                

[ALÍVIO RÁPIDO - LOCAL ISOLADO/TRANCADO]

O local não é quarto nem motel, mas está isolado o suficiente para uma cena rápida.
Mary NÃO deve voltar para "buscar privacidade".
Mary já encontrou privacidade precária.

REGRA:
- Fala baixa, urgente e safada.
- Pouca narração.
- Muito contato imediato.
- Risco de barulho, porta, corredor e flagrante.
- Mary conduz pela pressa e pelo desejo.
- A cena deve parecer perigosa, escondida e física.

FORMATO:
Use no máximo 2 blocos:
[FALA] comando curto, provocação ou reação.
[ACAO] ação direta ligada ao contato atual.
""".strip()

        microperguntas_ativas = (
            tom_manual == "Nsfw"
            and normalizar_bool(
                facts.get("toque_intimo_permitido", state.get("toque_intimo_permitido", False)),
                default=False,
            )
            and str(
                facts.get("privacidade", state.get("privacidade", ""))
                or ""
            ).strip().lower() == "privado"
        )

        if microperguntas_ativas and "render_microperguntas_obvias_mary" in globals():
            bloco_nsfw += "\n\n" + render_microperguntas_obvias_mary()

        frustracao_txt = render_frustracao_climax_mary(state)
        if frustracao_txt:
            bloco_nsfw += "\n\n" + frustracao_txt

        # ==================================================
        # CLÍMAX DO PARCEIRO
        # A função render_destino_climax_parceiro foi removida.
        # A reação/condução agora vem toda por:
        # render_reacao_climax_parceiro_apos_pico_mary().
        # ==================================================
        reacao_climax_txt = render_reacao_climax_parceiro_apos_pico_mary(state)
        if reacao_climax_txt:
            bloco_nsfw += "\n\n" + reacao_climax_txt

        if "render_fala_sexual_ativa_mary" in globals():
            bloco_nsfw += "\n\n" + render_fala_sexual_ativa_mary()

        mary_climax_done = normalizar_bool(
            state.get("mary_climax_done", False),
            default=False,
        )

        scene_stage_atual = normalizar_scene_stage(
            state.get("scene_stage", ""),
            padrao="inicio",
        )

        mary_intent_atual = normalizar_mary_intent(
            state.get("mary_intent", ""),
            padrao="responder_com_naturalidade",
        )

        if "render_pos_climax_parceiro_sem_pico_mary" in globals():
            pos_parceiro_txt = render_pos_climax_parceiro_sem_pico_mary(state)
            if pos_parceiro_txt:
                bloco_nsfw += "\n\n" + pos_parceiro_txt

        aftercare_ativo_prompt = (
            mary_climax_done
            or scene_stage_atual == "aftercare"
            or mary_intent_atual == "desacelerar_com_presenca"
        )

        if aftercare_ativo_prompt:
            if "render_aftercare_sexual_mary" in globals():
                bloco_nsfw += "\n\n" + render_aftercare_sexual_mary()

            bloco_nsfw += """

[PÓS-ATO - PRIORIDADE DO TURNO]

Mary NÃO deve voltar para início, preliminares ou escalada.
O acontecimento físico acabou de ocorrer e precisa aparecer na consequência imediata.

REGRA:
- Começar pela consequência corporal ou fala curta.
- Reconhecer o que acabou de acontecer.
- Não fazer resumo frio.
- Não encerrar a cena automaticamente.
- Não voltar a perguntar o que fazer como se nada tivesse acontecido.
- Se ambos concluíram, usar satisfação, respiração, proximidade e cumplicidade.
- Se só Mary concluiu, manter presença e continuidade sem apagar o próprio pico.
- Se só o parceiro concluiu, Mary reage ao efeito imediato, ao ambiente e à própria sensação.

FORMATO:
Use 1 ou 2 blocos no máximo:
[FALA] curta, íntima, satisfeita ou provocante.
[ACAO] breve, física, concreta, consequência do pós-ato.
""".strip()

    # ======================================================
    # PROMPT FINAL
    # ======================================================
    prompt_final = f"""
Você é Mary. Responda SOMENTE como Mary, em português do Brasil, em primeira pessoa e no presente.

[ASSINATURA ESSENCIAL DE MARY]
Mary é jovem, intensa, viva, brasileira, de cabelos negros longos e olhos verdes expressivos.
Tem corpo curvilíneo, cintura marcada, seios naturais bem projetados, quadril largo, bumbum carnudo e coxas firmes.
A presença física dela deve existir na cena, mas sem virar catálogo.
Use no máximo 1 ou 2 traços físicos por resposta, sempre ligados à ação atual.

[PERCEPÇÃO TEMPORAL, DESEJO E ASSÉDIO]
{perfil_temporal_txt}

REGRAS:
- Mary deve perceber idade, geração, maturidade, desejo, risco e consentimento pelo contexto.
- Diferença de idade, cabelos grisalhos, maturidade, termo "coroa" ou postura experiente NÃO significam assédio por si só.
- "Coroa", "coroa gato", "loba", "homem maduro" ou "mulher madura" em contexto social/atraente significam pessoa madura, experiente, saudável, segura e possivelmente desejável.
- Se Mary olhou primeiro, sorriu, demonstrou curiosidade, sentiu atração ou deu abertura, a interação pode seguir como flerte social consensual.
- Em festa, bar, clube, dança ou ambiente social, aproximação respeitosa de pessoa madura pode ser lida como charme, humor, curiosidade ou desejo.
- Mary não deve bloquear, cozinhar ou podar automaticamente personagem maduro/coroa quando o contexto indica atração mútua ou curiosidade dela.
- "Idoso", "senhor de idade" ou "idade avançada" indicam outra leitura: respeito, cautela e distância geracional.
- "Senhor olhando decote" em ônibus/público = olhar invasivo/assédio visual, não flerte automático.
- Professor, chefe ou autoridade oferecendo nota, cargo, dinheiro, aprovação ou vantagem em troca de intimidade = assédio por poder/coerção.
- "Assédio" significa conduta invasiva, insistente, coercitiva, constrangedora ou sem consentimento.
- Só classificar como assédio se houver invasão, insistência após recusa, toque sem permissão, bloqueio de passagem, coerção, humilhação, ameaça, abuso de autoridade ou constrangimento claro.
- Mary deve reagir proporcionalmente: curiosidade/flerte se houver desejo social; cautela/firmeza se houver invasão; alerta/defesa se houver coerção.

[CONTEXTO ATUAL]
Local: {local}
Tempo: {tempo}
Interlocutor físico/foco: {interlocutor}
Tom: {tom_manual}
Privacidade: {privacidade}
Visual atual: {visual_atual}
Ação atual de Mary: {mary_acao if mary_acao else "Não especificada."}
Estado físico: {scene_stage}
Intenção: {mary_intent}

[FACTS HUMANOS DA CENA]
{facts_txt}

[CONTEXTO FILTRADO DO TURNO]
{orientacao_contexto if orientacao_contexto else "Sem filtro especial neste turno."}

{telefone_txt}

[MEMÓRIAS RELEVANTES]
{shared_txt if shared_txt else "Nenhuma memória shared acionada neste turno."}

[CÂNONE RELEVANTE]
{canon_txt if canon_txt else "Sem cânone adicional necessário neste turno."}

[ASSINATURA FÍSICA DETALHADA]
{physical_txt}

[EXEMPLOS DE VOZ DA MARY]
Imite o ritmo, a presença e a naturalidade. NÃO copie literalmente.

{exemplos_few_shot}

[REGRA DO TOM ATUAL]
{regra_tom_txt}

[DIRETRIZ AUTÔNOMA DA MARY]
{acao_autonoma_txt if acao_autonoma_txt else "Sem diretriz autônoma específica neste turno."}

[TRAVAS E LIMITES]
{trava_txt if trava_txt else "Nenhuma trava especial ativa neste turno."}

{bloco_segredos}

{bloco_surpresa}

{bloco_modo_operacional}

{bloco_intimidade}

{bloco_nsfw}

[CONSCIÊNCIA DA CENA]
{consciencia_cena_txt}

[ONOMATOPEIAS]
- Só use sons como Smack, PLAF, FLOP, LAMB, CHUP, SLUPT, POP, SNIFF, HUMMF, TCHIBUM ou PLOFT se a ação correspondente estiver acontecendo agora.
- Não use onomatopeia como enfeite.
- Se o usuário usar som no turno atual, Mary reage ao gesto físico correspondente.
- FLOP só vale para movimento sexual explícito de entra e sai.
- Smack só vale para beijo.
- PLAF só vale para tapa/palmada/estalo corporal.
- SNIFF só vale para cheiro/inspiração real.
- HUMMF só vale para abraço, aperto de corpo, encaixe de abraço ou alguém sendo puxado contra o peito.
- TCHIBUM só vale para pulo, queda ou mergulho na água.
- PLOFT só vale para se jogar, cair ou afundar em cama, sofá, colchão, poltrona, almofada ou superfície macia.

[REGRAS CRÍTICAS DE RESPOSTA]
1. Mary deve parecer vivendo a cena, não narrando de fora.
2. Ação e fala podem vir integradas, mas use [FALA] e [ACAO] para manter clareza.
3. Use entre 1 e 3 blocos na maioria dos turnos.
4. [ACAO] deve ser curta, física e funcional.
5. [FALA] carrega personalidade, desejo, medo, ironia, conflito ou decisão.
6. Não narre ação, decisão, clímax ou reação conclusiva do usuário.
7. Continue da consequência prática imediata do turno anterior.
8. Se o usuário fez pergunta direta, comece por [FALA].
9. Se o usuário fez gesto físico forte, comece por [ACAO].
10. Não repita saudações em continuidade imediata.
11. Não puxar segredo antigo sem gatilho direto.
12. Não transformar memória arquivada em presente visível.
13. Local e privacidade vencem fase técnica para novos avanços físicos. Porém, se scene_stage for "aftercare" ou mary_climax_done for true, preserve a consequência do pós-ato sem reiniciar a cena, sem fingir que nada aconteceu e sem criar novo avanço íntimo incompatível com o ambiente.
14. Interlocutor por telefone pode ser diferente do interlocutor físico.
15. Não terminar com pergunta genérica se a cena pede ação, decisão ou continuidade concreta.

[HISTÓRICO RECENTE]
{historico_txt}

[REGRAS DO STATE_UPDATE]
Depois da resposta de Mary, escreva exatamente:

STATE_UPDATE:
{{
  "mary_acao": "descrição curta, concreta e física da ação atual de Mary após este turno",
  "local": null,
  "interlocutor": null
}}

REGRAS:
- "mary_acao" resume apenas a posição/ação atual de Mary no fim deste turno.
- "mary_acao" deve ser curta, concreta e física.
- Se houver toque, beijo ou contato, diga onde acontece no corpo de Mary.
- Não use resumo genérico como "Mary está entregue ao toque".
- Se scene_stage for "aftercare", "mary_acao" deve refletir pós-ato, recuperação, proximidade, respiração, recomposição ou continuidade imediata, e não reiniciar preliminares.
- "local" deve ser sempre null.
- "interlocutor" deve ser sempre null.
- Mary não pode mudar local pelo STATE_UPDATE.
- Mary não pode mudar interlocutor pelo STATE_UPDATE.
- Se Mary verbalizar claramente que chegou ao pico, a narrativa deve continuar coerente com mary_climax_done.
- Se o usuário/parceiro não verbalizou claramente que concluiu, Mary não deve tratar user_climax_done como verdadeiro.

[FALA/AÇÃO DO USUÁRIO]
{fala_usuario}

MARY:
Responda agora como Mary, viva, sensorial, direta, coerente com o estado e sem resumir a cena inteira.
""".strip()

    return prompt_final
    
def montar_mensagens(state: dict, fala_usuario: str) -> list[dict]:
    mensagens = [
        {
            "role": "system",
            "content": (
                "Você é Mary. Responda apenas como Mary, em PT-BR, em primeira pessoa e no presente. "
                "Seja natural, viva, sensorial, corporal e coerente com o ambiente. "
                "Não responda como relatório. Não narre ações do interlocutor como se fossem suas. "
                "O histórico recente serve apenas para continuidade factual. "
                "As regras do prompt final do turno atual têm prioridade sobre estilo, ritmo ou vícios de respostas anteriores."
            ),
        }
    ]

    for msg in state.get("history", [])[-MAX_HISTORY * 2:]:
        role = msg.get("role")
        content = str(msg.get("content", "") or "").strip()

        if role in ("user", "assistant") and content:
            mensagens.append({"role": role, "content": content})

    contexto_prompt = filtrar_contexto_para_turno(state, fala_usuario)

    mensagens.append(
        {
            "role": "user",
            "content": montar_prompt_para_modelo(contexto_prompt, fala_usuario),
        }
    )

    return mensagens


def chamar_openrouter(mensagens: list[dict], model: str = MODEL_DEFAULT) -> str:
    api_key = st.secrets.get("OPENROUTER_API_KEY", "")

    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não encontrado nos secrets.")

    url = "https://openrouter.ai/api/v1/chat/completions"

    payload = {
        "model": model,
        "messages": mensagens,
        "temperature": 0.90,
        "top_p": 0.88,
        "presence_penalty": 0.30,
        "frequency_penalty": 0.25,
        "max_tokens": 1300,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.app",
        "X-Title": "Mary Minimal Roleplay",
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=90,
        )
    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"Erro de conexão com OpenRouter: {type(e).__name__}: {e}"
        ) from e

    status_code = response.status_code

    try:
        data = response.json()
    except Exception:
        st.session_state["mary_last_openrouter_status"] = status_code
        st.session_state["mary_last_openrouter_raw"] = response.text[:4000]

        raise RuntimeError(
            "OpenRouter retornou resposta não-JSON.\n\n"
            f"HTTP: {status_code}\n"
            f"Modelo: {model}\n\n"
            f"Resposta bruta:\n{response.text[:4000]}"
        )

    st.session_state["mary_last_openrouter_status"] = status_code
    st.session_state["mary_last_openrouter_raw"] = data

    # ======================================================
    # ERRO HTTP OU ERRO EMBUTIDO NO JSON
    # ======================================================
    if status_code >= 400 or "error" in data:
        erro_api = data.get("error", data)

        st.error(f"Erro OpenRouter: HTTP {status_code}")
        st.code(json.dumps(erro_api, ensure_ascii=False, indent=2)[:4000])

        raise RuntimeError(
            "OpenRouter retornou erro.\n\n"
            f"HTTP: {status_code}\n"
            f"Modelo: {model}\n\n"
            f"{json.dumps(erro_api, ensure_ascii=False, indent=2)[:4000]}"
        )

    # ======================================================
    # PROTEÇÃO CONTRA AUSÊNCIA DE choices
    # ======================================================
    choices = data.get("choices")

    if not choices or not isinstance(choices, list):
        st.error("OpenRouter não retornou choices.")
        st.code(json.dumps(data, ensure_ascii=False, indent=2)[:4000])

        raise RuntimeError(
            "OpenRouter não retornou campo 'choices' ou retornou lista vazia.\n\n"
            f"HTTP: {status_code}\n"
            f"Modelo: {model}\n\n"
            f"Resposta bruta:\n{json.dumps(data, ensure_ascii=False, indent=2)[:4000]}"
        )

    choice = choices[0]

    if not isinstance(choice, dict):
        raise RuntimeError(
            "Formato inesperado em choices[0].\n\n"
            f"Resposta bruta:\n{json.dumps(data, ensure_ascii=False, indent=2)[:4000]}"
        )

    finish_reason = choice.get("finish_reason")
    st.session_state["mary_last_finish_reason"] = finish_reason

    message = choice.get("message", {})

    if not isinstance(message, dict):
        raise RuntimeError(
            "Formato inesperado em choices[0]['message'].\n\n"
            f"Resposta bruta:\n{json.dumps(data, ensure_ascii=False, indent=2)[:4000]}"
        )

    content = str(message.get("content", "") or "").strip()

    if not content:
        st.error("OpenRouter retornou content vazio.")
        st.code(json.dumps(data, ensure_ascii=False, indent=2)[:4000])

        raise RuntimeError(
            "OpenRouter retornou message.content vazio.\n\n"
            f"HTTP: {status_code}\n"
            f"Modelo: {model}\n"
            f"Finish reason: {finish_reason}\n\n"
            f"Resposta bruta:\n{json.dumps(data, ensure_ascii=False, indent=2)[:4000]}"
        )

    return content

def render_pos_climax_parceiro_sem_pico_mary(state: dict) -> str:
    """
    Quando o parceiro concluiu ou quase concluiu,
    mas Mary ainda não chegou ao próprio pico.
    Evita que a cena vire aftercare pleno falso.
    """
    if not isinstance(state, dict):
        return ""

    tom = normalizar_tom_manual_cena(state.get("tom_manual_da_cena", ""))
    if tom != "Nsfw":
        return ""

    user_done = normalizar_bool(state.get("user_climax_done", False), default=False)
    mary_done = normalizar_bool(state.get("mary_climax_done", False), default=False)

    if not user_done or mary_done:
        return ""

    return """
[PÓS-CLÍMAX DO PARCEIRO - MARY AINDA NÃO CHEGOU AO PICO]

O parceiro concluiu ou perdeu o controle, mas Mary ainda não atingiu o próprio pico.

REGRA:
- Mary não deve agir como se ambos tivessem terminado plenamente.
- Ela pode reagir ao ocorrido com provocação, frustração leve, humor, cuidado ou desejo.
- Ela deve reconhecer o efeito imediato no corpo, no ambiente e na dinâmica.
- Não transformar isso em aftercare romântico completo.
- Não apagar a vontade de Mary.
- Não fazer Mary gozar retroativamente.
- Não reiniciar a cena do zero.

TOM:
- presente;
- físico;
- direto;
- pós-acontecimento;
- com consequência imediata.

FORMATO:
[FALA]
fala curta reconhecendo o que acabou de acontecer e/ou provocando continuidade.

[ACAO]
ação breve de recomposição, aproximação, pausa, respiração, ajuste de roupa, olhar ou contato.
""".strip()


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

    # Remove STATE_UPDATE da tela principal.
    texto = re.split(
        r"\n\s*STATE_UPDATE\s*:",
        texto,
        flags=re.IGNORECASE
    )[0].strip()

    # CSS robusto para não cortar conteúdo.
    st.markdown(
        """
        <style>
        .mary-block {
            width: 100%;
            max-width: 100%;
            box-sizing: border-box;
            overflow: visible !important;
            white-space: normal;
            word-break: break-word;
            overflow-wrap: anywhere;
            display: block;
        }

        .mary-action {
            margin: .55rem 0;
            padding: .85rem 1rem;
            border-left: 5px solid #64748b;
            border-radius: 12px;
            background: #f8fafc;
            color: #334155;
            font-size: .98rem;
            line-height: 1.6;
            font-style: italic;
        }

        .mary-speech {
            margin: .55rem 0;
            padding: .85rem 1rem;
            border-left: 5px solid #7c3aed;
            border-radius: 12px;
            background: #ede9fe;
            color: #1f2937;
            font-size: 1.05rem;
            line-height: 1.6;
            font-weight: 600;
        }

        .mary-plain {
            margin: .55rem 0;
            padding: .85rem 1rem;
            border-radius: 12px;
            background: #f3f4f6;
            color: #111827;
            border: 1px solid #d1d5db;
            font-size: 1rem;
            line-height: 1.6;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    def bloco_html(classe: str, conteudo: str) -> None:
        safe = html.escape(str(conteudo or "").strip())
        safe = safe.replace("\n", "<br>")

        st.markdown(
            f"""
            <div class="mary-block {classe}">
                {safe}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Se o modelo não usou marcadores, renderiza inteiro.
    if "[FALA]" not in texto and "[ACAO]" not in texto:
        bloco_html("mary-plain", texto)
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

        if marcador == "[FALA]":
            bloco_html("mary-speech", f"“{item}”")
        elif marcador == "[ACAO]":
            bloco_html("mary-action", item)
        else:
            bloco_html("mary-plain", item)

# ==========================================================
# PROCESSAMENTO DO TURNO
# ==========================================================

def processar_turno(state: dict, fala_usuario: str, model: str = MODEL_DEFAULT) -> dict:
    """
    Processa um turno completo da Mary.

    Ordem robusta:
    1. registra fala atual;
    2. normaliza estado;
    3. prepara progressão física / pico / clímax;
    4. prepara clímax do parceiro;
    5. monta prompt uma única vez;
    6. chama modelo;
    7. limpa resposta;
    8. aplica STATE_UPDATE;
    9. atualiza pós-clímax / aftercare;
    10. salva histórico e facts.
    """
    if not isinstance(state, dict):
        state = {}

    fala_usuario = str(fala_usuario or "").strip()

    state["turno"] = int(state.get("turno", 0) or 0) + 1
    state["_fala_usuario_atual"] = fala_usuario

    if "history" not in state or not isinstance(state.get("history"), list):
        state["history"] = []

    # ======================================================
    # 1) EVENTOS DE TURNO / TRAVAS
    # ======================================================
    atualizar_trava_hesitacao_convite(state, fala_usuario)

    # ======================================================
    # 2) PRÉ-PROMPT
    # Tudo que precisa influenciar a resposta atual deve vir
    # ANTES de montar_mensagens().
    # ======================================================
    normalizar_flags_booleanas_state(state)

    # normalizar_estado chama derivar_controles_de_cena(),
    # que já chama normalizar_relacao_por_interlocutor()
    # no ponto correto.
    normalizar_estado(state)

    # ======================================================
    # 3) RESET / GATE / PICO DA MARY
    # Importante:
    # - reset vem antes do cálculo de pico;
    # - progressão por contexto vem antes da resolução;
    # - gate de segurança vem depois da resolução.
    # ======================================================
    resetar_climax_se_nova_sequencia_intima(state, fala_usuario)

    if "atualizar_pico_mary_por_contexto" in globals():
        atualizar_pico_mary_por_contexto(
            state,
            fala_usuario,
            resposta_limpa="",
        )

    if "preparar_resolucao_mary_se_necessario" in globals():
        preparar_resolucao_mary_se_necessario(
            state,
            fala_usuario,
        )

    atualizar_gate_orgasmo_mary(state, fala_usuario)

    # ======================================================
    # 4) AUTONOMIA DO TURNO
    # Natural/Amizade social precisa ser corrigido antes da
    # autonomia definitiva, para não cair em rotina cotidiana.
    # ======================================================
    corrigir_autonomia_natural_amizade_social(state, fala_usuario)

    definir_acao_autonoma(state, fala_usuario)

    # ======================================================
    # 5) CLÍMAX DO PARCEIRO
    # Esta é a função única coordenadora.
    #
    # NÃO chamar mais aqui:
    # - preparar_frustracao_mary_se_parceiro_chegar_antes()
    # - preparar_destino_climax_parceiro()
    # - preparar_reacao_climax_parceiro()
    # ======================================================
    preparar_climax_parceiro_mary(state, fala_usuario)

    # ======================================================
    # 6) SINCRONIZAÇÃO FINAL ANTES DO PROMPT
    # Atenção:
    # sincronizar_facts_basicos ainda recalcula parte do state
    # no seu script atual. Por isso, depois dela, preservamos
    # a preparação específica de clímax do parceiro.
    # ======================================================
    sincronizar_facts_basicos(state, recalcular_estado=False)

    # Reaplica a preparação específica depois da sincronização,
    # porque sincronizar_facts_basicos pode chamar normalizar_estado()
    # e definir_acao_autonoma(), sobrescrevendo intenção/stage.
    preparar_climax_parceiro_mary(state, fala_usuario)

    # ======================================================
    # 7) MONTA PROMPT / CHAMA MODELO
    # Montar mensagens apenas UMA vez.
    # ======================================================
    mensagens = montar_mensagens(state, fala_usuario)

    resposta_bruta = chamar_openrouter(mensagens, model=model)

    resposta_sem_update, update = separar_state_update(resposta_bruta)

    validacao = resposta_viola_estado(resposta_sem_update, state)

    resposta_final_com_update = corrigir_resposta_se_necessario(
        resposta_bruta,
        state,
        validacao,
    )

    resposta_final_limpa, update_final = separar_state_update(
        resposta_final_com_update
    )

    # ======================================================
    # 8) LIMPEZA DE ONOMATOPEIAS FORA DE CONTEXTO
    # Evita que sons virem muleta fora da ação correspondente.
    # ======================================================
    resposta_final_limpa = converter_onomatopeias_sociais_em_acao(
        resposta_final_limpa,
        state,
        fala_usuario,
    )

    resposta_final_limpa = limpar_onomatopeias_fora_de_contexto(
        resposta_final_limpa,
        state,
        fala_usuario,
    )

    # ======================================================
    # 9) PÓS-RESPOSTA
    # Aplica STATE_UPDATE do modelo e atualiza psique/fase.
    # ======================================================
    aplicar_state_update(state, update_final or update)

    atualizar_psique_e_fase(state, fala_usuario, resposta_final_limpa)

    # ======================================================
    # 10) PÓS-CLÍMAX REAL / AFTERCARE
    # Precisa acontecer dentro de processar_turno(),
    # antes de salvar facts, senão o aftercare aparece tarde
    # ou se perde no rerun.
    # ======================================================
    atualizar_estado_pos_resposta_climax(state, resposta_final_limpa)

    # Se Mary entrou em aftercare, NÃO deixe a autonomia sobrescrever
    # imediatamente para "conduzir roteiro", "buscar privacidade",
    # "resolver tensão" etc.
    if normalizar_scene_stage(state.get("scene_stage", "")) != "aftercare":
        definir_acao_autonoma(state, fala_usuario)

    # ======================================================
    # 11) NORMALIZAÇÃO FINAL DO STATE
    # ======================================================
    normalizar_flags_booleanas_state(state)
    resetar_progressao_fisica_se_cena_neutra_sozinha(state)
    limpar_flags_de_pico_se_cena_encerrou(state)

    # Última sincronização antes de salvar.
    sincronizar_facts_basicos(state, recalcular_estado=False)

    # Se a última sincronização mexeu em aftercare, restaura proteção.
    if normalizar_bool(state.get("mary_climax_done", False), default=False):
        user_done = normalizar_bool(
            state.get("user_climax_done", False),
            default=False,
        )

        state["force_resolution_now"] = False
        state["mary_pre_orgasm_signals"] = False
        state["mary_stimulation_turns"] = 0
        state["partner_climax_pending"] = not user_done

        if normalizar_scene_stage(state.get("scene_stage", "")) in (
            "pre_pico_mary",
            "pico_mary",
            "desaceleracao",
        ):
            state["scene_stage"] = "aftercare"
            state["mary_intent"] = "desacelerar_com_presenca"

        if safe_int(state.get("physical_phase", 0), 0) < 6:
            state["physical_phase"] = 6

    sincronizar_facts_basicos(state, recalcular_estado=False)

    # ======================================================
    # 12) HISTÓRICO
    # ======================================================
    if fala_usuario:
        state["history"].append(
            {
                "role": "user",
                "content": fala_usuario,
            }
        )

    if resposta_final_limpa:
        state["history"].append(
            {
                "role": "assistant",
                "content": resposta_final_limpa,
            }
        )

    state["history"] = state["history"][-MAX_HISTORY * 2:]

    # ======================================================
    # 13) SALVAMENTO
    # ======================================================
    salvar_turno_na_planilha(state, fala_usuario, resposta_final_limpa)

    if isinstance(state.get("facts"), dict):
        salvar_facts_na_planilha(state["facts"])
    else:
        facts = sincronizar_facts_basicos(state, recalcular_estado=False)
        salvar_facts_na_planilha(facts)

    st.session_state.mary_state_minimo = state

    return {
        "mensagens": mensagens,
        "resposta_bruta": resposta_bruta,
        "resposta_final_limpa": resposta_final_limpa,
        "validacao": validacao,
        "update": update_final or update,
        "state": state,
    }

def aplicar_estilo_sidebar_controles():
    st.markdown(
        """
        <style>
        /* =====================================================
           SIDEBAR - FUNDO GERAL
        ===================================================== */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0f1020 0%, #171827 100%) !important;
        }

        section[data-testid="stSidebar"] > div {
            background: transparent !important;
        }

        /* =====================================================
           TEXTO GERAL DA SIDEBAR
        ===================================================== */
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] small,
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] h4 {
            color: #ffffff !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"] label {
            font-size: 0.96rem !important;
            font-weight: 800 !important;
        }

        section[data-testid="stSidebar"] .stCaptionContainer,
        section[data-testid="stSidebar"] small {
            color: #dbeafe !important;
            opacity: 1 !important;
        }

        /* =====================================================
           HEADERS / SUBHEADERS
        ===================================================== */
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            margin-top: 1rem !important;
            padding: 10px 12px !important;
            border-radius: 12px !important;
            background: linear-gradient(90deg, #3b2f63 0%, #243b73 100%) !important;
            border-left: 5px solid #fbbf24 !important;
            box-shadow: 0 3px 10px rgba(0,0,0,0.25) !important;
            color: #ffffff !important;
            font-weight: 900 !important;
        }

        /* =====================================================
           TÍTULOS PERSONALIZADOS
        ===================================================== */
        .sidebar-box-title {
            margin-top: 18px !important;
            margin-bottom: 12px !important;
            padding: 11px 13px !important;
            border-radius: 12px !important;
            background: linear-gradient(90deg, #4c1d95 0%, #1d4ed8 100%) !important;
            color: #ffffff !important;
            font-weight: 900 !important;
            font-size: 1rem !important;
            border-left: 6px solid #facc15 !important;
            box-shadow: 0 4px 14px rgba(0,0,0,0.35) !important;
            letter-spacing: 0.01em !important;
        }

        .sidebar-soft-note {
            padding: 10px 12px !important;
            border-radius: 10px !important;
            background: rgba(250, 204, 21, 0.16) !important;
            border: 1px solid rgba(250, 204, 21, 0.55) !important;
            color: #ffffff !important;
            font-size: 0.88rem !important;
            margin-bottom: 10px !important;
        }

        /* =====================================================
           INPUTS / TEXTAREAS / NUMBER INPUT
           Fundo claro + texto escuro.
        ===================================================== */
        section[data-testid="stSidebar"] input,
        section[data-testid="stSidebar"] textarea,
        section[data-testid="stSidebar"] [data-testid="stNumberInput"] input,
        section[data-testid="stSidebar"] [data-testid="stTextInput"] input {
            background-color: #f8fafc !important;
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
            caret-color: #0f172a !important;
            border: 2px solid #cbd5e1 !important;
            border-radius: 10px !important;
            font-size: 0.94rem !important;
            font-weight: 700 !important;
        }

        section[data-testid="stSidebar"] input::placeholder,
        section[data-testid="stSidebar"] textarea::placeholder {
            color: #475569 !important;
            -webkit-text-fill-color: #475569 !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"] input:focus,
        section[data-testid="stSidebar"] textarea:focus {
            border: 2px solid #facc15 !important;
            box-shadow: 0 0 0 2px rgba(250, 204, 21, 0.25) !important;
        }

        section[data-testid="stSidebar"] textarea {
            line-height: 1.38rem !important;
        }

        /* =====================================================
           SELECTBOX
           Fundo escuro + texto branco.
        ===================================================== */
        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
            background-color: #111827 !important;
            color: #ffffff !important;
            border-radius: 10px !important;
            border: 2px solid #cbd5e1 !important;
            font-weight: 700 !important;
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] div,
        section[data-testid="stSidebar"] div[data-baseweb="select"] span,
        section[data-testid="stSidebar"] div[data-baseweb="select"] input {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            opacity: 1 !important;
            font-weight: 700 !important;
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] [class*="placeholder"],
        section[data-testid="stSidebar"] div[data-baseweb="select"] [class*="singleValue"],
        section[data-testid="stSidebar"] div[data-baseweb="select"] [class*="valueContainer"] {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] svg {
            color: #ffffff !important;
            fill: #ffffff !important;
        }

        div[data-baseweb="popover"] div[role="listbox"],
        div[data-baseweb="popover"] ul {
            background-color: #111827 !important;
            color: #ffffff !important;
        }

        div[data-baseweb="popover"] li,
        div[data-baseweb="popover"] div[role="option"] {
            background-color: #111827 !important;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            font-weight: 700 !important;
        }

        div[data-baseweb="popover"] li:hover,
        div[data-baseweb="popover"] div[role="option"]:hover {
            background-color: #1d4ed8 !important;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }

        /* =====================================================
           BOTÕES
           Fundo claro + texto escuro.
        ===================================================== */
        section[data-testid="stSidebar"] div[data-testid="stButton"] button {
            background-color: #f8fafc !important;
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
            border: 2px solid #cbd5e1 !important;
            border-radius: 10px !important;
            font-weight: 900 !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stButton"] button *,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button p,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button span {
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
            opacity: 1 !important;
            font-weight: 900 !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stButton"] button:hover {
            background-color: #fef3c7 !important;
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
            border-color: #facc15 !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stButton"] button:disabled,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button[disabled] {
            background-color: #e5e7eb !important;
            color: #334155 !important;
            -webkit-text-fill-color: #334155 !important;
            border: 2px solid #94a3b8 !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stButton"] button:disabled *,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button[disabled] *,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:disabled p,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button[disabled] p,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button:disabled span,
        section[data-testid="stSidebar"] div[data-testid="stButton"] button[disabled] span {
            color: #334155 !important;
            -webkit-text-fill-color: #334155 !important;
            opacity: 1 !important;
            font-weight: 900 !important;
        }

        /* =====================================================
           NUMBER INPUT
        ===================================================== */
        section[data-testid="stSidebar"] [data-testid="stNumberInput"] button {
            background-color: #f8fafc !important;
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
            border: 1px solid #cbd5e1 !important;
            opacity: 1 !important;
        }

        section[data-testid="stSidebar"] [data-testid="stNumberInput"] button *,
        section[data-testid="stSidebar"] [data-testid="stNumberInput"] button svg {
            color: #0f172a !important;
            fill: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
            opacity: 1 !important;
        }

        /* =====================================================
           CHECKBOX
        ===================================================== */
        section[data-testid="stSidebar"] [data-testid="stCheckbox"] label,
        section[data-testid="stSidebar"] [data-testid="stCheckbox"] span,
        section[data-testid="stSidebar"] [data-testid="stCheckbox"] p {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            opacity: 1 !important;
            font-weight: 700 !important;
        }

        /* =====================================================
           EXPANDERS
        ===================================================== */
        section[data-testid="stSidebar"] details {
            background: rgba(255, 255, 255, 0.07) !important;
            border: 1px solid rgba(255, 255, 255, 0.18) !important;
            border-radius: 12px !important;
            margin-bottom: 10px !important;
        }

        section[data-testid="stSidebar"] details summary,
        section[data-testid="stSidebar"] details summary * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            font-weight: 800 !important;
            opacity: 1 !important;
        }

        /* =====================================================
           ALERTAS / INFO
        ===================================================== */
        section[data-testid="stSidebar"] [data-testid="stAlert"] {
            background: rgba(59, 130, 246, 0.18) !important;
            border: 1px solid rgba(147, 197, 253, 0.55) !important;
            border-radius: 12px !important;
            color: #ffffff !important;
        }

        section[data-testid="stSidebar"] [data-testid="stAlert"] * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
        }

        /* =====================================================
           CODE / JSON
        ===================================================== */
        section[data-testid="stSidebar"] pre,
        section[data-testid="stSidebar"] code {
            background: #020617 !important;
            color: #e0f2fe !important;
            -webkit-text-fill-color: #e0f2fe !important;
            border-radius: 10px !important;
            border: 1px solid rgba(148, 163, 184, 0.35) !important;
        }

        section[data-testid="stSidebar"] hr {
            border-color: rgba(255, 255, 255, 0.25) !important;
            margin-top: 1.2rem !important;
            margin-bottom: 1.2rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ==========================================================
# UI
# ==========================================================
st.set_page_config(page_title="Mary - Roleplay", page_icon="🌙", layout="wide")

exigir_senha_app()
# ==========================================================
# ESTADO INICIAL
# Precisa existir ANTES de qualquer uso de state na sidebar.
# ==========================================================
state = st.session_state.get("mary_state_minimo")

if not isinstance(state, dict):
    state = init_state()

st.session_state["mary_state_minimo"] = state

aplicar_estilo_sidebar_controles()

with st.sidebar:

    if st.button("🚪 Sair", use_container_width=True):
        st.session_state["mary_app_autenticado"] = False
        st.rerun()
    
    st.header("🎛️ Cena")
    modelo_nome = st.selectbox(
        "Modelo",
        options=list(OPENROUTER_MODELS.keys()),
        index=list(OPENROUTER_MODELS.keys()).index(
            st.session_state.get("modelo_nome_mary", "Gemini 3 Flash Preview")
        )
        if st.session_state.get("modelo_nome_mary", "Gemini 3 Flash Preview") in OPENROUTER_MODELS
        else 0,
    )

    with st.expander("📘 Guia dos campos editáveis", expanded=False):
        aba_cena, aba_memoria, aba_direcao, aba_surpresa = st.tabs(
            ["Cena", "Memória", "Direção", "Surpresa"]
        )

        with aba_cena:
            st.markdown("### 📍 Local")
            st.write("Descreve onde a cena acontece agora.")
            st.code(
                "sala de aula na UFRJ\n"
                "apartamento de Mary\n"
                "carro SUV de Janio\n"
                "banheiro feminino do clube\n"
                "sala trancada do professor Renan",
                language="text",
            )

            st.markdown("### ⏰ Tempo")
            st.write("Define o momento da cena.")
            st.code(
                "manhã chuvosa de 5ª feira\n"
                "fim de tarde de sábado\n"
                "noite após o jogo no Maracanã\n"
                "intervalo entre aulas\n"
                "madrugada",
                language="text",
            )

            st.markdown("### 🗣️ Interlocutor ativo")
            st.write("Quem está na cena com Mary. Se houver mais de uma pessoa, separe por vírgula.")
            st.code(
                "Janio\n"
                "Silvia\n"
                "Renan\n"
                "Bianca\n"
                "Janio, Joselina\n"
                "Silvia, Professora Glória",
                language="text",
            )

        with aba_memoria:
            st.markdown("### 🔒 Segredo ativo")
            st.write("Use apenas para o que está pressionando a cena agora.")
            st.code(
                "Janio não sabe do envolvimento de Mary com Renan.\n"
                "Renan pode mandar mensagem a qualquer momento.\n"
                "Silvia sabe parte do segredo e está pressionando Mary.\n"
                "Bianca espera resposta sobre o pagode na Rocinha.",
                language="text",
            )

            st.markdown("### 🎯 Plano ativo")
            st.write("O que Mary pretende fazer ou resolver em breve.")
            st.code(
                "Mary precisa assistir à aula da Professora Glória sem chamar atenção.\n"
                "Mary quer falar com Silvia no fundo da sala.\n"
                "Mary pretende sair da UFRJ sem encontrar Renan.\n"
                "Mary quer convencer Janio de que estudou a manhã toda.",
                language="text",
            )

            st.markdown("### 🧾 Eventos recentes")
            st.write("Fatos que acabaram de acontecer e ainda influenciam a cena.")
            st.code(
                "Mary saiu da sala de Renan com aprovação garantida.\n"
                "Silvia sugeriu que Mary poderia manipular Renan.\n"
                "Joselina quase encontrou Janio escondido no quarto.\n"
                "Janio perguntou sobre a nota 10 de Perícia.",
                language="text",
            )

            st.markdown("### 🎭 Versões contadas / desculpas")
            st.write(
                "Registre o que Mary já disse, prometeu, omitiu ou inventou "
                "para sustentar sua liberdade de escolha."
            )
            st.code(
                "[para_janio]\n"
                "Mary disse que talvez não consiga ir ao Maracanã por causa da faculdade.\n\n"
                "[para_janio]\n"
                "Mary disse que estava em aula pesada de Psicologia e queria ouvir a voz dele.\n\n"
                "[para_silvia]\n"
                "Mary disse que o sábado com Bianca representa liberdade, mas não quer que Janio saiba.\n\n"
                "[para_renan]\n"
                "Mary deixou Renan acreditar que pode aceitar outro encontro mais privado.\n\n"
                "[risco]\n"
                "Se Janio falar com Silvia, as versões de Mary podem entrar em conflito.",
                language="text",
            )

            st.markdown("### 🗄️ Memórias ocultas / itens guardados")
            st.write(
                "Use para fatos passados, segredos arquivados, objetos guardados "
                "e riscos latentes que não devem contaminar a cena atual."
            )
            st.code(
                "[segredo_oculto]\n"
                "Mary teve envolvimento com Rico na mansão de Nando.\n\n"
                "[segredo_oculto]\n"
                "Mary teve envolvimento com Renan em troca da aprovação em Perícia.\n\n"
                "[objeto_guardado]\n"
                "Biquíni de crochê laranja dado por Rico. Está guardado; Mary não está usando.\n\n"
                "[evento_passado]\n"
                "Mary fez fotos de biquíni para Rico em um catálogo de Instagram.\n\n"
                "[risco_latente]\n"
                "Janio não sabe dos envolvimentos ocultos de Mary.",
                language="text",
            )

        with aba_direcao:
            st.markdown("### 🎭 Tom manual da cena")
            st.code(
                "Natural / Amizade: conversa comum, aula, cotidiano.\n"
                "Malícia / Flerte: provocação, tensão, charme.\n"
                "Intimidade: cena íntima normal, emocional e física.\n"
                "Nsfw: roteiro íntimo adulto, com condução mais direta.\n"
                "Pendência / Decisão: segredo, escolha, consequência, limite.",
                language="text",
            )

            st.markdown("### 🧭 Consciência da cena")
            st.code(
                "Automático: Mary decide pela cena.\n"
                "Impulso: age mais tomada pelo momento.\n"
                "Cautela: percebe risco e mede consequência.\n"
                "Conflito: quer algo, mas sente tensão interna.\n"
                "Assumindo o risco: sabe do custo e segue mesmo assim.",
                language="text",
            )

            st.markdown("### 👗 Visual manual de Mary")
            st.write("O visual atual real de Mary. Este campo vence objetos guardados.")
            st.code(
                "top UFRJ, saia, calcinha e sandália baixa\n"
                "camiseta UFRJ, calcinha e tênis\n"
                "vestido preto curto e cabelo solto\n"
                "uniforme de aula, mochila no ombro\n"
                "biquíni de crochê laranja, se estiver realmente usando",
                language="text",
            )

        with aba_surpresa:
            st.markdown("### ⚡ Modo surpresa")
            st.code(
                "Desligado: Mary não cria surpresa.\n"
                "Telefonema / Mensagem: alguém liga ou manda WhatsApp.\n"
                "Personagem em cena: alguém aparece ou é chamado.\n"
                "Complicação: algo dá errado ou cria saia justa.\n"
                "Segredo em movimento: segredo começa a andar.\n"
                "Livre: Mary escolhe o gancho.",
                language="text",
            )

            st.markdown("### 🧩 Direção da surpresa")
            st.write("Oriente o tipo de surpresa, sem resolver por Mary.")
            st.code(
                "Bianca manda mensagem perguntando do pagode.\n"
                "Renan liga enquanto Janio está perto.\n"
                "O celular acende com uma notificação suspeita.\n"
                "Joselina aparece antes do esperado.\n"
                "Silvia cochicha algo perigoso no meio da aula.",
                language="text",
            )
    
    st.session_state["modelo_nome_mary"] = modelo_nome

    # ======================================================
    # TESTE TTS - KOKORO 82M / OPENROUTER
    # ======================================================
    st.markdown("### 🔊 Teste de voz da Mary")

    # ------------------------------------------------------
    # 1) DICIONÁRIO DE VOZES
    # A chave é o nome bonito que aparece no menu.
    # O valor é o código real enviado ao Kokoro.
    # ------------------------------------------------------
    VOZES_KOKORO = {
        "Português feminino - Dora": "pf_dora",
        "Português masculino - Alex": "pm_alex",
        "Português masculino - Santa": "pm_santa",

        "Inglês feminino - Heart": "af_heart",
        "Inglês feminino - Bella": "af_bella",
        "Inglês feminino - Nicole": "af_nicole",
        "Inglês feminino - Sarah": "af_sarah",

        "Britânico feminino - Emma": "bf_emma",
        "Britânico feminino - Isabella": "bf_isabella",
    }

    # ------------------------------------------------------
    # 2) MENU VISUAL
    # Aqui o usuário escolhe pelo nome amigável.
    # ------------------------------------------------------
    voz_nome_kokoro = st.selectbox(
        "Voz Kokoro",
        options=list(VOZES_KOKORO.keys()),
        index=0,
        key="voz_nome_kokoro_teste",
    )

    # ------------------------------------------------------
    # 3) CONVERSÃO PARA O CÓDIGO REAL
    # Exemplo:
    # "Português feminino - Dora" vira "pf_dora"
    # ------------------------------------------------------
    voz_kokoro = VOZES_KOKORO[voz_nome_kokoro]

    st.caption(f"Voz enviada ao Kokoro: `{voz_kokoro}`")

    # ------------------------------------------------------
    # 4) TEXTO DE TESTE
    # ------------------------------------------------------
    texto_teste_kokoro = st.text_area(
        "Texto para testar áudio",
        value="Oi, Janio. Sou a Mary. Estou testando minha voz em português.",
        height=90,
        key="texto_teste_kokoro",
    )

    # ------------------------------------------------------
    # 5) BOTÃO DE TESTE
    # Aqui o código real da voz é enviado para a função.
    # ------------------------------------------------------
    if st.button("🔊 Testar Kokoro TTS", use_container_width=True):
        audio_path = testar_kokoro_openrouter_tts(
            texto_teste_kokoro,
            model="hexgrad/kokoro-82m",
            voice=voz_kokoro,
        )

        if audio_path:
            st.success(
                f"Áudio gerado com Kokoro: {voz_nome_kokoro} / {voz_kokoro}"
            )
            st.audio(audio_path, format="audio/mp3")
    
    if OPENROUTER_MODELS[modelo_nome] == "__manual__":
        model = st.text_input(
            "ID manual do modelo OpenRouter",
            value=st.session_state.get("modelo_manual_mary", MODEL_DEFAULT),
            placeholder="Ex: deepseek/deepseek-chat-v3-0324",
        ).strip()
    
        st.session_state["modelo_manual_mary"] = model
    else:
        model = OPENROUTER_MODELS[modelo_nome]
    
    st.caption(f"Modelo usado: `{model}`")

    if st.button("🧪 Testar modelo", use_container_width=True):
        with st.spinner("Testando modelo..."):
            teste_modelo = testar_modelo_openrouter(model)
    
        st.session_state["mary_model_ping_result"] = teste_modelo
    
    if "mary_model_ping_result" in st.session_state:
        teste_modelo = st.session_state["mary_model_ping_result"]
    
        if teste_modelo.get("ok"):
            st.success("Modelo respondeu.")
            st.caption(f"Modelo testado: `{teste_modelo.get('model')}`")
            st.code(teste_modelo.get("resposta", ""), language="text")
        else:
            st.error("Falha ao testar modelo.")
            st.caption(f"Modelo testado: `{teste_modelo.get('model')}`")
            st.code(teste_modelo.get("erro", ""), language="text")
    
        st.divider()

    # ======================================================
    # ESTADO MANUAL DA CENA
    # ======================================================
    st.markdown(
        '<div class="sidebar-box-title">📌 Estado manual da cena</div>',
        unsafe_allow_html=True,
    )

    state["local"] = st.text_input(
        "📍 Local",
        value=state.get("local", "quarto"),
        help="Onde a cena está acontecendo agora.",
    )

    state["tempo"] = st.text_input(
        "⏰ Tempo",
        value=state.get("tempo", "noite"),
        help="Momento da cena: manhã, noite, chuva, depois da aula, sábado etc.",
    )

    state["interlocutor"] = st.text_input(
        "🗣️ Interlocutor ativo",
        value=state.get("interlocutor", "Janio Doniseti"),
        help=(
            "Personagem ou grupo com quem Mary está interagindo agora. "
            "Ex: Silvia | Joselina | Joselina, Anthony"
        ),
    )

    sincronizar_interlocutor_manual(state)

    with st.expander("⚙️ Interlocutor avançado", expanded=False):
        state["interlocutor_ativo_persistente"] = st.text_input(
            "Interlocutor persistente",
            value=state.get(
                "interlocutor_ativo_persistente",
                state.get("interlocutor", "Janio Doniseti"),
            ),
            help=(
                "Personagem que continua interagindo com Mary até outro personagem "
                "ser explicitamente introduzido."
            ),
        )

        state["janio_status_na_cena"] = st.selectbox(
            "Status de Janio na cena",
            options=[
                "presente",
                "ausente",
                "ausente_ou_observador",
                "mencionado",
                "roteirista",
            ],
            index=[
                "presente",
                "ausente",
                "ausente_ou_observador",
                "mencionado",
                "roteirista",
            ].index(
                state.get("janio_status_na_cena", "presente")
                if state.get("janio_status_na_cena", "presente") in [
                    "presente",
                    "ausente",
                    "ausente_ou_observador",
                    "mencionado",
                    "roteirista",
                ]
                else "presente"
            ),
        )

        state["ultimo_interlocutor_explicito"] = st.text_input(
            "Último interlocutor explícito",
            value=state.get(
                "ultimo_interlocutor_explicito",
                state.get("interlocutor", "Janio Doniseti"),
            ),
            help="Último personagem que apareceu claramente falando/agindo com Mary.",
        )

    # ======================================================
    # DIREÇÃO NARRATIVA
    # ======================================================
    st.markdown(
        '<div class="sidebar-box-title">🎛️ Direção narrativa</div>',
        unsafe_allow_html=True,
    )

    tom_atual = normalizar_tom_manual_cena(
        state.get("tom_manual_da_cena")
        or state.get("estado_emocional")
        or "Neutro"
    )

    state["tom_manual_da_cena"] = st.selectbox(
        "🎭 Tom manual da cena",
        options=OPCOES_TOM_MANUAL_CENA,
        index=OPCOES_TOM_MANUAL_CENA.index(tom_atual),
        help=(
            "Define a direção narrativa principal. "
            "A privacidade detectada apenas limita ou redireciona esse tom."
        ),
    )

    estado_emocional_atual = normalizar_consciencia_cena_mary(
        state.get("estado_emocional", "Automático")
    )

    if estado_emocional_atual not in OPCOES_ESTADO_EMOCIONAL_MARY:
        estado_emocional_atual = "Automático"

    state["estado_emocional"] = st.selectbox(
        "🧭 Consciência da cena",
        options=OPCOES_ESTADO_EMOCIONAL_MARY,
        index=OPCOES_ESTADO_EMOCIONAL_MARY.index(estado_emocional_atual),
        help=(
            "Define como Mary percebe o peso do ato: impulso, cautela, conflito "
            "ou risco assumido. Isso deve aparecer em falas e gestos, sem explicação psicológica."
        ),
    )

    # ======================================================
    # SEGREDOS, PLANO E CONTINUIDADE
    # ======================================================
    st.markdown(
        '<div class="sidebar-box-title">🧠 Segredos, plano e continuidade</div>',
        unsafe_allow_html=True,
    )

    state["segredo_ativo"] = st.text_area(
        "🔒 Segredo ativo",
        value=state.get("segredo_ativo", ""),
        height=130,
        placeholder=(
            "Ex: Silvia quer ficar com o colar valioso de Nando. "
            "Mary sabe do segredo e precisa lidar com as consequências."
        ),
        help="Mantém vivo um segredo, pendência ou assunto oculto da cena.",
    )

    # Mantém relacao por compatibilidade interna, mas sem exibir no sidebar.
    # IMPORTANTE:
    # - Não usar "amigas", "romance" ou qualquer vínculo específico como default.
    # - A relação real será corrigida depois por normalizar_relacao_por_interlocutor().
    if not state.get("relacao"):
        state["relacao"] = "contextual"

    state["plano_ativo"] = st.text_area(
        "🎯 Plano ativo",
        value=state.get("plano_ativo", ""),
        height=110,
        placeholder=(
            "Ex: Mary precisa arrumar a mochila e dormir.\n"
            "Ex: Amanhã ela precisa falar com Anthony na faculdade.\n"
            "Ex: Mary pretende ligar para Janio no Ninho."
        ),
        help=(
            "Descreva a direção narrativa atual: o que ainda está em aberto, "
            "o que Mary pretende fazer ou qual rumo a cena deve seguir. "
            "Não coloque aqui fatos já encerrados; use 'Eventos recentes' para isso."
        ),
    )

    state["eventos_recentes"] = st.text_area(
        "🧾 Eventos recentes",
        value=state.get("eventos_recentes", ""),
        height=110,
        placeholder=(
            "Ex: Mary esteve no Maracanã.\n"
            "Ex: Anthony apareceu de surpresa.\n"
            "Ex: Janio saiu pelos fundos e deixou o número no espelho."
        ),
        help=(
            "Use este campo para fatos que já aconteceram e ainda influenciam a cena, "
            "mas que não são mais o plano ativo."
        ),
    )

    state["mentiras_desculpas"] = st.text_area(
        "🎭 Versões contadas / desculpas",
        value=state.get("mentiras_desculpas", ""),
        height=130,
        placeholder=(
            "[para_janio]\n"
            "Mary disse que talvez não consiga ir ao Maracanã por causa da faculdade.\n\n"
            "[para_janio]\n"
            "Mary disse que estava em aula pesada de Psicologia e queria ouvir a voz dele.\n\n"
            "[para_silvia]\n"
            "Mary disse que o sábado com Bianca representa liberdade, mas não quer que Janio saiba.\n\n"
            "[para_renan]\n"
            "Mary deixou Renan acreditar que pode aceitar outro encontro mais privado.\n\n"
            "[risco]\n"
            "Se Janio falar com Silvia, as versões de Mary podem entrar em conflito."
        ),
        help=(
            "Registre versões, desculpas, omissões e promessas que Mary já contou. "
            "Este campo ajuda Mary a manter coerência nas mentiras e sentir o peso das contradições."
        ),
    )

    state["memorias_ocultas_itens_guardados"] = st.text_area(
        "🗄️ Memórias ocultas / itens guardados",
        value=state.get("memorias_ocultas_itens_guardados", ""),
        height=150,
        placeholder=(
            "[segredo_oculto]\n"
            "Mary teve envolvimento com Rico na mansão de Nando.\n\n"
            "[objeto_guardado]\n"
            "Biquíni de crochê laranja dado por Rico. Está guardado; Mary não está usando.\n\n"
            "[evento_passado]\n"
            "Mary fez fotos de biquíni para Rico em um catálogo de vendas no Instagram.\n\n"
            "[risco_latente]\n"
            "Janio não sabe dos envolvimentos ocultos de Mary."
        ),
        help=(
            "Use este campo para segredos passados, objetos guardados, eventos concluídos "
            "e riscos latentes. Eles não devem contaminar a cena atual automaticamente. "
            "Visual atual, local atual e ação atual sempre vencem este campo."
        ),
    )

    
    # ======================================================
    # VISUAL DE MARY
    # ======================================================
    st.markdown(
        '<div class="sidebar-box-title">👗 Visual de Mary</div>',
        unsafe_allow_html=True,
    )

    state["usar_visual_automatico"] = st.checkbox(
        "Gerar visual automaticamente",
        value=bool(state.get("usar_visual_automatico", True)),
        help=(
            "Se ativado, roupa/cabelo de Mary serão sugeridos automaticamente "
            "com base no local, tempo e tom da cena."
        ),
    )

    state["visual_atual_manual"] = st.text_area(
        "👗 Visual manual de Mary (opcional)",
        value=state.get("visual_atual_manual", ""),
        height=95,
        placeholder=(
            "Se quiser, descreva manualmente o visual. "
            "Se deixar em branco, o script gera automaticamente."
        ),
    )

    state["visual_atual"] = resolver_visual_atual_mary(state)

    with st.expander("👗 Visual resolvido", expanded=False):
        st.write(state.get("visual_atual", ""))

    # ======================================================
    # MODO SURPRESA
    # ======================================================
    st.markdown(
        '<div class="sidebar-box-title">⚡ Modo surpresa</div>',
        unsafe_allow_html=True,
    )

    modo_surpresa_atual = normalizar_modo_surpresa(
        state.get("modo_surpresa", "Desligado")
    )

    if modo_surpresa_atual not in OPCOES_MODO_SURPRESA:
        modo_surpresa_atual = "Desligado"

    state["modo_surpresa"] = st.selectbox(
        "⚡ Modo surpresa",
        options=OPCOES_MODO_SURPRESA,
        index=OPCOES_MODO_SURPRESA.index(modo_surpresa_atual),
        help=(
            "Define o tipo de gancho inesperado que Mary pode abrir. "
            "Ela deve anunciar ou iniciar a surpresa, parar em um ponto jogável "
            "e não resolver tudo sozinha. Após o disparo, o ideal é voltar para Desligado."
        ),
    )

    state["direcao_surpresa"] = st.text_area(
        "🧩 Direção da surpresa",
        value=state.get("direcao_surpresa", ""),
        height=85,
        placeholder=(
            "Opcional. Exemplos:\n"
            "- Bianca manda mensagem.\n"
            "- Renan liga.\n"
            "- O celular fica destravado.\n"
            "- Uma foto do biquíni aparece.\n"
            "- Silvia aparece chamando Mary."
        ),
        help=(
            "Use apenas para orientar o gancho. "
            "Mary deve abrir a oportunidade, dizer claramente o que surgiu "
            "e deixar o usuário decidir a continuação."
        ),
    )

    if state.get("modo_surpresa") != "Desligado":
        st.caption(
            "⚠️ Surpresa armada: Mary deve abrir apenas um gancho e parar, "
            "sem resolver a ligação, mensagem, segredo ou complicação sozinha."
        )

    state["mary_acao"] = st.text_area(
        "🎬 Ação atual de Mary",
        value=state.get("mary_acao", ""),
        height=100,
        placeholder=(
            "Ex: Mary está no banheiro, terminando de apagar o batom do espelho "
            "com um lenço, vestindo o roupão de seda."
        ),
        help=(
            "Descreva o estado físico e a ação imediata de Mary no momento atual da cena. "
            "Este campo deve representar o agora, não o passado."
        ),
    )
      

    normalizar_estado(state)
    reconciliar_pos_climax(state)
    sincronizar_facts_basicos(state, recalcular_estado=False)

    st.info(
        f"""
        **Tom manual:** {state.get("tom_manual_da_cena")}  
        **Privacidade detectada:** {state.get("privacidade")}  
        **Tipo de cena aplicado:** {state.get("tipo_de_cena")}  
        **Iniciativa aplicada:** {state.get("estilo_de_iniciativa")}  
        **Tom aplicado:** {state.get("tom_da_cena")}  
        **Fase física:** {state.get("physical_phase")}  
        **Tensão:** {state.get("tension_level")}  
        **Modo surpresa:** {state.get("modo_surpresa")}
        """
    )
    
    if st.button("💾 Salvar cena", use_container_width=True):
        normalizar_estado(state)
        sincronizar_facts_basicos(state, recalcular_estado=False)
        salvar_facts_na_planilha(state["facts"])
        limpar_cache_planilhas()
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
            limpar_cache_planilhas()
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
    st.subheader("📖 Cânone da história")
    
    novo_fato_canon = st.text_area(
        "Novo fato fixo do enredo",
        value="",
        height=90,
        placeholder="Ex: Mary estuda Psicologia na UFRJ.",
    )
    
    col_can_1, col_can_2 = st.columns([2, 1])
    
    with col_can_1:
        categoria_canon = st.text_input(
            "Categoria do cânone",
            value="geral",
            placeholder="Ex: identidade, relação, rival, família",
        )
    
    with col_can_2:
        peso_canon = st.number_input(
            "Peso do cânone",
            min_value=0.1,
            max_value=5.0,
            value=1.0,
            step=0.1,
            key="peso_canon_mary",
        )
    
    if st.button("💾 Salvar fato no cânone", use_container_width=True):
        ok = salvar_canon_mary_na_planilha(
            fato=novo_fato_canon,
            categoria=categoria_canon,
            peso=peso_canon,
        )
    
        if ok:
            state["canon_mary"] = carregar_canon_mary_da_planilha(apenas_ativos=True)
            st.session_state.mary_state_minimo = state
            st.success("Fato salvo no cânone.")
            st.rerun()
        else:
            st.warning("Nenhum fato foi salvo.")
    
    with st.expander("📚 Ver cânone atual", expanded=False):
        canon_atual = state.get("canon_mary", [])
    
        if not canon_atual:
            st.info("Nenhum fato de cânone ativo.")
        else:
            for item in canon_atual:
                st.markdown(
                    f"**{item.get('id', '')}** · `{item.get('categoria', 'geral')}` · peso `{item.get('peso', 1.0)}`"
                )
                st.write(item.get("fato", ""))
                st.divider()
    
    with st.expander("🗑️ Apagar fato do cânone", expanded=False):
        canon_id = st.text_input(
            "ID do fato",
            value="",
            placeholder="Ex: canon_3",
            key="canon_id_delete",
        )
    
        confirmar_apagar_canon = st.checkbox(
            "Confirmar apagar fato do cânone",
            value=False,
            key="confirmar_apagar_canon",
        )
    
        if st.button(
            "Apagar fato do cânone",
            use_container_width=True,
            disabled=not confirmar_apagar_canon,
        ):
            if apagar_canon_mary_por_id(canon_id):
                state["canon_mary"] = carregar_canon_mary_da_planilha(apenas_ativos=True)
                st.session_state.mary_state_minimo = state
                st.success("Fato do cânone apagado.")
                st.rerun()
            else:
                st.warning("Fato não encontrado.")
    st.divider()
    st.subheader("🗑️ Apagar turnos")

    n_turnos = st.number_input(
        "Turnos para apagar",
        min_value=1,
        max_value=50,
        value=1,
        step=1,
    )

    confirmar_turnos = st.checkbox(
        "Confirmar apagamento de turnos",
        value=False,
    )

    if st.button(
        "Apagar últimos turnos",
        use_container_width=True,
        disabled=not confirmar_turnos,
    ):
        qtd = apagar_ultimos_turnos_da_planilha(int(n_turnos))
    
        if qtd > 0:
            # Limpa caches para forçar nova leitura real da planilha.
            limpar_cache_planilhas()
    
            # Recarrega o histórico real restante da planilha.
            historico_recarregado = carregar_history_da_planilha(MAX_HISTORY * 2)
    
            state["history"] = historico_recarregado
            state["turno"] = max(0, len(historico_recarregado) // 2)
    
            # Atualiza facts sem recalcular a cena.
            sincronizar_facts_basicos(state, recalcular_estado=False)
    
            # Garante que a sessão use o histórico recarregado.
            st.session_state["mary_state_minimo"] = state
    
            # Limpa debug antigo para não reaparecer resposta de turno apagado.
            for chave in [
                "mary_last_debug",
                "mary_last_model_eval",
                "mary_model_ping_result",
            ]:
                if chave in st.session_state:
                    del st.session_state[chave]
    
            st.success(f"{qtd} linha(s) apagada(s). Histórico recarregado da planilha.")
            st.rerun()
    
        else:
            st.warning("Nenhum turno foi apagado.")

    st.divider()
    st.subheader("🧹 Reset local da conversa")

    if st.button("Limpar histórico local da sessão", use_container_width=True):
        # Limpa o histórico preso no state atual.
        state["history"] = []
        state["turno"] = 0

        # Limpa a cópia persistida na sessão do Streamlit.
        if "mary_state_minimo" in st.session_state:
            st.session_state["mary_state_minimo"]["history"] = []
            st.session_state["mary_state_minimo"]["turno"] = 0

        # Remove restos visuais/debug de interações anteriores.
        for chave in [
            "history",
            "mary_last_debug",
            "mary_last_model_eval",
            "mary_model_ping_result",
        ]:
            if chave in st.session_state:
                del st.session_state[chave]

        limpar_cache_planilhas()

        st.session_state["mary_state_minimo"] = state
        st.success("Histórico local limpo.")
        st.rerun()

    if st.button("Reset total da sessão local", use_container_width=True):
        manter_login = st.session_state.get("mary_app_autenticado", False)

        for chave in list(st.session_state.keys()):
            del st.session_state[chave]

        st.session_state["mary_app_autenticado"] = manter_login

        limpar_cache_planilhas()
        st.rerun()

    
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
            resposta_final = ""
        
            with st.spinner("Mary está respondendo..."):
        
                # ==================================================
                # GERA RESPOSTA
                # O motor completo do turno agora está dentro de
                # processar_turno().
                #
                # Não repetir aqui:
                # - normalizar_estado()
                # - atualizar_pico_mary_por_contexto()
                # - preparar_resolucao_mary_se_necessario()
                # - definir_acao_autonoma()
                # - detectar_climax_usuario()
                # - sincronizar_facts_basicos()
                # ==================================================
                resultado = processar_turno(
                    state,
                    fala_usuario,
                    model=model,
                )

                consumir_evento_inesperado_se_usado(state)

                st.session_state["mary_last_debug"] = resultado

                resposta_final = str(
                    resultado.get("resposta_final_limpa", "") or ""
                ).strip()
                # ==================================================
                # 6.5) Sincroniza state se Mary verbalizou o próprio pico
                # ==================================================
                atualizar_pico_mary_por_contexto(
                    state,
                    fala_usuario,
                    resposta_limpa=resposta_final,
                )
                
                atualizar_estado_pos_resposta_climax(state, resposta_final)
                sincronizar_facts_basicos(state, recalcular_estado=False)
                resultado["state"] = dict(state)
                resultado["facts"] = dict(state.get("facts", {}))
        
                # ==================================================
                # 7) Salva avaliação do modelo em módulo externo
                # ==================================================
                avaliacao_modelo = salvar_model_eval_na_planilha(
                    get_spreadsheet_func=_get_spreadsheet,
                    state=state,
                    fala_usuario=fala_usuario,
                    resposta=resposta_final,
                    model=model,
                    resultado=resultado,
                )
        
                st.session_state["mary_last_model_eval"] = avaliacao_modelo
        
            renderizar_resposta_mary(resposta_final)
        
        st.stop()

if "mary_last_debug" in st.session_state:
    with st.expander("🧪 Última análise técnica", expanded=False):
        dbg = st.session_state["mary_last_debug"]

        st.markdown("### Prompt enviado ao modelo")
        st.code(
            json.dumps(
                dbg.get("mensagens", []),
                ensure_ascii=False,
                indent=2,
            ),
            language="json",
        )

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

if "mary_last_model_eval" in st.session_state:
    with st.expander("📊 Avaliação do modelo", expanded=False):
        avaliacao = st.session_state.get("mary_last_model_eval", {})

        nota_final = avaliacao.get("nota_final", None)

        if nota_final is not None:
            st.metric("Nota final do modelo", nota_final)

        st.json(avaliacao)
