# pages/mary_app.py
from __future__ import annotations

# ==========================================================
# IMPORTS PADRÃO
# ==========================================================
import time
import re
import traceback
import importlib
import inspect
from typing import Any
import streamlit as st

# ==========================================================
# 🔥 HARD RESET NO BOOT (ANTI-VAZAMENTO ENTRE TIMELINES)
# ==========================================================
def _hard_reset_on_boot_if_needed() -> None:
    """
    Streamlit reidrata session_state ao reabrir o app.
    Se a timeline mudou desde o último boot, limpamos TUDO
    antes de qualquer render.
    """
    current_tl = str(st.session_state.get("mary_timeline") or "cumplice").strip()
    last_tl = st.session_state.get("mary_last_boot_timeline")

    if last_tl != current_tl:
        for k in list(st.session_state.keys()):
            if not isinstance(k, str):
                continue

            if k.startswith("_mary_service::"):
                st.session_state.pop(k, None)
                continue

            if k.startswith(("facts::", "history::", "mem::", "longmem::")):
                st.session_state.pop(k, None)
                continue

            if k.startswith(("intro_ctx_injected::", "intro_injected::")):
                st.session_state.pop(k, None)

        # ✅ evita ficar travado ao reabrir
        st.session_state.pop("mary_timeline_locked", None)
        # ✅ Destrava a timeline no boot (evita entrar travado em cúmplice)
        st.session_state.pop("mary_timeline_locked", None)
        # também remove a seleção visual (será recalculada pela timeline)
        st.session_state.pop("persona_label", None)

        st.session_state["mary_last_boot_timeline"] = current_tl


# ⚠️ EXECUTA IMEDIATAMENTE NO BOOT
_hard_reset_on_boot_if_needed()

# ==========================================================
# IMPORTS DO PROJETO (SEMPRE DEPOIS DO FUTURE)
# ==========================================================
from core.repositories import (
    list_memories,
    delete_last_memory,
    delete_all_memories,
    get_history_docs,
    get_history_docs_multi,
    get_facts,
    set_fact,
    append_memory,  # ✅ necessário para o botão "virgem"
    delete_fact,
    delete_last_interaction,
    delete_user_history,
    # ✅ LONG MEMORY (Mongo text search)
    append_long_memory,
    list_long_memory,
    search_long_memory_text,
    ensure_long_memory_indexes,
    delete_last_long_memory,
    delete_all_long_memory,
)

import characters.mary.persona as mary_persona
from characters.mary.service import get_service_class
import core.repositories as crep
import core.service_router as service_router
from core.database import db_status, ping_db, get_backend


# ==========================================================
# CONFIG
# ==========================================================
st.set_page_config(
    page_title="Roleplay",
    page_icon="💍💍",
    layout="centered",
)

SENHA_CORRETA = "311071"
DEFAULT_VISUAL_LIMIT = 80

DEFAULT_MODEL = "tngtech/tng-r1t-chimera:free"
FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324"


# ==========================================================
# UI / CSS (Base44-like + dark + chat_input fixo)
# ==========================================================
def _apply_dark_ui() -> None:
    st.markdown(
        """
        <style>
        html, body, #root, .stApp { background: #0b0b0b !important; }
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] { background: #0b0b0b !important; }

        footer { visibility: hidden !important; height: 0 !important; }

        /* espaço no fim para não esconder mensagens atrás do input fixo */
        .block-container {
            max-width: 980px !important;
            padding-top: 1rem !important;
            padding-bottom: 9rem !important;
        }

        /* Card header */
        .rp-card {
            background: rgba(18,18,18,0.92);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 16px;
            padding: 16px;
            margin: 0 0 12px 0;
            box-shadow: 0 12px 28px rgba(0,0,0,0.55);
            backdrop-filter: blur(6px);
        }
        .rp-title { font-size: 22px; font-weight: 800; margin: 0; color: #fff; }
        .rp-sub { font-size: 13px; margin-top: 6px; color: rgba(255,255,255,0.65); }

        /* Chat bubbles */
        div[data-testid="stChatMessage"] > div{
            background: rgba(15,15,15,0.92) !important;
            border: 1px solid rgba(255,255,255,0.08) !important;
            border-radius: 16px !important;
            padding: 14px 14px 10px 14px !important;
            box-shadow: 0 10px 26px rgba(0,0,0,0.55) !important;
        }
        div[data-testid="stChatMessage"][aria-label="user"] > div{
            background: rgba(24,24,24,0.95) !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
        }
        div[data-testid="stChatMessage"] p{
            margin: 0 0 0.95rem 0 !important;
            line-height: 1.55 !important;
            font-size: 1.02rem !important;
            color: #f2f2f2 !important;
        }

        /* INPUT FIXO */
        .stChatInput, div[data-testid="stChatInput"] {
            position: fixed !important;
            left: 0 !important;
            right: 0 !important;
            bottom: 0 !important;
            z-index: 9999 !important;
            background: rgba(11,11,11,0.88) !important;
            backdrop-filter: blur(10px) !important;
            border-top: 1px solid rgba(255,255,255,0.10) !important;
            padding: 10px 0 !important;
        }

        .stChatInput > div, div[data-testid="stChatInput"] > div {
            max-width: 980px !important;
            margin: 0 auto !important;
            padding: 0 1rem !important;
        }

        .stChatInput textarea, div[data-testid="stChatInput"] textarea {
            min-height: 96px !important;
            max-height: 240px !important;
            border-radius: 14px !important;
            background: #101010 !important;
            color: #f2f2f2 !important;
            border: 1px solid rgba(255,255,255,0.14) !important;
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
    st.title("🔐 Acesso Restrito")
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
# KEYS (não depender do service)
# ==========================================================
def _uid() -> str:
    uid = (st.session_state.get("user_id") or "anon").strip() or "anon"
    return uid


def _timeline() -> str:
    return str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"


def _usuario_key_atual() -> str:
    return f"{_uid()}::mary::{_timeline()}"


def _usuario_key_for_timeline(timeline: str) -> str:
    tl = str(timeline or "cumplice").strip() or "cumplice"
    return f"{_uid()}::mary::{tl}"


def _shared_key_atual() -> str:
    return f"{_uid()}::mary::shared"


def _keys_para_mary() -> list[str]:
    # ✅ SEMPRE somente a timeline ativa
    return [_usuario_key_atual()]


# ==========================================================
# ✅ CANON BUTTON HELPERS (Virgem -> Consumado)
# ==========================================================
def _today_iso() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _set_virginity_canon(*, usuario_key: str, shared_key: str, timeline: str, user_id: str) -> None:
    """
    Marca no CANON que Mary NÃO é mais virgem (consumado).
    - Grava na memória permanente shared como kind='canon' (fonte de verdade).
    - Atualiza rel.state::<timeline> nos facts (camada derivada, para consistência imediata).
    """
    date_iso = _today_iso()

    canon_text = (
        f"MEMÓRIA CANÔNICA: Mary e {user_id} consumaram a relação. "
        f"Mary NÃO é mais virgem. (válido para o universo compartilhado)\n"
        f"Data: {date_iso}\n"
        f"Timeline ativa no momento do registro: {timeline}"
    )

    meta = {
        "kind": "canon",
        "title": "Virgindade — consumado",
        "key": "virginity",
        "value": "nao_virgem",
        "date": date_iso,
        "source": "ui_button",
        "timeline_at_save": timeline,
        "user_id": user_id,
    }

    # 1) CANON (shared)
    append_memory(shared_key, canon_text, meta=meta)

    # 2) FACTS (relationship_state) — derivado
    facts = get_facts(usuario_key) or {}
    rel_key = f"rel.state::{timeline}"
    rel = facts.get(rel_key) if isinstance(facts.get(rel_key), dict) else {}

    if not isinstance(rel, dict):
        rel = {}

    rel["consummated"] = True
    rel["virginity"] = "nao_virgem"
    rel.setdefault("allows_penetration", True)

    set_fact(usuario_key, rel_key, rel, {"fonte": "ui_button_canon"})
    set_fact(usuario_key, "mary.virginity", "nao_virgem", {"fonte": "ui_button_canon"})


# ==========================================================
# HELPERS
# ==========================================================
def _service_key_for_userkey(userkey: str) -> str:
    return f"_mary_service::{userkey}"


def _instantiate_mary_service(*, userkey: str, timeline: str):
    """
    Cria o service correto para a timeline (universitaria/cumplice) e tenta
    respeitar diferentes assinaturas de __init__ do service_core.

    ✅ Importante: a escolha da classe é feita via characters.mary.service.get_service_class(timeline)
    para evitar que a timeline "universitaria" use o service errado.
    """
    cls = get_service_class(timeline)

    try:
        sig = inspect.signature(cls.__init__)
        params = set(sig.parameters.keys())  # inclui "self"
    except Exception:
        params = set()

    kwargs: dict[str, Any] = {}
    if "usuario_key" in params:
        kwargs["usuario_key"] = userkey
    if "user_key" in params:
        kwargs["user_key"] = userkey
    if "timeline" in params:
        kwargs["timeline"] = timeline

    try:
        return cls(**kwargs) if kwargs else cls()
    except TypeError:
        # Fallbacks defensivos (não quebrar em assinaturas antigas)
        try:
            return cls()
        except Exception:
            try:
                return cls(userkey)  # type: ignore[misc]
            except Exception:
                return cls()  # type: ignore[misc]



def _get_service():
    """
    ✅ FIX DO VAZAMENTO:
    Service é isolado por usuario_key (que inclui timeline).
    Trocar timeline => outro service.
    """
    uk = _usuario_key_atual()
    tl = _timeline()

    sk = _service_key_for_userkey(uk)
    svc = st.session_state.get(sk)

    if svc is None:
        svc = _instantiate_mary_service(userkey=uk, timeline=tl)
        st.session_state[sk] = svc

    return svc


def _kill_all_mary_services() -> None:
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith("_mary_service::"):
            st.session_state.pop(k, None)


def _invalidate_backend_cache() -> None:
    st.session_state["backend_hist_cache"] = None
    st.session_state["backend_hist_cache_ts"] = 0.0
    st.session_state["backend_hist_cache_key"] = ""

    # ✅ também derruba cache de memórias do service
    sk = _shared_key_atual()
    prefix_mem = f"mem::{sk}::"
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(prefix_mem):
            st.session_state.pop(k, None)


def _choose_default_model(available: list[str]) -> str:
    if available and DEFAULT_MODEL in available:
        return DEFAULT_MODEL
    if available:
        non_grok = [m for m in available if "grok" not in (m or "").lower()]
        return non_grok[0] if non_grok else available[0]
    return FALLBACK_MODEL


def _garantir_estado_inicial() -> None:
    # timeline precisa existir ANTES de qualquer key
    if "mary_timeline" not in st.session_state:
        st.session_state["mary_timeline"] = "cumplice"
    if "mary_timeline_locked" not in st.session_state:
        st.session_state["mary_timeline_locked"] = False

    if "user_id" not in st.session_state or not st.session_state["user_id"]:
        st.session_state["user_id"] = "Janio Donisete"

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # ✅ se a timeline ficou travada por reidratação do Streamlit, mas NÃO há mensagens,
    # destrava para permitir escolher a persona (ex: Mary Universitária)
    if st.session_state.get('mary_timeline_locked') and not st.session_state.get('chat_history'):
        st.session_state['mary_timeline_locked'] = False

    if "backend_hist_cache_key" not in st.session_state:
        st.session_state["backend_hist_cache_key"] = ""

    # Relationship Debug
    if "mary_debug_rel_panel" not in st.session_state:
        st.session_state["mary_debug_rel_panel"] = False
    if "mary_rel_meta_last" not in st.session_state:
        st.session_state["mary_rel_meta_last"] = None

    # modelos disponíveis
    try:
        modelos = service_router.list_models() or []
    except Exception:
        modelos = []

    if "model" not in st.session_state or not st.session_state["model"]:
        st.session_state["model"] = _choose_default_model(modelos)
    else:
        if modelos and st.session_state["model"] not in modelos:
            st.session_state["model"] = _choose_default_model(modelos)

    # NSFW default por timeline
    if "mary_nsfw_on" not in st.session_state:
        st.session_state["mary_nsfw_on"] = (_timeline() != "universitaria")

    # para detectar mudança e persistir sem loop
    if "mary_nsfw_last_saved" not in st.session_state:
        st.session_state["mary_nsfw_last_saved"] = None

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

    # view de memórias
    if "__mem_list" not in st.session_state:
        st.session_state["__mem_list"] = None


def _clear_service_caches_for_keys(keys: list[str]) -> None:
    # ✅ remove facts + TODOS history::<key>::<limit> + mem::<key>::<limit>
    for k in keys:
        # facts
        fk = f"facts::{k}"
        if fk in st.session_state:
            del st.session_state[fk]

        # history
        prefix_hist = f"history::{k}::"
        for sk in list(st.session_state.keys()):
            if isinstance(sk, str) and sk.startswith(prefix_hist):
                st.session_state.pop(sk, None)

        # ✅ mem cache
        prefix_mem = f"mem::{k}::"
        for sk in list(st.session_state.keys()):
            if isinstance(sk, str) and sk.startswith(prefix_mem):
                st.session_state.pop(sk, None)


def _reset_intro_flags_for_keys(keys: list[str]) -> None:
    for k in keys:
        st.session_state.pop(f"intro_ctx_injected::{k}", None)
        st.session_state.pop(f"intro_injected::{k}", None)


def _clear_mary_caches_all_related(*, also_clear_other_timeline: bool = True) -> None:
    """
    Limpa caches do usuario_key atual E do shared_key.
    Para evitar “vazamento visual” na troca de timeline, também limpa a OUTRA timeline.
    """
    uk = _usuario_key_atual()
    sk = _shared_key_atual()

    keys = [uk, sk]

    if also_clear_other_timeline:
        other = "universitaria" if _timeline() == "cumplice" else "cumplice"
        keys.append(_usuario_key_for_timeline(other))

    _clear_service_caches_for_keys(keys)
    _reset_intro_flags_for_keys(keys)


def _persist_nsfw_for_current_timeline_if_needed_inline() -> None:
    """
    Persistência NSFW INLINE (não depende de helper fora do callback).
    Evita NameError em callback antigo preso na sessão.
    """
    uk = _usuario_key_atual()
    current = bool(st.session_state.get("mary_nsfw_on", False))
    last = st.session_state.get("mary_nsfw_last_saved", None)

    if last is None or bool(last) != current:
        try:
            set_fact(uk, "mary.nsfw", current, {"fonte": "ui_toggle"})
        except Exception:
            pass
        st.session_state["mary_nsfw_last_saved"] = current
        _clear_service_caches_for_keys([uk])


def _sort_backend_docs(docs: list[dict]) -> list[dict]:
    """
    ✅ Corrige “não retorna na posição correta”.
    Ordena pelo melhor timestamp disponível, mantendo estabilidade.
    """
    if not docs:
        return docs

    def _ts(d: dict) -> float:
        for k in ("ts", "timestamp", "created_ts", "created_at", "time", "date"):
            v = d.get(k)
            if v is None:
                continue
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    vv = v.replace("T", " ").replace("Z", "").strip()
                    if vv.isdigit():
                        return float(vv)
                except Exception:
                    pass
        return 0.0

    indexed = list(enumerate(docs))
    indexed.sort(key=lambda it: (_ts(it[1]), it[0]))
    return [d for _, d in indexed]


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

    try:
        docs = get_history_docs_multi(keys, limit=800) or []
        docs = _sort_backend_docs(docs)
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
    st.session_state["backend_hist_cache_key"] = cache_key
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
            docs = _sort_backend_docs(docs)
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
    usuario_key = _usuario_key_atual()
    try:
        ok = bool(delete_last_interaction(usuario_key))
    except Exception:
        ok = False

    _invalidate_backend_cache()
    _clear_mary_caches_all_related()
    return ok


def _reset_chapter_current_timeline() -> int:
    """
    Reset de capítulo: apaga history da timeline atual,
    mantém memórias permanentes (shared).
    """
    uk = _usuario_key_atual()
    n = 0
    try:
        n = int(delete_user_history(uk) or 0)
    except Exception:
        pass

    st.session_state["chat_history"] = []
    st.session_state["mary_intro_done"] = False
    _invalidate_backend_cache()
    _clear_mary_caches_all_related()
    st.session_state["mary_timeline_locked"] = False
    return n


def _on_timeline_change() -> None:
    """
    ✅ Anti-vazamento + anti-NameError:
    - Limpa caches do backend + service + visual.
    - Persiste NSFW inline (sem depender de helper externo no callback).
    - MATA services isolados por usuario_key (para garantir troca limpa).
    """

    personas = {
        "Mary – Esposa Cúmplice": "cumplice",
        "Mary – Universitária (linha alternativa)": "universitaria",
    }

    old_tl = str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"
    new_tl = personas.get(st.session_state.get("persona_label") or "", "cumplice")

    # troca timeline
    st.session_state["mary_timeline"] = new_tl

    # default NSFW por timeline
    st.session_state["mary_nsfw_on"] = (new_tl != "universitaria")

    # ✅ Persistência NSFW (inline)
    _persist_nsfw_for_current_timeline_if_needed_inline()

    # limpa visual + caches (inclui timeline antiga para matar vazamento)
    st.session_state["chat_history"] = []
    st.session_state["mary_intro_done"] = False
    _invalidate_backend_cache()
    _clear_mary_caches_all_related(also_clear_other_timeline=True)
    _clear_service_caches_for_keys([_usuario_key_for_timeline(old_tl), _usuario_key_for_timeline(new_tl)])

    # 🔥 ponto crítico: matar instâncias de service para não reaproveitar estado
    _kill_all_mary_services()


def _get_intro_persona_text(timeline: str) -> str:
    """
    Busca a primeira mensagem 'assistant' da persona para a timeline.
    Retorna fallback se não achar.
    """
    try:
        _, boot = mary_persona.get_persona(timeline)
    except Exception:
        boot = None

    intro = ""
    if isinstance(boot, list):
        for m in boot:
            if not isinstance(m, dict):
                continue
            if m.get("role") != "assistant":
                continue
            if str(m.get("timeline") or "").strip() != str(timeline or "").strip():
                continue
            c = (m.get("content") or "").strip()
            if c:
                intro = c
                break

    if not intro:
        intro = "Eu já estava ali quando você chegou. Eu te vejo e espero sua atitude."

    return intro.strip()


def _inject_intro_visual_if_needed() -> None:
    """
    Injeta a intro visual somente se backend não tem histórico
    e chat_history está vazio.
    """
    if st.session_state.get("mary_intro_done", False):
        return

    if st.session_state.get("chat_history"):
        st.session_state["mary_intro_done"] = True
        return

    backend_hist = _carregar_chat_visual_do_backend(force=False)
    if backend_hist:
        st.session_state["chat_history"] = backend_hist
        st.session_state["mary_intro_done"] = True
        return

    tl = _timeline()
    intro = _get_intro_persona_text(tl)

    st.session_state["chat_history"] = [("assistant", intro)]
    st.session_state["mary_intro_done"] = True


def _boot_visual_if_empty() -> None:
    if st.session_state.get("chat_history"):
        st.session_state["mary_intro_done"] = True
        return

    backend_hist = _carregar_chat_visual_do_backend(force=False)
    if backend_hist:
        st.session_state["chat_history"] = backend_hist
        st.session_state["mary_intro_done"] = True
        return

    st.session_state["chat_history"] = []
    st.session_state["mary_intro_done"] = False
    _inject_intro_visual_if_needed()


def _auto_unlock_if_sem_interacao() -> None:
    """
    ✅ Resolve o teu caso: menu já abre travado na 'cumplice'.
    Se NÃO há nenhuma mensagem do usuário (nem no visual, nem no backend),
    destrava automaticamente para permitir escolher 'universitaria'.
    """
    if not st.session_state.get("mary_timeline_locked", False):
        return

    # se já teve user no visual, mantém travado
    hist = st.session_state.get("chat_history") or []
    if any(r == "user" for r, _ in hist):
        return

    # se existe user no backend, mantém travado
    try:
        docs = get_history_docs(_usuario_key_atual(), limit=3) or []
    except Exception:
        docs = []

    for d in docs:
        if (d.get("mensagem_usuario") or "").strip():
            return

    st.session_state["mary_timeline_locked"] = False


# ==========================================================
# APP
# ==========================================================
def main() -> None:
    _apply_dark_ui()
    _garantir_estado_inicial()
    _auto_unlock_if_sem_interacao()

    st.caption("🧩 mary_app.py v3.13 (service isolado por timeline + anti-vazamento hard + botão CANON virgem)")
    backend, detail = db_status()
    st.caption(f"🗄️ Backend atual: **{backend}** ({detail})")

    # ==========================================================
    # 🗄️ DEBUG — BANCO DE DADOS (db_status + ping_db)
    # ==========================================================
    with st.expander("🗄️ Banco de Dados — Debug (db_status + ping_db)", expanded=False):
        b_kind, b_detail = db_status()
        st.write("**db_status():**")
        st.code(f"{b_kind} — {b_detail}")

        colA, colB, colC = st.columns([1, 1, 1])
        with colA:
            run_ping = st.button("🔎 Rodar ping_db()", key="btn_run_ping_db")
        with colB:
            auto_ping = st.checkbox("Auto ping (a cada rerun)", value=False, key="chk_auto_ping_db")
        with colC:
            show_env = st.checkbox("Mostrar config (mascarada)", value=False, key="chk_show_db_env")

        if run_ping or auto_ping:
            backend, ok, info = ping_db()
            st.write("**ping_db():**")
            if ok:
                st.success(f"{backend} ✅ {info}")
            else:
                st.error(f"{backend} ❌ {info}")

        if show_env:
            try:
                from core.config import settings as _settings  # type: ignore

                uri = ""
                try:
                    uri = str(_settings.mongo_uri() or "")
                except Exception:
                    uri = ""

                def _mask_uri(u: str) -> str:
                    u = u.strip()
                    if not u:
                        return ""
                    u = re.sub(r"//([^:/@]+):([^@]+)@", r"//***:***@", u)
                    if "?" in u:
                        base, _q = u.split("?", 1)
                        return base + "?…"
                    return u

                dbname = (getattr(_settings, "MONGO_DB", "") or "").strip() or getattr(_settings, "APP_NAME", "app")
                st.write("**Config detectada:**")
                st.json(
                    {
                        "DB_BACKEND (settings/env)": (getattr(_settings, "DB_BACKEND", "") or ""),
                        "get_backend() (runtime)": get_backend(),
                        "mongo_uri() (mascarada)": _mask_uri(uri),
                        "MONGO_DB or APP_NAME": dbname,
                    }
                )
            except Exception as e:
                st.warning(f"Não consegui ler settings para debug: {type(e).__name__}: {e}")

    # ===== Header =====
    st.markdown(
        f"""
        <div class="rp-card">
          <div class="rp-title">Mary 💍💍</div>
          <div class="rp-sub">
            Timeline: <b>{_timeline()}</b> •
            Modelo: <b>{st.session_state.get('model','')}</b>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    personas = {
        "Mary – Esposa Cúmplice": "cumplice",
        "Mary – Universitária (linha alternativa)": "universitaria",
    }

    label_atual = next(
        (k for k, v in personas.items() if v == _timeline()),
        "Mary – Esposa Cúmplice",
    )

    st.selectbox(
        "🎭 Linha temporal da Mary",
        list(personas.keys()),
        index=list(personas.keys()).index(label_atual),
        disabled=False,
        key="persona_label",
        on_change=_on_timeline_change,
    )

    if st.session_state["mary_timeline_locked"]:
        st.caption("🔒 Persona travada após a 1ª mensagem do usuário.")
        st.caption("👉 Se travou sem você ter falado nada, use: Sidebar → 'Destravar timeline'.")

    keys = _keys_para_mary()

    # ==========================================================
    # ✅ PAINEL DEBUG RELATIONSHIP (MAIN AREA) — READ-ONLY
    # ==========================================================
    with st.expander("🧠 Relationship Engine — Painel de diagnóstico (turno a turno)", expanded=False):
        col1, col2 = st.columns([1, 1])

        with col1:
            enabled = bool(st.session_state.get("mary_debug_rel_panel", False))
            st.caption(
                "Ative em **Sidebar → Debug → Mostrar painel Relationship**  •  "
                f"Status: **{'ON' if enabled else 'OFF'}**"
            )
            st.caption("Fonte: st.session_state['mary_rel_meta_last'] (gravado pelo service.py após cada resposta).")

        with col2:
            if st.button("Limpar diagnóstico (só visual)", key="btn_clear_rel_diag_main"):
                st.session_state["mary_rel_meta_last"] = None
                st.success("Diagnóstico limpo.")

        last = st.session_state.get("mary_rel_meta_last")

        if not enabled:
            st.info("Painel desativado. Ative no sidebar para ver o diagnóstico a cada turno.")
        else:
            if not last:
                st.warning("Ainda não há diagnóstico. Envie uma mensagem e depois volte aqui.")
            else:
                cA, cB, cC, cD = st.columns(4)
                with cA:
                    st.metric("Timeline", str(last.get("timeline") or "—"))
                with cB:
                    st.metric("Stage", str(last.get("stage") or "—"))
                with cC:
                    st.metric("Mature turns", str(last.get("mature_turns") or 0))
                with cD:
                    hp = last.get("hazard_p")
                    st.metric("Hazard P", f"{hp:.2f}" if isinstance(hp, (int, float)) else "—")

                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Virginity", str(last.get("virginity") or "—"))
                with c2:
                    st.metric("Consummated", "true" if last.get("consummated") else "false")
                with c3:
                    st.metric("Virginity changed", "true" if last.get("virginity_changed") else "false")

                reason = (last.get("virginity_reason") or "").strip()
                if reason:
                    st.caption("Motivo (virginity_reason):")
                    st.code(reason)

                st.caption("Raw dump:")
                st.json(last)

    # ==========================================================
    # BACKEND RESET / DIAGNÓSTICO
    # ==========================================================
    with st.expander("🧨 BACKEND — apagar histórico de verdade + diagnóstico", expanded=False):
        st.write("Chaves usadas:", keys)

        if st.button("🔎 Diagnóstico agora", key="btn_diag_now"):
            st.json(_diagnostico_hist(keys))

        st.markdown("### Reset de capítulo / reset total")

        colX, colY = st.columns(2)
        with colX:
            if st.button("🧼 Reset capítulo (apagar history da timeline ativa)", key="btn_reset_chapter"):
                n = _reset_chapter_current_timeline()
                st.success(f"✅ Capítulo resetado. Apaguei {n} registros de history da timeline ativa.")
                st.rerun()

        with colY:
            confirm_total = st.checkbox(
                "Confirmo RESET TOTAL (history + opcional eventos + opcional memórias shared)",
                value=False,
                key="chk_confirm_total_reset",
            )
            delete_events = st.checkbox("Também apagar facts mary.evento.*", value=False, key="chk_total_del_events")
            delete_shared = st.checkbox(
                "Também apagar TODAS memórias permanentes (shared)", value=False, key="chk_total_del_shared"
            )

            if st.button("🔥 RESET TOTAL AGORA", type="primary", key="btn_total_reset_now"):
                if not confirm_total:
                    st.error("Marque a confirmação do RESET TOTAL.")
                else:
                    n_hist = _apagar_hist_bd_novo_e_legado()

                    n_evt = 0
                    if delete_events:
                        n_evt = _apagar_eventos_mary_fact(_usuario_key_atual())

                    n_mems = 0
                    if delete_shared:
                        try:
                            n_mems = int(delete_all_memories(_shared_key_atual()) or 0)
                        except Exception:
                            n_mems = 0
                        st.session_state["__mem_list"] = []

                    st.session_state["chat_history"] = []
                    st.session_state["mary_intro_done"] = False
                    st.session_state["mary_timeline_locked"] = False
                    st.session_state["mary_rel_meta_last"] = None
                    _invalidate_backend_cache()
                    _clear_mary_caches_all_related()
                    _kill_all_mary_services()

                    st.success(f"✅ RESET TOTAL concluído. history={n_hist} | eventos={n_evt} | mems_shared={n_mems}")
                    st.rerun()

    # ==========================================================
    # SIDEBAR
    # ==========================================================
    with st.sidebar:
        st.header("Mary – Controles")

        st.text_input(
            "👤 Usuário",
            value=st.session_state.get("user_id", "Janio Donisete"),
            disabled=True,
            key="inp_user_disabled",
        )
        st.caption(f"🧩 Timeline: {_timeline()}")
        st.caption(f"🔑 usuario_key atual: {_usuario_key_atual()}")

        # ✅ botão para resolver travamento sem apagar BD
        if st.session_state.get("mary_timeline_locked", False):
            if st.button("🔓 Destravar timeline (visual)", key="btn_unlock_timeline_visual"):
                st.session_state["mary_timeline_locked"] = False
                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                _invalidate_backend_cache()
                _clear_mary_caches_all_related(also_clear_other_timeline=True)
                _kill_all_mary_services()
                st.rerun()

        try:
            all_models = service_router.list_models() or []
        except Exception:
            all_models = []

        if not all_models:
            all_models = [FALLBACK_MODEL]

        if st.session_state.get("model") not in all_models:
            st.session_state["model"] = _choose_default_model(all_models)

        current = st.session_state.get("model")
        idx = all_models.index(current) if current in all_models else 0

        st.selectbox(
            "🧠 Modelo",
            all_models,
            index=idx,
            key="model",
        )

        st.markdown("---")
        # ✅ NSFW: persiste no facts quando muda (INLINE)
        nsfw_before = bool(st.session_state.get("mary_nsfw_on", False))
        st.checkbox("Modo adulto liberado (NSFW)", key="mary_nsfw_on")
        nsfw_after = bool(st.session_state.get("mary_nsfw_on", False))
        if nsfw_after != nsfw_before:
            _persist_nsfw_for_current_timeline_if_needed_inline()

        # ======================================================
        # ✅ BOTÃO "VIRGEM" (CANON) — gravar consumado
        # ======================================================
        st.markdown("---")
        st.subheader("🧬 Canon — Estado íntimo")

        uk_now = _usuario_key_atual()
        tl_now = _timeline()
        sk_now = _shared_key_atual()
        uid_now = str(st.session_state.get("user_id", "Janio Donisete"))

        try:
            facts_now = get_facts(uk_now) or {}
        except Exception:
            facts_now = {}

        rel_now = (
            facts_now.get(f"rel.state::{tl_now}")
            if isinstance(facts_now.get(f"rel.state::{tl_now}"), dict)
            else {}
        )
        is_consumado = bool(rel_now.get("consummated")) or (str(rel_now.get("virginity") or "") == "nao_virgem")

        label_btn = "✅ Virgem (marcar CONSUMADO)" if not is_consumado else "🔥 Consumado (manter)"

        if st.button(label_btn, key="btn_canon_virginity_consumado"):
            try:
                if not is_consumado:
                    _set_virginity_canon(
                        usuario_key=uk_now,
                        shared_key=sk_now,
                        timeline=tl_now,
                        user_id=uid_now,
                    )

                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                _invalidate_backend_cache()
                _clear_mary_caches_all_related(also_clear_other_timeline=True)
                _kill_all_mary_services()

                st.success("✅ CANON atualizado: Mary NÃO é mais virgem (consumado).")
                st.rerun()

            except Exception as e:
                st.error(f"Falha ao gravar CANON: {type(e).__name__}: {e}")

        st.caption("Obs.: Reset capítulo não apaga canon. Reset total com apagar memórias shared apaga.")

        st.markdown("---")
        st.subheader("🔍 Debug")

        st.session_state["mary_debug_rel_panel"] = st.checkbox(
            "Mostrar painel Relationship",
            value=bool(st.session_state.get("mary_debug_rel_panel", False)),
            key="mary_debug_rel_panel__ui",
        )

        if st.button("Ver último diagnóstico (popup)", key="btn_show_rel_diag_popup"):
            last = st.session_state.get("mary_rel_meta_last")
            if last:
                st.json(last)
            else:
                st.info("Ainda não existe mary_rel_meta_last.")

        st.markdown("---")
        st.subheader("Turnos")

        if st.button("Apagar último turno (backend)", key="btn_delete_last_turn"):
            ok = _delete_last_turn_active()
            if ok:
                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                st.success("✅ Último turno apagado (timeline ativa).")
            else:
                st.warning("Nada para apagar (backend não retornou sucesso).")
            st.rerun()

        st.markdown("---")
        st.subheader("Limpar tela")
        if st.button("Limpar tela (visual)", key="btn_clear_screen_visual"):
            st.session_state["chat_history"] = []
            st.rerun()

        st.markdown("---")
        st.subheader("🎭 Persona")
        st.caption("Arquivo ativo:")
        st.code(inspect.getfile(mary_persona.get_persona))
        st.caption("repositories.py ativo:")
        st.code(inspect.getfile(crep.delete_last_interaction))

        if st.button("🧾 Listar FACTS (usuario_key atual)", key="btn_list_facts_now"):
            uk = _usuario_key_atual()
            st.write("usuario_key:", uk)
            try:
                st.json(get_facts(uk) or {})
            except Exception as e:
                st.error(f"Falha ao ler facts: {type(e).__name__}: {e}")

        if st.button("♻️ Recarregar persona AGORA", key="btn_reload_persona"):
            importlib.reload(mary_persona)
            import characters.mary.service as mary_service
            import characters.mary.service_core as mary_service_core
            import characters.mary.service_cumplice as mary_service_cumplice
            import characters.mary.service_universitaria as mary_service_universitaria

            importlib.reload(mary_service_core)
            importlib.reload(mary_service_cumplice)
            importlib.reload(mary_service_universitaria)
            importlib.reload(mary_service)

            _kill_all_mary_services()
            st.session_state["mary_intro_done"] = False
            st.session_state["chat_history"] = []
            _invalidate_backend_cache()
            _clear_mary_caches_all_related()
            st.session_state["mary_timeline_locked"] = False
            st.session_state["mary_rel_meta_last"] = None
            st.success("Persona + Service recarregados. Contexto reinjetado.")
            st.rerun()

        # ======================================================
        # 🧠 MEMÓRIAS PERMANENTES (shared)
        # ======================================================
        st.markdown("---")
        st.subheader("🧠 Memórias permanentes (shared)")

        shared_key = _shared_key_atual()
        st.caption("Key compartilhada:")
        st.code(shared_key)

        if st.button("📜 Listar memórias", key="btn_list_mems"):
            st.session_state["__mem_list"] = list_memories(shared_key, limit=200) or []

        if st.button("🧽 Apagar última memória", key="btn_delete_last_mem"):
            ok = delete_last_memory(shared_key)
            st.success("✅ Última memória apagada." if ok else "Nada para apagar.")
            st.session_state["__mem_list"] = list_memories(shared_key, limit=200) or []
            _clear_mary_caches_all_related()
            st.rerun()

        if st.button("💣 Apagar TODAS as memórias", key="btn_delete_all_mems"):
            n = delete_all_memories(shared_key)
            st.success(f"✅ Apaguei {n} memórias.")
            st.session_state["__mem_list"] = []
            _clear_mary_caches_all_related()
            st.rerun()

        mems_view = st.session_state.get("__mem_list")
        if mems_view is not None:
            st.json(mems_view)

        # ======================================================
        # 🗃️ LONG MEMORY (DB) — 1 doc por memória + Text Search
        # ======================================================
        st.markdown("---")
        st.subheader("🗃️ Long Memory (DB) — Text Search")

        lm_userkey = _shared_key_atual()
        st.caption("Key usada na Long Memory:")
        st.code(lm_userkey)

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("🧱 Criar índices Long Memory (Mongo)", key="btn_lm_indexes"):
                try:
                    ensure_long_memory_indexes()
                    st.success("✅ Índices da long_memory garantidos (se backend=mongo).")
                except Exception as e:
                    st.error(f"Falha ao criar índices: {type(e).__name__}: {e}")

        with col2:
            if st.button("📚 Listar últimas 50 (DB)", key="btn_lm_list"):
                try:
                    st.session_state["__lm_list"] = list_long_memory(lm_userkey, limit=50) or []
                except Exception as e:
                    st.error(f"Falha ao listar: {type(e).__name__}: {e}")
                    st.session_state["__lm_list"] = []

        col3, col4 = st.columns(2)

        with col3:
            if st.button("🧽 Apagar última (DB)", key="btn_lm_delete_last"):
                try:
                    ok = delete_last_long_memory(lm_userkey)
                    if ok:
                        st.success("✅ Última memória (DB) apagada.")
                    else:
                        st.info("Nada para apagar (DB).")
                    st.session_state["__lm_list"] = list_long_memory(lm_userkey, limit=50) or []
                except Exception as e:
                    st.error(f"Falha ao apagar última (DB): {type(e).__name__}: {e}")
                st.rerun()

        with col4:
            confirm_all = st.checkbox("Confirmo apagar TODAS (DB)", key="lm_confirm_delete_all")
            if st.button("💣 Apagar TODAS (DB)", key="btn_lm_delete_all", disabled=not confirm_all):
                try:
                    n = delete_all_long_memory(lm_userkey)
                    st.success(f"✅ Apaguei {n} memórias (DB).")
                    st.session_state["__lm_list"] = []
                    st.session_state["__lm_search"] = []
                    st.session_state["lm_confirm_delete_all"] = False
                except Exception as e:
                    st.error(f"Falha ao apagar todas (DB): {type(e).__name__}: {e}")
                st.rerun()

        st.markdown("### ➕ Inserir memória (DB)")
        lm_text = st.text_area("Texto da memória", key="lm_text_area", height=90, placeholder="Ex: Mary odeia amendoim #500...")
        lm_title = st.text_input("Título (opcional)", key="lm_title_inp", value="")
        lm_kind = st.text_input("kind (opcional)", key="lm_kind_inp", value="memory")

        if st.button("💾 Salvar na long_memory", key="btn_lm_save"):
            try:
                meta = {
                    "kind": (lm_kind or "memory").strip(),
                    "title": (lm_title or "").strip(),
                    "timeline_at_save": _timeline(),
                    "user_id": str(st.session_state.get("user_id", "Janio Donisete")),
                    "source": "ui_long_memory",
                }
                doc = append_long_memory(lm_userkey, lm_text, meta=meta)
                st.success(f"✅ Gravado: id={doc.get('id')} ts={doc.get('ts')}")
            except Exception as e:
                st.error(f"Falha ao gravar: {type(e).__name__}: {e}")

        st.markdown("### 🔎 Buscar (Mongo $text)")
        q = st.text_input("Consulta", key="lm_q_inp", value="", placeholder="Ex: amendoim 500")
        lim = st.slider("Limite de resultados", min_value=5, max_value=50, value=20, step=5, key="lm_lim_slider")

        if st.button("🔍 Buscar agora", key="btn_lm_search"):
            try:
                st.session_state["__lm_search"] = search_long_memory_text(lm_userkey, q, limit=int(lim)) or []
            except Exception as e:
                st.error(f"Falha na busca: {type(e).__name__}: {e}")
                st.session_state["__lm_search"] = []

        if st.session_state.get("__lm_search") is not None:
            st.caption("Resultados da busca:")
            st.json(st.session_state.get("__lm_search") or [])

        if st.session_state.get("__lm_list") is not None:
            st.caption("Últimas memórias (DB):")
            st.json(st.session_state.get("__lm_list") or [])

    # ===== BOOT =====
    _boot_visual_if_empty()

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

    shown_msgs = len(visible)
    total_msgs = len(hist)
    shown_interactions = sum(1 for r, _ in visible if r == "user")
    total_interactions = sum(1 for r, _ in hist if r == "user")
    st.caption(
        f"📌 Mostrando {shown_interactions} interações ({shown_msgs} mensagens) — "
        f"Total no capítulo: {total_interactions} interações ({total_msgs} mensagens)."
    )

    # ===== INPUT =====
    prompt = st.chat_input("Fala algo pra Mary... (Shift+Enter quebra linha)")
    if prompt:
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

        svc = _get_service()
        tl_active = _timeline()
        nsfw_active = bool(st.session_state.get("mary_nsfw_on", False))

        try:
            resposta = svc.reply(
                user=st.session_state.get("user_id", "Janio Donisete"),
                model=st.session_state.get("model") or DEFAULT_MODEL,
                prompt=prompt,
                timeline=tl_active,
                nsfw=nsfw_active,
            )
        except Exception as e:
            st.error(f"💥 Erro real ao chamar o modelo: {type(e).__name__}: {e}")
            st.code(traceback.format_exc())
            st.stop()

        if not (resposta or "").strip():
            st.warning("⚠️ O modelo retornou vazio.")
            st.stop()

        with st.chat_message("assistant"):
            st.markdown(_format_paragraphs(resposta))

        st.session_state["chat_history"].append(("assistant", resposta))
        _invalidate_backend_cache()
        st.rerun()


if __name__ == "__main__":
    main()
