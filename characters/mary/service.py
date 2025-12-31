# characters/mary/service.py
from __future__ import annotations
"""
MaryService (v3.19 – Timeline-Aware + Canon + RelationshipEngine v2
            + Scene Lock (continuidade espacial)
            + Memórias compartilhadas (CANON + suave)
            + Long Memory (Mongo $text)
            + NSFW unificado (core.nsfw)
            + Pacing anti-"corrida" + Intimacy phases
            + CONFLICT_MODE
            + ✅ LEAK GATE v2 (detecção + sanitização + REPAIR PASS)
              - impede NPCs de confirmarem segredos / inventarem offscreen
              - evita inglês / vazamento de nomes em NPC
              - fallback seguro se o modelo insistir
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
- Romance e tensão emocional permitidos.
- Evite descrição gráfica de atos sexuais.
- Não quebre o tom nem a continuidade.
""".strip()

NSFW_TOGGLE_STYLE = """
[NSFW_ON]
- Linguagem adulta é permitida conforme o contexto.
- Preserve coerência, consentimento e continuidade.
- Não suavize o tom por padrão; siga o sistema e o modo.
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
# NSFW ENABLE (unificado)
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
        r"\bdo\s+outro\s+lado\b",
        r"\bcena\s+seguinte\b",
    ]
    return any(re.search(p, txt) for p in patterns)


# ==========================================================
# INTRO CANÔNICO (1x por sessão) — condicional ao CANON
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

    try:
        stored_hash = str(get_fact(usuario_key, hash_key, default="") or "").strip()
        stored_text = str(get_fact(usuario_key, text_key, default="") or "").strip()

        if (not stored_hash) or (stored_hash != current_id) or (not stored_text):
            set_fact_safe(usuario_key, hash_key, current_id, {"fonte": "persona_intro_sync"})
            set_fact_safe(usuario_key, text_key, current_text, {"fonte": "persona_intro_sync"})
            clear_user_cache(usuario_key)

        return current_id, current_text
    except Exception:
        return current_id, current_text


# ==========================================================
# CANON + memórias compartilhadas
# ==========================================================
def _get_all_memories(shared_key: str, limit: int = 200) -> List[Dict[str, Any]]:
    return cached_list_memories(shared_key, limit=limit)


def _memory_timeline_ok(meta: Dict[str, Any], timeline: str) -> bool:
    tl = _normalize_timeline(timeline)
    tms = str(meta.get("timeline_at_save") or meta.get("timeline") or "").strip()
    if not tms:
        return True
    return tms in (tl, "[all]")


def _has_canon_memories(shared_key: str, timeline: str) -> bool:
    mems = _get_all_memories(shared_key, limit=240)
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
    max_items: int = 60,
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    mems = _get_all_memories(shared_key, limit=320)
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
    lines.append("Fatos do universo. Se contradizer a persona, CANON vence.")
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


def _inject_shared_soft_context(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    max_items: int = 6,
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

    lines = ["[MEMÓRIAS COMPARTILHADAS (suave)]", "Use para coerência. Não citar literalmente.", ""]
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
        messages.append({"role": "system", "content": f"[QUADRO ZERO — INTRO DA PERSONA]\n{intro_text}"})
    st.session_state[flag] = True


# ==========================================================
# LONG MEMORY ($text Mongo)
# ==========================================================
def _inject_long_memory_textsearch(
    shared_key: str,
    timeline: str,
    user_prompt: str,
    messages: List[Dict[str, str]],
    *,
    limit: int = 8,
    dedupe_bucket: Optional[set] = None,
) -> None:
    try:
        rows = search_long_memory_text(shared_key, user_prompt, limit=max(1, int(limit or 8)))
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
        if len(picked) >= int(limit or 8):
            break

    if not picked:
        return

    lines = [
        "[LONG MEMORY — $text (Mongo)]",
        "Use para continuidade (sem citar literalmente).",
        "",
    ]
    for i, d in enumerate(picked, 1):
        ts = d.get("ts") or ""
        header = f"- LM {i}" + (f" (ts: {ts})" if ts else "")
        lines.append(header)
        lines.append(str(d.get("text") or "").strip())
        lines.append("")

    messages.append({"role": "system", "content": "\n".join(lines).strip()})


# ==========================================================
# MEMÓRIAS — comandos (enxuto)
# ==========================================================
_SAVE_RE = re.compile(r"^\s*(?:mary\s*,?\s*)?(?:salve|salvar|guarde)\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})\b")


def _is_save_memory_command(user_text: str) -> bool:
    return bool(_SAVE_RE.search(user_text or ""))


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


# ==========================================================
# RELATIONSHIP STATE (facts > canon default)
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

    base.setdefault("mature_turns", 0)
    base.setdefault("intimacy_level", 0 if timeline == "universitaria" else 3)
    base.setdefault("consummated", False if timeline == "universitaria" else True)
    base.setdefault("virginity", "virgem" if timeline == "universitaria" else "nao_virgem")
    base.setdefault("stage", "conhecendo" if timeline == "universitaria" else "casados")

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
# INTIMACY: sinais e travas (enxuto)
# ==========================================================
_RE_CLIMAX_SIGNAL = re.compile(r"\b(goza|orgasmo|gozar|goze|gozando)\b", re.IGNORECASE)
_RE_AFTERCARE_SIGNAL = re.compile(r"\b(depois|abraça|acolhe|dorme|banho|água|calma|carinho)\b", re.IGNORECASE)

_RE_ESCALATE_0_TO_1 = re.compile(r"\b(beijo|encosta|toque|abraço|aproximo)\b", re.IGNORECASE)
_RE_ESCALATE_1_TO_2 = re.compile(r"\b(roupa|tirar|desliza|entre as pernas|calcinha|sutiã|mamil)\b", re.IGNORECASE)
_RE_ESCALATE_2_TO_3 = re.compile(r"\b(quase|não ainda|controle|devagar|nega|implorar)\b", re.IGNORECASE)


def _user_explicitly_allows_climax(user_text: str) -> bool:
    return bool(_RE_CLIMAX_SIGNAL.search(user_text or ""))


def _user_signals_aftercare(user_text: str) -> bool:
    return bool(_RE_AFTERCARE_SIGNAL.search(user_text or ""))


def _should_advance_phase(current_phase: int, user_text: str, mary_text: str) -> bool:
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
    if tl in ("universitaria",):
        return "off"
    return "soft"


_RE_CONFLICT_IMMINENT = re.compile(
    r"\b(briga|agarr(a|o|ou)|segura|empurra|amea(c|ç)a|grita|bater|soco|chute|murro|"
    r"arrasta|seguran(ç|c)a|pol[ií]cia|porta arromb|me mata|vou te matar)\b",
    re.IGNORECASE,
)


def _conflict_imminent(user_text: str) -> bool:
    return bool(_RE_CONFLICT_IMMINENT.search(user_text or ""))


# ==========================================================
# ✅ LEAK GATE v2 (detecção + sanitização + repair)
# ==========================================================
_RE_ENG_HEAVY = re.compile(
    r"\b(raises|meanwhile|your phone|she leans|watching you|bellhop|elevator)\b",
    re.IGNORECASE,
)
_RE_SECRET_CONFIRM = re.compile(
    r"\b(ela\s+sabe|ela\s+descobriu|o\s+jogo\s+acabou|game\s+is\s+up|sempre\s+sabe)\b",
    re.IGNORECASE,
)
_RE_OFFSCREEN = re.compile(
    r"\b(celular\s+vibra|mensagem\s+chega|your\s+phone\s+buzzes|mensagem\s+de\s+)\b",
    re.IGNORECASE,
)
_RE_QUOTED = re.compile(r"(?s)\".{0,800}?\"")
_RE_NPC_LABEL = re.compile(r"(?im)^\s*(npc|atendente|m[aã]e|amigo|amiga|rival|flertador|flertadora)\s*:\s*")


def _user_secret_lock_requested(user_prompt: str) -> bool:
    # gatilho “duro” do usuário, sem depender de entidades
    return bool(re.search(r"(?i)\b(se\s+.*quebrar\s+o\s+segredo\s*,?\s*termino)\b", user_prompt or ""))


def _strip_english_lines(text: str) -> str:
    if not text:
        return ""
    out = []
    for ln in text.splitlines():
        if _RE_ENG_HEAVY.search(ln):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _sanitize_offscreen(text: str, user_prompt: str) -> str:
    if not text:
        return ""
    # se usuário não colou conteúdo, proíbe conteúdo inventado
    user_has_pasted_message = bool(re.search(r"(?i)\bmensagem\s+de\s+.+?:", user_prompt or ""))

    if _RE_OFFSCREEN.search(text) and not user_has_pasted_message:
        # troca qualquer bloco de mensagem por marcador neutro
        text = re.sub(r"(?is)(mensagem\s+de\s+[^:\n]{1,60}\s*:)\s*.+?(\n\n|$)", r"\1 [mensagem não revelada]\2", text)
        text = re.sub(r"(?is)(your\s+phone\s+buzzes.+?)(\n\n|$)", "[mensagem não revelada]\n\n", text, flags=re.IGNORECASE)
        # remove aspas longas típicas de “mensagem”
        text = _RE_QUOTED.sub("[mensagem não revelada]", text)

    return text.strip()


def _sanitize_secret_confirmations(text: str) -> str:
    if not text:
        return ""
    # remove “ela sabe / game is up”
    text = _RE_SECRET_CONFIRM.sub("…", text)
    return text.strip()


def _sanitize_npc_naming(text: str, secret_lock: bool) -> str:
    """
    Regra estrutural: personagem extra = NPC (sem nomes próprios).
    - Se secret_lock, bloqueia NPC citando nomes sensíveis.
    """
    if not text:
        return ""

    # Se o modelo “batizou” um extra como nome próprio, padroniza para NPC:
    # (heurística segura: troca linhas iniciadas por Nome: para NPC:)
    text = re.sub(r"(?im)^\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]{2,20}\s*:\s*", "NPC: ", text)

    # Se secret_lock, impede NPC de citar “Janio” como fato (vira pronome neutro)
    if secret_lock:
        text = re.sub(r"(?i)\bseu\s+janio\b", "ele", text)
        text = re.sub(r"(?i)\bjanio\b", "ele", text)

    return text.strip()


def _leak_detected(text: str) -> bool:
    if not text:
        return False
    if _RE_ENG_HEAVY.search(text):
        return True
    if _RE_SECRET_CONFIRM.search(text):
        return True
    # se inventou mensagens (vai sobrar marcador após sanitize, mas detectamos antes do repair)
    if re.search(r"(?i)\byour\s+phone\s+buzzes\b", text):
        return True
    return False


def _apply_leakage_gate(text: str, user_prompt: str, *, secret_lock: bool) -> str:
    if not text:
        return ""

    t = text
    t = _strip_english_lines(t)
    t = _sanitize_offscreen(t, user_prompt)
    t = _sanitize_secret_confirmations(t)
    t = _sanitize_npc_naming(t, secret_lock=secret_lock)

    # último “cinto de segurança”: se restou afirmação de segredo, neutraliza
    t = re.sub(r"(?i)\b(ela\s+.*sabe|ela\s+.*descobriu)\b", "…", t)

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

        # fatos mínimos
        facts0 = cached_get_facts(usuario_key)
        if "cena.locked" not in facts0:
            _lock_scene(usuario_key)

        if "intimacy.phase" not in facts0:
            set_fact_safe(usuario_key, "intimacy.phase", 0, {"fonte": "intimacy_init"})
            facts0["intimacy.phase"] = 0

        # mudança explícita (permitida)
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou and novo_local:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            _lock_scene(usuario_key)
            return f"_Eu te puxo comigo até **{novo_local}**…_"

        # cena paralela
        facts_pre = cached_get_facts(usuario_key)
        scene_locked = _scene_is_locked(facts_pre)
        scene_parallel = bool(scene_locked and _detect_scene_violation(prompt))

        # salvar memória (enxuto)
        if _is_save_memory_command(prompt):
            raw_body = _strip_save_prefix(prompt)
            date_iso = _extract_date_iso(prompt) or _extract_date_iso(raw_body)
            body = raw_body.strip()

            if not body:
                return "⚠️ Cole o texto a salvar (e opcionalmente a data dd/mm/aaaa)."

            meta = {"kind": "user_request", "date": date_iso or "", "timeline_at_save": timeline_final}
            try:
                append_memory_safe(shared_key, body, meta=meta, user_id=user_id)
                append_long_memory_safe(
                    shared_key,
                    body,
                    meta={**meta, "source": "ui_long_memory", "user_id": user_id, "timeline_at_save": timeline_final},
                )
            except Exception as e:
                logger.exception("Falha ao salvar memória", exc_info=e)
                return f"⚠️ Falha ao salvar memória: {type(e).__name__}: {e}"

            return "✅ Memória permanente salva (compartilhada)."

        # persona + system
        persona_text, _ = get_persona(timeline_final)
        facts = cached_get_facts(usuario_key)

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

        intimacy_phase = self._get_intimacy_phase(facts)

        # secret lock (gatilho do usuário + opcional por facts)
        secret_lock = bool((facts or {}).get("secret.lock", False)) or _user_secret_lock_requested(prompt)

        # regras (compactas, mas duras)
        system = f"""
{spatial_context}

VOCÊ É MARY. Responda sempre em primeira pessoa.

[REGRA DE AUTORIA — ABSOLUTA]
- Não invente ações/falas/pensamentos do usuário.

[SEGREDOS & NPC — ABSOLUTO]
- Personagens extras NÃO confirmam segredos; no máximo suspeitam/insinuam.
- Personagem extra deve ser "NPC:" (sem nomes próprios).
- NPC não move a trama; apenas reage ao que o usuário direcionar.
- Proibido inventar conteúdo de mensagens/celular (só se usuário colar).

[IDIOMA]
- PT-BR apenas.

TIMELINE: {timeline_final}

[CANON — VERDADE ATUAL]
{canon_txt}

PERSONA (baseline):
{persona_text}

{rel_block}

[CONTINUIDADE]
- Não mude local/tempo sozinho. Se usuário narrar paralelo, trate como cena paralela (Mary não teleporta).
{"[CENA PARALELA ATIVA] Use o paralelo só como gatilho emocional (sem afirmar como fato)." if scene_parallel else ""}

[PACING]
- Avance em micro-passos. Sem concluir tudo.
- Não termine com pergunta ao usuário.

[INTIMACY]
FASE ATUAL: {intimacy_phase} ({INTIMACY_PHASES.get(intimacy_phase, '—')})
- Máximo +1 fase por resposta.
- Clímax só com sinal explícito do usuário.

[CONFLICT_MODE — {conflict_mode.upper()}]
- Se conflito iminente: reação humana, proporcional, sem moralizar.

[SECRET_LOCK]
- {"ATIVO" if secret_lock else "inativo"}.

{nsfw_block}
""".strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]

        # dedupe
        dedupe_hashes: set = set()

        # intro 1x (se não há canon)
        _inject_intro_as_context_once(usuario_key, timeline_final, shared_key, messages)

        # canon + longmem + suave
        _inject_canon_memories_always(shared_key, timeline_final, messages, max_items=60, dedupe_bucket=dedupe_hashes)
        _inject_long_memory_textsearch(shared_key, timeline_final, prompt, messages, limit=8, dedupe_bucket=dedupe_hashes)
        _inject_shared_soft_context(shared_key, timeline_final, messages, max_items=6, dedupe_bucket=dedupe_hashes)

        # histórico curto
        history = cached_get_history(usuario_key, limit=400)
        for d in history[-26:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": u})
            if a:
                messages.append({"role": "assistant", "content": a})

        messages.append({"role": "user", "content": prompt})

        # tentativas (enxuto)
        attempts = []
        if nsfw_on:
            attempts = [{"model": model, "temperature": 0.85}, {"model": model, "temperature": 0.65}]
        else:
            attempts = [
                {"model": model, "temperature": 0.70},
                {"model": model, "temperature": 0.50},
                {"model": "deepseek/deepseek-chat-v3-0324", "temperature": 0.60},
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

                # ✅ LEAK GATE (sanitize)
                texto = _apply_leakage_gate(texto, prompt, secret_lock=secret_lock)

                # ✅ se ainda vaza, REPAIR PASS (melhor opção técnica: mesmo modelo usado, temp baixa)
                if _leak_detected(texto):
                    repaired = self._repair_response(
                        used_model or attempt["model"],
                        user_prompt=prompt,
                        assistant_text=texto,
                        *,
                        secret_lock=secret_lock,
                    )
                    repaired = _apply_leakage_gate(repaired, prompt, secret_lock=secret_lock)

                    if _leak_detected(repaired):
                        # fallback final: seguro e curto (não quebra regras)
                        texto = "Eu mantenho a postura e não revelo nada a ninguém. Eu sigo com cautela, por dentro em alerta."
                    else:
                        texto = repaired

                # Relationship Engine (pós-resposta)
                promoted = False
                meta: Dict[str, Any] = {}

                if conflict_now:
                    meta = {"conflict_mode": conflict_mode, "conflict_now": True}
                else:
                    try:
                        assessor_model = used_model or attempt["model"]

                        def _assessor(system_prompt: str, user_prompt2: str) -> str:
                            data2, _, _ = self._chat(
                                assessor_model,
                                [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt2}],
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

                        # promoção automática (universitaria -> cumplice)
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

                # debug
                debug_tl = "cumplice" if promoted else timeline_final
                st.session_state["mary_rel_meta_last"] = {
                    "timeline": debug_tl,
                    "stage": rel_state.get("stage"),
                    "intimacy_level": rel_state.get("intimacy_level"),
                    "virginity": rel_state.get("virginity"),
                    "consummated": rel_state.get("consummated"),
                    "mature_turns": rel_state.get("mature_turns"),
                    "nsfw_on": nsfw_on,
                    "conflict_mode": conflict_mode,
                    "conflict_now": conflict_now,
                    "secret_lock": secret_lock,
                }

                # salva histórico
                save_interaction_safe(usuario_key, prompt, texto, used_model or attempt["model"])

                # mantém cena travada
                _lock_scene(usuario_key)

                # avança fase íntima (máx 1 por turno)
                try:
                    current_phase = self._get_intimacy_phase(cached_get_facts(usuario_key))
                    if _should_advance_phase(current_phase, prompt, texto):
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
    # REPAIR PASS
    # -------------------------
    def _repair_response(self, model: str, user_prompt: str, assistant_text: str, *, secret_lock: bool) -> str:
        repair_system = f"""
Você é um REVISOR TÉCNICO. Reescreva a resposta para cumprir regras estruturais.

REGRAS:
- PT-BR apenas (sem inglês).
- Personagens extra: SEMPRE "NPC:" (sem nomes próprios).
- NPC NÃO confirma segredos; no máximo suspeita/insinua (sem afirmar).
- PROIBIDO inventar conteúdo de mensagens/celular; se existir, use "[mensagem não revelada]" sem texto.
- Proibido inventar ações/falas/pensamentos do usuário.
- Preserve intenção e clima da resposta, mas dentro das regras.

SECRET_LOCK: {"ATIVO" if secret_lock else "inativo"}.
Se ATIVO: nunca deixe NPC citar nome sensível; use "ele" ou "essa pessoa".
""".strip()

        repair_user = f"""
[USUÁRIO]
{user_prompt}

[RESPOSTA A SER REPARADA]
{assistant_text}

Reescreva agora, mantendo a resposta em primeira pessoa (Mary).
""".strip()

        try:
            data, _, _ = self._chat(
                model,
                [{"role": "system", "content": repair_system}, {"role": "user", "content": repair_user}],
                temperature=0.15,
                max_tokens=900,
            )
            return self._extract_text(data) or ""
        except Exception:
            return ""

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
