from __future__ import annotations
# pages/mary_app.py

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
import httpx
import core.service_router as service_router

# ==========================================================
# 🔥 HARD RESET NO BOOT (ANTI-VAZAMENTO ENTRE TIMELINES)
# + MIGRAÇÃO: limpar schema quebrado de mary.intro.fixed
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
        # também remove a seleção visual (será recalculada pela timeline)
        st.session_state.pop("persona_label", None)

        # limpa telemetria do modelo real (se existir)
        st.session_state.pop("mary_last_used_model", None)
        st.session_state.pop("mary_last_used_provider", None)

        st.session_state["mary_last_boot_timeline"] = current_tl


def _cleanup_broken_facts_schema_on_boot() -> None:
    """
    MIGRAÇÃO DEFINITIVA (BOOT-SAFE):
    - remove mary.intro.fixed (string antiga)
    - remove mary.intro.fixed.<timeline> (schema híbrido)
    - remove virgindade global conflitante (apenas universitaria)
    """
    try:
        tl = str(st.session_state.get("mary_timeline") or "cumplice").strip()
        user = str(st.session_state.get("user_id") or "Janio Donisete").strip()
        usuario_key = f"{user}::mary::{tl}"

        from core.repositories import delete_fact

        # --- limpar intro FIXO (2 schemas) ---
        delete_fact(usuario_key, "mary.intro.fixed")
        if tl:
            delete_fact(usuario_key, f"mary.intro.fixed.{tl}")

        # --- limpar conflito de virgindade (universitaria) ---
        if tl == "universitaria":
            delete_fact(usuario_key, "virginity")

    except Exception:
        pass


# ⚠️ EXECUTA IMEDIATAMENTE NO BOOT
_hard_reset_on_boot_if_needed()
_cleanup_broken_facts_schema_on_boot()

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
    append_memory,
    delete_fact,
    delete_last_interaction,
    delete_user_history,
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

# ✅ TROCA AQUI (como você pediu)
DEFAULT_MODEL = "tngtech/deepseek-r1t2-chimera:free"
FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324"

# ✅ MODELO ANTIGO (para migração automática de sessão)
OLD_DEFAULT_MODEL = "tngtech/tng-r1t-chimera:free"


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

        .block-container {
            max-width: 980px !important;
            padding-top: 1rem !important;
            padding-bottom: 9rem !important;
        }

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

        div[data-testid="stChatInput"]{
          position: fixed !important;
          left: 0 !important;
          right: 0 !important;
          bottom: 0 !important;
          z-index: 9999 !important;
          background: rgba(11,11,11,0.88) !important;
          backdrop-filter: blur(10px) !important;
          border-top: 1px solid rgba(255,255,255,0.10) !important;
          padding: 10px 0 !important;
          width: 100% !important;
        }

        div[data-testid="stChatInput"] > div{
          width: 100% !important;
          max-width: 980px !important;
          margin: 0 auto !important;
          padding: 0 1rem !important;
          box-sizing: border-box !important;
        }

        div[data-testid="stChatInput"] form{
          width: 100% !important;
          display: flex !important;
          gap: 10px !important;
          align-items: flex-end !important;
          box-sizing: border-box !important;
        }

        div[data-testid="stChatInput"] form > div:first-child{
          flex: 1 1 auto !important;
          width: 100% !important;
          min-width: 0 !important;
        }

        div[data-testid="stChatInput"] form > div:last-child{
          flex: 0 0 auto !important;
          width: auto !important;
          min-width: 0 !important;
        }

        div[data-testid="stChatInput"] textarea{
          width: 100% !important;
          min-height: 96px !important;
          max-height: 240px !important;
          border-radius: 14px !important;
          background: #101010 !important;
          color: #f2f2f2 !important;
          border: 1px solid rgba(255,255,255,0.14) !important;
          box-sizing: border-box !important;
        }

        div[data-testid="stChatInput"] button{
          flex: 0 0 auto !important;
        }

        @media (max-width: 768px) {
            div[data-testid="stChatInput"] {
                bottom: calc(env(safe-area-inset-bottom, 0px) + 58px) !important;
            }
            .block-container {
                padding-bottom: 13rem !important;
            }
            div[data-testid="stChatInput"] textarea {
                padding-right: 96px !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _apply_dark_ui_once() -> None:
    if st.session_state.get("_dark_ui_applied", False):
        return
    _apply_dark_ui()
    st.session_state["_dark_ui_applied"] = True


def _strip_persona_echo_if_any(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t

    markers = ["⟦MARY⟧", "RESPOSTA DA MARY:", "Resposta da Mary:"]
    for mk in markers:
        if mk in t:
            tail = t.split(mk, 1)[-1].strip()
            if tail:
                return tail

    bad_starts = ("PERSONA (SYSTEM)", "### PERSONA", "INSTRUÇÕES INTERNAS", "MENSAGEM DO USUÁRIO:")
    if any(t.startswith(b) for b in bad_starts):
        return ""
    return t


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

    _apply_dark_ui_once()
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
    return [_usuario_key_atual()]


# ==========================================================
# ✅ CANON BUTTON HELPERS (Virgem -> Consumado)
# ==========================================================
def _today_iso() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _set_virginity_canon(*, usuario_key: str, shared_key: str, timeline: str, user_id: str) -> None:
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

    append_memory(shared_key, canon_text, meta=meta)

    facts = get_facts(usuario_key) or {}
    rel_key = f"rel.state::{timeline}"
    rel = facts.get(rel_key) if isinstance(facts.get(rel_key), dict) else {}
    if not isinstance(rel, dict):
        rel = {}

    rel["consummated"] = True
    rel["virginity"] = "nao_virgem"
    rel["allows_penetration"] = True

    set_fact(usuario_key, rel_key, rel, {"fonte": "ui_button_canon"})
    set_fact(usuario_key, "mary.virginity", "nao_virgem", {"fonte": "ui_button_canon"})


# ==========================================================
# ✅ SYNC DEFINITIVO: virgindade GLOBAL <-> TIMELINE  (Modelo B)
# ==========================================================
def _sync_virginity_global_timeline(*, usuario_key: str, timeline: str) -> dict:
    notes: list[str] = []
    changed = False

    from core.repositories import get_facts, set_fact, delete_fact

    tl = str(timeline or "").strip() or "cumplice"
    uk = str(usuario_key or "").strip()
    if not uk:
        return {"changed": False, "notes": ["usuario_key vazio"]}

    facts = get_facts(uk) or {}
    if not isinstance(facts, dict):
        facts = {}

    g_key = "mary.virginity"
    g_before = (facts.get(g_key) if isinstance(facts.get(g_key), str) else None)
    g_before = (g_before or "").strip().lower() or None

    def _norm(v: str | None) -> str | None:
        v = (v or "").strip().lower()
        if not v:
            return None
        if v in ("virgem", "nao_virgem"):
            return v
        if v in ("não_virgem", "naovirgem", "nao virgem", "não virgem"):
            return "nao_virgem"
        return None

    g_before = _norm(g_before)

    rel_key = f"rel.state::{tl}"
    rel_obj = facts.get(rel_key)
    rel = rel_obj if isinstance(rel_obj, dict) else {}
    if not isinstance(rel, dict):
        rel = {}

    rel_before = {
        "virginity": _norm(rel.get("virginity") if isinstance(rel.get("virginity"), str) else None),
        "consummated": bool(rel.get("consummated")) if rel.get("consummated") is not None else None,
        "allows_penetration": bool(rel.get("allows_penetration")) if rel.get("allows_penetration") is not None else None,
    }

    g_after = g_before

    if g_after is None:
        g_after = "virgem"
        notes.append("GLOBAL ausente => inicializado como 'virgem'")
        changed = True
        try:
            set_fact(uk, g_key, g_after, {"fonte": "virginity_sync_init"})
        except Exception:
            pass

    rel_after = dict(rel)

    if g_after == "nao_virgem":
        if rel_before["virginity"] != "nao_virgem":
            rel_after["virginity"] = "nao_virgem"
            changed = True
            notes.append("GLOBAL='nao_virgem' => forçando REL.virginity='nao_virgem'")
        if rel.get("consummated") is not True:
            rel_after["consummated"] = True
            changed = True
        if rel.get("allows_penetration") is not True:
            rel_after["allows_penetration"] = True
            changed = True

    if g_after == "virgem":
        if tl == "universitaria":
            if rel_before["virginity"] != "virgem":
                rel_after["virginity"] = "virgem"
                changed = True
                notes.append("Universitária + GLOBAL='virgem' => REL.virginity='virgem'")
            if rel.get("consummated") not in (False, None):
                rel_after["consummated"] = False
                changed = True
            if rel.get("allows_penetration") not in (False, None):
                rel_after["allows_penetration"] = False
                changed = True
        else:
            if rel_before["virginity"] is None:
                rel_after["virginity"] = "virgem"
                changed = True
                notes.append(f"{tl} + GLOBAL='virgem' => REL.virginity ausente, setado 'virgem'")

    rel_v = _norm(rel_after.get("virginity") if isinstance(rel_after.get("virginity"), str) else None)
    if rel_v == "nao_virgem" and g_after != "nao_virgem":
        g_after = "nao_virgem"
        changed = True
        notes.append("REL indica 'nao_virgem' enquanto GLOBAL não => promovendo GLOBAL='nao_virgem'")
        try:
            set_fact(uk, g_key, "nao_virgem", {"fonte": "virginity_sync_promote_global"})
        except Exception:
            pass

    if rel_after != rel:
        try:
            set_fact(uk, rel_key, rel_after, {"fonte": "virginity_sync_rel"})
        except Exception:
            pass

    try:
        if "virginity" in facts and tl == "universitaria":
            delete_fact(uk, "virginity")
            notes.append("Removido legado facts['virginity'] (conflito antigo)")
            changed = True
    except Exception:
        pass

    rel_after_summary = {
        "virginity": _norm(rel_after.get("virginity") if isinstance(rel_after.get("virginity"), str) else None),
        "consummated": bool(rel_after.get("consummated")) if rel_after.get("consummated") is not None else None,
        "allows_penetration": bool(rel_after.get("allows_penetration")) if rel_after.get("allows_penetration") is not None else None,
    }

    return {
        "changed": bool(changed),
        "notes": notes,
        "global_before": g_before,
        "global_after": g_after,
        "rel_before": rel_before,
        "rel_after": rel_after_summary,
        "usuario_key": uk,
        "timeline": tl,
    }


# ==========================================================
# ✅ PERSONA DEBUG + FALLBACK INJECTION (quando service não injeta)
# ==========================================================
def _flatten_boot_messages(boot: Any, timeline: str) -> str:
    if not isinstance(boot, list):
        return ""

    parts: list[str] = []
    for m in boot:
        if not isinstance(m, dict):
            continue
        if (m.get("role") or "") not in ("system", "assistant", "user"):
            continue
        tl = str(m.get("timeline") or "").strip()
        if tl and tl != str(timeline or "").strip():
            continue
        c = (m.get("content") or "").strip()
        if not c:
            continue
        parts.append(c)

    out = "\n\n".join(parts).strip()
    if len(out) > 2400:
        out = out[:2400].rstrip() + "\n\n[…boot truncado…]"
    return out


def _get_persona_bundle(timeline: str) -> tuple[str, Any]:
    try:
        system_text, boot = mary_persona.get_persona(timeline)
    except Exception:
        system_text, boot = "", None
    return (str(system_text or "").strip(), boot)


def _build_prompt_with_persona_fallback(*, prompt: str, timeline: str) -> str:
    system_text, boot = _get_persona_bundle(timeline)
    boot_txt = _flatten_boot_messages(boot, timeline)

    if not system_text and not boot_txt:
        return prompt

    return (
        "⟦SYS⟧\n"
        f"{system_text}\n\n"
        "⟦BOOT⟧\n"
        f"{boot_txt}\n\n"
        "⟦RULE⟧ Responda APENAS como Mary. Não repita nada acima.\n\n"
        "⟦USER⟧\n"
        f"{prompt}\n"
        "⟦MARY⟧"
    )


# ==========================================================
# HELPERS
# ==========================================================
def _service_key_for_userkey(userkey: str) -> str:
    return f"_mary_service::{userkey}"


def _render_relationship_debug_panel() -> None:
    st.markdown("---")
    st.subheader("🔍 Relationship Engine — Debug")

    try:
        tl = _timeline()
        uk = _usuario_key_atual()

        facts = get_facts(uk) or {}
        if not isinstance(facts, dict):
            facts = {}

        rel = facts.get(f"rel.state::{tl}")

        if not isinstance(rel, dict):
            rel_block = facts.get("rel")
            if isinstance(rel_block, dict):
                rel = rel_block.get(f"state::{tl}")

        if not isinstance(rel, dict):
            rel = {}

        st.json(
            {
                "timeline": tl,
                "usuario_key": uk,
                "rel_state": rel,
                "nsfw": bool(st.session_state.get("mary_nsfw_on", False)),
                "third_party": bool(st.session_state.get("mary_allow_third_party_seduction", False)),
                "debug_rel_keys_found": [k for k in facts.keys() if str(k).startswith("rel")][:30],
            }
        )
    except Exception as e:
        st.error(f"Falha ao renderizar painel Relationship: {type(e).__name__}: {e}")


def _instantiate_mary_service(*, userkey: str, timeline: str):
    cls = get_service_class(timeline)

    try:
        sig = inspect.signature(cls.__init__)
        params = set(sig.parameters.keys())
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
        try:
            return cls()
        except Exception:
            try:
                return cls(userkey)  # type: ignore[misc]
            except Exception:
                return cls()  # type: ignore[misc]


def _get_service():
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
    if "mary_timeline" not in st.session_state:
        st.session_state["mary_timeline"] = "cumplice"
    if "mary_timeline_locked" not in st.session_state:
        st.session_state["mary_timeline_locked"] = False

    if "user_id" not in st.session_state or not st.session_state["user_id"]:
        st.session_state["user_id"] = "Janio Donisete"

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    if st.session_state.get("mary_timeline_locked") and not st.session_state.get("chat_history"):
        st.session_state["mary_timeline_locked"] = False

    if "backend_hist_cache_key" not in st.session_state:
        st.session_state["backend_hist_cache_key"] = ""

    if "mary_debug_rel_panel" not in st.session_state:
        st.session_state["mary_debug_rel_panel"] = False
    if "mary_rel_meta_last" not in st.session_state:
        st.session_state["mary_rel_meta_last"] = None

    try:
        modelos = service_router.list_models() or []
    except Exception:
        modelos = []

    # ✅ MIGRAÇÃO: se sessão está presa no modelo antigo, troca para o novo
    if str(st.session_state.get("model") or "").strip() == OLD_DEFAULT_MODEL:
        st.session_state["model"] = DEFAULT_MODEL

    if "model" not in st.session_state or not st.session_state["model"]:
        st.session_state["model"] = _choose_default_model(modelos)
    else:
        if modelos and st.session_state["model"] not in modelos:
            st.session_state["model"] = _choose_default_model(modelos)

    if "mary_nsfw_on" not in st.session_state:
        st.session_state["mary_nsfw_on"] = (_timeline() != "universitaria")

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

    if "last_submit_ts" not in st.session_state:
        st.session_state["last_submit_ts"] = 0.0
    if "last_submit_text" not in st.session_state:
        st.session_state["last_submit_text"] = ""

    if "__mem_list" not in st.session_state:
        st.session_state["__mem_list"] = None

    # ✅ fallback injection toggle (para provar persona)
    for tl in ("cumplice", "universitaria"):
        k = f"mary_ui_persona_fallback::{tl}"
        if k not in st.session_state:
            st.session_state[k] = False

    # ✅ telemetria do modelo real (fora do loop!)
    if "mary_last_used_model" not in st.session_state:
        st.session_state["mary_last_used_model"] = None
    if "mary_last_used_provider" not in st.session_state:
        st.session_state["mary_last_used_provider"] = None


def _clear_service_caches_for_keys(keys: list[str]) -> None:
    for k in keys:
        fk = f"facts::{k}"
        if fk in st.session_state:
            del st.session_state[fk]

        prefix_hist = f"history::{k}::"
        for sk in list(st.session_state.keys()):
            if isinstance(sk, str) and sk.startswith(prefix_hist):
                st.session_state.pop(sk, None)

        prefix_mem = f"mem::{k}::"
        for sk in list(st.session_state.keys()):
            if isinstance(sk, str) and sk.startswith(prefix_mem):
                st.session_state.pop(sk, None)


def _reset_intro_flags_for_keys(keys: list[str]) -> None:
    for k in keys:
        st.session_state.pop(f"intro_ctx_injected::{k}", None)
        st.session_state.pop(f"intro_injected::{k}", None)


def _clear_mary_caches_all_related(*, also_clear_other_timeline: bool = True) -> None:
    uk = _usuario_key_atual()
    sk = _shared_key_atual()

    keys = [uk, sk]

    if also_clear_other_timeline:
        other = "universitaria" if _timeline() == "cumplice" else "cumplice"
        keys.append(_usuario_key_for_timeline(other))

    _clear_service_caches_for_keys(keys)
    _reset_intro_flags_for_keys(keys)


def _persist_nsfw_for_current_timeline_if_needed_inline() -> None:
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

    st.session_state["mary_last_used_model"] = None
    st.session_state["mary_last_used_provider"] = None
    return n


def _on_timeline_change() -> None:
    personas = {
        "Mary – Esposa Cúmplice": "cumplice",
        "Mary – Universitária (linha alternativa)": "universitaria",
    }

    old_tl = str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"
    new_tl = personas.get(st.session_state.get("persona_label") or "", "cumplice")

    st.session_state["mary_timeline"] = new_tl

    # ✅ Sync virgindade (GLOBAL <-> timeline) ao trocar timeline
    try:
        res = _sync_virginity_global_timeline(usuario_key=_usuario_key_atual(), timeline=new_tl)
        st.session_state["mary_virginity_sync_last"] = res
    except Exception:
        pass

    st.session_state["mary_nsfw_on"] = (new_tl != "universitaria")
    _persist_nsfw_for_current_timeline_if_needed_inline()

    st.session_state["chat_history"] = []
    st.session_state["mary_intro_done"] = False
    _invalidate_backend_cache()
    _clear_mary_caches_all_related(also_clear_other_timeline=True)
    _clear_service_caches_for_keys([_usuario_key_for_timeline(old_tl), _usuario_key_for_timeline(new_tl)])

    st.session_state["mary_last_used_model"] = None
    st.session_state["mary_last_used_provider"] = None

    _kill_all_mary_services()


def _get_intro_persona_text(timeline: str) -> str:
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
            tl = str(m.get("timeline") or "").strip()
            if tl and tl != str(timeline or "").strip():
                continue
            c = (m.get("content") or "").strip()
            if c:
                intro = c
                break

    if not intro:
        intro = "Eu já estava ali quando você chegou. Eu te vejo e espero sua atitude."

    return intro.strip()


def _inject_intro_visual_if_needed() -> None:
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
    if bool(st.session_state.get("mary_intro_done", False)):
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
    if not st.session_state.get("mary_timeline_locked", False):
        return

    hist = st.session_state.get("chat_history") or []
    if any(r == "user" for r, _ in hist):
        return

    try:
        docs = get_history_docs(_usuario_key_atual(), limit=3) or []
    except Exception:
        docs = []

    for d in docs:
        if (d.get("mensagem_usuario") or "").strip():
            return

    st.session_state["mary_timeline_locked"] = False


def _extract_router_text(resp: Any) -> str:
    if resp is None:
        return ""

    if isinstance(resp, tuple) and resp:
        return _extract_router_text(resp[0])

    if isinstance(resp, str):
        return resp.strip()

    if isinstance(resp, dict):
        try:
            choices = resp.get("choices") or []
            c0 = (choices[0] if isinstance(choices, list) and choices else {}) or {}
            msg = c0.get("message") or {}

            txt = msg.get("content")
            if isinstance(txt, str) and txt.strip():
                return txt.strip()

            if isinstance(txt, list):
                parts = []
                for p in txt:
                    if isinstance(p, dict):
                        t = p.get("text")
                        if isinstance(t, str) and t.strip():
                            parts.append(t.strip())
                    elif isinstance(p, str) and p.strip():
                        parts.append(p.strip())
                if parts:
                    return "\n".join(parts).strip()

            r = msg.get("reasoning")
            if isinstance(r, str) and r.strip():
                return r.strip()

            txt2 = c0.get("text")
            if isinstance(txt2, str) and txt2.strip():
                return txt2.strip()

            return ""
        except Exception:
            return ""

    return str(resp).strip()


def _extract_router_used_model_provider(resp: Any) -> tuple[str | None, str | None]:
    if isinstance(resp, tuple):
        used_model: str | None = None
        provider: str | None = None

        if len(resp) >= 3:
            used_model = resp[1].strip() if isinstance(resp[1], str) and resp[1].strip() else None
            provider = resp[2].strip() if isinstance(resp[2], str) and resp[2].strip() else None
            return (provider, used_model)

        for item in resp:
            if isinstance(item, str) and item.strip():
                low = item.strip().lower()
                if low in ("openrouter", "together", "huggingface"):
                    provider = item.strip()
                else:
                    used_model = used_model or item.strip()

        return (provider, used_model)

    if not isinstance(resp, dict):
        return (None, None)

    provider_keys = ["provider", "used_provider", "provider_used", "last_used_provider"]
    model_keys = ["used_model", "resolved_model", "model_used", "last_used_model", "model"]

    provider: str | None = None
    model: str | None = None

    for k in provider_keys:
        v = resp.get(k)
        if isinstance(v, str) and v.strip():
            provider = v.strip()
            break

    for k in model_keys:
        v = resp.get(k)
        if isinstance(v, str) and v.strip():
            model = v.strip()
            break

    meta = resp.get("meta")
    if isinstance(meta, dict):
        if provider is None:
            v = meta.get("provider") or meta.get("used_provider") or meta.get("provider_used")
            if isinstance(v, str) and v.strip():
                provider = v.strip()
        if model is None:
            v = meta.get("used_model") or meta.get("resolved_model") or meta.get("model") or meta.get("model_used")
            if isinstance(v, str) and v.strip():
                model = v.strip()

    dbg = resp.get("debug")
    if isinstance(dbg, dict):
        if provider is None:
            v = dbg.get("provider") or dbg.get("used_provider") or dbg.get("provider_used")
            if isinstance(v, str) and v.strip():
                provider = v.strip()
        if model is None:
            v = dbg.get("used_model") or dbg.get("resolved_model") or dbg.get("model") or dbg.get("model_used")
            if isinstance(v, str) and v.strip():
                model = v.strip()

    return (provider, model)


def _summarize_raw(resp: Any) -> dict[str, Any]:
    info: dict[str, Any] = {"raw_type": type(resp).__name__}

    if isinstance(resp, tuple):
        info["tuple_len"] = len(resp)
        try:
            info["tuple_0_type"] = type(resp[0]).__name__ if len(resp) > 0 else None
            info["tuple_used_model"] = resp[1] if len(resp) > 1 else None
            info["tuple_provider"] = resp[2] if len(resp) > 2 else None
        except Exception:
            pass

        data = resp[0] if len(resp) > 0 else None
        info["data_preview"] = _summarize_raw(data)
        return info

    if isinstance(resp, dict):
        info["keys"] = list(resp.keys())[:40]

        def _pick_str(d: dict | None, *keys: str) -> str | None:
            if not isinstance(d, dict):
                return None
            for k in keys:
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return None

        provider_root = _pick_str(resp, "provider", "used_provider", "provider_used", "last_used_provider")
        model_root = _pick_str(resp, "used_model", "resolved_model", "model_used", "last_used_model", "model")

        meta = resp.get("meta") if isinstance(resp.get("meta"), dict) else None
        debug = resp.get("debug") if isinstance(resp.get("debug"), dict) else None

        provider_meta = _pick_str(meta, "provider", "used_provider", "provider_used")
        model_meta = _pick_str(meta, "used_model", "resolved_model", "model", "model_used")

        provider_dbg = _pick_str(debug, "provider", "used_provider", "provider_used")
        model_dbg = _pick_str(debug, "used_model", "resolved_model", "model", "model_used")

        info["provider"] = provider_root or provider_meta or provider_dbg
        info["used_model"] = model_root or model_meta or model_dbg
        info["has_meta"] = bool(meta)
        info["has_debug"] = bool(debug)

        choices = resp.get("choices")
        info["choices_type"] = type(choices).__name__
        try:
            if isinstance(choices, list) and choices:
                c0 = choices[0] or {}
                msg = c0.get("message") or {}

                info["c0_keys"] = list(c0.keys())[:40]
                info["msg_keys"] = list(msg.keys())[:40] if isinstance(msg, dict) else None

                ct = msg.get("content") if isinstance(msg, dict) else None
                info["content_type"] = type(ct).__name__

                if isinstance(ct, str) and ct.strip():
                    info["content_preview"] = ct[:500]
                elif isinstance(ct, list):
                    parts: list[str] = []
                    for p in ct:
                        if isinstance(p, dict):
                            t = p.get("text")
                            if isinstance(t, str) and t.strip():
                                parts.append(t.strip())
                        elif isinstance(p, str) and p.strip():
                            parts.append(p.strip())
                    if parts:
                        info["content_preview"] = "\n".join(parts)[:500]

                txt2 = c0.get("text")
                if isinstance(txt2, str) and txt2.strip() and not info.get("content_preview"):
                    info["text_preview"] = txt2[:500]

                if isinstance(msg, dict):
                    r = msg.get("reasoning")
                    if isinstance(r, str) and r.strip():
                        info["reasoning_preview"] = r[:500]
            else:
                info["choices_len"] = len(choices) if isinstance(choices, list) else None
        except Exception as e:
            info["parse_error"] = f"{type(e).__name__}: {e}"

        return info

    if isinstance(resp, str):
        info["text_preview"] = resp[:500]
        info["text_len"] = len(resp)
        return info

    try:
        s = repr(resp)
        info["repr_preview"] = s[:500]
    except Exception:
        pass
    return info


def _router_ping_once(user: str, model: str) -> dict:
    def _safe_extract_text(data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        try:
            choices = data.get("choices") or []
            if not isinstance(choices, list) or not choices:
                return ""
            c0 = choices[0] or {}
            msg = c0.get("message") or {}
            ct = msg.get("content")

            if isinstance(ct, str):
                return ct

            if isinstance(ct, list):
                parts: list[str] = []
                for item in ct:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        t = item.get("text")
                        if isinstance(t, str):
                            parts.append(t)
                return "\n".join([p for p in parts if p])

            txt2 = c0.get("text")
            return txt2 if isinstance(txt2, str) else ""
        except Exception:
            return ""

    def _do_call(msgs: list[dict[str, str]]) -> tuple[Any, str | None, str | None, str]:
        raw = service_router.chat(
            model=str(model or "").strip(),
            messages=msgs,
            max_tokens=12,
            temperature=0.0,
            top_p=1.0,
            extra={"stop": ["\n"]},
        )

        data = raw
        used_model = None
        used_provider = None

        if isinstance(raw, tuple) and len(raw) >= 1:
            data = raw[0]
            if len(raw) >= 2 and isinstance(raw[1], str):
                used_model = raw[1].strip() or None
            if len(raw) >= 3 and isinstance(raw[2], str):
                used_provider = raw[2].strip() or None

        txt = _safe_extract_text(data)

        if not used_provider:
            try:
                if hasattr(service_router, "_provider_for"):
                    used_provider = service_router._provider_for(str(model or "").strip())
            except Exception:
                used_provider = None

        return raw, used_model, used_provider, txt

    prompt = "Responda APENAS com a palavra: PONG"
    msgs1 = [{"role": "user", "content": prompt}]

    msgs2 = [
        {"role": "system", "content": "Responda somente com 'PONG'. Nenhuma outra palavra, número ou pontuação."},
        {"role": "user", "content": "PONG"},
    ]

    try:
        raw, used_model, used_provider, txt = _do_call(msgs1)
        pong_ok = "PONG" in (txt or "").upper()

        if not pong_ok:
            raw2, used_model2, used_provider2, txt2 = _do_call(msgs2)
            if (txt2 or "").strip():
                raw, used_model, used_provider, txt = raw2, used_model2, used_provider2, txt2
            pong_ok = "PONG" in (txt or "").upper()

        try:
            st.session_state["mary_ping_raw_summary"] = _summarize_raw(raw)
        except Exception:
            st.session_state["mary_ping_raw_summary"] = {"raw_type": type(raw).__name__}

        ok_transport = True
        ok_route = bool((used_provider or "").strip()) and bool((used_model or "").strip())

        return {
            "ok": bool(ok_transport and ok_route),
            "pong_ok": bool(pong_ok),
            "status": 200,
            "ui_model": model,
            "used_model": used_model,
            "used_provider": used_provider,
            "text": (txt or "")[:600],
            "raw_type": type(raw).__name__,
        }

    except Exception as e:
        err_txt = f"{type(e).__name__}: {e}"
        st.session_state["mary_ping_last_error"] = err_txt
        return {"ok": False, "status": None, "error": err_txt, "ui_model": model}


def _call_service_reply_safe(
    *,
    svc: Any,
    user: str,
    model: str,
    prompt: str,
    timeline: str,
    nsfw: bool | None,
    allow_third_party_seduction: bool | None = None,
) -> str:
    fb_key = f"mary_ui_persona_fallback::{timeline}"
    if bool(st.session_state.get(fb_key, False)):
        prompt_to_send = _build_prompt_with_persona_fallback(prompt=prompt, timeline=timeline)
    else:
        prompt_to_send = prompt

    if nsfw is None:
        nsfw_value = bool(st.session_state.get("mary_nsfw_on", False))
    else:
        nsfw_value = bool(nsfw)

    if allow_third_party_seduction is None:
        allow_3p = bool(st.session_state.get("mary_allow_third_party_seduction", False))
    else:
        allow_3p = bool(allow_third_party_seduction)

    kwargs = {
        "user": user,
        "model": model,
        "prompt": prompt_to_send,
        "timeline": timeline,
        "nsfw": nsfw_value,
        "allow_third_party_seduction": allow_3p,
    }

    try:
        sig = inspect.signature(svc.reply)
        params = set(sig.parameters.keys())
        kwargs = {k: v for k, v in kwargs.items() if k in params}
    except Exception:
        pass

    resp = svc.reply(**kwargs)

    try:
        st.session_state["mary_last_raw_resp"] = _summarize_raw(resp)
    except Exception:
        st.session_state["mary_last_raw_resp"] = {"raw_type": type(resp).__name__}

    txt = _extract_router_text(resp) or ""
    st.session_state["mary_last_extracted_text_preview"] = txt[:600]

    try:
        prov, used_model = _extract_router_used_model_provider(resp)
    except Exception:
        prov, used_model = (None, None)

    if used_model or prov:
        st.session_state["mary_last_used_model"] = used_model
        st.session_state["mary_last_used_provider"] = prov

    clean = _strip_persona_echo_if_any(txt) or ""
    st.session_state["mary_last_clean_text_preview"] = clean[:600]
    return clean


# ==========================================================
# APP
# ==========================================================
def main() -> None:
    _apply_dark_ui_once()
    _garantir_estado_inicial()

    # ✅ Sync virgindade (GLOBAL <-> timeline) no boot
    try:
        res = _sync_virginity_global_timeline(
            usuario_key=_usuario_key_atual(),
            timeline=_timeline(),
        )
        st.session_state["mary_virginity_sync_last"] = res
    except Exception:
        pass

    _auto_unlock_if_sem_interacao()

    # ===== Header técnico =====
    backend, detail = db_status()

    used_model = st.session_state.get("mary_last_used_model")
    used_provider = st.session_state.get("mary_last_used_provider")
    used_str = ""
    if used_model or used_provider:
        used_str = f" • Usado: <b>{(used_provider or '—')}</b> / <b>{(used_model or '—')}</b>"

    st.caption("🧩 mary_app.py (default model migrado + debug persona + telemetria)")
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
            backend2, ok, info = ping_db()
            st.write("**ping_db():**")
            if ok:
                st.success(f"{backend2} ✅ {info}")
            else:
                st.error(f"{backend2} ❌ {info}")

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

    with st.sidebar.expander("🧩 Debug Persona Import", expanded=True):
        try:
            import importlib.util

            st.write("📌 persona.py ativo:", getattr(mary_persona, "__file__", "—"))
            st.write(
                "✅ import OK:",
                (mary_persona._LAST_PERSONA_IMPORT.get("ok") if hasattr(mary_persona, "_LAST_PERSONA_IMPORT") else "—"),
            )
            st.write(
                "❌ import ERR:",
                (mary_persona._LAST_PERSONA_IMPORT.get("err") if hasattr(mary_persona, "_LAST_PERSONA_IMPORT") else "—"),
            )

            spec = importlib.util.find_spec("characters.mary.persona_universitaria")
            st.write("🔎 find_spec(persona_universitaria):", "ENCONTRADO" if spec else "NÃO ENCONTRADO")

            try:
                import characters.mary.persona_universitaria as pu
                st.success(f"✅ Import direto OK: {getattr(pu, '__file__', '—')}")
            except Exception as e:
                st.error(f"❌ Import direto FALHOU: {type(e).__name__}: {e}")

        except Exception as e:
            st.error(f"Falha ao ler debug persona: {type(e).__name__}: {e}")

    # ===== Header visual =====
    st.markdown(
        f"""
        <div class="rp-card">
          <div class="rp-title">Mary 💍💍</div>
          <div class="rp-sub">
            Timeline: <b>{_timeline()}</b> •
            Modelo(UI): <b>{st.session_state.get('model','')}</b>
            {used_str}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    personas = {
        "Mary – Esposa Cúmplice": "cumplice",
        "Mary – Universitária (linha alternativa)": "universitaria",
    }

    label_atual = next((k for k, v in personas.items() if v == _timeline()), "Mary – Esposa Cúmplice")

    st.selectbox(
        "🎭 Linha temporal da Mary",
        list(personas.keys()),
        index=list(personas.keys()).index(label_atual),
        disabled=bool(st.session_state.get("mary_timeline_locked", False)),
        key="persona_label",
        on_change=_on_timeline_change,
    )

    if st.session_state.get("mary_timeline_locked", False):
        st.caption("🔒 Persona travada após a 1ª mensagem do usuário.")
        st.caption("👉 Se travou sem você ter falado nada, use: Sidebar → 'Destravar timeline'.")

    keys = _keys_para_mary()

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
            delete_shared = st.checkbox("Também apagar TODAS memórias permanentes (shared)", value=False, key="chk_total_del_shared")

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
                    st.session_state["mary_last_used_model"] = None
                    st.session_state["mary_last_used_provider"] = None
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

        if st.session_state.get("mary_timeline_locked", False):
            if st.button("🔓 Destravar timeline (visual)", key="btn_unlock_timeline_visual"):
                st.session_state["mary_timeline_locked"] = False
                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                st.session_state["mary_last_used_model"] = None
                st.session_state["mary_last_used_provider"] = None
                st.session_state["mary_allow_third_party_seduction"] = False
                st.session_state["persona_label"] = None
                _invalidate_backend_cache()
                _clear_mary_caches_all_related(also_clear_other_timeline=True)
                _kill_all_mary_services()
                st.rerun()

        try:
            all_models = service_router.list_models() or []
        except Exception:
            all_models = []

        if not all_models:
            all_models = [DEFAULT_MODEL, FALLBACK_MODEL]

        # ✅ garante que o DEFAULT_MODEL apareça como opção mesmo se list_models falhar/omitir
        if DEFAULT_MODEL not in all_models:
            all_models = [DEFAULT_MODEL] + [m for m in all_models if m != DEFAULT_MODEL]

        # ✅ se estava no antigo, troca automaticamente
        if str(st.session_state.get("model") or "").strip() == OLD_DEFAULT_MODEL:
            st.session_state["model"] = DEFAULT_MODEL

        if st.session_state.get("model") not in all_models:
            st.session_state["model"] = _choose_default_model(all_models)

        current = st.session_state.get("model")
        idx = all_models.index(current) if current in all_models else 0

        st.selectbox("🧠 Modelo", all_models, index=idx, key="model")

        st.markdown("---")
        st.subheader("🛰️ Ping/Pong — confirmar modelo REAL")

        if st.button("🛰️ Ping agora (router)", key="btn_ping_router_now"):
            res = _router_ping_once(
                user=str(st.session_state.get("user_id", "Janio Donisete")),
                model=str(st.session_state.get("model") or DEFAULT_MODEL),
            )
            st.session_state["mary_ping_result"] = res

        ping = st.session_state.get("mary_ping_result")
        if isinstance(ping, dict):
            if ping.get("ok"):
                st.success("✅ Ping executado (router confirmou provider/model).")
                if not ping.get("pong_ok"):
                    st.warning(
                        "⚠️ O modelo respondeu, mas NÃO obedeceu o teste estrito de 'PONG'. "
                        "Isso não impede confirmar o roteamento (provider/model)."
                    )
                st.write("Modelo (UI):", ping.get("ui_model") or "—")
                st.write("Usado (router):", f"{ping.get('used_provider') or '—'} / {ping.get('used_model') or '—'}")
                st.caption("PONG (trecho retornado):")
                st.code(ping.get("text") or "")
            else:
                st.error("❌ Falha no ping.")
                st.code(ping.get("error") or str(ping))

        st.markdown("---")
        nsfw_before = bool(st.session_state.get("mary_nsfw_on", False))
        st.checkbox("Modo adulto liberado (NSFW)", key="mary_nsfw_on")
        nsfw_after = bool(st.session_state.get("mary_nsfw_on", False))

        if "mary_allow_third_party_seduction" not in st.session_state:
            st.session_state["mary_allow_third_party_seduction"] = False

        if not nsfw_after:
            st.session_state["mary_allow_third_party_seduction"] = False

        if nsfw_after != nsfw_before:
            _persist_nsfw_for_current_timeline_if_needed_inline()

        if nsfw_after:
            st.checkbox(
                "Permitir Mary ceder a terceiros (segredo)",
                key="mary_allow_third_party_seduction",
                help="Libera Mary a ir além do 'desvio curto' com terceiros. NÃO altera nada com Janio.",
            )

        # ✅ BOTÃO CANON (corrigido)
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

        rel_now = facts_now.get(f"rel.state::{tl_now}") if isinstance(facts_now.get(f"rel.state::{tl_now}"), dict) else {}
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

                    # ✅ garante que GLOBAL e REL ficam alinhados imediatamente
                    try:
                        res = _sync_virginity_global_timeline(usuario_key=uk_now, timeline=tl_now)
                        st.session_state["mary_virginity_sync_last"] = res
                    except Exception:
                        pass

                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                st.session_state["mary_last_used_model"] = None
                st.session_state["mary_last_used_provider"] = None
                _invalidate_backend_cache()
                _clear_mary_caches_all_related(also_clear_other_timeline=True)
                _kill_all_mary_services()

                st.success("✅ CANON atualizado: Mary NÃO é mais virgem (consumado).")
                st.rerun()

            except Exception as e:
                st.error(f"Falha ao gravar CANON: {type(e).__name__}: {e}")

    # ===== BOOT =====
    _boot_visual_if_empty()

    if st.session_state.get("mary_debug_rel_panel", False):
        _render_relationship_debug_panel()

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
        third_active = bool(st.session_state.get("mary_allow_third_party_seduction", False))

        try:
            set_fact(_usuario_key_atual(), "mary.allow_third_party_seduction", third_active, {"fonte": "ui_toggle"})
        except Exception:
            pass

        try:
            resposta = _call_service_reply_safe(
                svc=svc,
                user=st.session_state.get("user_id", "Janio Donisete"),
                model=st.session_state.get("model") or DEFAULT_MODEL,
                prompt=prompt,
                timeline=tl_active,
                nsfw=nsfw_active,
                allow_third_party_seduction=third_active,
            )
        except Exception as e:
            st.session_state["mary_last_error"] = {
                "type": type(e).__name__,
                "msg": str(e),
                "timeline": tl_active,
                "nsfw": nsfw_active,
                "ui_model": st.session_state.get("model") or DEFAULT_MODEL,
                "used_provider": st.session_state.get("mary_last_used_provider"),
                "used_model": st.session_state.get("mary_last_used_model"),
                "trace": traceback.format_exc()[:4000],
            }
            st.error(f"💥 Erro real ao chamar o modelo: {type(e).__name__}: {e}")
            st.code(st.session_state["mary_last_error"]["trace"])
            st.stop()

        if not (resposta or "").strip():
            st.error("⚠️ Resposta vazia. Diagnóstico abaixo.")
            with st.expander("🧪 Diagnóstico do retorno vazio", expanded=True):
                st.write("Timeline:", tl_active)
                st.write("NSFW:", nsfw_active)
                st.write("Modelo (UI):", st.session_state.get("model"))
                st.write(
                    "Usado (capturado):",
                    f"{st.session_state.get('mary_last_used_provider') or '—'} / {st.session_state.get('mary_last_used_model') or '—'}",
                )
                st.write("Preview extracted (antes do strip):")
                st.code(st.session_state.get("mary_last_extracted_text_preview") or "")
                st.write("Preview clean (depois do strip):")
                st.code(st.session_state.get("mary_last_clean_text_preview") or "")
                st.write("RAW summary:")
                st.json(st.session_state.get("mary_last_raw_resp") or {})
            st.stop()

        with st.chat_message("assistant"):
            st.markdown(_format_paragraphs(resposta))

        st.session_state["chat_history"].append(("assistant", resposta))
        _invalidate_backend_cache()
        st.rerun()


if __name__ == "__main__":
    main()
