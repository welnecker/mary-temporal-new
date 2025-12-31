# characters/mary/service.py
from __future__ import annotations
"""
MaryService (v3.18.0 – Enxuta + Gate Anti-Vazamento + NPC Genérico)

Mantém:
- Timeline-aware + Canon (shared/state_data)
- Long Memory ($text Mongo)
- BM25 fallback
- Scene Lock (continuidade espacial)
- NSFW unificado (core.nsfw)
- RelationshipEngine v2 (pós-resposta)
- Progressão íntima por fases
- CONFLICT_MODE

NOVO (v3.18):
- REGRA ESTRUTURAL: NPCs SEMPRE são "NPC:" (sem nomes fixos)
- GATE PÓS-MODELO:
  - Normaliza qualquer personagem extra -> "NPC:"
  - Remove nomes próprios e "Seu <Nome>" das falas de NPC
  - Bloqueia confirmação de segredos por NPC (vira ambiguidade)
  - Bloqueia conteúdo inventado de mensagens offscreen (vira “[mensagem não revelada]”)
"""

import logging
import re
import hashlib
import time
from typing import Any, Dict, List, Tuple, Optional

import streamlit as st

from core.common.base_service import BaseCharacter
import core.service_router as service_router
from core.canon import get_canon, canon_to_text
from core.relationship_engine import (
    evolve_relationship,
    rel_state_to_prompt_block,
    default_relationship_state,
    EngineConfig,
)
from core.repositories import (
    get_facts,
    get_fact,
    get_history_docs,
    save_interaction,
    set_fact,
    append_memory,
    list_memories,
    # LONG MEMORY
    append_long_memory,
    search_long_memory_text,
)
from core.nsfw import nsfw_enabled as nsfw_enabled_unified

from characters.registry import _SERVICE_CACHE
from .persona import get_persona

logger = logging.getLogger(__name__)
_SERVICE_CACHE.clear()


# ==========================================================
# CONTROLE DE PROGRESSÃO ÍNTIMA (FASES)
# ==========================================================
INTIMACY_PHASES = {
    0: "tensao",
    1: "contato",
    2: "excitacao",
    3: "pre_climax",
    4: "climax",
    5: "aftercare",
}
MAX_INTIMACY_PHASE = 5


# ==========================================================
# USER / KEYS
# ==========================================================
def _normalize_user_id(user: Optional[str]) -> str:
    u = (user or "").strip()
    return u or "anon"


def _current_user_id_fallback() -> str:
    uid = st.session_state.get("user_id") or st.session_state.get("usuario") or ""
    return _normalize_user_id(str(uid))


def _normalize_timeline(timeline: Optional[str]) -> str:
    return (timeline or "").strip() or "cumplice"


def _user_key(user_id: str, timeline: str) -> str:
    return f"{user_id}::mary::{timeline}"


def _shared_key(user_id: str) -> str:
    return f"{user_id}::mary::shared"


def _current_user_key() -> str:
    uid = _current_user_id_fallback()
    tl = _normalize_timeline(str(st.session_state.get("mary_timeline") or "cumplice"))
    return _user_key(uid, tl)


def _shared_memory_key() -> str:
    uid = _current_user_id_fallback()
    return _shared_key(uid)


# ==========================================================
# NSFW TOGGLE (fonte de verdade é core.nsfw)
# ==========================================================
SAFE_SENSUAL_STYLE = """
[NSFW_OFF]
- Romance e tensão emocional OK.
- Evite descrição gráfica.
""".strip()

NSFW_TOGGLE_STYLE = """
[NSFW_ON]
- Linguagem adulta permitida conforme contexto.
- Coerência + consentimento + continuidade.
""".strip()


# ==========================================================
# CACHE (facts/history/memories)
# ==========================================================
def cached_get_facts(usuario_key: str) -> Dict[str, Any]:
    ck = f"facts::{usuario_key}"
    if ck in st.session_state:
        return st.session_state[ck]
    try:
        f = get_facts(usuario_key) or {}
    except Exception:
        f = {}
    st.session_state[ck] = f
    return f


def cached_get_history(usuario_key: str, limit: int = 400) -> List[Dict[str, Any]]:
    hk = f"history::{usuario_key}::{limit}"
    if hk in st.session_state:
        return st.session_state[hk]
    try:
        docs = get_history_docs(usuario_key, limit=limit) or []
    except Exception:
        docs = []
    st.session_state[hk] = docs
    return docs


def cached_list_memories(shared_key: str, limit: int = 200) -> List[Dict[str, Any]]:
    mk = f"mem::{shared_key}::{limit}"
    if mk in st.session_state:
        return st.session_state[mk]
    try:
        mems = list_memories(shared_key, limit=limit) or []
    except Exception:
        mems = []
    st.session_state[mk] = mems
    return mems


def clear_user_cache(usuario_key: str) -> None:
    fk = f"facts::{usuario_key}"
    st.session_state.pop(fk, None)

    prefix = f"history::{usuario_key}::"
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(prefix):
            st.session_state.pop(k, None)


def clear_mem_cache_for_shared(shared_key: str) -> None:
    prefix = f"mem::{shared_key}::"
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(prefix):
            st.session_state.pop(k, None)


def clear_shared_memory_cache(user_id: str) -> None:
    clear_mem_cache_for_shared(_shared_key(user_id))


# ==========================================================
# WRAPPERS DE ESCRITA
# ==========================================================
def set_fact_safe(usuario_key: str, key: str, value: Any, meta: Optional[dict] = None) -> None:
    set_fact(usuario_key, key, value, meta or {})
    clear_user_cache(usuario_key)


def append_memory_safe(
    shared_key: str,
    text: str,
    meta: Optional[dict] = None,
    *,
    user_id: Optional[str] = None,
) -> None:
    append_memory(shared_key, text, meta=meta or {})
    clear_mem_cache_for_shared(shared_key)
    if user_id:
        tl = _normalize_timeline(str(st.session_state.get("mary_timeline") or "cumplice"))
        clear_user_cache(_user_key(user_id, tl))


def append_long_memory_safe(shared_key: str, text: str, meta: Optional[dict] = None) -> None:
    append_long_memory(shared_key, text, meta=meta or {})


def save_interaction_safe(usuario_key: str, prompt: str, texto: str, model_used: str) -> None:
    save_interaction(usuario_key, prompt, texto, model_used)
    clear_user_cache(usuario_key)


# ==========================================================
# NSFW ENABLE
# ==========================================================
def nsfw_enabled(usuario_key: str, nsfw_override: Optional[bool] = None, timeline: Optional[str] = None) -> bool:
    return nsfw_enabled_unified(usuario_key, nsfw_override=nsfw_override, timeline=timeline)


# ==========================================================
# CONTINUIDADE ESPACIAL (Scene Lock)
# ==========================================================
def _get_scene_state(facts: Dict[str, Any]) -> Tuple[str, str, str]:
    local = str(facts.get("cena.local") or facts.get("local_cena_atual") or "—")
    tempo = str(facts.get("cena.tempo") or "agora")
    acao = str(facts.get("cena.acao") or "em andamento")
    return local, tempo, acao


def _scene_is_locked(facts: Dict[str, Any]) -> bool:
    return bool(facts.get("cena.locked", True))


def _lock_scene(usuario_key: str) -> None:
    set_fact_safe(usuario_key, "cena.locked", True, {"fonte": "scene_lock"})


def _persist_scene_basics(usuario_key: str, local: str, tempo: str, acao: str) -> None:
    if local:
        set_fact_safe(usuario_key, "cena.local", local, {"fonte": "scene"})
        set_fact_safe(usuario_key, "local_cena_atual", local, {"fonte": "scene_compat"})
    if tempo:
        set_fact_safe(usuario_key, "cena.tempo", tempo, {"fonte": "scene"})
    if acao:
        set_fact_safe(usuario_key, "cena.acao", acao, {"fonte": "scene"})


def _build_spatial_context(local: str, tempo: str, acao: str) -> str:
    if not local or local == "—":
        return ""
    return f"""
[CONTEXTO ESPACIAL — FIXO]
Local: {local}
Tempo: {tempo}
Ação: {acao}
""".strip()


def _user_requested_location_change(user_message: str) -> Tuple[bool, str]:
    patterns = [
        r"\bcorta\s+para\s+([^\n\r]+)$",
        r"\bhoras\s+depois\s*(?:,\s*)?([^\n\r]*)$",
        r"vamos (pro|pra|para o|para a)\s+([^\n\r,.!?]+)",
        r"me leva (pro|pra|para o|para a)\s+([^\n\r,.!?]+)",
        r"vamos para\s+([^\n\r,.!?]+)",
        r"ir para\s+([^\n\r,.!?]+)",
    ]
    msg = (user_message or "").lower().strip()
    for p in patterns:
        m = re.search(p, msg)
        if m:
            destino = (m.group(m.lastindex) or "").strip()
            return True, destino
    return False, ""


def _detect_scene_violation(user_text: str) -> bool:
    txt = (user_text or "").lower()

    if re.search(r"\bcorta\s+para\b", txt) or re.search(r"\bhoras\s+depois\b", txt):
        return False
    if re.search(r"\b(vamos|me leva|ir)\s+(pro|pra|para)\b", txt):
        return False

    patterns = [
        r"\bap[oó]s\s+isso\b",
        r"\bdepois\s+disso\b",
        r"\bmais\s+tarde\b",
        r"\bno\s+outro\s+dia\b",
        r"\bno\s+dia\s+seguinte\b",
        r"\benquanto\s+isso\b",
        r"\bcena\s+seguinte\b",
    ]
    return any(re.search(p, txt) for p in patterns)


# ==========================================================
# INTRO CANÔNICO (1x por sessão) — CONDICIONAL AO CANON
# ==========================================================
def _hash_text(text: str) -> str:
    t = (text or "").strip().encode("utf-8")
    return hashlib.sha256(t).hexdigest()


def _extract_intro_from_persona(timeline: str) -> Tuple[str, str]:
    _, history_boot = get_persona(timeline)

    intro_text = ""
    if isinstance(history_boot, list):
        for msg in history_boot:
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("content"):
                if msg.get("timeline") and str(msg.get("timeline")) != str(timeline):
                    continue
                intro_text = str(msg["content"]).strip()
                break

    if not intro_text:
        intro_text = "Eu já estava ali quando você chegou. Eu te vejo e espero sua atitude."

    intro_id = _hash_text(intro_text)
    return intro_id, intro_text


def _sync_intro_fact(usuario_key: str, timeline: str) -> Tuple[str, str]:
    prefix = f"mary.intro.{(timeline or '').strip() or 'cumplice'}"
    text_key = f"{prefix}.text"
    hash_key = f"{prefix}.hash"

    current_id, current_text = _extract_intro_from_persona(timeline)
    current_hash = current_id

    try:
        stored_hash = str(get_fact(usuario_key, hash_key, default="") or "").strip()
        stored_text = str(get_fact(usuario_key, text_key, default="") or "").strip()

        if (not stored_hash) or (stored_hash != current_hash) or (not stored_text):
            set_fact_safe(usuario_key, hash_key, current_hash, {"fonte": "persona_intro_sync"})
            set_fact_safe(usuario_key, text_key, current_text, {"fonte": "persona_intro_sync"})
            clear_user_cache(usuario_key)

        return current_id, current_text
    except Exception:
        return current_id, current_text


# ==========================================================
# CANON + MEMÓRIAS (shared)
# ==========================================================
def _memory_timeline_ok(meta: Dict[str, Any], timeline: str) -> bool:
    tl = _normalize_timeline(timeline)
    tms = str(meta.get("timeline_at_save") or meta.get("timeline") or "").strip()
    if not tms:
        return True
    return tms in (tl, "[all]")


def _has_canon_memories(shared_key: str, timeline: str) -> bool:
    mems = cached_list_memories(shared_key, limit=240)
    for m in mems:
        meta = m.get("meta") or {}
        if str(meta.get("kind") or "").strip().lower() != "canon":
            continue
        if _memory_timeline_ok(meta, timeline):
            return True
    return False


def _extract_canon_overrides(mems: List[Dict[str, Any]], timeline: str) -> List[Tuple[str, Any, str]]:
    out: List[Tuple[str, Any, str]] = []
    for m in mems or []:
        meta = m.get("meta") or {}
        if str(meta.get("kind") or "").strip().lower() != "canon":
            continue
        if not _memory_timeline_ok(meta, timeline):
            continue
        key = str(meta.get("key") or "").strip()
        if not key:
            continue
        value = meta.get("value")
        date_iso = str(meta.get("date") or "").strip()
        out.append((key, value, date_iso))
    return out


def _build_overrides_block(overrides: List[Tuple[str, Any, str]]) -> str:
    if not overrides:
        return ""
    lines = ["[FATOS CANÔNICOS — OVERRIDES]"]
    for key, value, date_iso in overrides:
        if isinstance(value, bool):
            v = "true" if value else "false"
        elif value is None:
            v = "null"
        else:
            v = str(value)
        lines.append(f"- {key} = {v}" + (f" (desde {date_iso})" if date_iso else ""))
    return "\n".join(lines).strip()


def _inject_canon_memories_always(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    max_items: int = 80,
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    mems = cached_list_memories(shared_key, limit=360)
    if not mems:
        return

    canon: List[Dict[str, Any]] = []
    for m in mems:
        meta = m.get("meta") or {}
        if str(meta.get("kind") or "").strip().lower() != "canon":
            continue
        if not _memory_timeline_ok(meta, timeline):
            continue
        canon.append(m)

    if not canon:
        return

    selected = canon[-max_items:] if len(canon) > max_items else canon
    overrides = _extract_canon_overrides(selected, timeline)
    overrides_block = _build_overrides_block(overrides)

    lines: List[str] = []
    lines.append("[MEMÓRIAS CANÔNICAS — COMPARTILHADAS]")
    lines.append("Fatos do universo. Se a persona contradizer, estas memórias vencem.")
    lines.append("")
    if overrides_block:
        lines.append(overrides_block)
        lines.append("")

    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        title = meta.get("title") or meta.get("key") or ""
        header = f"- CANON {i}"
        if d:
            header += f" (data: {d})"
        if title:
            header += f" — {title}"
        lines.append(header)

        txt = str(m.get("text") or "").strip()
        lines.append(txt)
        lines.append("")

        if dedupe_bucket is not None and txt:
            dedupe_bucket.add(hashlib.sha1(txt.encode("utf-8")).hexdigest())

    messages.append({"role": "system", "content": "\n".join(lines).strip()})


def _inject_intro_as_context_once(
    usuario_key: str,
    timeline: str,
    shared_key: str,
    messages: List[Dict[str, str]],
) -> None:
    flag = f"intro_ctx_injected::{usuario_key}"
    if st.session_state.get(flag):
        return

    if _has_canon_memories(shared_key, timeline):
        st.session_state[flag] = True
        return

    _, intro_text = _sync_intro_fact(usuario_key, timeline)
    intro_text = (intro_text or "").strip()
    if intro_text:
        messages.append({"role": "system", "content": f"[QUADRO ZERO — INTRO]\n{intro_text}"})
    st.session_state[flag] = True


def _inject_shared_soft_context(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    max_items: int = 8,
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    mems = cached_list_memories(shared_key, limit=220)
    if not mems:
        return

    soft: List[Dict[str, Any]] = []
    for m in mems:
        meta = m.get("meta") or {}
        kind = str(meta.get("kind") or "").strip().lower()
        if kind == "canon":
            continue
        if not _memory_timeline_ok(meta, timeline):
            continue
        txt = str(m.get("text") or "").strip()
        if not txt:
            continue
        if dedupe_bucket is not None:
            h = hashlib.sha1(txt.encode("utf-8")).hexdigest()
            if h in dedupe_bucket:
                continue
        soft.append(m)

    if not soft:
        return

    selected = soft[-max_items:] if len(soft) > max_items else soft

    lines = ["[MEMÓRIAS COMPARTILHADAS — SUAVE]", "Use para coerência. Não citar literalmente.", ""]
    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        header = f"- MEM {i}" + (f" (data: {d})" if d else "")
        lines.append(header)
        txt = str(m.get("text") or "").strip()
        lines.append(txt)
        lines.append("")
        if dedupe_bucket is not None and txt:
            dedupe_bucket.add(hashlib.sha1(txt.encode("utf-8")).hexdigest())

    messages.append({"role": "system", "content": "\n".join(lines).strip()})


# ==========================================================
# LONG MEMORY ($text)
# ==========================================================
def _inject_long_memory_textsearch(
    shared_key: str,
    timeline: str,
    user_prompt: str,
    messages: List[Dict[str, str]],
    *,
    limit: int = 10,
    dedupe_bucket: Optional[set] = None,
) -> None:
    try:
        rows = search_long_memory_text(shared_key, user_prompt, limit=max(1, int(limit or 10)))
    except Exception:
        rows = []

    if not rows:
        return

    picked: List[Dict[str, Any]] = []
    tl = _normalize_timeline(timeline)

    for d in rows:
        txt = str(d.get("text") or "").strip()
        if not txt:
            continue

        meta = d.get("meta") or {}
        if not isinstance(meta, dict):
            meta = {}

        tms = str(meta.get("timeline_at_save") or meta.get("timeline") or "").strip()
        if tms and tms not in (tl, "[all]"):
            continue

        kind = str(meta.get("kind") or "").strip().lower()
        if kind == "canon":
            continue

        if dedupe_bucket is not None:
            h = hashlib.sha1(txt.encode("utf-8")).hexdigest()
            if h in dedupe_bucket:
                continue
            dedupe_bucket.add(h)

        picked.append(d)
        if len(picked) >= int(limit or 10):
            break

    if not picked:
        return

    lines = ["[LONG MEMORY — $text]", "Use para continuidade. Não citar literalmente.", ""]
    for i, d in enumerate(picked, 1):
        meta = d.get("meta") or {}
        title = str(meta.get("title") or meta.get("key") or "").strip() if isinstance(meta, dict) else ""
        ts = d.get("ts") or ""
        header = f"- LM {i}" + (f" (ts: {ts})" if ts else "") + (f" — {title}" if title else "")
        lines.append(header)
        lines.append(str(d.get("text") or "").strip())
        lines.append("")

    messages.append({"role": "system", "content": "\n".join(lines).strip()})


# ==========================================================
# BM25 LEVE
# ==========================================================
_WORD_RE = re.compile(r"[\w\u00C0-\u017F']+", re.UNICODE)


def _tok(text: str) -> List[str]:
    return [t.lower() for t in _WORD_RE.findall(text or "") if t.strip()]


def _bm25_topk(docs: List[str], query: str, k: int = 8) -> List[int]:
    q = _tok(query)
    if not docs or not q:
        return []
    N = len(docs)

    tf_list: List[Dict[str, int]] = []
    df: Dict[str, int] = {}
    lengths: List[int] = []

    for d in docs:
        toks = _tok(d)
        lengths.append(len(toks))
        tf: Dict[str, int] = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        tf_list.append(tf)
        for w in set(tf.keys()):
            df[w] = df.get(w, 0) + 1

    avgdl = (sum(lengths) / N) if N else 1.0
    k1 = 1.5
    b = 0.75

    def _idf_raw(w: str) -> float:
        n_q = df.get(w, 0)
        return max(0.0, ((N - n_q + 0.5) / (n_q + 0.5)))

    import math
    idf_cache = {w: math.log(1.0 + _idf_raw(w)) for w in set(q)}

    scores: List[float] = []
    for i, tf in enumerate(tf_list):
        dl = lengths[i] or 1
        s = 0.0
        for w in q:
            f = tf.get(w, 0)
            if not f:
                continue
            w_idf = idf_cache.get(w, 0.0)
            denom = f + k1 * (1 - b + b * (dl / avgdl))
            s += w_idf * (f * (k1 + 1)) / denom
        scores.append(s)

    ranked = sorted(range(N), key=lambda i: scores[i], reverse=True)
    ranked = [i for i in ranked if scores[i] > 0.0]
    return ranked[: max(0, int(k))]


def _inject_relevant_memories(
    shared_key: str,
    timeline: str,
    user_prompt: str,
    messages: List[Dict[str, str]],
    k: int = 8,
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    mems = cached_list_memories(shared_key, limit=260)
    if not mems:
        return

    soft: List[Dict[str, Any]] = []
    docs: List[str] = []

    for m in mems:
        meta = m.get("meta") or {}
        kind = str(meta.get("kind") or "").strip().lower()
        if kind == "canon":
            continue
        if not _memory_timeline_ok(meta, timeline):
            continue

        text = str(m.get("text") or "").strip()
        if not text:
            continue

        if dedupe_bucket is not None:
            h = hashlib.sha1(text.encode("utf-8")).hexdigest()
            if h in dedupe_bucket:
                continue

        soft.append(m)
        title = str(meta.get("title") or meta.get("key") or "").strip()
        docs.append(f"{title}\n{text}" if title else text)

    if not soft:
        return

    idxs = _bm25_topk(docs, user_prompt, k=k)
    if not idxs:
        return

    selected = [soft[i] for i in idxs if 0 <= i < len(soft)]
    if not selected:
        return

    lines = ["[MEMÓRIAS RELEVANTES — BM25]", "Use para coerência. Não citar literalmente.", ""]
    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        title = meta.get("title") or meta.get("key") or ""
        header = f"- REL {i}" + (f" (data: {d})" if d else "") + (f" — {title}" if title else "")
        lines.append(header)
        txt = str(m.get("text") or "").strip()
        lines.append(txt)
        lines.append("")
        if dedupe_bucket is not None and txt:
            dedupe_bucket.add(hashlib.sha1(txt.encode("utf-8")).hexdigest())

    messages.append({"role": "system", "content": "\n".join(lines).strip()})


# ==========================================================
# MEMÓRIAS PERMANENTES — comandos e parsing
# ==========================================================
_SAVE_RE = re.compile(r"^\s*(?:mary\s*,?\s*)?(?:salve|salvar|guarde)\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})\b")
_SUMMARY_HINT_RE = re.compile(r"\b(resumo|resuma|resumir|resumindo)\b", re.IGNORECASE)
_RANGE_RE = re.compile(r"\bde\s+(?P<start>.+?)\s+at[ée]\s+(?P<end>.+?)\s*$", re.IGNORECASE | re.DOTALL)


def _is_save_memory_command(user_text: str) -> bool:
    return bool(_SAVE_RE.search(user_text or ""))


def _wants_auto_summary(user_text: str) -> bool:
    return bool(_SUMMARY_HINT_RE.search(user_text or ""))


def _extract_date_iso(text: str) -> Optional[str]:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    d, mo, y = m.group(1), m.group(2), m.group(3)
    try:
        dd = int(d)
        mm = int(mo)
        yy = int(y)
        if 1 <= dd <= 31 and 1 <= mm <= 12:
            return f"{yy:04d}-{mm:02d}-{dd:02d}"
    except Exception:
        return None
    return None


def _strip_save_prefix(full_text: str) -> str:
    t = (full_text or "").strip()
    m = _SAVE_RE.search(t)
    if not m:
        return t
    rest = t[m.end():].strip()
    rest = re.sub(r"^\s*(na|no|em)\s+mem[oó]ria\s+permanente\b\s*:?\s*", "", rest, flags=re.IGNORECASE)
    rest = re.sub(r"^\s*(como|que)\s+", "", rest, flags=re.IGNORECASE)
    return rest.strip() or t


def _fallback_capture_recent_history(usuario_key: str, turns: int = 8) -> str:
    docs = cached_get_history(usuario_key, limit=400)
    if not docs:
        return ""
    slice_docs = docs[-turns:]
    chunks: List[str] = []
    for d in slice_docs:
        u = (d.get("mensagem_usuario") or "").strip()
        a = (d.get("resposta_mary") or "").strip()
        if u:
            chunks.append(f"USUÁRIO:\n{u}")
        if a:
            chunks.append(f"MARY:\n{a}")
    return "\n\n".join(chunks).strip()


def _extract_range_request(user_text: str) -> Tuple[Optional[str], Optional[str]]:
    t = (user_text or "").strip()
    m = _RANGE_RE.search(t)
    if not m:
        return None, None
    start = (m.group("start") or "").strip(" \n\r\t\"'.,:;")
    end = (m.group("end") or "").strip(" \n\r\t\"'.,:;")
    if len(start) < 3 or len(end) < 3:
        return None, None
    return start, end


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _mary_only_turns(usuario_key: str, limit_turns: int = 120) -> List[str]:
    docs = get_history_docs(usuario_key, limit=400) or []
    docs = docs[-limit_turns:] if len(docs) > limit_turns else docs
    out: List[str] = []
    for d in docs:
        a = (d.get("resposta_mary") or "").strip()
        if a:
            out.append(a)
    return out


def _slice_mary_between_markers(mary_msgs: List[str], start_hint: str, end_hint: str) -> Tuple[List[str], str]:
    if not mary_msgs:
        return [], "no_history"

    sh = _normalize(start_hint)
    eh = _normalize(end_hint)

    def find_idx(hint: str) -> Optional[int]:
        if not hint:
            return None
        for i, msg in enumerate(mary_msgs):
            if hint in _normalize(msg):
                return i
        return None

    i0 = find_idx(sh)
    i1 = find_idx(eh)

    if i0 is None and i1 is None:
        return [], "markers_not_found"

    if i0 is None and i1 is not None:
        i0 = max(0, i1 - 8)
        return mary_msgs[i0:i1 + 1], "only_end_found"

    if i0 is not None and i1 is None:
        i1 = min(len(mary_msgs) - 1, i0 + 8)
        return mary_msgs[i0:i1 + 1], "only_start_found"

    if i0 is not None and i1 is not None:
        if i1 < i0:
            i0, i1 = i1, i0
            return mary_msgs[i0:i1 + 1], "markers_swapped"
        return mary_msgs[i0:i1 + 1], "both_found"

    return [], "unexpected"


def _build_dynamic_mary_transcript(usuario_key: str, prompt: str) -> Tuple[str, Dict[str, Any]]:
    start_hint, end_hint = _extract_range_request(prompt)
    mary_msgs = _mary_only_turns(usuario_key, limit_turns=160)

    if start_hint and end_hint:
        sliced, dbg = _slice_mary_between_markers(mary_msgs, start_hint, end_hint)
        if not sliced:
            sliced = mary_msgs[-10:]
            dbg = f"{dbg}__fallback_last10"
        transcript = "\n\n".join([f"[MARY #{i + 1}]\n{m}" for i, m in enumerate(sliced)])
        meta = {
            "mode": "dynamic_range",
            "debug": dbg,
            "start_hint": start_hint,
            "end_hint": end_hint,
            "mary_msgs_used": len(sliced),
        }
        return transcript.strip(), meta

    sliced = mary_msgs[-10:]
    transcript = "\n\n".join([f"[MARY #{i + 1}]\n{m}" for i, m in enumerate(sliced)])
    meta = {"mode": "fallback_last10", "debug": "no_range_in_prompt", "mary_msgs_used": len(sliced)}
    return transcript.strip(), meta


# ==========================================================
# RELATIONSHIP STATE
# ==========================================================
def _rel_fact_key(timeline: str) -> str:
    tl = (timeline or "").strip() or "cumplice"
    return f"rel.state::{tl}"


def _load_rel_state(
    facts: Dict[str, Any],
    timeline: str,
    canon_default: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = default_relationship_state(timeline)

    if isinstance(canon_default, dict):
        for k, v in canon_default.items():
            if not str(k).startswith("_"):
                base[k] = v

    key = _rel_fact_key(timeline)
    raw = (facts or {}).get(key)
    if isinstance(raw, dict):
        for k, v in raw.items():
            base[k] = v

    base.setdefault("_promote_streak", 0)
    base.setdefault("_regress_streak", 0)
    base.setdefault("_loop_streak", 0)
    base.setdefault("_last_pattern", "")
    base.setdefault("_last_updated_ts", 0)

    base.setdefault("mature_turns", 0)
    base.setdefault("intimacy_level", 0 if timeline == "universitaria" else 3)
    base.setdefault("consummated", False if timeline == "universitaria" else True)
    base.setdefault("virginity", "virgem" if timeline == "universitaria" else "nao_virgem")

    base.setdefault("desire", 25 if timeline == "universitaria" else 45)
    base.setdefault("arousal", 18 if timeline == "universitaria" else 35)
    base.setdefault("self_control", 72 if timeline == "universitaria" else 45)

    base.setdefault("allows_touch", True)
    base.setdefault("allows_extended_touch", False if timeline == "universitaria" else True)
    base.setdefault("allows_sleep_together", False if timeline == "universitaria" else True)
    base.setdefault("allows_masturbation", True)
    base.setdefault("allows_mutual_relief", False if timeline == "universitaria" else True)
    base.setdefault("allows_penetration", False if timeline == "universitaria" else True)

    if not base.get("stage"):
        base["stage"] = "conhecendo" if timeline == "universitaria" else "casados"

    return base


def _save_rel_state(usuario_key: str, timeline: str, rel: Dict[str, Any]) -> None:
    set_fact_safe(usuario_key, _rel_fact_key(timeline), rel, {"fonte": "relationship_engine"})


def _ensure_rel_state_for_timeline(user_id: str, timeline: str) -> None:
    tl = _normalize_timeline(timeline)
    uk = _user_key(user_id, tl)
    facts = cached_get_facts(uk)
    key = _rel_fact_key(tl)

    if isinstance((facts or {}).get(key), dict):
        return

    canon = get_canon("mary", timeline=tl, user_key=user_id) or {}
    canon_rel_default = canon.get("relationship_state") if isinstance(canon.get("relationship_state"), dict) else None
    rel = _load_rel_state(facts or {}, tl, canon_rel_default)

    try:
        _save_rel_state(uk, tl, rel)
        clear_user_cache(uk)
    except Exception:
        pass


# ==========================================================
# INTIMACY: sinais e travas
# ==========================================================
_RE_CLIMAX_SIGNAL = re.compile(r"\b(goza|orgasmo|gozar|goze|gozando)\b", re.IGNORECASE)
_RE_AFTERCARE_SIGNAL = re.compile(r"\b(depois|abraça|acolhe|dorme|banho|água|calma|carinho)\b", re.IGNORECASE)

_RE_ESCALATE_0_TO_1 = re.compile(r"\b(beijo|beij[oa]|encosta|toque|abraço|aproximo)\b", re.IGNORECASE)
_RE_ESCALATE_1_TO_2 = re.compile(r"\b(roupa|tirar|entre as pernas|boca|língua|calcinha|sutiã)\b", re.IGNORECASE)
_RE_ESCALATE_2_TO_3 = re.compile(r"\b(quase|devagar|controle|nega|provoca|implorar)\b", re.IGNORECASE)


def _user_explicitly_allows_climax(user_text: str) -> bool:
    return bool(_RE_CLIMAX_SIGNAL.search(user_text or ""))


def _user_signals_aftercare(user_text: str) -> bool:
    return bool(_RE_AFTERCARE_SIGNAL.search(user_text or ""))


def _should_advance_phase(
    current_phase: int,
    user_text: str,
    mary_text: str,
    *,
    engine_meta: Optional[Dict[str, Any]] = None,
) -> bool:
    meta = engine_meta or {}
    if isinstance(meta.get("intimacy_progressed"), bool):
        return bool(meta["intimacy_progressed"])

    ut = (user_text or "")
    mt = (mary_text or "")

    if current_phase == 0:
        return bool(_RE_ESCALATE_0_TO_1.search(ut) or _RE_ESCALATE_0_TO_1.search(mt))
    if current_phase == 1:
        return bool(_RE_ESCALATE_1_TO_2.search(ut) or _RE_ESCALATE_1_TO_2.search(mt))
    if current_phase == 2:
        return bool(_RE_ESCALATE_2_TO_3.search(ut) or _RE_ESCALATE_2_TO_3.search(mt))
    if current_phase == 3:
        return _user_explicitly_allows_climax(ut)
    if current_phase == 4:
        return _user_signals_aftercare(ut)
    return False


def _cap_next_phase(current_phase: int, desired_next: int) -> int:
    return min(desired_next, current_phase + 1)


# ==========================================================
# CONFLICT_MODE
# ==========================================================
def _resolve_conflict_mode(timeline: str) -> str:
    tl = _normalize_timeline(timeline)
    if tl in ("cumplice", "esposa_cumplice", "casados", "livre"):
        return "soft"
    if tl in ("universitaria",):
        return "off"
    return "soft"


_RE_CONFLICT_IMMINENT = re.compile(
    r"\b(briga|agarr(a|o|ou)|segura|empurra|amea(c|ç)a|grita|bater|soco|chute|murro|"
    r"arrasta|seguran(ç|c)a|pol[ií]cia|expulsa|invad(i|ir)|porta arromb)\b",
    re.IGNORECASE,
)


def _conflict_imminent(user_text: str) -> bool:
    return bool(_RE_CONFLICT_IMMINENT.search(user_text or ""))


# ==========================================================
# GATE ANTI-VAZAMENTO (NPC GENÉRICO + OFFSCREEN)
# ==========================================================
# Converte "NOME:" -> "NPC:" (exceto MARY/USUÁRIO/SISTEMA)
_RE_SPEAKER = re.compile(r"(?m)^\s*([A-ZÀ-Ÿ][\wÀ-ÿ'\- ]{1,24})\s*:\s+")
_ALLOWED_SPEAKERS = {"MARY", "USUÁRIO", "USUARIO", "SYSTEM", "SISTEMA", "NPC"}

# Remove "Seu Nome" e nomes capitalizados no meio
_RE_SEU_NOME = re.compile(r"\b(seu|sua)\s+[A-ZÀ-Ÿ][\wÀ-ÿ'-]{1,}\b")
_RE_CAPITAL_MID = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-ZÀ-Ÿ][a-zà-ÿ]{2,}\b")

# Frases de "conhecimento indevido" por NPC
_RE_ILLEGAL_KNOW = re.compile(
    r"(?i)\b(eu\s+sei|eu\s+li|eu\s+vi|eu\s+descobri|no\s+seu\s+celular|tua\s+mensagem|sua\s+mensagem|seu\s+plano)\b"
)

# Offscreen: “Mensagem de X:”, “O celular vibra...”, conteúdo inventado
_RE_OFFSCREEN_TRIGGER = re.compile(r"(?i)\b(celular\s+vibra|mensagem\s+chega|mensagem\s+de\s+.+?:)\b")
_RE_QUOTED = re.compile(r"[\"“”].+?[\"“”]")


def _normalize_speaker_labels(text: str) -> str:
    if not text:
        return text

    def repl(m: re.Match) -> str:
        spk = (m.group(1) or "").strip()
        spk_u = spk.upper()
        if spk_u in _ALLOWED_SPEAKERS:
            return f"{spk_u}: "
        return "NPC: "

    return _RE_SPEAKER.sub(repl, text)


def _sanitize_npc_lines(text: str) -> str:
    if not text:
        return text

    lines = text.splitlines()
    out: List[str] = []

    for ln in lines:
        if re.match(r"(?i)^\s*NPC\s*:\s*", ln):
            content = re.sub(r"(?i)^\s*NPC\s*:\s*", "", ln).strip()

            # remove "Seu Nome"
            content = _RE_SEU_NOME.sub("isso", content)

            # remove capitalizadas no meio
            content = _RE_CAPITAL_MID.sub("", content)

            # se confirmou conhecimento/logística/segredo => vira ambiguidade
            if _RE_ILLEGAL_KNOW.search(content):
                content = "…tá escondendo alguma coisa, né? Eu só testo, sem afirmar nada."

            content = re.sub(r"\s{2,}", " ", content).strip()
            out.append(f"NPC: {content}".rstrip())
        else:
            out.append(ln)

    return "\n".join(out).strip()


def _sanitize_offscreen(text: str, user_prompt: str) -> str:
    """
    Se o modelo inventar conteúdo de mensagem, troca por ambiguidade.
    Não depende de entidades.
    """
    if not text:
        return text

    # Se o usuário colou explicitamente uma mensagem (ex.: "Mensagem de Janio: ..."), não sanitiza quotes
    user_has_message_dump = bool(re.search(r"(?i)\bmensagem\s+de\s+.+?:", user_prompt or ""))

    if not _RE_OFFSCREEN_TRIGGER.search(text):
        return text

    # Se o usuário NÃO colou dump, remover conteúdo citado de mensagens
    if not user_has_message_dump:
        # troca qualquer "Mensagem de X:" por "Uma mensagem chega."
        text = re.sub(r"(?im)^\s*mensagem\s+de\s+.+?:\s*$", "Uma mensagem chega.", text)
        # remove trechos entre aspas que pareçam "conteúdo de mensagem" perto de gatilhos
        # (heurística: se tiver trigger, qualquer quoted no texto vira [mensagem não revelada])
        text = _RE_QUOTED.sub("[mensagem não revelada]", text)

    return text.strip()


def _apply_leakage_gate(assistant_text: str, user_prompt: str) -> str:
    """
    Pipeline:
    1) Normaliza qualquer falante extra -> NPC:
    2) Sanitiza falas de NPC (sem nomes/sem confirmação)
    3) Sanitiza mensagens offscreen inventadas
    """
    t = (assistant_text or "").strip()
    t = _normalize_speaker_labels(t)
    t = _sanitize_npc_lines(t)
    t = _sanitize_offscreen(t, user_prompt)
    return t.strip()


# ==========================================================
# SERVICE
# ==========================================================
class MaryService(BaseCharacter):
    id = "mary"
    display_name = "Mary"

    def reply(
        self,
        user: str,
        model: str,
        *,
        prompt: Optional[str] = None,
        timeline: Optional[str] = None,
        nsfw: Optional[bool] = None,
    ) -> str:
        # prompt
        if prompt is None:
            prompt = (st.session_state.get("chat_input") or "").strip()
        else:
            prompt = (prompt or "").strip()

        if not prompt:
            return ""

        user_id = _normalize_user_id(user) if user else _current_user_id_fallback()
        timeline_final = _normalize_timeline(timeline) if timeline else _normalize_timeline(
            str(st.session_state.get("mary_timeline") or "cumplice")
        )

        usuario_key = _user_key(user_id, timeline_final)
        shared_key = _shared_key(user_id)

        # 0) scene lock + facts mínimos
        facts0 = cached_get_facts(usuario_key)
        if "cena.locked" not in facts0:
            _lock_scene(usuario_key)

        # 0.1) intimacy phase init
        if "intimacy.phase" not in facts0:
            set_fact_safe(usuario_key, "intimacy.phase", 0, {"fonte": "intimacy_init"})
            facts0["intimacy.phase"] = 0

        # 1) mudança explícita de local/tempo
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou and novo_local:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            _lock_scene(usuario_key)
            return f"_Eu te puxo comigo até **{novo_local}**…_"

        # 1.1) cena paralela
        facts_pre = cached_get_facts(usuario_key)
        scene_locked = _scene_is_locked(facts_pre)
        scene_parallel = bool(scene_locked and _detect_scene_violation(prompt))

        # 2) comando salvar memória
        if _is_save_memory_command(prompt):
            raw_body = _strip_save_prefix(prompt)
            date_iso = _extract_date_iso(prompt) or _extract_date_iso(raw_body)

            # resumo dinâmico
            if _wants_auto_summary(prompt):
                transcript, dbg_meta = _build_dynamic_mary_transcript(usuario_key, prompt)
                if not transcript.strip():
                    return "⚠️ Não encontrei histórico suficiente da Mary para resumir."

                summary_system = (
                    "Tarefa: gerar RESUMO FACTUAL para memória.\n"
                    "REGRAS:\n"
                    "- Use SOMENTE o que está em [TRANSCRIÇÃO].\n"
                    "- NÃO invente.\n"
                    "- Texto corrido, PT-BR, 8 a 16 linhas.\n"
                )
                summary_user = (
                    "Gere resumo factual para memória permanente.\n"
                    f"Data: {date_iso or '—'}\n\n"
                    f"[TRANSCRIÇÃO — APENAS FALAS DA MARY]\n{transcript}"
                )

                try:
                    data, used_model, _ = self._chat(
                        model,
                        [{"role": "system", "content": summary_system}, {"role": "user", "content": summary_user}],
                        temperature=0.2,
                        max_tokens=850,
                    )
                    resumo = self._extract_text(data)
                    if not resumo:
                        return "⚠️ Resumo vazio. Tente novamente."

                    meta = {
                        "kind": "dynamic_summary",
                        "date": date_iso or "",
                        "timeline_at_save": timeline_final,
                        "model_used": used_model or model,
                        **(dbg_meta or {}),
                    }

                    append_memory_safe(shared_key, resumo.strip(), meta=meta, user_id=user_id)
                    append_long_memory_safe(
                        shared_key,
                        resumo.strip(),
                        meta={**meta, "source": "ui_long_memory", "user_id": user_id, "timeline_at_save": timeline_final},
                    )
                    return "✅ Resumo salvo na memória permanente."

                except Exception as e:
                    logger.exception("Falha resumo dinâmico", exc_info=e)
                    return f"⚠️ Falha ao salvar resumo: {type(e).__name__}: {e}"

            # salvamento direto
            body = raw_body
            if len(body.strip()) < 40:
                captured = _fallback_capture_recent_history(usuario_key, turns=10)
                if captured:
                    body = f"{body}\n\n[FONTE: recorte do histórico]\n{captured}".strip()

            if not body.strip():
                return "⚠️ Cole o texto do momento (ou descreva) e informe a data (dd/mm/aaaa)."

            meta = {"kind": "user_request", "date": date_iso or "", "timeline_at_save": timeline_final}
            try:
                append_memory_safe(shared_key, body.strip(), meta=meta, user_id=user_id)
                append_long_memory_safe(
                    shared_key,
                    body.strip(),
                    meta={**meta, "source": "ui_long_memory", "user_id": user_id, "timeline_at_save": timeline_final},
                )
            except Exception as e:
                logger.exception("Falha ao salvar memória", exc_info=e)
                return f"⚠️ Falha ao salvar memória: {type(e).__name__}: {e}"

            return "✅ Memória permanente salva."

        # 3) Persona + system
        persona_text, _ = get_persona(timeline_final)
        facts = cached_get_facts(usuario_key)

        if "intimacy.phase" not in facts:
            set_fact_safe(usuario_key, "intimacy.phase", 0, {"fonte": "intimacy_init_late"})
            facts["intimacy.phase"] = 0

        # conflict
        conflict_mode = _resolve_conflict_mode(timeline_final)
        conflict_now = (conflict_mode != "off") and _conflict_imminent(prompt)

        canon = get_canon("mary", timeline=timeline_final, user_key=user_id) or {}
        canon_txt = canon_to_text(canon)

        canon_rel_default = canon.get("relationship_state") if isinstance(canon.get("relationship_state"), dict) else None
        rel_state = _load_rel_state(facts, timeline_final, canon_rel_default)
        rel_block = rel_state_to_prompt_block(rel_state)

        scene_loc, scene_time, scene_action = _get_scene_state(facts)
        spatial_context = _build_spatial_context(scene_loc, scene_time, scene_action)

        nsfw_on = nsfw_enabled(usuario_key, nsfw_override=nsfw, timeline=timeline_final)
        nsfw_block = NSFW_TOGGLE_STYLE if nsfw_on else SAFE_SENSUAL_STYLE

        # ===== REGRAS CURTAS (v3.18) =====
        user_authorship_rule = """
[REGRA DE AUTORIA DO USUÁRIO — ABSOLUTA]
- Mary NÃO inventa ações/falas/pensamentos do usuário.
- Mary só reage ao que o usuário declarou.
""".strip()

        npc_structure_rule = """
[REGRA ESTRUTURAL — NPC GENÉRICO]
- Qualquer personagem extra deve ser rotulado APENAS como "NPC:" (sem nomes).
- "NPC:" NÃO pode citar nomes próprios nem "Seu <nome>".
- Se houver segredo, "NPC:" só pode DESCONFIAR/INSINUAR (nunca confirmar).
""".strip()

        offscreen_rule = """
[OFFSCREEN — ABSOLUTO]
- "Celular vibra / mensagem chega" pode existir como detalhe, mas é PROIBIDO inventar o conteúdo.
- Só reproduza conteúdo se o usuário colar o texto.
""".strip()

        scene_lock_rule = """
[CONTINUIDADE]
- Mary não muda local/tempo sozinha.
- Se o usuário narrar outro lugar/tempo: tratar como paralelo (Mary fica onde está).
""".strip()

        parallel_scene_rule = (
            "[CENA PARALELA] O usuário descreveu eventos paralelos. Mary permanece na cena atual."
            if scene_parallel
            else ""
        )

        manipulation_block = """
[MARY — DISCRETA/ESTRATEGISTA]
- Sutileza. Conduz por micro-ação e micro-intenção.
- Não teatralize. Não explique “manipulação”.
""".strip()

        pacing_rule = """
[PACING]
- 1 micro-ação + 1 micro-decisão no máximo.
- Não conclua tudo num turno.
- Não termine com pergunta ao usuário.
""".strip()

        intimacy_phase = self._get_intimacy_phase(facts)
        intimacy_control_block = f"""
[INTIMACY_PHASE]
Atual: {intimacy_phase} ({INTIMACY_PHASES.get(intimacy_phase, '—')})
- Avança no máximo 1 fase por turno.
- Fase 4 (clímax) só com sinal explícito do usuário.
""".strip()

        conflict_block = ""
        if conflict_mode != "off":
            conflict_block = f"""
[CONFLICT_MODE — {conflict_mode.upper()}]
- Reaja com realismo e proporcionalidade.
- Evite violência extrema e detalhes gráficos.
""".strip()

        system = f"""
{spatial_context}

VOCÊ É MARY.
Primeira pessoa. Coerência absoluta.

{user_authorship_rule}
{npc_structure_rule}
{offscreen_rule}

TIMELINE: {timeline_final}

[CANON]
{canon_txt}

[PERSONA]
{persona_text}

{rel_block}

{scene_lock_rule}
{parallel_scene_rule}

{manipulation_block}
{pacing_rule}
{conflict_block}

REGRAS ABSOLUTAS:
- NÃO misture timelines.
- NÃO avance cena sem comando explícito.
- Se CANON contradizer a persona, CANON vence.

{intimacy_control_block}

{nsfw_block}
""".strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]

        # dedupe
        dedupe_hashes: set = set()

        # Intro 1x (só se não houver canon aplicável)
        _inject_intro_as_context_once(usuario_key, timeline_final, shared_key, messages)

        # CANON
        _inject_canon_memories_always(shared_key, timeline_final, messages, max_items=80, dedupe_bucket=dedupe_hashes)

        # LONGMEM
        _inject_long_memory_textsearch(shared_key, timeline_final, prompt, messages, limit=10, dedupe_bucket=dedupe_hashes)

        # BM25
        _inject_relevant_memories(shared_key, timeline_final, prompt, messages, k=8, dedupe_bucket=dedupe_hashes)

        # SUAVE
        _inject_shared_soft_context(shared_key, timeline_final, messages, max_items=8, dedupe_bucket=dedupe_hashes)

        # histórico
        history = cached_get_history(usuario_key, limit=400)
        for d in history[-30:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": u})
            if a:
                messages.append({"role": "assistant", "content": a})

        messages.append({"role": "user", "content": prompt})

        # attempts
        if nsfw_on:
            attempts = [{"model": model, "temperature": 0.85}, {"model": model, "temperature": 0.70}]
        else:
            attempts = [
                {"model": model, "temperature": 0.75},
                {"model": model, "temperature": 0.55},
                {"model": "deepseek/deepseek-chat-v3-0324", "temperature": 0.65},
            ]

        last_err: Optional[Exception] = None

        for attempt in attempts:
            try:
                data, used_model, _provider_meta = self._chat(
                    attempt["model"],
                    messages,
                    temperature=attempt["temperature"],
                    max_tokens=1400,
                )

                texto = self._extract_text(data)
                if not texto:
                    continue

                # ✅ GATE ANTI-VAZAMENTO (sem entidades fixas)
                texto = _apply_leakage_gate(texto, prompt)

                # Relationship Engine (pós-resposta)
                promoted = False
                meta: Dict[str, Any] = {}

                if conflict_now:
                    meta = {"conflict_mode": conflict_mode, "conflict_now": True}
                else:
                    try:
                        assessor_model = used_model or attempt["model"]

                        def _assessor(system_prompt: str, user_prompt: str) -> str:
                            data2, _, _ = self._chat(
                                assessor_model,
                                [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                                temperature=0.0,
                                max_tokens=280,
                            )
                            return self._extract_text(data2)

                        new_rel, _assessment, meta = evolve_relationship(
                            rel_state,
                            prompt,
                            texto,
                            timeline_final,
                            _assessor,
                            cfg=EngineConfig(),
                        )

                        rel_state = new_rel
                        _save_rel_state(usuario_key, timeline_final, rel_state)

                        # Promoção automática universitária -> cúmplice
                        if timeline_final == "universitaria" and meta.get("suggested_timeline") == "cumplice":
                            promoted = True
                            old_key = usuario_key
                            old_tl = timeline_final

                            st.session_state["mary_timeline"] = "cumplice"
                            _ensure_rel_state_for_timeline(user_id, "cumplice")

                            timeline_final = "cumplice"
                            usuario_key = _user_key(user_id, "cumplice")

                            clear_user_cache(old_key)
                            clear_user_cache(usuario_key)
                            clear_shared_memory_cache(user_id)

                            st.session_state.pop(f"intro_ctx_injected::{old_key}", None)
                            st.session_state.pop(f"intro_ctx_injected::{usuario_key}", None)

                            for k in list(st.session_state.keys()):
                                if isinstance(k, str) and (
                                    k.startswith(f"history::{old_key}::") or k.startswith(f"history::{usuario_key}::")
                                ):
                                    st.session_state.pop(k, None)

                            st.session_state["mary_last_promotion"] = {
                                "ts": int(time.time()),
                                "from_timeline": old_tl,
                                "to_timeline": "cumplice",
                            }

                            _lock_scene(usuario_key)

                    except Exception:
                        promoted = False
                        meta = meta or {}

                # Debug rápido
                debug_tl = "cumplice" if promoted else timeline_final
                st.session_state["mary_rel_meta_last"] = {
                    "timeline": debug_tl,
                    "stage": rel_state.get("stage"),
                    "intimacy_level": rel_state.get("intimacy_level"),
                    "virginity": rel_state.get("virginity"),
                    "consummated": rel_state.get("consummated"),
                    "mature_turns": rel_state.get("mature_turns"),
                    "desire": rel_state.get("desire"),
                    "arousal": rel_state.get("arousal"),
                    "self_control": rel_state.get("self_control"),
                    "hazard_p": meta.get("hazard_p"),
                    "forced_variation": meta.get("forced_variation"),
                    "pattern": meta.get("pattern"),
                    "virginity_changed": meta.get("virginity_changed"),
                    "virginity_reason": meta.get("virginity_reason"),
                    "nsfw_on": nsfw_on,
                    "conflict_mode": conflict_mode,
                    "conflict_now": conflict_now,
                }

                st.session_state["mary_debug_nsfw"] = {
                    "nsfw_on": nsfw_on,
                    "model": model,
                    "timeline": timeline_final,
                    "intimacy_phase": self._get_intimacy_phase(facts),
                    "conflict_mode": conflict_mode,
                    "conflict_now": conflict_now,
                }

                # Salva histórico
                save_interaction_safe(usuario_key, prompt, texto, used_model or attempt["model"])

                # Mantém cena travada
                _lock_scene(usuario_key)

                # Avança fase íntima
                try:
                    current_phase = self._get_intimacy_phase(cached_get_facts(usuario_key))
                    if _should_advance_phase(current_phase, prompt, texto, engine_meta=meta):
                        desired_next = _cap_next_phase(current_phase, current_phase + 1)

                        if desired_next == 4 and not _user_explicitly_allows_climax(prompt):
                            desired_next = current_phase
                        if desired_next == 5 and (current_phase < 4 or not _user_signals_aftercare(prompt)):
                            desired_next = current_phase

                        if desired_next != current_phase:
                            self._set_intimacy_phase(usuario_key, desired_next)
                except Exception:
                    pass

                return texto

            except Exception as e:
                last_err = e

        if last_err:
            logger.exception("Falha em todas tentativas de chat", exc_info=last_err)

        return "⚠️ O modelo retornou vazio. Troque o modelo no sidebar."

    # -------------------------
    # helpers
    # -------------------------
    @staticmethod
    def _extract_text(resp: Any) -> str:
        try:
            if resp is None:
                return ""
            if isinstance(resp, str):
                return resp.strip()

            if isinstance(resp, dict):
                choices = resp.get("choices")
                if isinstance(choices, list) and choices:
                    c0 = choices[0] or {}
                    msg = c0.get("message") or {}
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if isinstance(content, str) and content.strip():
                            return content.strip()
                    txt = c0.get("text")
                    if isinstance(txt, str) and txt.strip():
                        return txt.strip()

                for k in ("output_text", "text", "content", "result"):
                    v = resp.get(k)
                    if isinstance(v, str) and v.strip():
                        return v.strip()

                msgs = resp.get("messages")
                if isinstance(msgs, list) and msgs:
                    last = msgs[-1] or {}
                    if isinstance(last, dict):
                        v = last.get("content")
                        if isinstance(v, str) and v.strip():
                            return v.strip()

            return ""
        except Exception:
            return ""

    @staticmethod
    def _get_intimacy_phase(facts: Dict[str, Any]) -> int:
        try:
            return int((facts or {}).get("intimacy.phase", 0))
        except Exception:
            return 0

    @staticmethod
    def _set_intimacy_phase(usuario_key: str, phase: int) -> None:
        phase = max(0, min(int(phase), MAX_INTIMACY_PHASE))
        set_fact_safe(usuario_key, "intimacy.phase", phase, {"fonte": "intimacy_progression"})

    def _chat(self, model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: int):
        return service_router.route_chat_strict(
            model,
            {
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": max_tokens,
            },
        )
