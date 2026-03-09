
from __future__ import annotations
from core.repositories import force_reset_virginity_universitaria
from characters.mary.service_core import append_long_memory_safe
# mary_app_harmonized_core_v6.py

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

        # remove a seleção visual (será recalculada pela timeline)
        st.session_state.pop("persona_label", None)

        # limpa telemetria do modelo real (se existir)
        st.session_state.pop("mary_last_used_model", None)
        st.session_state.pop("mary_last_used_provider", None)

        # marca novo boot
        st.session_state["mary_last_boot_timeline"] = current_tl

        # ✅ Shared key override NÃO pode atravessar timelines
        st.session_state.pop("shared_key_override", None)
        st.session_state.pop("__mem_list", None)

        # limpa cache visual de long memory (UI)
        st.session_state.pop("__longmem_list", None)
        

def _cleanup_broken_facts_schema_on_boot() -> None:
    """
    MIGRAÇÃO DEFINITIVA (BOOT-SAFE):
    - remove mary.intro.fixed (string antiga)
    - remove mary.intro.fixed.<timeline> (schema híbrido)
    - remove virgindade global conflitante (apenas universitaria)
    """
    try:
        # ✅ não depende de _timeline() / _usuario_key_atual()
        tl = str(st.session_state.get("mary_timeline") or "cumplice").strip()
        user = str(st.session_state.get("user_id") or "Janio Donisete").strip()
        usuario_key = f"{user}::mary::{tl}"

        # ✅ import local pra não depender da ordem dos imports do arquivo
        from core.repositories import delete_fact

        # --- limpar intro FIXO (2 schemas) ---
        delete_fact(usuario_key, "mary.intro.fixed")
        if tl:
            delete_fact(usuario_key, f"mary.intro.fixed.{tl}")

        # --- limpar conflito de virgindade (universitaria) ---
        # você tem facts.virginity="nao_virgem" mas rel.state::universitaria diz "virgem"
        if tl == "universitaria":
            delete_fact(usuario_key, "virginity")

    except Exception:
        # não deixa o boot quebrar
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

DEFAULT_MODEL = "tngtech/deepseek-r1t2-chimera"
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

        /* ==========================================================
           INPUT FIXO — RESPONSIVO (FIX DEFINITIVO)
           ========================================================== */
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

        /* container interno centralizado, mas sem encolher */
        div[data-testid="stChatInput"] > div{
          width: 100% !important;
          max-width: 980px !important;
          margin: 0 auto !important;
          padding: 0 1rem !important;
          box-sizing: border-box !important;
        }

        /* o FORM era quem estava encolhendo */
        div[data-testid="stChatInput"] form{
          width: 100% !important;
          display: flex !important;
          gap: 10px !important;
          align-items: flex-end !important;
          box-sizing: border-box !important;
        }

        /* ✅ só o wrapper do textarea expande */
        div[data-testid="stChatInput"] form > div:first-child{
          flex: 1 1 auto !important;
          width: 100% !important;
          min-width: 0 !important;  /* crítico em flex */
        }

        /* ✅ wrapper do botão NÃO expande */
        div[data-testid="stChatInput"] form > div:last-child{
          flex: 0 0 auto !important;
          width: auto !important;
          min-width: 0 !important;
        }

        /* textarea ocupa tudo */
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

        /* botão não rouba largura do textarea */
        div[data-testid="stChatInput"] button{
          flex: 0 0 auto !important;
        }

        /* ==========================================================
           FIX MOBILE: botão "Manage app" (Streamlit Cloud) sobrepondo input
           ========================================================== */
        @media (max-width: 768px) {

            /* Sobe a barra inteira do chat_input (libera o canto inferior direito) */
            div[data-testid="stChatInput"] {
                bottom: calc(env(safe-area-inset-bottom, 0px) + 58px) !important;
            }

            /* Garante espaço extra no final para as mensagens não ficarem “atrás” da barra */
            .block-container {
                padding-bottom: 13rem !important;
            }

            /* Evita digitação sob overlays no canto direito */
            div[data-testid="stChatInput"] textarea {
                padding-right: 96px !important;
            }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def _apply_dark_ui_once() -> None:
    """
    Aplica o CSS uma única vez por sessão para evitar repetição em reruns.
    """
    if st.session_state.get("_dark_ui_applied", False):
        return
    _apply_dark_ui()
    st.session_state["_dark_ui_applied"] = True


def _strip_persona_echo_if_any(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t

    # Se o modelo ecoar o prompt do fallback, corta tudo antes do marcador final.
    markers = [
        "⟦MARY⟧",
        "RESPOSTA DA MARY:",
        "Resposta da Mary:",
    ]
    for mk in markers:
        if mk in t:
            tail = t.split(mk, 1)[-1].strip()
            if tail:
                return tail

    # Se ainda assim vier com começo típico de echo, tenta remover blocos conhecidos
    bad_starts = (
        "PERSONA (SYSTEM)",
        "### PERSONA",
        "INSTRUÇÕES INTERNAS",
        "MENSAGEM DO USUÁRIO:",
    )
    if any(t.startswith(b) for b in bad_starts):
        # não achou marcador; devolve vazio para não “colar persona” na tela
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
    # ✅ Shared exclusivo por timeline
    return f"{_uid()}::mary::{_timeline()}::shared"

def _long_key_atual() -> str:
    # ✅ Long memory global (comum às duas MARYs)
    # Mantendo o "usuario" LEGADO para não perder suas 50 memórias já gravadas:
    # Janio Donisete::mary::shared
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
    - Atualiza facts["mary"] (camada global/world_v que o service usa no virginity_rule).
    """
    date_iso = _today_iso()
    tl = (str(timeline or "").strip().lower() or "universitaria")

    canon_text = (
        f"MEMÓRIA CANÔNICA: Mary e {user_id} consumaram a relação. "
        f"Mary NÃO é mais virgem. (válido para o universo compartilhado)\n"
        f"Data: {date_iso}\n"
        f"Timeline ativa no momento do registro: {tl}"
    )

    meta = {
        "kind": "canon",
        "title": "Virgindade — consumado",
        "key": "virginity",
        "value": "nao_virgem",
        "date": date_iso,
        "source": "ui_button",
        "timeline_at_save": tl,
        "user_id": user_id,
    }

    # 1) CANON (shared)
    append_memory(shared_key, canon_text, meta=meta)

    # 2) FACTS (relationship_state) — derivado
    facts = get_facts(usuario_key) or {}
    if not isinstance(facts, dict):
        facts = {}

    rel_key = f"rel.state::{tl}"
    rel = facts.get(rel_key) if isinstance(facts.get(rel_key), dict) else {}
    if not isinstance(rel, dict):
        rel = {}

    rel["consummated"] = True
    rel["virginity"] = "nao_virgem"
    rel["allows_penetration"] = True
    rel.setdefault("allows_extended_touch", True)
    rel.setdefault("allows_mutual_relief", True)

    set_fact(usuario_key, rel_key, rel, {"fonte": "ui_button_canon"})

    # 3) FACTS (mary) — virgindade GLOBAL do mundo (camada que o service lê)
    facts2 = get_facts(usuario_key) or {}
    if not isinstance(facts2, dict):
        facts2 = {}

    mary_obj = facts2.get("mary") if isinstance(facts2.get("mary"), dict) else {}
    if not isinstance(mary_obj, dict):
        mary_obj = {}

    mary_obj["virginity"] = "nao_virgem"          # global fallback
    mary_obj[f"virginity::{tl}"] = "nao_virgem"   # por timeline (world_v)

    set_fact(usuario_key, "mary", mary_obj, {"fonte": "ui_button_canon"})

    # 4) (opcional, mas recomendado) limpa schema legado "dotted"
    #    Isso impede UI/rotinas antigas de ressuscitarem valor errado.
    try:
        delete_fact(usuario_key, "mary.virginity")
    except Exception:
        pass


# ==========================================================
# ✅ SYNC DEFINITIVO: virgindade GLOBAL <-> TIMELINE  (Modelo B)
# ==========================================================
def _sync_virginity_global_timeline(*, usuario_key: str, timeline: str) -> dict:
    """
    Sincroniza:
      - facts["mary"]["virginity"] (global)
      - facts["mary"][f"virginity::{timeline}"] (por timeline / world_v)
      - facts[f"rel.state::{timeline}"] (derivado)

    Regras:
      - Prioridade de leitura: timeline > global > default("virgem")
      - Nunca regride: se qualquer camada indicar "nao_virgem", promove e fixa.
      - Boot-safe, não depende do service.
    """
    notes: list[str] = []
    changed = False

    from core.repositories import get_facts, set_fact, delete_fact

    uk = str(usuario_key or "").strip()
    tl = (str(timeline or "").strip().lower() or "cumplice")

    if not uk:
        return {"changed": False, "notes": ["usuario_key vazio"], "usuario_key": uk, "timeline": tl}

    def _norm(v) -> str | None:
        if not isinstance(v, str):
            return None
        v = v.strip().lower()
        if v in ("virgem", "nao_virgem"):
            return v
        return None

    facts = get_facts(uk) or {}
    if not isinstance(facts, dict):
        facts = {}

    # ----------------------------------------------------------
    # 1) Lê GLOBAL/TIMELINE (dict "mary")
    # ----------------------------------------------------------
    mary_obj = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
    if not isinstance(mary_obj, dict):
        mary_obj = {}

    g_before = _norm(mary_obj.get("virginity"))
    g_tl = _norm(mary_obj.get(f"virginity::{tl}"))

    # ----------------------------------------------------------
    # 2) Decide g_after (timeline > global > default)
    # ----------------------------------------------------------
    g_after = g_tl or g_before
    if g_after is None:
        g_after = "virgem"
        notes.append("GLOBAL ausente => default 'virgem'")
        changed = True

    # Proteção: se QUALQUER lado já marcou nao_virgem, fixa nao_virgem
    if g_before == "nao_virgem" or g_tl == "nao_virgem":
        if g_after != "nao_virgem":
            notes.append("Detectado nao_virgem em alguma camada => promovendo g_after='nao_virgem'")
        g_after = "nao_virgem"

    # ----------------------------------------------------------
    # 3) Persiste dict "mary" (sem regressão)
    # ----------------------------------------------------------
    try:
        need_write = False

        # garante presença e coerência
        if mary_obj.get("virginity") != g_after:
            # nunca regride: só permite escrever 'virgem' se não existe nao_virgem em nenhum lugar
            if g_after == "virgem" and (_norm(mary_obj.get("virginity")) == "nao_virgem"):
                notes.append("Bloqueado: tentativa de regressão GLOBAL nao_virgem -> virgem")
            else:
                mary_obj["virginity"] = g_after
                need_write = True

        if mary_obj.get(f"virginity::{tl}") != g_after:
            # idem: sem regressão
            if g_after == "virgem" and (_norm(mary_obj.get(f"virginity::{tl}")) == "nao_virgem"):
                notes.append("Bloqueado: tentativa de regressão TIMELINE nao_virgem -> virgem")
            else:
                mary_obj[f"virginity::{tl}"] = g_after
                need_write = True

        if need_write:
            set_fact(uk, "mary", mary_obj, {"fonte": "virginity_sync"})
            changed = True

        # remove legado “dotted”
        try:
            delete_fact(uk, "mary.virginity")
        except Exception:
            pass

    except Exception:
        pass

    # ----------------------------------------------------------
    # 4) Sincroniza REL derivado com g_after
    # ----------------------------------------------------------
    rel_key = f"rel.state::{tl}"
    rel = facts.get(rel_key) if isinstance(facts.get(rel_key), dict) else {}
    if not isinstance(rel, dict):
        rel = {}

    rel_before = {
        "virginity": _norm(rel.get("virginity")),
        "consummated": rel.get("consummated"),
        "allows_penetration": rel.get("allows_penetration"),
    }

    rel_after = dict(rel)

    if g_after == "nao_virgem":
        rel_after["virginity"] = "nao_virgem"
        rel_after["consummated"] = True
        rel_after["allows_penetration"] = True
        rel_after.setdefault("allows_extended_touch", True)
        rel_after.setdefault("allows_mutual_relief", True)
    else:
        # g_after == "virgem"
        # universitaria: mantém virgem enquanto não consumou
        if tl == "universitaria":
            # só força virgem se REL estiver vazio/None (não sobrescreve consumado real)
            if _norm(rel_after.get("virginity")) is None and not bool(rel_after.get("consummated")):
                rel_after["virginity"] = "virgem"
                rel_after.setdefault("consummated", False)
                rel_after.setdefault("allows_penetration", False)
        else:
            # outras timelines: se REL não tem valor ainda, alinha virgem
            if _norm(rel_after.get("virginity")) is None:
                rel_after["virginity"] = "virgem"

    if rel_after != rel:
        try:
            set_fact(uk, rel_key, rel_after, {"fonte": "virginity_sync_rel"})
            changed = True
        except Exception:
            pass

    # ----------------------------------------------------------
    # 5) Remove legados que costumam causar “virgem fantasma”
    # ----------------------------------------------------------
    try:
        if "virginity" in facts:
            delete_fact(uk, "virginity")
            notes.append("Removido legado facts['virginity']")
            changed = True
    except Exception:
        pass

    # ----------------------------------------------------------
    # 6) Retorno debug
    # ----------------------------------------------------------
    rel_after_summary = {
        "virginity": _norm(rel_after.get("virginity")),
        "consummated": bool(rel_after.get("consummated")) if rel_after.get("consummated") is not None else None,
        "allows_penetration": bool(rel_after.get("allows_penetration")) if rel_after.get("allows_penetration") is not None else None,
    }

    return {
        "changed": bool(changed),
        "notes": notes,
        "global_before": g_before,
        "global_after": _norm(mary_obj.get("virginity")),
        "global_timeline": _norm(mary_obj.get(f"virginity::{tl}")),
        "rel_before": rel_before,
        "rel_after": rel_after_summary,
        "usuario_key": uk,
        "timeline": tl,
    }
# ==========================================================
# ✅ PERSONA DEBUG + FALLBACK INJECTION (quando service não injeta)
# ==========================================================
def _flatten_boot_messages(boot: Any, timeline: str) -> str:
    """
    Converte boot list[dict] em texto curto.
    Não explode se o formato vier diferente.
    """
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
    """
    Retorna (system_text, boot_messages) da persona para a timeline.
    """
    try:
        system_text, boot = mary_persona.get_persona(timeline)
    except Exception:
        system_text, boot = "", None
    return (str(system_text or "").strip(), boot)


def _build_prompt_with_persona_fallback(*, prompt: str, timeline: str) -> str:
    """
    Fallback: injeta persona no prompt quando o service não injeta.
    IMPORTANTE: formato ANTI-ECHO usando delimitadores raros.
    """
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
    """
    Painel SOMENTE de debug do relationship_engine.
    NÃO altera estado, NÃO grava facts.
    """
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
    """
    Cria o service correto para a timeline (universitaria/cumplice) e tenta
    respeitar diferentes assinaturas de __init__ do service_core.
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
    if st.session_state.get("mary_timeline_locked") and not st.session_state.get("chat_history"):
        st.session_state["mary_timeline_locked"] = False

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

    # fallback injection toggle (para provar persona) — por timeline
    for tl in ("cumplice", "universitaria"):
        k = f"mary_ui_persona_fallback::{tl}"
        if k not in st.session_state:
            st.session_state[k] = False

    # telemetria do modelo real
    if "mary_last_used_model" not in st.session_state:
        st.session_state["mary_last_used_model"] = None
    if "mary_last_used_provider" not in st.session_state:
        st.session_state["mary_last_used_provider"] = None


def _clear_service_caches_for_keys(keys: list[str]) -> None:
    # ✅ remove facts + TODOS history::<key>::<limit> + mem::<key>::<limit>
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

    IMPORTANTE (harmonização com service_core v6):
    - service_core dá prioridade ao flag por timeline: mary["nsfw::<timeline>"].
    - então aqui persistimos SEMPRE:
        1) mary.nsfw (global)
        2) mary.nsfw::<timeline> (por timeline atual)
    """
    uk = _usuario_key_atual()
    current = bool(st.session_state.get("mary_nsfw_on", False))
    last = st.session_state.get("mary_nsfw_last_saved", None)

    # tenta inferir timeline do usuario_key: "Nome::mary::<timeline>"
    tl = ""
    try:
        tl = str(uk).split("::")[-1].strip().lower()
    except Exception:
        tl = ""

    if last is None or bool(last) != current:
        try:
            # global
            set_fact(uk, "mary.nsfw", current, {"fonte": "ui_toggle"})
            # por timeline (prioridade no core)
            if tl:
                set_fact(uk, f"mary.nsfw::{tl}", current, {"fonte": "ui_toggle"})
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

    st.session_state["mary_last_used_model"] = None
    st.session_state["mary_last_used_provider"] = None
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

    # ✅ Sync virgindade (GLOBAL <-> timeline) ao trocar timeline
    try:
        res = _sync_virginity_global_timeline(
            usuario_key=_usuario_key_atual(),
            timeline=new_tl,
        )
        st.session_state["mary_virginity_sync_last"] = res
    except Exception:
        pass

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

    # telemetria
    st.session_state["mary_last_used_model"] = None
    st.session_state["mary_last_used_provider"] = None

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
    """
    Boot visual do app.
    IMPORTANTE: NÃO renderiza persona (SYSTEM/BOOT) na tela.
    Persona deve ficar só no service (ou no fallback de UI), mas invisível pro usuário.
    """
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
    """
    ✅ Resolve o teu caso: menu já abre travado na 'cumplice'.
    Se NÃO há nenhuma mensagem do usuário (nem no visual, nem no backend),
    destrava automaticamente para permitir escolher 'universitaria'.
    """
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


def _capture_used_model_provider_from_service(svc: Any) -> None:
    """
    Tenta capturar modelo/provedor REAL usado pelo service, se ele expõe isso.
    Não quebra se não existir.
    """
    model = None
    provider = None

    for attr in ("used_model", "last_used_model", "model_used", "resolved_model", "last_model"):
        if hasattr(svc, attr):
            try:
                v = getattr(svc, attr)
                if isinstance(v, str) and v.strip():
                    model = v.strip()
                    break
            except Exception:
                pass

    for attr in ("provider", "used_provider", "last_used_provider", "provider_used", "last_provider"):
        if hasattr(svc, attr):
            try:
                v = getattr(svc, attr)
                if isinstance(v, str) and v.strip():
                    provider = v.strip()
                    break
            except Exception:
                pass

    st.session_state["mary_last_used_model"] = model
    st.session_state["mary_last_used_provider"] = provider


def _extract_router_text(resp: Any) -> str:
    """
    Extrai texto de:
      - tuple(data, used_model, provider)
      - dict (OpenAI-like)
      - str

    FIX CRÍTICO:
      Alguns providers/modelos retornam o texto em message.reasoning
      e deixam message.content vazio. Nesse caso, usamos reasoning.
    """
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
    """
    Retorna (provider, used_model).

    ✅ Suporta tuple(data, used_model, provider) (OpenRouter/Together/HF no seu projeto)
    ✅ Suporta dict com chaves em níveis diferentes:
       - direto: provider/model/used_model/resolved_model...
       - meta: meta.provider/meta.used_model...
       - debug: debug.provider/debug.used_model...
    """
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
    """
    Resume o retorno do router/service sem vazar payload inteiro.
    ✅ Captura provider/model/used_model em:
      - tuple(data, used_model, provider)
      - dict raiz
      - dict.meta
      - dict.debug
      - preview do content/text
    """
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

        provider_meta = _pick_str(meta, "provider", "used_provider", "provider_used") if meta else None
        model_meta = _pick_str(meta, "used_model", "resolved_model", "model", "model_used") if meta else None

        provider_dbg = _pick_str(debug, "provider", "used_provider", "provider_used") if debug else None
        model_dbg = _pick_str(debug, "used_model", "resolved_model", "model", "model_used") if debug else None

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
    """
    Chama svc.reply sem depender de assinatura fixa.
    E, se o service NÃO injeta persona, permite fallback opcional via UI.

    ✅ Robustez:
    - tenta prompt=...
    - se der TypeError (unexpected keyword 'prompt'), re-tenta com text=...
    - se der TypeError, re-tenta com user_text=...
    - filtra kwargs por assinatura quando possível
    """

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

    # -------------------------
    # Base kwargs "completos"
    # -------------------------
    base_kwargs = {
        "user": user,
        "model": model,
        "prompt": prompt_to_send,
        "timeline": timeline,
        "nsfw": nsfw_value,
        "allow_third_party_seduction": allow_3p,
    }

    # -------------------------
    # Helper: filtra por assinatura
    # - se tiver **kwargs, pode mandar tudo
    # -------------------------
    def _filter_kwargs_by_signature(func: Any, kw: dict) -> dict:
        try:
            sig = inspect.signature(func)
            params = sig.parameters

            # Se aceita **kwargs, não filtra
            for p in params.values():
                if p.kind == inspect.Parameter.VAR_KEYWORD:
                    return kw

            allowed = set(params.keys())
            return {k: v for k, v in kw.items() if k in allowed}
        except Exception:
            # assinatura indisponível → devolve como está (vamos tratar via tentativas)
            return kw

    # -------------------------
    # Candidatos de chamada
    # (ordem importa)
    # -------------------------
    candidates: list[dict] = []

    # 1) Tenta como você queria (prompt)
    candidates.append(dict(base_kwargs))

    # 2) Tenta "text" (mais comum em BaseCharacter)
    kw2 = dict(base_kwargs)
    kw2.pop("prompt", None)
    kw2["text"] = prompt_to_send
    candidates.append(kw2)

    # 3) Tenta "user_text" (alguns cores usam isso)
    kw3 = dict(base_kwargs)
    kw3.pop("prompt", None)
    kw3["user_text"] = prompt_to_send
    candidates.append(kw3)

    # 4) Alguns services não aceitam timeline no reply() → tenta sem timeline
    kw4 = dict(kw2)
    kw4.pop("timeline", None)
    candidates.append(kw4)

    kw5 = dict(kw3)
    kw5.pop("timeline", None)
    candidates.append(kw5)

    # 5) Alguns services usam nsfw_on em vez de nsfw
    kw6 = dict(kw2)
    if "nsfw" in kw6:
        kw6["nsfw_on"] = kw6.pop("nsfw")
    candidates.append(kw6)

    kw7 = dict(kw4)
    if "nsfw" in kw7:
        kw7["nsfw_on"] = kw7.pop("nsfw")
    candidates.append(kw7)

    # -------------------------
    # Executa tentativas
    # -------------------------
    last_err: Exception | None = None
    resp = None

    for i, kw in enumerate(candidates, start=1):
        # filtra se der (quando signature funciona)
        kw = _filter_kwargs_by_signature(svc.reply, kw)

        try:
            resp = svc.reply(**kw)
            last_err = None
            break
        except TypeError as e:
            # guarda e tenta próximo
            last_err = e
            continue
        except Exception as e:
            # erro real do provider/service → não é problema de assinatura
            last_err = e
            break

    if last_err is not None and resp is None:
        # re-levanta com contexto mínimo (pra você ver no log)
        raise last_err

    # -------------------------
    # Debug raw
    # -------------------------
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
    else:
        _capture_used_model_provider_from_service(svc)

    clean = _strip_persona_echo_if_any(txt) or ""
    st.session_state["mary_last_clean_text_preview"] = clean[:600]

    return clean

# ==========================================================
# APP
# ==========================================================
def main() -> None:
    _apply_dark_ui_once()
    _garantir_estado_inicial()

    # ✅ MIGRAÇÃO DE MODELO (default novo)
    # - se ainda estiver no antigo, troca automaticamente
    # - se não existir "model" por algum motivo, seta o novo default
    try:
        if not st.session_state.get("model"):
            st.session_state["model"] = DEFAULT_MODEL
        elif st.session_state.get("model") == "tngtech/deepseek-r1t2-chimera":
            st.session_state["model"] = DEFAULT_MODEL  # "tngtech/deepseek-r1t2-chimera"
    except Exception:
        pass

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
    backend, detail = db_status()

    used_model = st.session_state.get("mary_last_used_model")
    used_provider = st.session_state.get("mary_last_used_provider")
    used_str = ""
    if used_model or used_provider:
        used_str = f" • Usado: <b>{(used_provider or '—')}</b> / <b>{(used_model or '—')}</b>"

    st.caption("🧩 mary_app.py v3.14 (debug persona + fallback persona UI + telemetria modelo/provedor)")
    st.caption(f"🗄️ Backend atual: **{backend}** ({detail})")

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

            st.write("✅ import OK:", (mary_persona._LAST_PERSONA_IMPORT.get("ok") if hasattr(mary_persona, "_LAST_PERSONA_IMPORT") else "—"))
            st.write("❌ import ERR:", (mary_persona._LAST_PERSONA_IMPORT.get("err") if hasattr(mary_persona, "_LAST_PERSONA_IMPORT") else "—"))

            spec = importlib.util.find_spec("characters.mary.persona_universitaria")
            st.write("🔎 find_spec(persona_universitaria):", "ENCONTRADO" if spec else "NÃO ENCONTRADO")

            try:
                import characters.mary.persona_universitaria as pu
                st.success(f"✅ Import direto OK: {getattr(pu, '__file__', '—')}")
            except Exception as e:
                st.error(f"❌ Import direto FALHOU: {type(e).__name__}: {e}")

        except Exception as e:
            st.error(f"Falha ao ler debug persona: {type(e).__name__}: {e}")

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
                    st.session_state["mary_last_used_model"] = None
                    st.session_state["mary_last_used_provider"] = None
                    _invalidate_backend_cache()
                    _clear_mary_caches_all_related()
                    _kill_all_mary_services()

                    st.success(f"✅ RESET TOTAL concluído. history={n_hist} | eventos={n_evt} | mems_shared={n_mems}")
                    st.rerun()

def _clear_sidebar_state_fields(usuario_key: str) -> None:
    # limpa facts persistidos
    for k in (
        "state.local",
        "state.roupa",
        "state.cabelo",
        "state.horarios",
        "state.horario",
        "state.assunto",
        "state.desculpa",
        "state.pendencias",
    ):
        set_fact(usuario_key, k, "", {"fonte": "sidebar_state_clear"})

    # limpa widgets do sidebar
    st.session_state["sb_state_local"] = ""
    st.session_state["sb_state_roupa"] = ""
    st.session_state["sb_state_cabelo"] = ""
    st.session_state["sb_state_horarios"] = ""
    st.session_state["sb_state_assunto"] = ""

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

        # ----------------------------
        # Destravar timeline (visual)
        # ----------------------------
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

        # ----------------------------
        # Lista de modelos
        # ----------------------------
        try:
            all_models = service_router.list_models() or []
            st.session_state["models_debug"] = {
                "ok": True,
                "len": len(all_models),
                "head": all_models[:10],
                "providers": (service_router.available_providers() if hasattr(service_router, "available_providers") else "—"),
                "err": None,
            }
        except Exception as e:
            all_models = []
            st.session_state["models_debug"] = {
                "ok": False,
                "len": 0,
                "head": [],
                "providers": "—",
                "err": f"{type(e).__name__}: {e}",
            }

        if not all_models:
            all_models = [FALLBACK_MODEL]

        if st.session_state.get("model") not in all_models:
            st.session_state["model"] = _choose_default_model(all_models)

        current = st.session_state.get("model")
        idx = all_models.index(current) if current in all_models else 0

        st.selectbox("🧠 Modelo", all_models, index=idx, key="model")

        with st.expander("🧪 Debug imports (service_router)", expanded=True):
            try:
                st.json(service_router.import_errors())
            except Exception as e:
                st.write(f"falhou: {type(e).__name__}: {e}")

        # Provider detectado
        try:
            prov_detected = None
            if hasattr(service_router, "_provider_for"):
                prov_detected = service_router._provider_for(str(st.session_state.get("model") or "").strip())

            if not prov_detected:
                msel = str(st.session_state.get("model") or "").strip().lower()
                if msel.startswith("together/"):
                    prov_detected = "Together"
                elif msel in [x.lower() for x in getattr(service_router, "HF_MODELS", [])]:
                    prov_detected = "HuggingFace"
                else:
                    prov_detected = "OpenRouter"

            st.caption(f"🔌 Provider detectado: **{prov_detected}**")
        except Exception:
            st.caption("🔌 Provider detectado: **—**")

        # ----------------------------
        # Ping/Pong
        # ----------------------------
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
                        "Isso não impede confirmar o roteamento (provider/model), apenas indica que o modelo ignora instruções curtas."
                    )
                st.write("Modelo (UI):", ping.get("ui_model") or "—")

                used_p = ping.get("used_provider")
                used_m = ping.get("used_model")

                if not used_p:
                    try:
                        if hasattr(service_router, "_provider_for"):
                            used_p = service_router._provider_for(str(ping.get("ui_model") or "").strip())
                    except Exception:
                        used_p = None

                st.write("Usado (router):", f"{used_p or '—'} / {used_m or '—'}")

                st.caption("PONG (trecho retornado):")
                st.code(ping.get("text") or "")

                if not used_m:
                    st.warning(
                        "⚠️ O router NÃO retornou o modelo usado no payload. "
                        "Se quiser 100% garantido, faça o service_router.chat sempre retornar (data, used_model, used_provider)."
                    )
            else:
                st.error("❌ Falha no ping.")
                err = ping.get("error")
                st.code(err if isinstance(err, str) and err.strip() else str(ping))

        # ----------------------------
        # Último erro
        # ----------------------------
        st.markdown("---")
        st.subheader("🧨 Último erro (service)")

        if st.button("📌 Mostrar diagnóstico completo", key="btn_show_last_error"):
            st.markdown("**Modelo/Provider capturados (última call):**")
            st.write(
                "Usado:",
                f"{st.session_state.get('mary_last_used_provider') or '—'} / {st.session_state.get('mary_last_used_model') or '—'}",
            )

            st.markdown("**Preview extracted (antes do strip):**")
            st.code(st.session_state.get("mary_last_extracted_text_preview") or "")

            st.markdown("**Preview clean (depois do strip):**")
            st.code(st.session_state.get("mary_last_clean_text_preview") or "")

            st.markdown("**RAW summary:**")
            st.json(st.session_state.get("mary_last_raw_resp") or {})

            st.markdown("**Último erro registrado:**")
            st.json(st.session_state.get("mary_last_error") or {})

        # ----------------------------
        # NSFW + Third-party
        # ----------------------------
        st.markdown("---")
        nsfw_before = bool(st.session_state.get("mary_nsfw_on", False))
        st.checkbox("Modo adulto liberado (NSFW)", key="mary_nsfw_on")
        nsfw_after = bool(st.session_state.get("mary_nsfw_on", False))
        
        if "mary_allow_third_party_seduction" not in st.session_state:
            st.session_state["mary_allow_third_party_seduction"] = False
        
        # Se desligou NSFW, força OFF e zera seeds/ciúme no facts (sem derrubar UI)
        if not nsfw_after:
            st.session_state["mary_allow_third_party_seduction"] = False
            try:
                uk = _usuario_key_atual()
                set_fact(uk, "rel.ciume_flerte_segredo", "", {"fonte": "nsfw_off_reset"})
                set_fact(uk, "rel.jealousy_level", 0, {"fonte": "nsfw_off_reset"})
                set_fact(uk, "rel.ciume_last_trigger_turn", 0, {"fonte": "nsfw_off_reset"})
            except Exception:
                pass
        
        # Persistência de NSFW por timeline (quando alternar)
        if nsfw_after != nsfw_before:
            _persist_nsfw_for_current_timeline_if_needed_inline()
        
        if nsfw_after:
            st.checkbox(
                "Permitir Mary ceder a terceiros (segredo)",
                key="mary_allow_third_party_seduction",
                help="Libera Mary a ir além do 'desvio curto' com terceiros. NÃO altera nada com Janio.",
            )
            st.caption("⚠️ Convite degradante/“sumir” com terceiro continua proibido pelas regras.")
        
            # ======================================================
            # 🧾 Estado Atual (facts → service_core)
            # ======================================================
            st.markdown("---")
            st.subheader("🧾 Estado Atual (facts → service_core)")
    
            try:
                _uk = _usuario_key_atual()
                _facts_now = get_facts(_uk) or {}
                if not isinstance(_facts_now, dict):
                    _facts_now = {}
            except Exception:
                _uk = _usuario_key_atual()
                _facts_now = {}
    
            def _f(k: str) -> str:
                v = _facts_now.get(k, "")
                return "" if v is None else str(v).strip()
    
            _horarios_default = _f("state.horarios") or _f("state.horario")
    
            with st.expander("Editar Estado Atual (aparece no prompt)", expanded=False):
                st.text_input("1) Local", value=_f("state.local"), key="sb_state_local")
                st.text_input("2) Roupa", value=_f("state.roupa"), key="sb_state_roupa")
                st.text_input("3) Cabelo", value=_f("state.cabelo"), key="sb_state_cabelo")
    
                st.markdown("**Opcionais**")
                st.text_input("(+) Horários", value=_horarios_default, key="sb_state_horarios")
                st.text_input(
                    "(+) Assunto",
                    value=_f("state.assunto"),
                    key="sb_state_assunto",
                    placeholder="Ex.: supermercado, Enzo, academia, ciúme",
                    help="Tema vivo da cena. Não vira ação obrigatória; só inclina o foco da Mary."
                )
    
                c1, c2 = st.columns(2)
    
                
                with c1:
                    if st.button("💾 Aplicar Estado", key="btn_apply_state"):
                        updates = {
                            "state.local": st.session_state.get("sb_state_local", "").strip(),
                            "state.roupa": st.session_state.get("sb_state_roupa", "").strip(),
                            "state.cabelo": st.session_state.get("sb_state_cabelo", "").strip(),
                            "state.horarios": st.session_state.get("sb_state_horarios", "").strip(),
                            "state.assunto": st.session_state.get("sb_state_assunto", "").strip(),
                        }
                
                        try:
                            for k, v in updates.items():
                                set_fact(_uk, k, v, {"fonte": "sidebar_state"})
                            st.success("✅ Estado atual atualizado.")
                        except Exception as e:
                            st.error(f"Falha ao aplicar estado: {type(e).__name__}: {e}")
                
                with c2:
                    st.button(
                        "🧹 Limpar Estado",
                        key="btn_clear_state",
                        on_click=_clear_sidebar_state_fields,
                        args=(_uk,),
                    )                                set_fact(_uk, k, "", {"fonte": "sidebar_state_clear"})
    
                            st.session_state["sb_state_local"] = ""
                            st.session_state["sb_state_roupa"] = ""
                            st.session_state["sb_state_cabelo"] = ""
                            st.session_state["sb_state_horarios"] = ""
                            st.session_state["sb_state_assunto"] = ""
    
                            st.success("✅ Estado atual limpo.")
                        except Exception as e:
                            st.error(f"Falha ao limpar estado: {type(e).__name__}: {e}")

        # ======================================================
        # 🎲 SURPRESA / DINÂMICA
        # ======================================================
        st.markdown("---")
        st.subheader("🎲 Dinâmica de Surpresa")

        try:
            _uk_surprise = _usuario_key_atual()
            _facts_surprise = get_facts(_uk_surprise) or {}
            if not isinstance(_facts_surprise, dict):
                _facts_surprise = {}
        except Exception:
            _uk_surprise = _usuario_key_atual()
            _facts_surprise = {}

        current_surprise = int(_facts_surprise.get("mary.surprise_level", 0) or 0)

        st.slider(
            "Nível de surpresa ativa da Mary",
            min_value=0,
            max_value=3,
            value=current_surprise,
            step=1,
            help=(
                "0 = Inerte (Mary não muda ritmo sozinha)\n"
                "1 = Leve (micro provocação ocasional)\n"
                "2 = Ativa (muda ritmo inesperadamente)\n"
                "3 = Dominante (vira a energia da cena)"
            ),
            key="sb_surprise_level",
        )

        col_s1, col_s2 = st.columns(2)

        with col_s1:
            if st.button("💾 Aplicar surpresa", key="btn_apply_surprise"):
                try:
                    set_fact(
                        _uk_surprise,
                        "mary.surprise_level",
                        int(st.session_state.get("sb_surprise_level", 0)),
                        {"fonte": "sidebar_surprise"},
                    )
                    _invalidate_backend_cache()
                    _clear_mary_caches_all_related()
                    _kill_all_mary_services()
                    st.success("✅ surprise_level aplicado.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha ao aplicar surpresa: {type(e).__name__}: {e}")

        with col_s2:
            if st.button("🧹 Resetar surpresa", key="btn_clear_surprise"):
                try:
                    delete_fact(_uk_surprise, "mary.surprise_level")
                except Exception:
                    pass

                _invalidate_backend_cache()
                _clear_mary_caches_all_related()
                _kill_all_mary_services()
                st.success("✅ surprise_level removido.")
                st.rerun()

        # ======================================================
        # 🧬 Persona — Debug / Injeção
        # ======================================================
        st.markdown("---")
        st.subheader("🧬 Persona — Debug / Injeção")

        sys_txt, boot = _get_persona_bundle(_timeline())
        boot_txt = _flatten_boot_messages(boot, _timeline())

        st.caption("Arquivo persona ativo:")
        try:
            st.code(getattr(mary_persona, "__file__", "—"))
        except Exception:
            st.code("(não consegui resolver path)")

        st.write({"system_len": len(sys_txt or ""), "boot_len": len(boot_txt or ""), "timeline": _timeline()})

        if not sys_txt and not boot_txt:
            st.error("⚠️ Persona parece VAZIA para essa timeline. O modelo vai inventar traços físicos.")
        else:
            with st.expander("👀 Preview SYSTEM (primeiros 500)", expanded=False):
                st.code((sys_txt or "")[:500])
            with st.expander("👀 Preview BOOT (primeiros 800)", expanded=False):
                st.code((boot_txt or "")[:800])

        tl = _timeline()
        fb_key = f"mary_ui_persona_fallback::{tl}"
        st.checkbox("Fallback: injetar persona via UI no prompt (se service não injeta)", key=fb_key)
        st.caption("Dica: deixe ON até confirmar que o service injeta SYSTEM+BOOT.")

        # ======================================================
        # 🧬 Canon — Estado íntimo
        # ======================================================
        st.markdown("---")
        st.subheader("🧬 Canon — Estado íntimo")

        uk_now = _usuario_key_atual()
        tl_now = _timeline()
        sk_now = _shared_key_atual()
        uid_now = str(st.session_state.get("user_id", "Janio Donisete"))

        try:
            facts_now = get_facts(uk_now) or {}
            if not isinstance(facts_now, dict):
                facts_now = {}
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

        # ======================================================
        # 🔁 Reset rápido
        # ======================================================
        st.markdown("---")
        st.subheader("🔁 Reset rápido")

        is_uni = (str(tl_now or "").strip().lower() == "universitaria")

        if st.button(
            "🟢 Forçar VIRGEM (Universitária)",
            key="btn_force_virginity_universitaria",
            disabled=not is_uni,
            help="Reverte virginity/consummated/permissões e zera intimacy.phase::universitaria.",
        ):
            try:
                force_reset_virginity_universitaria(uk_now)

                st.session_state["chat_history"] = []
                st.session_state["mary_intro_done"] = False
                st.session_state["mary_last_used_model"] = None
                st.session_state["mary_last_used_provider"] = None

                _invalidate_backend_cache()
                _clear_mary_caches_all_related(also_clear_other_timeline=True)
                _kill_all_mary_services()

                st.success("✅ UNIVERSITÁRIA resetada para VIRGEM (facts/rel/intimacy).")
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao forçar virgindade: {type(e).__name__}: {e}")

        st.caption("Obs.: Reset capítulo não apaga canon. Reset total com apagar memórias shared apaga.")

        # ======================================================
        # 🔍 Debug
        # ======================================================
        st.markdown("---")
        st.subheader("🔍 Debug")
        st.caption(
            f"NSFW={bool(st.session_state.get('mary_nsfw_on', False))} | "
            f"ThirdParty={bool(st.session_state.get('mary_allow_third_party_seduction', False))}"
        )

        st.session_state["mary_debug_rel_panel"] = st.checkbox(
            "Mostrar painel Relationship",
            value=bool(st.session_state.get("mary_debug_rel_panel", False)),
            key="mary_debug_rel_panel__ui",
        )

        # ======================================================
        # Turnos / Limpar
        # ======================================================
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

        # ======================================================
        # 🎭 Persona / Facts quick tools
        # ======================================================
        st.markdown("---")
        st.subheader("🎭 Persona")
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
            _kill_all_mary_services()
            st.session_state["mary_intro_done"] = False
            st.session_state["chat_history"] = []
            st.session_state["mary_timeline_locked"] = False
            st.session_state["mary_rel_meta_last"] = None
            st.session_state["mary_last_used_model"] = None
            st.session_state["mary_last_used_provider"] = None

            try:
                st.cache_data.clear()
            except Exception:
                pass
            try:
                st.cache_resource.clear()
            except Exception:
                pass

            _invalidate_backend_cache()
            _clear_mary_caches_all_related()
            st.success("Services/caches reiniciados. Persona será reinjetada no próximo reply.")
            st.rerun()

        # ======================================================
        # 🧠 MEMÓRIAS PERMANENTES (shared)
        # ======================================================
        st.markdown("---")
        st.subheader("🧠 Memórias permanentes (shared)")
        st.session_state.setdefault("long_key_override", "")

        shared_default = _shared_key_atual()

        if "shared_key_override" not in st.session_state:
            st.session_state["shared_key_override"] = ""

        with st.form("shared_key_form", clear_on_submit=False):
            shared_in = st.text_input(
                "Key compartilhada (editável):",
                value=st.session_state.get("shared_key_override") or shared_default,
                help="Ex: Janio Donisete::mary::shared",
            ).strip()
            apply_shared = st.form_submit_button("✅ Aplicar key")

        if apply_shared:
            st.session_state["shared_key_override"] = shared_in or shared_default
            st.session_state["__mem_list"] = None
            st.rerun()

        shared_key = (st.session_state.get("shared_key_override") or shared_default).strip() or shared_default

        st.caption("Key efetiva:")
        st.code(shared_key)

        st.markdown("**➕ Inserir memória (shared)**")
        mem_text = st.text_area(
            "Texto da memória",
            placeholder="Ex: Mary e Janio moram em Vitória.\nEx: Estão de férias em Balneário Camboriú.\nEx: Evento no quiosque com Canobio (não altera a cena ativa).",
            height=120,
            key="shared_mem_text",
        )
        mem_title = st.text_input(
            "Título (opcional)",
            placeholder="Ex: Moradia / Férias em BC / Evento quiosque",
            key="shared_mem_title",
        )

        mem_kind = st.selectbox(
            "Tipo da memória",
            ["estado_ativo", "evento_passado", "canon", "nota"],
            index=0,
            key="shared_mem_kind",
        )

        mem_tags = st.text_input(
            "Tags (opcional) — use vírgula",
            placeholder="Ex: Arthur, telefone, uber",
            key="shared_mem_tags",
            help="Essas tags viram o cabeçalho [TAGS: ...] e são usadas para gatilhos compostos (ex: Arthur+telefone).",
        )

        mem_latent = st.text_input(
            "Latente (opcional) — regra de ativação automática",
            placeholder="Ex: tension>0.5; guilt<0.2",
            key="shared_mem_latent",
            help="Vira o cabeçalho [LATENT: ...]. Use quando quiser memórias que 'acordam' automaticamente por estado (tensão, culpa, etc.).",
        )

        if st.button("✅ Salvar memória (shared)", key="btn_save_shared_mem"):
            t_raw = (mem_text or "").strip()
            if not t_raw:
                st.warning("Escreva o texto da memória antes de salvar.")
            else:
                tags_raw = (st.session_state.get("shared_mem_tags") or mem_tags or "").strip()
                latent_raw = (st.session_state.get("shared_mem_latent") or mem_latent or "").strip()

                header_lines = []
                if tags_raw:
                    tags_norm = ", ".join([x.strip() for x in re.split(r"[;,]", tags_raw) if x.strip()])
                    header_lines.append(f"[TAGS: {tags_norm}]")
                if latent_raw:
                    header_lines.append(f"[LATENT: {latent_raw}]")

                t = ("\n".join(header_lines) + ("\n" if header_lines else "") + t_raw).strip()

                meta = {
                    "kind": str(st.session_state.get("shared_mem_kind") or mem_kind).strip(),
                    "source": "ui_shared_memory",
                }
                if (mem_title or "").strip():
                    meta["title"] = mem_title.strip()

                try:
                    append_memory(shared_key, t, meta=meta)
                    st.success("✅ Memória salva em (shared).")

                    st.session_state["__mem_list"] = list_memories(shared_key, limit=200) or []
                    _clear_service_caches_for_keys([shared_key])
                    _clear_mary_caches_all_related()
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha ao salvar memória: {type(e).__name__}: {e}")

        if st.button("🔄 Atualizar lista", key="btn_refresh_shared_list"):
            st.session_state["__mem_list"] = list_memories(shared_key, limit=200) or []
            st.success("Lista atualizada ✅")

        if st.button("🧽 Apagar última memória", key="btn_delete_last_mem"):
            ok = delete_last_memory(shared_key)
            st.success("✅ Última memória apagada." if ok else "Nada para apagar.")
            st.session_state["__mem_list"] = list_memories(shared_key, limit=200) or []
            _clear_service_caches_for_keys([shared_key])
            _clear_mary_caches_all_related()
            st.rerun()

        if st.button("💣 Apagar TODAS as memórias", key="btn_delete_all_mems"):
            n = delete_all_memories(shared_key)
            st.success(f"✅ Apaguei {n} memórias.")
            st.session_state["__mem_list"] = []
            _clear_service_caches_for_keys([shared_key])
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

        lm_userkey = st.session_state.get("long_key_override") or f"{_uid()}::mary::shared"

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
                    st.success("✅ Última memória (DB) apagada." if ok else "Nada para apagar (DB).")
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
        lm_terms = st.text_input(
            "Termos de busca (opcional)",
            key="lm_terms_inp",
            value="",
            placeholder="Ex: mary, formação, psicologia, ufes"
        )
        lm_pin = st.checkbox("📌 Fixar (sempre presente nas respostas)", key="lm_pin_chk", value=False)        

        if st.button("💾 Salvar na long_memory", key="btn_lm_save"):
            try:
                txt = (lm_text or "").strip()
                if not txt:
                    st.warning("⚠️ Texto da memória está vazio.")
                else:
                    kind_final = "pin" if bool(lm_pin) else "memory"
                    tl_current = _timeline()
                    timeline_at_save = "[all]" if kind_final == "pin" else tl_current
                    terms_list = [t.strip() for t in (lm_terms or "").split(",") if t.strip()]
        
                    meta = {
                        "title": (lm_title or "").strip() or ("PIN (UI)" if kind_final == "pin" else ""),
                        "kind": kind_final,
                        "timeline_at_save": timeline_at_save,
                        "user_id": str(st.session_state.get("user_id", "Janio Donisete")),
                        "source": "ui_long_memory",
                        "tags": terms_list,
                    }
        
                    append_long_memory_safe(
                        lm_userkey,
                        txt,
                        meta=meta,
                        user_id=str(st.session_state.get("user_id", "Janio Donisete")),
                    )
        
                    st.success(f"✅ Gravado: kind={kind_final} tl={timeline_at_save}")
        
                    st.session_state["__lm_list"] = list_long_memory(lm_userkey, limit=50) or []
                    st.rerun()
            except Exception as e:
                st.error(f"Falha ao gravar: {type(e).__name__}: {e}")
        st.markdown("### 🔎 Buscar (Mongo $text)")
        q = st.text_input("Consulta", key="lm_q_inp", value="", placeholder="Ex: amendoim 500")
        lim = st.slider("Limite de resultados", min_value=5, max_value=50, value=20, step=5, key="lm_lim_slider")

        if st.button("🔍 Buscar agora", key="btn_lm_search"):
            qq = (q or "").strip()
            if not qq:
                st.warning("Digite uma consulta antes de buscar.")
            else:
                try:
                    st.session_state["__lm_search"] = search_long_memory_text(lm_userkey, qq, limit=int(lim)) or []
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

    # ===== DEBUG VISUAL (opcional) =====
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
            st.error("⚠️ Resposta vazia. Diagnóstico abaixo (NÃO é 'mistério', é pipeline).")

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
