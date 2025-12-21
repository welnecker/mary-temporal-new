from __future__ import annotations

import time
import re
import traceback
import importlib
import inspect

import streamlit as st

import characters.mary.persona as mary_persona
from characters.mary.service import MaryService, _current_user_key
from characters.mary.persona import get_persona

from core.service_router import list_models
from core.database import db_status
from core.repositories import (
    get_history_docs,
    get_history_docs_multi,
    get_facts,
    set_fact,
    delete_fact,
    delete_last_interaction,
    delete_user_history,
)

# ==========================================================
# CONFIG
# ==========================================================
st.set_page_config(
    page_title="Mary – Esposa Cúmplice",
    page_icon="💍💍",
    layout="centered",
)

SENHA_CORRETA = "311071"
DEFAULT_VISUAL_LIMIT = 80

DEFAULT_MODEL = "tngtech/deepseek-r1t2-chimera:free"
FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324"


# ==========================================================
# UI / CSS
# ==========================================================
def _apply_dark_ui() -> None:
    st.markdown(
        """
        <style>
        html, body, #root, .stApp { background: #0b0b0b !important; }
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        section.main { background: #0b0b0b !important; }

        header[data-testid="stHeader"],
        [data-testid="stDecoration"],
        [data-testid="stToolbar"] { background: #0b0b0b !important; }

        footer { visibility: hidden !important; height: 0 !important; }
        .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; }

        section[data-testid="stSidebar"] {
            background: #141414 !important;
            border-right: 1px solid #222 !important;
        }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] div { color: #f2f2f2 !important; }

        [data-testid="stMarkdownContainer"],
        [data-testid="stCaptionContainer"],
        .stApp p, .stApp span, .stApp label { color: #f2f2f2; }

        input, textarea {
            background: #101010 !important;
            color: #f2f2f2 !important;
            border: 1px solid #2a2a2a !important;
        }

        div[data-baseweb="select"] > div {
            background: #101010 !important;
            border: 1px solid #2a2a2a !important;
        }
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div { color: #f2f2f2 !important; }

        button {
            background: #141414 !important;
            color: #f2f2f2 !important;
            border: 1px solid #2a2a2a !important;
        }
        button:hover { border-color: #3a3a3a !important; }

        div[data-testid="stChatMessage"] > div{
            background: rgba(15,15,15,0.92) !important;
            border: 1px solid rgba(255,255,255,0.08) !important;
            border-radius: 16px !important;
            padding: 14px 14px 10px 14px !important;
            box-shadow: 0 10px 26px rgba(0,0,0,0.55) !important;
            backdrop-filter: blur(6px);
        }
        div[data-testid="stChatMessage"] p{
            margin: 0 0 0.95rem 0 !important;
            line-height: 1.55 !important;
            font-size: 1.02rem !important;
            color: #f2f2f2 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _format_paragraphs(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    if "\n\n" in t:
        return t

    if "\n" in t and t.count("\n") >= 2:
        t2 = re.sub(r"\n{2,}", "\n\n", t)
        if "\n\n" in t2:
            return t2
        t = t2.replace("\n", " ")

    sentences = re.split(r"(?<=[.!?…])\s+", t)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) <= 3:
        return t

    chunks = []
    i = 0
    while i < len(sentences):
        size = 2 if (i % 6) != 4 else 3
        chunk = " ".join(sentences[i : i + size]).strip()
        if chunk:
            chunks.append(chunk)
        i += size

    return "\n\n".join(chunks)


# ==========================================================
# SENHA
# ==========================================================
def check_password() -> bool:
    if "senha_ok" not in st.session_state:
        st.session_state["senha_ok"] = False
    if st.session_state["senha_ok"]:
        return True

    _apply_dark_ui()
    st.title("🔐 Mary – Acesso Restrito")
    with st.form("form_senha", clear_on_submit=False):
        senha = st.text_input("Digite a senha de acesso:", type="password")
        ok = st.form_submit_button("Entrar")

    if ok:
        if senha == SENHA_CORRETA:
            st.session_state["senha_ok"] = True
            st.success("Acesso liberado!")
            st.rerun()
        else:
            st.error("Senha incorreta. Tente novamente.")
    return False


if not check_password():
    st.stop()


# ==========================================================
# HELPERS
# ==========================================================
def _get_service() -> MaryService:
    svc = st.session_state.get("_mary_service")
    if svc is None:
        svc = MaryService()
        st.session_state["_mary_service"] = svc
    return svc


def _invalidate_backend_cache() -> None:
    st.session_state["backend_hist_cache"] = None
    st.session_state["backend_hist_cache_ts"] = 0.0
     st.session_state["backend_hist_cache_key"] = ""   # <<< ADICIONE

def _keys_para_mary() -> list[str]:
    # A key REAL é a do service, e ela inclui timeline (uid::mary::{timeline})
    return [_current_user_key()]


def _choose_default_model(available: list[str]) -> str:
    if available and DEFAULT_MODEL in available:
        return DEFAULT_MODEL
    if available:
        non_grok = [m for m in available if "grok" not in (m or "").lower()]
        return non_grok[0] if non_grok else available[0]
    return FALLBACK_MODEL


def _garantir_estado_inicial() -> None:
    # 1) timeline precisa existir ANTES de qualquer coisa que dependa de _current_user_key()
    if "mary_timeline" not in st.session_state:
        st.session_state["mary_timeline"] = "cumplice"
    if "mary_timeline_locked" not in st.session_state:
        st.session_state["mary_timeline_locked"] = False

    if "user_id" not in st.session_state or not st.session_state["user_id"]:
        st.session_state["user_id"] = "Janio Donisete"

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    if "backend_hist_cache_key" not in st.session_state:
    st.session_state["backend_hist_cache_key"] = ""


    # modelos disponíveis
    try:
        modelos = list_models() or []
    except Exception:
        modelos = []

    if "model" not in st.session_state or not st.session_state["model"]:
        st.session_state["model"] = _choose_default_model(modelos)
    else:
        if modelos and st.session_state["model"] not in modelos:
            st.session_state["model"] = _choose_default_model(modelos)

    # NSFW default: cúmplice = True | universitária = False
    if "mary_nsfw_on" not in st.session_state:
        st.session_state["mary_nsfw_on"] = (st.session_state.get("mary_timeline") != "universitaria")

    if "mary_intro_done" not in st.session_state:
        st.session_state["mary_intro_done"] = False
    if "visual_limit" not in st.session_state:
        st.session_state["visual_limit"] = DEFAULT_VISUAL_LIMIT
    if "backend_hist_cache" not in st.session_state:
        st.session_state["backend_hist_cache"] = None
    if "backend_hist_cache_ts" not in st.session_state:
        st.session_state["backend_hist_cache_ts"] = 0.0

    # debounce
    if "last_submit_ts" not in st.session_state:
        st.session_state["last_submit_ts"] = 0.0
    if "last_submit_text" not in st.session_state:
        st.session_state["last_submit_text"] = ""


def _clear_service_caches_for_keys(keys: list[str]) -> None:
    for k in keys:
        for ck in (f"facts::{k}", f"history::{k}"):
            if ck in st.session_state:
                del st.session_state[ck]


def _intro_fact_key_for_timeline(timeline: str) -> str:
    tl = (timeline or "").strip() or "cumplice"
    return f"mary.intro.fixed.{tl}"


def _pick_intro_from_persona(timeline: str) -> str:
    persona_text, history_boot = get_persona(timeline)

    opcoes = []
    if isinstance(history_boot, list):
        for msg in history_boot:
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("content"):
                # se vier timeline no dict, respeita
                if msg.get("timeline") and str(msg.get("timeline")) != str(timeline):
                    continue
                opcoes.append(str(msg["content"]).strip())

    if not opcoes:
        return "Oi… eu tô aqui."
    return opcoes[0]  # determinístico


def _get_or_fix_intro_for_current_timeline() -> str:
    usuario_key = _current_user_key()
    timeline = str(st.session_state.get("mary_timeline") or "cumplice").strip()
    fact_key = _intro_fact_key_for_timeline(timeline)

    # 1) tenta ler o fact
    try:
        facts = get_facts(usuario_key) or {}
        intro = str(facts.get(fact_key) or "").strip()
        if intro:
            return intro
    except Exception:
        pass

    # 2) não existe -> escolhe da persona e fixa no fact dessa timeline
    intro = _pick_intro_from_persona(timeline)
    try:
        set_fact(usuario_key, fact_key, intro, {"fonte": "persona_intro_fixada"})
    except Exception:
        pass
    return intro


def _colar_fala_inicial_na_tela() -> None:
    intro = _get_or_fix_intro_for_current_timeline()
    st.session_state["chat_history"] = [("assistant", intro)]
    st.session_state["mary_intro_done"] = True


def _carregar_chat_visual_do_backend(force: bool = False) -> list[tuple[str, str]]:
    now = time.time()
    keys = _keys_para_mary()
    cache_key = "|".join(keys)

    if not force:
        cached = st.session_state.get("backend_hist_cache")
        ts = float(st.session_state.get("backend_hist_cache_ts", 0.0))
        ck = str(st.session_state.get("backend_hist_cache_key", ""))
        if cached is not None and (now - ts) < 2.0 and ck == cache_key:
            return cached


    keys = _keys_para_mary()

    try:
        docs = get_history_docs_multi(keys, limit=800) or []
    except Exception as e:
        st.session_state["last_model_error"] = f"BOOT history load failed: {type(e).__name__}: {e}"
        st.error("💥 Falha ao carregar histórico do backend.")
        st.write("Chaves consultadas:", keys)
        st.code(traceback.format_exc())
        st.stop()

    hist: list[tuple[str, str]] = []
    for d in docs:
        u = (d.get("mensagem_usuario") or "").strip()
        a = (d.get("resposta_mary") or "").strip()
        if u:
            hist.append(("user", u))
        if a:
            hist.append(("assistant", a))

    st.session_state["backend_hist_cache"] = hist
    st.session_state["backend_hist_cache_ts"] = now
    st.session_state["backend_hist_cache_key"] = cache_key   # <<< ADICIONE
    return hist


def _apagar_hist_bd_novo_e_legado() -> int:
    keys = _keys_para_mary()
    total = 0
    for k in keys:
        try:
            total += int(delete_user_history(k) or 0)
        except Exception:
            pass
    return total


def _diagnostico_hist(keys: list[str]) -> dict:
    out = {}
    for k in keys:
        try:
            docs = get_history_docs(k, limit=5) or []
            out[k] = {
                "count_approx_5": len(docs),
                "first_user": (docs[0].get("mensagem_usuario") if docs else None),
                "first_mary": (docs[0].get("resposta_mary") if docs else None),
                "last_user": (docs[-1].get("mensagem_usuario") if docs else None),
                "last_mary": (docs[-1].get("resposta_mary") if docs else None),
            }
        except Exception as e:
            out[k] = {"error": f"{type(e).__name__}: {e}"}
    return out


def _apagar_eventos_mary_fact(usuario_key: str) -> int:
    try:
        facts = get_facts(usuario_key) or {}
    except Exception:
        facts = {}

    keys = [
        k
        for k in facts.keys()
        if isinstance(k, str) and (k.startswith("mary.evento.") or k.startswith("mary.eventos."))
    ]
    removed = 0
    for k in keys:
        try:
            if delete_fact(usuario_key, k):
                removed += 1
        except Exception:
            pass
    return removed


def _delete_last_turn_active() -> bool:
    usuario_key = _current_user_key()

    try:
        ok = bool(delete_last_interaction(usuario_key))
    except Exception:
        ok = False

    _invalidate_backend_cache()
    _clear_service_caches_for_keys([usuario_key])
    return ok


def _on_timeline_change() -> None:
    # só permite trocar antes de conversar
    if st.session_state.get("mary_timeline_locked"):
        return

    # aplica timeline do select
    personas = {
        "Mary – Esposa Cúmplice": "cumplice",
        "Mary – Universitária (linha alternativa)": "universitaria",
    }
    st.session_state["mary_timeline"] = personas.get(st.session_state.get("persona_label") or "", "cumplice")

    # ajusta NSFW default quando troca timeline (apenas se usuário ainda não mexeu)
    # aqui: se já existe a chave, não força; mas se quiser forçar sempre, descomente a linha abaixo.
    st.session_state["mary_nsfw_on"] = (st.session_state["mary_timeline"] != "universitaria")

    # reseta visual e caches para boot carregar a key correta
    st.session_state["chat_history"] = []
    st.session_state["mary_intro_done"] = False
    _invalidate_backend_cache()

    # limpa caches do service para a key NOVA
    keys = _keys_para_mary()
    _clear_service_caches_for_keys(keys)


# ==========================================================
# APP
# ==========================================================
def main() -> None:
    _apply_dark_ui()
    _garantir_estado_inicial()
    svc = _get_service()

    st.caption("🧩 mary_app.py v3.4 (FIX REAL: timeline antes do boot + intro por timeline + keys corretas)")

    backend, detail = db_status()
    st.caption(f"🗄️ Backend atual: **{backend}** ({detail})")

    st.title("Mary – Esposa Cúmplice 💍💍")

    # ===== TIMELINE (ANTES DO BOOT!) =====
    personas = {
        "Mary – Esposa Cúmplice": "cumplice",
        "Mary – Universitária (linha alternativa)": "universitaria",
    }

    label_atual = next(
        (k for k, v in personas.items() if v == st.session_state.get("mary_timeline")),
        "Mary – Esposa Cúmplice",
    )

    st.selectbox(
        "🎭 Linha temporal da Mary",
        list(personas.keys()),
        index=list(personas.keys()).index(label_atual),
        disabled=st.session_state["mary_timeline_locked"],
        key="persona_label",
        on_change=_on_timeline_change,
    )

    # garante que mary_timeline reflita o label mesmo sem on_change (primeiro load)
    st.session_state["mary_timeline"] = personas.get(st.session_state["persona_label"], "cumplice")

    if st.session_state["mary_timeline_locked"]:
        st.caption("🔒 Persona travada até limpar a conversa (ou apagar histórico).")

    # ===== KEYS SEMPRE DEPOIS DO SELECT =====
    keys = _keys_para_mary()

    # ===== BACKEND =====
    with st.expander("🧨 BACKEND — apagar histórico de verdade + diagnóstico", expanded=False):
        st.write("Chaves usadas:", keys)

        if st.button("🔎 Diagnóstico agora"):
            st.json(_diagnostico_hist(keys))

        colA, colB = st.columns(2)
        with colA:
            confirmar = st.checkbox("Confirmo apagar TODO histórico do BD (history)", value=False)
            if st.button("🔥 APAGAR HISTÓRICO DO BD (AGORA)", type="primary"):
                if not confirmar:
                    st.error("Marque a confirmação.")
                else:
                    n = _apagar_hist_bd_novo_e_legado()
                    _invalidate_backend_cache()
                    _clear_service_caches_for_keys(keys)
                    st.session_state["chat_history"] = []
                    st.session_state["mary_intro_done"] = False
                    st.session_state["mary_timeline_locked"] = False
                    st.success(f"✅ Apaguei do BD (history): {n} registros.")
                    st.rerun()

        with colB:
            confirmar2 = st.checkbox("Confirmo apagar facts mary.evento.* também", value=False)
            if st.button("💣 APAGAR EVENTOS mary.evento.* (facts)"):
                if not confirmar2:
                    st.error("Marque a confirmação.")
                else:
                    removed = _apagar_eventos_mary_fact(_current_user_key())
                    _clear_service_caches_for_keys(keys)
                    st.success(f"✅ Apaguei {removed} facts de eventos mary.evento.*")
                    st.rerun()

    # ===== SIDEBAR =====
    with st.sidebar:
        st.header("Mary – Controles")

        st.text_input("👤 Usuário", value="Janio Donisete", disabled=True)
        st.caption(f"🧩 Timeline: {st.session_state['mary_timeline']}")
        st.caption(f"🔑 usuario_key atual: {_current_user_key()}")

        try:
            all_models = list_models() or []
        except Exception:
            all_models = []
        if not all_models:
            all_models = [FALLBACK_MODEL]

        if st.session_state.get("model") not in all_models:
            st.session_state["model"] = _choose_default_model(all_models)

        current = st.session_state.get("model")
        idx = all_models.index(current) if current in all_models else 0

        st.selectbox("🧠 Modelo", all_models, index=idx, key="model")

        st.markdown("---")
        st.checkbox("Modo adulto liberado (NSFW)", key="mary_nsfw_on")

        st.markdown("---")
        st.subheader("Turnos")

        if st.button("Apagar último turno (backend)"):
            ok = _delete_last_turn_active()
            if ok:
                # deixa o BOOT recarregar corretamente
                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                st.success("✅ Último turno apagado (Mary ativa).")
            else:
                st.warning("Nada para apagar (backend não retornou sucesso).")
            st.rerun()


        st.markdown("---")
        st.subheader("Limpar tela")
        if st.button("Limpar tela (visual)"):
            st.session_state["chat_history"] = []
            st.rerun()

        st.markdown("---")
        st.subheader("🎭 Persona")
        st.caption("Arquivo ativo:")
        st.code(inspect.getfile(mary_persona.get_persona))

        if st.button("♻️ Recarregar persona AGORA"):
            importlib.reload(mary_persona)
            st.session_state.pop("_mary_service", None)
            st.session_state["mary_intro_done"] = False
            st.session_state["chat_history"] = []
            _invalidate_backend_cache()
            _clear_service_caches_for_keys(_keys_para_mary())
            st.session_state["mary_timeline_locked"] = False
            st.success("Persona recarregada. Boot vai colar a intro correta por timeline.")
            st.rerun()

    # ===== BOOT (AGORA timeline já está correta) =====
    if not st.session_state["chat_history"]:
        backend_hist = _carregar_chat_visual_do_backend(force=False)

        if backend_hist:
            st.session_state["chat_history"] = backend_hist
            st.session_state["mary_intro_done"] = True
        else:
            # se não tem histórico, cola intro da timeline atual
            if not st.session_state.get("mary_intro_done", False):
                _colar_fala_inicial_na_tela()

    # ===== RENDER =====
    hist = st.session_state.get("chat_history", [])
    visual_limit = int(st.session_state.get("visual_limit", DEFAULT_VISUAL_LIMIT))
    visible = hist[-visual_limit:] if len(hist) > visual_limit else hist

    for role, content in visible:
        with st.chat_message(role):
            if role == "assistant":
                st.markdown(_format_paragraphs(content))
            else:
                st.markdown(content)

    # ===== INPUT =====
    prompt = st.chat_input("Fala algo pra Mary...")
    if prompt:
        # trava persona após o primeiro envio
        if not st.session_state["mary_timeline_locked"]:
            st.session_state["mary_timeline_locked"] = True

        now = time.time()
        last_ts = float(st.session_state.get("last_submit_ts", 0.0))
        last_txt = str(st.session_state.get("last_submit_text", ""))

        if prompt.strip() == last_txt.strip() and (now - last_ts) < 1.2:
            st.warning("⚠️ Mensagem repetida muito rápido. Ignorando para evitar duplicação.")
            st.stop()

        st.session_state["last_submit_ts"] = now
        st.session_state["last_submit_text"] = prompt

        st.session_state["chat_history"].append(("user", prompt))
        with st.chat_message("user"):
            st.markdown(prompt)

        st.session_state["chat_input"] = prompt

        try:
            resposta = svc.reply(
                user=st.session_state.get("user_id", "Janio Donisete"),
                model=st.session_state.get("model") or DEFAULT_MODEL,
            )
        except Exception as e:
            st.session_state["chat_input"] = ""
            st.error(f"💥 Erro real ao chamar o modelo: {type(e).__name__}: {e}")
            st.code(traceback.format_exc())
            st.stop()

        st.session_state["chat_input"] = ""

        if not (resposta or "").strip():
            st.warning("⚠️ O modelo retornou vazio.")
            st.stop()

        with st.chat_message("assistant"):
            st.markdown(_format_paragraphs(resposta))

        st.session_state["chat_history"].append(("assistant", resposta))
        _invalidate_backend_cache()


if __name__ == "__main__":
    main()
