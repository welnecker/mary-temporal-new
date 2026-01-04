# characters/mary/service.py
from __future__ import annotations
"""
MaryService (v3.22 — Hardening final + testes de estresse, em cima da v3.20)

✅ FOCO (v3.22):
- Mantém TUDO da v3.20 (canon + longmem $text + bm25 + scene lock + relationship engine + intimacy phases + conflict + guardião/repair).
- Hardening final:
  - Validação FORTE de formato (4 parágrafos; 2–4 frases por parágrafo).
  - Guardião também reprova respostas com formato inválido (força repair).
  - Diagnósticos silenciosos de estresse (mary_last_diagnostics) por turno.
  - Retry mais previsível: tentativa -> guardião -> repair (até 2) -> fallback seguro.
  - Nunca volta com 1 parágrafo só (ou 6 parágrafos), nem com “perguntas” no final.
- Continua: Regra-mãe: usuário decide fatos/ações/logística. Mary não completa lacunas.
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
# 🔑 USER / KEYS
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
- Mantenha romance, intimidade emocional e tensão.
- Evite descrição gráfica de atos sexuais.
- Não quebre o tom nem a continuidade.
""".strip()

NSFW_TOGGLE_STYLE = """
[NSFW_ON]
- Linguagem adulta é permitida conforme o contexto.
- Preserve coerência, consentimento e continuidade.
- Não suavize o tom por padrão; apenas siga as regras do sistema e do modo.
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
    if fk in st.session_state:
        del st.session_state[fk]

    prefix = f"history::{usuario_key}::"
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(prefix):
            del st.session_state[k]


def clear_mem_cache_for_shared(shared_key: str) -> None:
    prefix = f"mem::{shared_key}::"
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.startswith(prefix):
            del st.session_state[k]


def clear_shared_memory_cache(user_id: str) -> None:
    clear_mem_cache_for_shared(_shared_key(user_id))

# ==========================================================
# WRAPPERS DE ESCRITA (invalida cache automaticamente)
# ==========================================================
def set_fact_safe(usuario_key: str, key: str, value: Any, meta: Optional[dict] = None) -> None:
    set_fact(usuario_key, key, value, meta or {})
    clear_user_cache(usuario_key)


def append_memory_safe(shared_key: str, text: str, meta: Optional[dict] = None, *, user_id: Optional[str] = None) -> None:
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
# NSFW ENABLE (usa implementação unificada do core)
# ==========================================================
def nsfw_enabled(usuario_key: str, nsfw_override: Optional[bool] = None, timeline: Optional[str] = None) -> bool:
    return nsfw_enabled_unified(usuario_key, nsfw_override=nsfw_override, timeline=timeline)

# ==========================================================
# CONTINUIDADE ESPACIAL (Scene Lock REAL)
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
[CONTEXTO ESPACIAL — OBRIGATÓRIO]
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
        r"\bdo\s+outro\s+lado\s+da\s+cidade\b",
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
# ✅ CANON: memórias que prevalecem sobre a persona
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

    lines: List[str] = []
    lines.append("[MEMÓRIAS CANÔNICAS — COMPARTILHADAS]")
    lines.append("Estas memórias são fatos do universo e DEVEM ser seguidas.")
    lines.append("Se a persona contradizer, as memórias vencem.")
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


def _inject_intro_as_context_once(usuario_key: str, timeline: str, shared_key: str, messages: List[Dict[str, str]]) -> None:
    flag = f"intro_ctx_injected::{usuario_key}"
    if st.session_state.get(flag):
        return

    if _has_canon_memories(shared_key, timeline):
        st.session_state[flag] = True
        return

    _, intro_text = _sync_intro_fact(usuario_key, timeline)
    intro_text = (intro_text or "").strip()
    if intro_text:
        messages.append({"role": "system", "content": f"[QUADRO ZERO — INTRO DA PERSONA]\n{intro_text}"})
    st.session_state[flag] = True

# ==========================================================
# ✅ LONG MEMORY (Mongo $text)
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

    lines = [
        "[LONG MEMORY — $text (Mongo)]",
        "Use para continuidade. Não citar literalmente.",
        "",
    ]

    for i, d in enumerate(picked, 1):
        meta = d.get("meta") or {}
        title = ""
        if isinstance(meta, dict):
            title = str(meta.get("title") or meta.get("key") or "").strip()
        ts = d.get("ts") or ""
        header = f"- LM {i}"
        if ts:
            header += f" (ts: {ts})"
        if title:
            header += f" — {title}"
        lines.append(header)
        lines.append(str(d.get("text") or "").strip())
        lines.append("")

    messages.append({"role": "system", "content": "\n".join(lines).strip()})

# ==========================================================
# BM25 (fallback leve)
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

    import math

    def _idf_raw(w: str) -> float:
        n_q = df.get(w, 0)
        return max(0.0, ((N - n_q + 0.5) / (n_q + 0.5)))

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

    lines = [
        "[MEMÓRIAS RELEVANTES (BM25)]",
        "Use para coerência, sem citar literalmente.",
        "",
    ]

    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        title = meta.get("title") or meta.get("key") or ""
        header = f"- REL {i}"
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

    lines = ["[MEMÓRIAS COMPARTILHADAS (suave)]", "Use para coerência, sem citar literalmente.", ""]
    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        header = f"- MEM {i}"
        if d:
            header += f" (data: {d})"
        lines.append(header)
        txt = str(m.get("text") or "").strip()
        lines.append(txt)
        lines.append("")
        if dedupe_bucket is not None and txt:
            dedupe_bucket.add(hashlib.sha1(txt.encode("utf-8")).hexdigest())

    messages.append({"role": "system", "content": "\n".join(lines).strip()})

# ==========================================================
# RELATIONSHIP STATE
# ==========================================================
def _rel_fact_key(timeline: str) -> str:
    tl = (timeline or "").strip() or "cumplice"
    return f"rel.state::{tl}"

def _load_rel_state(facts: Dict[str, Any], timeline: str, canon_default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
_RE_CLIMAX_SIGNAL = re.compile(r"\b(goza|orgasmo|gozar|goze|gozando|gozar pra mim)\b", re.IGNORECASE)
_RE_AFTERCARE_SIGNAL = re.compile(r"\b(depois|abraça|acolhe|dorme|dormimos|banho|água|calma|respira|carinho)\b", re.IGNORECASE)
_RE_ESCALATE_0_TO_1 = re.compile(r"\b(beijo|beij[oa]|encosta|toque|abraço|aproximo)\b", re.IGNORECASE)
_RE_ESCALATE_1_TO_2 = re.compile(r"\b(pele|roupa|tirar|abrir|desliza|entre as pernas|boca|língua|calcinha|sutiã|mamil)\b", re.IGNORECASE)
_RE_ESCALATE_2_TO_3 = re.compile(r"\b(quase|não ainda|segura|devagar|controle|nega|para|provoca|faz eu implorar)\b", re.IGNORECASE)

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
    return current_phase + 1 if desired_next > current_phase + 1 else desired_next


# ==========================================================
# RIVALRY / DEFENSIVE BOND (Mary x Rivais)
# ==========================================================
# Detecção LEVE de “rival” tentando se aproximar do Janio.
# Importante: isso NÃO dá onisciência. Só reage ao que o usuário trouxe.
_RE_RIVAL_FEMALE = re.compile(
    r"\b("
    r"amanda|"
    r"outra\s+mulher|"
    r"ela\s+se\s+aproxima|"
    r"se\s+aproximou\s+dele|"
    r"falou\s+com\s+ele\s+sozinha|"
    r"consol(a|ando)|"
    r"apoio\s+afetivo|"
    r"apoio\s+emocional|"
    r"abraç(ou|a)|"
    r"toc(ou|a)\s+nele|"
    r"pegou\s+no\s+braço|"
    r"deu\s+em\s+cima|"
    r"flert(ou|a)|"
    r"quer\s+ele|"
    r"tentou\s+beij(ar|o)|"
    r"faz(er)?\s+ele\s+esquecer"
    r")\b",
    re.IGNORECASE,
)

def _detect_rivalry_threat(user_text: str, *, rel_state: Dict[str, Any]) -> bool:
    """
    Ativa o 'modo defesa instintiva' da Mary quando uma rival tenta se aproximar do Janio
    num contexto em que:
      - ainda há vínculo (não é indiferença/rompimento)
      - existe culpa ativa (ela traiu / há arrependimento pendente)
    Não cria onisciência: reage apenas ao que o usuário descreveu.
    """
    txt = (user_text or "").strip()
    if not txt:
        return False

    stage = str((rel_state or {}).get("stage") or "").strip().lower()
    if stage in ("rompidos", "indiferente", "acabou", "fim"):
        return False

    guilt = rel_state.get("guilt", 0)
    infidelity = bool(rel_state.get("infidelity", False))
    has_guilt = (isinstance(guilt, (int, float)) and guilt > 0) or infidelity
    if not has_guilt:
        return False

    return bool(_RE_RIVAL_FEMALE.search(txt))


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
    r"\b("
    r"briga|brigar|agarr(a|o|ou)|segura|segurar|empurra|empurrar|"
    r"amea(c|ç)a|ameaçar|grita|gritar|bater|soco|chute|murro|"
    r"puxa|puxar|arrasta|arrastar|seguran(ç|c)a|pol[ií]cia|"
    r"expulsa|expulsar|invad(i|ir)|porta arromb|"
    r"ci[uú]mes? extremo|tra[ií]ç(ão|ao)|"
    r"me mata|vou te matar|te quebro|te arrebento"
    r")\b",
    re.IGNORECASE,
)

def _conflict_imminent(user_text: str) -> bool:
    return bool(_RE_CONFLICT_IMMINENT.search(user_text or ""))

# ==========================================================
# ✅ FORMAT GUARD (v3.22)
# ==========================================================
def _split_paragraphs(text: str) -> List[str]:
    # mantém separação por linha em branco (robusto)
    raw = (text or "").strip()
    if not raw:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    return paras

def _count_sentences(paragraph: str) -> int:
    # conta sentenças aproximadas por pontuação final
    p = (paragraph or "").strip()
    if not p:
        return 0
    parts = re.split(r"[.!?]+", p)
    parts = [x.strip() for x in parts if x.strip()]
    return len(parts)

def _format_ok(text: str) -> bool:
    paras = _split_paragraphs(text)
    if len(paras) != 4:
        return False
    for p in paras:
        n = _count_sentences(p)
        if n < 2 or n > 4:
            return False
    # v3.22: não terminar com pergunta
    last = paras[-1].strip()
    if last.endswith("?"):
        return False
    return True

# ==========================================================
# ✅ GUARDIÃO (anti-vazamento / anti-offscreen / PT-BR / POV)
# ==========================================================
_RE_OFFSCREEN_MSG = re.compile(
    r"(?is)\b(mensagem\s+de|whatsapp|sms|telegram|o\s+celular\s+vibra.*?:|seu\s+celular\s+vibra.*?:)\b.*?(\".+?\"|“.+?”|'.+?')"
)
_RE_DOC_LOGISTICS = re.compile(
    r"(?is)\b(passaporte\s+falso|documento\s+falso|identidade\s+falsa|reserva\s+em\s+seu\s+nome|check-?in\s+confirmado|"
    r"gerente\s+examina|balc[aã]o\s+de\s+check-?in|cart[aã]o\s+magn[eé]tico\s+da\s+su[ií]te|upgrade|"
    r"confirmam\s+a\s+reserva|negam\s+a\s+reserva|sistema\s+do\s+hotel)\b"
)
_RE_NPC_SPEAKER_LINE = re.compile(r"(?m)^\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁ-ú\- ]{2,40}\s*[:—].*?\bjanio\b", re.IGNORECASE)
_RE_ENGLISH_LEAK = re.compile(r"(?i)\b(raises an eyebrow|meanwhile|she murmurs|knowing glint|bellhop|the game is up)\b")

# placeholder proibido
_RE_PLACEHOLDER_REVEAL = re.compile(r"(?i)\[\s*mensagem\s+n[aã]o\s+revelada\s*\]")

# POV do usuário “vaza” se Mary assume identidade/voz do narrador do prompt (Janio/Marcos/etc)
_RE_POV_USER_ID = re.compile(
    r"(?is)\b(me chamo|meu nome é|eu sou)\s+(janio|donisete|marcos|von\s+mecklenburg)\b"
)

def _build_context_for_guard(usuario_key: str, prompt: str) -> str:
    hist = cached_get_history(usuario_key, limit=200)
    last_users: List[str] = []
    for d in hist[-12:]:
        u = (d.get("mensagem_usuario") or "").strip()
        if u:
            last_users.append(u)
    ctx = "\n".join(last_users + [prompt]).lower()
    return ctx

def _violations(texto: str, ctx_lower: str) -> List[str]:
    t = texto or ""
    out: List[str] = []

    # 0) placeholders proibidos
    if _RE_PLACEHOLDER_REVEAL.search(t):
        out.append("placeholder_mensagem_nao_revelada")

    # 1) Offscreen inventado (mensagens com conteúdo)
    if _RE_OFFSCREEN_MSG.search(t):
        user_pasted = ("mensagem:" in ctx_lower) or ("texto:" in ctx_lower) or ("print" in ctx_lower) or ("segue a mensagem" in ctx_lower)
        if not user_pasted:
            out.append("offscreen_message_inventada")

    # 2) Logística/documentos/reserva/check-in inventados (sempre bloqueia)
    if _RE_DOC_LOGISTICS.search(t):
        out.append("logistica_inventada")

    # 3) NPC falando “Janio” (quebra de segredo) se o usuário não autorizou explicitamente
    allow = ("contei" in ctx_lower and "janio" in ctx_lower) or ("revelei" in ctx_lower and "janio" in ctx_lower) or ("disse o nome" in ctx_lower and "janio" in ctx_lower)
    if (not allow) and _RE_NPC_SPEAKER_LINE.search(t):
        out.append("npc_quebrou_segredo_janio")

    # 4) Inglês vazando
    if _RE_ENGLISH_LEAK.search(t):
        out.append("ingles_vazou")

    # 5) Mary assumindo identidade do narrador do usuário
    if _RE_POV_USER_ID.search(t):
        out.append("pov_usuario_assumido")

    # 6) v3.22: formato inválido (força repair)
    if not _format_ok(t):
        out.append("formato_invalido")

    return out

def _repair_instruction(violations: List[str]) -> str:
    bullets = []
    if "placeholder_mensagem_nao_revelada" in violations:
        bullets.append("- Remova QUALQUER placeholder tipo '[mensagem não revelada]'. Não substitua por nada.")
    if "offscreen_message_inventada" in violations:
        bullets.append("- Remova qualquer conteúdo inventado de mensagens/telefonemas. Se houver celular, deixe só 'vibra' sem texto.")
    if "logistica_inventada" in violations:
        bullets.append("- Remova qualquer logística/documento/reserva/check-in que não foi narrado explicitamente pelo usuário.")
    if "npc_quebrou_segredo_janio" in violations:
        bullets.append("- Remova qualquer NPC citando 'Janio'. NPCs só podem suspeitar genericamente, sem nomes/planos.")
    if "ingles_vazou" in violations:
        bullets.append("- Reescreva 100% em PT-BR.")
    if "pov_usuario_assumido" in violations:
        bullets.append("- Reescreva como MARY (1ª pessoa da Mary). Não assuma 'eu sou Janio/Marcos' nem narre como o usuário.")
    if "formato_invalido" in violations:
        bullets.append("- Corrija o FORMATO: exatamente 4 parágrafos curtos; 2–4 frases por parágrafo; sem lista; sem títulos; sem meta; sem pergunta no final.")
    bullets.append("- NÃO adicione fatos novos. Preserve a cena e o tom. 1 micro-ação + 1 micro-intenção. Sem perguntas.")
    return "\n".join(bullets).strip()

# ==========================================================
# ✅ Blindagem de POV (o usuário pode escrever em 1ª pessoa)
# ==========================================================
def _wrap_user_prompt_for_pov_guard(raw_prompt: str) -> str:
    p = (raw_prompt or "").strip()
    return (
        "[CENA DO USUÁRIO — NÃO É A VOZ DA MARY]\n"
        "O texto abaixo é a narração/ação do usuário. Você (Mary) NÃO deve continuar em 1ª pessoa como se fosse ele.\n"
        "Responda apenas como Mary, em primeira pessoa da Mary, mantendo segredos e sem inventar logística.\n\n"
        f"{p}"
    )

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

        # ----------------------------------------------------------
        # v3.22: diagnóstico silencioso por turno (stress hardening)
        # ----------------------------------------------------------
        diag = {
            "ts": int(time.time()),
            "timeline": timeline_final,
            "model_requested": model,
            "model_used": None,
            "repairs": 0,
            "violations": [],
            "attempts": 0,
            "nsfw_on": None,
            "conflict_now": None,
            "intimacy_phase_pre": None,
        }

        # 0) Garantir scene lock/facts mínimos
        facts0 = cached_get_facts(usuario_key)
        if "cena.locked" not in facts0:
            _lock_scene(usuario_key)

        # 0.1) INTIMACY PHASE — inicialização segura
        if "intimacy.phase" not in facts0:
            set_fact_safe(usuario_key, "intimacy.phase", 0, {"fonte": "intimacy_init"})
            facts0["intimacy.phase"] = 0

        # 1) Mudança explícita de local/tempo (permitida)
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou and novo_local:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            _lock_scene(usuario_key)
            st.session_state["mary_last_diagnostics"] = diag
            return f"_Eu te acompanho até **{novo_local}**…_"

        # 1.1) Cena paralela (não teleporta Mary)
        facts_pre = cached_get_facts(usuario_key)
        scene_locked = _scene_is_locked(facts_pre)
        scene_parallel = bool(scene_locked and _detect_scene_violation(prompt))

        # 2) Persona + system
        persona_text, _ = get_persona(timeline_final)
        facts = cached_get_facts(usuario_key)

        # 3) CONFLICT_MODE
        conflict_mode = _resolve_conflict_mode(timeline_final)
        conflict_now = (conflict_mode != "off") and _conflict_imminent(prompt)
        diag["conflict_now"] = bool(conflict_now)

        canon = get_canon("mary", timeline=timeline_final, user_key=user_id) or {}
        canon_txt = canon_to_text(canon)

        canon_rel_default = canon.get("relationship_state") if isinstance(canon.get("relationship_state"), dict) else None
        rel_state = _load_rel_state(facts, timeline_final, canon_rel_default)
        rel_block = rel_state_to_prompt_block(rel_state)

        scene_loc, scene_time, scene_action = _get_scene_state(facts)
        spatial_context = _build_spatial_context(scene_loc, scene_time, scene_action)

        nsfw_on = nsfw_enabled(usuario_key, nsfw_override=nsfw, timeline=timeline_final)
        diag["nsfw_on"] = bool(nsfw_on)
        nsfw_block = NSFW_TOGGLE_STYLE if nsfw_on else SAFE_SENSUAL_STYLE

        scene_lock_rule = """
[CONTINUIDADE — ABSOLUTO]
- Mary NÃO muda de local/tempo/evento sozinha.
- Se o usuário narrar outro lugar/tempo, trate como CENA PARALELA: Mary permanece onde está e reage sem afirmar como fato.
- Só altere a cena se o usuário ordenar explicitamente ("corta para:", "horas depois:", "vamos para ...").
- NÃO explique regras ao usuário.
""".strip()

        parallel_scene_rule = (
            """
[CENA PARALELA DO USUÁRIO]
O usuário descreveu outro lugar/tempo. NÃO mova Mary. Use apenas como tensão emocional, sem confirmar fatos externos.
""".strip()
            if scene_parallel
            else ""
        )

        manipulation_block = """
[MARY — DISCRETA / ESTRATEGISTA]
- Mary é socialmente inteligente e sutil. Nada caricato.
- Evite “teatro” e narração grandiosa.
""".strip()

        format_rule = """
[FORMATO — ABSOLUTO]
- Entregue SEMPRE 4 parágrafos curtos (2–4 frases cada).
- Sem listas, sem títulos, sem meta-comentários.
- O último parágrafo NÃO termina em pergunta.
""".strip()

        pacing_rule = """
[PACING — ABSOLUTO]
- Em cada parágrafo: no máximo 1 micro-ação + 1 micro-intenção.
- PROIBIDO concluir “toda a história” em um turno.
- PROIBIDO terminar com pergunta ao usuário.
- Termine com um gancho interno (sensação/decisão imediata).
""".strip()

        intimacy_phase = self._get_intimacy_phase(facts)
        diag["intimacy_phase_pre"] = int(intimacy_phase)

        intimacy_control_block = f"""
[INTIMIDADE — FASES (ABSOLUTO)]
FASE ATUAL: {intimacy_phase} ({INTIMACY_PHASES.get(intimacy_phase, 'desconhecida')})
- Mary pode avançar NO MÁXIMO 1 fase por resposta.
- Clímax (fase 4) só com sinal explícito do usuário.
- Aftercare (fase 5) só após fase 4.
""".strip()

        user_authorship_rule = """
[REGRA DE AUTORIA DO USUÁRIO — ABSOLUTA]
- Mary NÃO inventa falas internas do usuário.
- Mary NÃO descreve ações do usuário que ele NÃO declarou.
- Se o usuário DECLARAR explicitamente uma ação/estado/intenção, Mary pode tratar como fato e reagir,
  sem acrescentar novos detalhes sobre o corpo/mente do usuário.
""".strip()

        pov_rule = """
[BLINDAGEM DE POV — ABSOLUTA]
- O usuário pode narrar em 1ª pessoa (como Janio/Marcos/etc). ISSO NÃO MUDA a sua voz.
- Você escreve apenas como MARY (1ª pessoa da Mary). Nunca “continua” como o narrador do usuário.
""".strip()

        secrets_offscreen_admin_rule = """
[SEGREDO + OFFSCREEN + LOGÍSTICA — ABSOLUTO]
- Mary NÃO inventa fatos de logística: reserva, check-in, documentos, nomes em cadastro, confirmação/negação, horários, compras, pagamentos, chaves, suíte, upgrade, etc.
- Mary NÃO inventa mensagens, ligações, áudios ou conteúdo de celular. No máximo: "o celular vibra" / "há uma notificação".
- Se o usuário NÃO colou o conteúdo, Mary NÃO reproduz nada.
- NPCs NÃO sabem segredos (nome do Janio, plano, encontro, etc.) a menos que o usuário NARRE explicitamente que contou ou que eles ouviram.
- NPCs podem apenas DESCONFIAR de forma genérica (olhar, silêncio, insinuação), sem confirmar e sem citar nomes/planos como fato.
- Se o usuário mencionar algo sensível/ilegal (ex.: documento falso), Mary NÃO adiciona detalhes, NÃO ensina, NÃO completa lacunas. Ela apenas reage ao que o usuário já declarou.
""".strip()

        language_rule = """
[IDIOMA — ABSOLUTO]
- Escreva 100% em PT-BR.
""".strip()

        conflict_block = ""
        if conflict_mode != "off":
            conflict_block = f"""
[CONFLICT_MODE — {conflict_mode.upper()}]
- Conflitos cotidianos podem ocorrer, mas sem violência extrema/gráfica.
- Se houver conflito iminente: reação humana e proporcional, sem moralizar.
""".strip()

        system = f"""
{spatial_context}

VOCÊ É MARY.
Responda em primeira pessoa, do ponto de vista da Mary.

{language_rule}
{pov_rule}
{user_authorship_rule}
{secrets_offscreen_admin_rule}

TIMELINE ATUAL: {timeline_final}

[CANON — VERDADE ATUAL]
{canon_txt}

PERSONA (baseline):
{persona_text}

{rel_block}

{scene_lock_rule}
{parallel_scene_rule}

{format_rule}
{pacing_rule}
{manipulation_block}
{conflict_block}

REGRAS ABSOLUTAS:
- NÃO misture timelines.
- NÃO avance cena sem comando explícito.
- Se MEMÓRIA CANÔNICA contradizer a persona, a MEMÓRIA vence.

{intimacy_control_block}

{nsfw_block}
""".strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]

        dedupe_hashes: set = set()

        _inject_intro_as_context_once(usuario_key, timeline_final, shared_key, messages)
        _inject_canon_memories_always(shared_key, timeline_final, messages, max_items=80, dedupe_bucket=dedupe_hashes)
        _inject_long_memory_textsearch(shared_key, timeline_final, prompt, messages, limit=10, dedupe_bucket=dedupe_hashes)
        _inject_relevant_memories(shared_key, timeline_final, prompt, messages, k=8, dedupe_bucket=dedupe_hashes)
        _inject_shared_soft_context(shared_key, timeline_final, messages, max_items=8, dedupe_bucket=dedupe_hashes)

        history = cached_get_history(usuario_key, limit=400)
        for d in history[-30:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": _wrap_user_prompt_for_pov_guard(u)})
            if a:
                messages.append({"role": "assistant", "content": a})

        # ✅ ÚLTIMA MENSAGEM: blindagem de POV (resolve “Mary virou Janio”)
        messages.append({"role": "user", "content": _wrap_user_prompt_for_pov_guard(prompt)})

        # ----------------------------------------------------------
        # Chat com retry + GUARDIÃO (repair automático)
        # ----------------------------------------------------------
        # v3.22: tenta manter mais previsível; sempre registra diag.
        if nsfw_on:
            attempts = [
                {"model": model, "temperature": 0.85},
                {"model": model, "temperature": 0.70},
            ]
        else:
            attempts = [
                {"model": model, "temperature": 0.75},
                {"model": model, "temperature": 0.55},
                {"model": "deepseek/deepseek-chat-v3-0324", "temperature": 0.65},
            ]

        ctx_lower = _build_context_for_guard(usuario_key, prompt)
        last_err: Optional[Exception] = None

        for attempt in attempts:
            diag["attempts"] += 1
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

                diag["model_used"] = used_model or attempt["model"]

                v = _violations(texto, ctx_lower)
                if v:
                    diag["repairs"] += 1
                    diag["violations"].extend(v)

                    repair_sys = (
                        "Você é um revisor rígido de continuidade do roleplay.\n"
                        "TAREFA: reescrever a resposta da Mary SEM violar regras.\n"
                        "REGRAS: não inventar fatos/logística/mensagens; NPC não sabe segredos; PT-BR; 4 parágrafos curtos; "
                        "micro-ação/micro-intenção; sem perguntas; Mary não assume voz do usuário.\n"
                    )
                    repair_user = (
                        "Reescreva a resposta abaixo removendo violações.\n"
                        f"VIOLAÇÕES DETECTADAS: {', '.join(v)}\n"
                        f"INSTRUÇÕES DE CORREÇÃO:\n{_repair_instruction(v)}\n\n"
                        "[RESPOSTA ORIGINAL]\n"
                        f"{texto}\n"
                    )

                    repaired = ""
                    # v3.22: até 2 repairs, obrigando também o formato
                    for _i in range(2):
                        dataR, usedR, _ = self._chat(
                            used_model or attempt["model"],
                            [{"role": "system", "content": repair_sys}, {"role": "user", "content": repair_user}],
                            temperature=0.2,
                            max_tokens=1200,
                        )
                        repaired = (self._extract_text(dataR) or "").strip()

                        vr = _violations(repaired, ctx_lower) if repaired else ["formato_invalido"]
                        if repaired and not vr:
                            texto = repaired
                            diag["model_used"] = usedR or diag["model_used"]
                            break

                        diag["repairs"] += 1
                        diag["violations"].extend(vr)
                        repair_user = (
                            repair_user
                            + "\n\nATENÇÃO: ainda há violação. Reescreva novamente MAIS CURTO, mais contido, "
                              "exatamente 4 parágrafos (2–4 frases), e sem pergunta no final."
                        )

                    # se ainda falhar -> fallback seguro (e já vem formatado)
                    if _violations(texto, ctx_lower):
                        texto = (
                            "Eu mantenho meu rosto neutro e respiro com cuidado, como se nada me atingisse.\n\n"
                            "Por dentro, eu registro cada detalhe sem me permitir completar o que você não declarou.\n\n"
                            "Eu faço apenas um gesto mínimo, o suficiente para manter a tensão sem criar fatos novos.\n\n"
                            "E sigo firme, decidida a não deixar nenhum detalhe escapar."
                        )

                # v3.22: proteção extra final de formato (mesmo sem violações)
                if not _format_ok(texto):
                    diag["repairs"] += 1
                    diag["violations"].append("formato_invalido_pos_final")
                    texto = (
                        "Eu fico imóvel por um segundo, escolhendo com cuidado o que deixo aparecer no meu rosto.\n\n"
                        "Por dentro, eu sinto a tensão subir, mas seguro isso onde ninguém vê.\n\n"
                        "Eu te encaro com calma e faço só um movimento pequeno, medido, sem criar nada além do que você trouxe.\n\n"
                        "E continuo, consciente de cada risco, mantendo o controle por mais um instante."
                    )

                # Relationship Engine (pós-resposta)
                promoted = False
                meta: Dict[str, Any] = {}

                if conflict_now:
                    meta = {"conflict_mode": conflict_mode, "conflict_now": True}
                else:
                    try:
                        assessor_model = diag["model_used"] or used_model or attempt["model"]

                        def _assessor(system_prompt: str, user_prompt: str) -> str:
                            data2, _, _ = self._chat(
                                assessor_model,
                                [
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": user_prompt},
                                ],
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
                        meta = meta or {}

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
                    "intimacy_phase": intimacy_phase,
                    "conflict_mode": conflict_mode,
                    "conflict_now": conflict_now,
                }

                # Salva
                save_interaction_safe(usuario_key, prompt, texto, diag["model_used"] or used_model or attempt["model"])
                _lock_scene(usuario_key)

                # Intimacy progression
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

                st.session_state["mary_last_diagnostics"] = diag
                return texto

            except Exception as e:
                last_err = e

        if last_err:
            logger.exception("Falha em todas tentativas de chat", exc_info=last_err)

        st.session_state["mary_last_diagnostics"] = diag
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
