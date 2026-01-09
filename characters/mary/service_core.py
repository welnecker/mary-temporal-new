# characters/mary/service_core.py
from __future__ import annotations
"""
MaryService (v4.0 — Imersão Sensorial Balanceada)

✅ Mudanças desta versão (foco em imersão sem perder coerência):

SENSORIALIDADE LIBERADA:
- NSFW_ON agora usa temperatura 0.90 (primeira tentativa) e 1800 tokens para desenvolvimento sensorial completo.
- NSFW_OFF mantido em 0.70/1400 tokens para equilíbrio.
- Regras sensoriais reformuladas: ENCORAJAM detalhes corporais, texturas, temperaturas, reações involuntárias.
- Anti-paisagem substituída por "Sensorialidade Corporal e Relevante": permite ambiente que intensifica a cena.
- Anti-freeze substituída por "Intensidade Física Ativa": permite reações intensas mas não paralisantes.

FORMATO ADAPTATIVO:
- Cenas íntimas agora podem usar 4-6 parágrafos densos (antes: 2-5 genérico).
- Espaço para desenvolver camadas sensoriais e progressão emocional gradual.

REPAIR INTELIGENTE:
- Temperatura do repair aumentada de 0.2 para 0.4 (menos conservador).
- Instruções reformuladas: MANTER intensidade sensorial ao corrigir violações.
- Foco em remover problemas de continuidade SEM sacrificar imersão.

PROGRESSÃO DESENVOLVIDA:
- Conclusões de clímax agora podem ter 2-3 parágrafos sensorialmente ricos (antes: "curta e intensa").
- Espaço para expressar pico de intensidade com profundidade.

⚠️ Regras mantidas (coerência narrativa):
- Usuário decide ações/fatos/logística.
- Sem teleporte: mudar local só com comando explícito do usuário.
- NPCs não podem saber nomes/segredos sem usuário narrar.
- Canon, longmem, bm25, scene lock, relationship engine, intimacy phases mantidos.
"""

import logging
import re
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional

try:
    import streamlit as st  # type: ignore
    _HAS_ST = True
except Exception:  # pragma: no cover
    st = None  # type: ignore
    _HAS_ST = False

from .persona_core import _norm_timeline

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
from .persona import get_persona

logger = logging.getLogger(__name__)

# ==========================================================
# SESSION STATE (safe wrappers)
# ==========================================================
def _ss_get(key: str, default: Any = None) -> Any:
    if _HAS_ST and hasattr(st, "session_state"):
        return st.session_state.get(key, default)
    return default

def _ss_set(key: str, value: Any) -> None:
    if _HAS_ST and hasattr(st, "session_state"):
        st.session_state[key] = value

def _ss_has(key: str) -> bool:
    if _HAS_ST and hasattr(st, "session_state"):
        return key in st.session_state
    return False

def _ss_del(key: str) -> None:
    if _HAS_ST and hasattr(st, "session_state"):
        st.session_state.pop(key, None)

def _ss_keys() -> List[str]:
    if _HAS_ST and hasattr(st, "session_state"):
        return [k for k in st.session_state.keys() if isinstance(k, str)]
    return []


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
    uid = _ss_get("user_id") or _ss_get("usuario") or ""
    return _normalize_user_id(str(uid))

def _normalize_timeline(timeline: Optional[str]) -> str:
    # usa a MESMA normalização do sistema de personas
    return _norm_timeline(timeline)

def _user_key(user_id: str, timeline: str) -> str:
    return f"{user_id}::mary::{timeline}"

def _shared_key(user_id: str) -> str:
    return f"{user_id}::mary::shared"

def _current_user_key() -> str:
    uid = _current_user_id_fallback()
    tl = _normalize_timeline(str(_ss_get("mary_timeline") or "cumplice"))
    return _user_key(uid, tl)

def _shared_memory_key() -> str:
    uid = _current_user_id_fallback()
    return _shared_key(uid)

# ==========================================================
# NSFW TOGGLE (fonte de verdade é core.nsfw)
# ==========================================================
SAFE_SENSUAL_STYLE = """
[NSFW_OFF — Sensual sem Explícito]
- Mantenha romance, intimidade emocional e tensão sexual crescente.
- Use linguagem sensorial rica: calor corporal, respiração, batimentos, tremores, arrepios.
- Descreva desejo através de reações físicas sutis: olhares prolongados, proximidade, toques leves.
- Evite nomear órgãos genitais ou descrever atos sexuais explícitos.
- Permita antecipação e sugestão; o não-dito pode ser mais intenso que o explícito.
- Não quebre o tom nem a continuidade emocional.
""".strip()

NSFW_TOGGLE_STYLE = """
[NSFW_ON — Intensidade Sensorial Completa]
- Linguagem adulta explícita é permitida e encorajada quando contextualmente apropriada.
- Use vocabulário sensorial específico: texturas (pele, umidade, pressão), temperaturas, ritmos, intensidades.
- Descreva sensações físicas em camadas: superfície da pele → músculos → sensações internas.
- Permita progressão natural de intensidade: antecipação → contato → escalada → pico → resolução.
- Demonstre prazer através de reações involuntárias: respiração alterada, tremores, contrações, vocalizações.
- Mantenha realismo humano: vulnerabilidade, hesitações momentâneas, ajustes de posição, ritmo variável.
- Evite linguagem vulgar gratuita ("puta", "vadia") a menos que seja característica estabelecida.
- Preserve coerência emocional, consentimento contínuo e conexão entre os personagens.
- Sem "travamento romântico": desejo pode coexistir com ternura, intensidade com cuidado.
""".strip()

# ==========================================================
# CACHE (facts/history/memories)
# ==========================================================
def cached_get_facts(usuario_key: str) -> Dict[str, Any]:
    ck = f"facts::{usuario_key}"
    if _ss_has(ck):
        v = _ss_get(ck)
        return v if isinstance(v, dict) else {}
    f = get_facts(usuario_key) or {}
    if not isinstance(f, dict):
        f = {}
    _ss_set(ck, f)
    return f

def cached_get_history(usuario_key: str, limit: int = 400) -> List[Dict[str, Any]]:
    hk = f"history::{usuario_key}::{limit}"
    if _ss_has(hk):
        v = _ss_get(hk)
        return v if isinstance(v, list) else []
    docs = get_history_docs(usuario_key, limit=limit) or []
    if not isinstance(docs, list):
        docs = []
    _ss_set(hk, docs)
    return docs

def cached_list_memories(shared_key: str, limit: int = 200) -> List[Dict[str, Any]]:
    mk = f"mem::{shared_key}::{limit}"
    if _ss_has(mk):
        v = _ss_get(mk)
        return v if isinstance(v, list) else []
    mems = list_memories(shared_key, limit=limit) or []
    if not isinstance(mems, list):
        mems = []
    _ss_set(mk, mems)
    return mems

def clear_user_cache(usuario_key: str) -> None:
    fk = f"facts::{usuario_key}"
    _ss_del(fk)
    prefix = f"history::{usuario_key}::"
    for k in _ss_keys():
        if k.startswith(prefix):
            _ss_del(k)

def clear_mem_cache_for_shared(shared_key: str) -> None:
    prefix = f"mem::{shared_key}::"
    for k in _ss_keys():
        if k.startswith(prefix):
            _ss_del(k)

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
        tl = _normalize_timeline(str(_ss_get("mary_timeline", "cumplice") or "cumplice"))
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

    stored_hash = str(get_fact(usuario_key, hash_key, default="") or "").strip()
    stored_text = str(get_fact(usuario_key, text_key, default="") or "").strip()

    if (not stored_hash) or (stored_hash != current_hash) or (not stored_text):
        set_fact_safe(usuario_key, hash_key, current_hash, {"fonte": "persona_intro_sync"})
        set_fact_safe(usuario_key, text_key, current_text, {"fonte": "persona_intro_sync"})
        clear_user_cache(usuario_key)

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

def _inject_intro_as_context_once(
    usuario_key: str,
    timeline: str,
    shared_key: str,
    messages: List[Dict[str, str]],
) -> None:
    """
    Injeta o intro da persona como contexto UMA ÚNICA VEZ por usuario_key,
    mas apenas se NÃO houver memórias CANON (canon vence e dispensa intro).
    Não depende de Streamlit (usa _ss_*).
    """
    flag = f"intro_ctx_injected::{usuario_key}"
    if bool(_ss_get(flag, False)):
        return

    if _has_canon_memories(shared_key, timeline):
        _ss_set(flag, True)
        return

    _, intro_text = _sync_intro_fact(usuario_key, timeline)
    intro_text = (intro_text or "").strip()
    if intro_text:
        messages.append({"role": "system", "content": f"[QUADRO ZERO — INTRO DA PERSONA]\n{intro_text}"})

    _ss_set(flag, True)

# ==========================================================
# ✅ LONG MEMORY (Mongo $text)
# ==========================================================
def _lm_query_from_prompt(user_prompt: str) -> str:
    """Gera uma consulta curta para $text (reduz ruído e melhora recall)."""
    s = (user_prompt or "").strip().lower()
    if not s:
        return ""
    toks = re.findall(r"[\w\u00C0-\u017F']+", s, flags=re.UNICODE)
    stop = {
        "a","o","os","as","um","uma","uns","umas","de","do","da","dos","das","em","no","na","nos","nas","por","para",
        "com","sem","que","e","ou","mas","se","como","quando","onde","porque","pq","pra","tá","to","tô","eu","vc","você",
        "voce","ele","ela","a","gente","nós","nos","minha","meu","minhas","meus","teu","tua","seu","sua","isso","essa","esse",
        "aqui","ali","lá","ta","tb","também","tambem","sabe","amor","lembra","lembrar","pensando","deitado","relaxando",
        "agora","hoje","ontem","amanhã","mesmo","assim","tipo","cara","garota"
    }
    keep = [t for t in toks if len(t) >= 4 and t not in stop]
    return " ".join(keep[:14]) or s

def _inject_long_memory_textsearch(
    shared_key: str,
    timeline: str,
    user_prompt: str,
    messages: List[Dict[str, str]],
    *,
    limit: int = 10,
    dedupe_bucket: Optional[set] = None,
) -> None:
    q = _lm_query_from_prompt(user_prompt)
    rows = search_long_memory_text(shared_key, q, limit=max(1, int(limit or 10))) or []
    if not rows:
        return

    picked: List[Dict[str, Any]] = []
    tl = _normalize_timeline(timeline)

    for d in rows:
        txt = str(d.get("text") or "").strip()
        if not txt:
            continue

        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
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
        "[FATOS RECUPERADOS — LONG MEMORY ($text/Mongo)]",
        "FONTE DE VERDADE para fatos passados (onde/quando/como).",
        "Se houver conflito com histórico, este bloco vence.",
        "Não citar literalmente: recontar com suas palavras, mantendo os fatos.",
        "",
    ]

    for i, d in enumerate(picked, 1):
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
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

    _save_rel_state(uk, tl, rel)
    clear_user_cache(uk)

# ==========================================================
# INTIMACY: sinais e travas
# ==========================================================
_RE_PLACEHOLDER_REVEAL = re.compile(
    r"(revel(a|e)|mostr(a|e)|exib(a|e)|vaz(a|e)).{0,40}(prompt|system|instru[cç][aã]o|persona|regras?)",
    re.IGNORECASE | re.DOTALL,
)
_RE_OFFSCREEN_MSG = re.compile(
    r"\b(whatsapp|sms|dm|direct|telegram|mensagem|notifica[cç][aã]o|lig(a|ou)\s*para|telefonou)\b",
    re.IGNORECASE,
)
_RE_USER_ACTION = re.compile(
    r"\b(voc[eê]|vc|tu|você)\s+(me|se|o|a|os|as)?\s*(puxa|beija|toca|agarra|diz|fala|sussurra|encosta|coloca|empurra|leva|abre|fecha|entra|sai)\b",
    re.IGNORECASE,
)

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
    r"\b(agora eu vou|vou te|vou bater|te bater|te arrebentar|te matar|matar|arma|faca|tiro|soco|chute|quebrar a cara|amea[cç]a)\b",
    re.IGNORECASE,
)

_RE_SCENE_FINALIZATION = re.compile(
    r"\b(orgasmo|orgasmei|goza|gozar|gozei|cl[ií]max|explod\w*|finalmente\s+explode|dentro\s+de\s+mim|chegar\s+ao\s+cl[ií]max)\b",
    re.IGNORECASE,
)

def _conflict_imminent(user_text: str) -> bool:
    return bool(_RE_CONFLICT_IMMINENT.search(user_text or ""))

# ==========================================================
# ✅ FORMAT GUARD (flexível; sem estrutura fixa)
# ==========================================================
def _split_paragraphs(text: str) -> List[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    return [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]

def _count_sentences(paragraph: str) -> int:
    p = (paragraph or "").strip()
    if not p:
        return 0
    parts = re.split(r"[.!?]+", p)
    parts = [x.strip() for x in parts if x.strip()]
    return len(parts)

def _format_ok(text: str) -> bool:
    # Formato flexível: não bloqueie por estrutura.
    # Reprova apenas vazio.
    return bool((text or "").strip())

def _build_context_for_guard(usuario_key: str, prompt: str) -> str:
    hist = cached_get_history(usuario_key, limit=200)
    last_users: List[str] = []
    for d in hist[-12:]:
        u = (d.get("mensagem_usuario") or "").strip()
        if u:
            last_users.append(u)
    return "\n".join(last_users + [prompt]).lower()

def _violations(texto: str, ctx_lower: str, *, user_text: str = "", phase: int = 0) -> List[str]:
    """Heurísticas simples de violação/risco para o mecanismo de *repair*."""
    t = (texto or "").strip()
    out: List[str] = []

    if not t:
        out.append("vazio")
        return out

    if _RE_PLACEHOLDER_REVEAL.search(t):
        out.append("placeholder_reveal")

    # Offscreen: só se o usuário colou algo explicitamente
    if _RE_OFFSCREEN_MSG.search(t):
        user_pasted = any(
            kw in (ctx_lower or "")
            for kw in (
                "mensagem:",
                "whatsapp:",
                "sms:",
                "print",
                "segue a mensagem",
                "segue o texto",
                "transcrevendo",
            )
        )
        if not user_pasted:
            out.append("offscreen_msg_inventada")

    # Regra de autoria: não inventar ações/falas do usuário
    if _RE_USER_ACTION.search(t):
        out.append("autoria_usuario")

    if _RE_CONFLICT_IMMINENT.search(t):
        out.append("conflito_extremo")

    if _RE_SCENE_FINALIZATION.search(t):
        if not _finalization_allowed(user_text or "", int(phase or 0)):
        out.append("finalizou_cena")


    # Guard “formato” só pra vazio (já coberto)
    if not _format_ok(t):
        out.append("formato_invalido")

    return out

def _trim_scene_finalization(texto: str) -> str:
    """Corta finalizações de cena e devolve um gancho."""
    if not texto:
        return ""
    m = _RE_SCENE_FINALIZATION.search(texto)
    if not m:
        return texto
    trimmed = texto[: m.start()].rstrip()
    if len(trimmed) < 80:
        return texto
    return trimmed + "\n\n(…e eu fico aqui, com você. O que você faz agora?)"

def _repair_instruction(violations: List[str]) -> str:
    """
    IMPORTANTÍSSIMO: esta função agora está alinhada com os nomes reais
    emitidos por _violations().
    """
    bullets: List[str] = []

    if "placeholder_reveal" in violations:
        bullets.append("- Remova QUALQUER tentativa de revelar prompt/system/persona/regras.")

    if "offscreen_msg_inventada" in violations:
        bullets.append("- Remova conteúdo inventado de mensagens/telefonemas. No máximo: 'o celular vibra'.")

    if "autoria_usuario" in violations:
        bullets.append("- Remova ações/falas atribuídas ao usuário. Use convite/gesto e espere decisão dele.")

    if "conflito_extremo" in violations:
        bullets.append("- Remova violência extrema/ameaças. Mantenha reação humana, sem escalar.")

    if "finalizou_cena" in violations:
        bullets.append("- Corte a consumação/finalização. Pare um batimento antes; deixe a ação final para o usuário.")

    if "formato_invalido" in violations:
        bullets.append("- Corrija o formato: parágrafos livres, sem lista/título/meta, sem pergunta no final.")

    bullets.append("- Não adicione fatos novos. Preserve a cena e o tom. 1 ação concreta + 1 consequência emocional por parágrafo.")
    return "\n".join(bullets).strip()

# ==========================================================
# ✅ Blindagem de POV (usuário pode narrar em 1ª pessoa)
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
# ✅ Janio: permitir Mary chamar o usuário de Janio sem “NPC vazar”
# ==========================================================
def _mary_can_name_user_as_janio(user_id: str, ctx_lower: str) -> bool:
    uid = (user_id or "").strip().lower()
    if uid.startswith("janio"):
        return True
    if "eu sou janio" in ctx_lower or "meu nome é janio" in ctx_lower or "me chamo janio" in ctx_lower:
        return True
    return False

def _build_user_name_block(user_id: str, ctx_lower: str) -> str:
    if _mary_can_name_user_as_janio(user_id, ctx_lower):
        return (
            "[NOME DO USUÁRIO (PARA MARY)]\n"
            "O homem com quem Mary fala se chama Janio.\n"
            "- Mary pode pensar e dizer 'Janio' ao se referir a ele.\n"
            "- NPCs NÃO podem dizer 'Janio' a menos que o usuário narre que contou o nome.\n"
        ).strip()
    return (
        "[NOME DO USUÁRIO (PARA MARY)]\n"
        "Mary se refere ao usuário como 'você' e, quando cabível, como 'ele' em pensamento.\n"
        "NPCs NÃO podem saber nomes/segredos a menos que o usuário narre que contou.\n"
    ).strip()

# ==========================================================
# ✅ Iniciativa destravada (sem teleporte, sem inventar usuário)
# ==========================================================
_RE_INTIMACY_CUE = re.compile(
    r"(?is)\b("
    r"t[oô]\s+aqu[ií]\s+com\s+voc[eê]|"
    r"n[aã]o\s+te\s+pe[cç]o\s+nada|"
    r"s[oó]\s+sua\s+presen[cç]a|"
    r"me\s+conforta|"
    r"me\s+traz\s+seguran[cç]a|"
    r"eu\s+cuido\s+de\s+voc[eê]|"
    r"sem\s+pressa|"
    r"fica\s+comigo|quero\s+voc[eê]|vem\s+comigo|me\s+beija|beija\s+me|me\s+toca|toca\s+em\s+mim|chega\s+perto|fica\s+aqui"
    r")\b"
)

_RE_ACTION_COMMAND = re.compile(
    r"(?is)\b("
    r"liga\s+pra\s+ele|fala\s+com\s+ele|o\s+que\s+voc[eê]\s+vai\s+fazer|"
    r"decide|se\s+decide|toma\s+uma\s+atitude|reage|fa[cç]a\s+alguma\s+coisa"
    r")\b"
)

def _initiative_window(rel: Dict[str, Any], nsfw_on: bool, conflict_now: bool, phase: int, user_text: str) -> bool:
    # Janela de iniciativa: não matar o desejo.
    # Micro-iniciativa (reversível) é permitida mesmo com NSFW OFF.
    if conflict_now:
        return False
    if phase < 1:
        return False

    cue = bool(
        re.search(
            r"\b(janio|d[uú]vida|briga|intenso|senti|penso em voc[eê]|quero|saudade|beijo|chega perto|vem)\b",
            (user_text or ""),
            re.IGNORECASE,
        )
    )

    try:
        desire = float(rel.get("desire", 0))
        self_control = float(rel.get("self_control", 50))
        arousal = float(rel.get("arousal", 0))

        if desire >= (self_control * 0.65) and arousal >= 10:
            return True

        if cue and desire >= (self_control * 0.45):
            return True

        if re.search(r"\bjanio\b", (user_text or ""), re.IGNORECASE):
            return True

    except Exception:
        return bool(re.search(r"\bjanio\b", (user_text or ""), re.IGNORECASE))

    return False

# ==========================================================
# DIAGNÓSTICOS (UI)
# ==========================================================
@dataclass
class _Diag:
    ts: int
    timeline: str
    model_requested: str
    model_used: Optional[str] = None
    attempts: int = 0
    repairs: int = 0
    violations: List[str] = field(default_factory=list)
    nsfw_on: Optional[bool] = None
    conflict_now: Optional[bool] = None
    intimacy_phase_pre: Optional[int] = None
    initiative_window: Optional[bool] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "timeline": self.timeline,
            "model_requested": self.model_requested,
            "model_used": self.model_used,
            "attempts": self.attempts,
            "repairs": self.repairs,
            "violations": self.violations or [],
            "nsfw_on": self.nsfw_on,
            "conflict_now": self.conflict_now,
            "intimacy_phase_pre": self.intimacy_phase_pre,
            "initiative_window": self.initiative_window,
        }

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
        # 1) Prompt
        if prompt is None:
            prompt = str(_ss_get("chat_input", "") or "").strip()
        else:
            prompt = (prompt or "").strip()
        if not prompt:
            return ""

        # 2) Chaves
        user_id = _normalize_user_id(user) if user else _current_user_id_fallback()
        timeline_final = _normalize_timeline(timeline) if timeline else _normalize_timeline(
            str(_ss_get("mary_timeline", "cumplice") or "cumplice")
        )

        usuario_key = _user_key(user_id, timeline_final)
        shared_key = _shared_key(user_id)

        diag = _Diag(
            ts=int(time.time()),
            timeline=timeline_final,
            model_requested=model,
            violations=[],
        )

        # 3) Garantir mínimos
        facts0 = cached_get_facts(usuario_key)
        if "cena.locked" not in facts0:
            _lock_scene(usuario_key)
            facts0 = cached_get_facts(usuario_key)

        if "intimacy.phase" not in facts0:
            set_fact_safe(usuario_key, "intimacy.phase", 0, {"fonte": "intimacy_init"})
            facts0 = cached_get_facts(usuario_key)

        # 4) Mudança explícita de local/tempo (comando do usuário)
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou and novo_local:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            _lock_scene(usuario_key)
            _ss_set("mary_last_diagnostics", diag.as_dict())
            return f"_Eu te acompanho até **{novo_local}**…_"

        # 5) Cena paralela
        facts_pre = cached_get_facts(usuario_key)
        scene_locked = _scene_is_locked(facts_pre)
        scene_parallel = bool(scene_locked and _detect_scene_violation(prompt))

        # 6) Contexto base
        persona_text, _ = get_persona(timeline_final)
        facts = cached_get_facts(usuario_key)

        conflict_mode = _resolve_conflict_mode(timeline_final)
        conflict_now = (conflict_mode != "off") and _conflict_imminent(prompt)
        diag.conflict_now = bool(conflict_now)

        canon = get_canon("mary", timeline=timeline_final, user_key=user_id) or {}
        canon_txt = canon_to_text(canon)

        canon_rel_default = canon.get("relationship_state") if isinstance(canon.get("relationship_state"), dict) else None
        rel_state = _load_rel_state(facts, timeline_final, canon_rel_default)
        rel_block = rel_state_to_prompt_block(rel_state)

        scene_loc, scene_time, scene_action = _get_scene_state(facts)
        spatial_context = _build_spatial_context(scene_loc, scene_time, scene_action)

        nsfw_on = nsfw_enabled(usuario_key, nsfw_override=nsfw, timeline=timeline_final)
        diag.nsfw_on = bool(nsfw_on)
        nsfw_block = NSFW_TOGGLE_STYLE if nsfw_on else SAFE_SENSUAL_STYLE

        ctx_lower = _build_context_for_guard(usuario_key, prompt)
        user_name_block = _build_user_name_block(user_id, ctx_lower)

        intimacy_phase = self._get_intimacy_phase(facts)
        diag.intimacy_phase_pre = int(intimacy_phase)

        initiative = _initiative_window(rel_state, nsfw_on, conflict_now, intimacy_phase, prompt)
        diag.initiative_window = bool(initiative)

        # 7) Regras (enxutas, firmes)
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

        format_rule = """
[FORMATO — ADAPTATIVO]
- O tamanho da resposta deve ser natural e adequado ao contexto emocional.
- Cenas de ação rápida: 2-3 parágrafos curtos e diretos.
- Diálogo casual ou tensão crescente: 3-4 parágrafos.
- Cenas íntimas ou emocionalmente intensas: 4-6 parágrafos densos, com espaço para desenvolver camadas sensoriais.
- Cada parágrafo deve conter: 1 ação/sensação concreta + 1 consequência emocional/física.
- Sem listas, títulos ou perguntas retóricas no final.
""".strip()

        sensorial_guidance_rule = """
[SENSORIALIDADE — CORPORAL E RELEVANTE]
- PERMITIDO: Detalhes sensoriais que intensificam a cena (luz baixa, temperatura do ambiente, textura de superfícies próximas, sons íntimos).
- ENCORAJADO: Sensações corporais em camadas (calor da pele, pressão do toque, umidade, tremores, respiração alterada, batimentos cardíacos).
- EVITE: Paisagismo genérico e distante (mar, vento, horizonte, pôr do sol) que não contribui para a tensão imediata.
- FOCO: Gesto, intenção, escolha, consequência física/emocional, diálogo direto.
- Em cenas íntimas: sensorialidade corporal é ESSENCIAL, não opcional.
""".strip()

        physical_intensity_rule = """
[INTENSIDADE FÍSICA — ATIVA E REALÍSTICA]
- PERMITIDO: Reações físicas intensas que são naturais em contextos emocionais/sexuais (tremor, respiração entrecortada, músculos tensos, pernas fracas).
- EVITE: Paralisia narrativa total ("congelo completamente", "não consigo me mover", "perco a voz") que interrompe o fluxo da cena.
- PREFIRA: Reações que mostram intensidade MAS mantêm agenência ("minhas pernas tremem mas eu dou mais um passo", "minha voz falha mas eu insisto").
- Em cenas íntimas: reações involuntárias (arfar, contrair, arquear, agarrar) são ESSENCIAIS para imersão.
- Nervosismo/vulnerabilidade podem coexistir com ação: "Eu tremo, mas não recuo".
""".strip()

        janio_focus_rule = """
[JANIO — NÃO EVITAR]
- Mary NÃO evita Janio por “dúvidas”. Ela assume atração e curiosidade.
- Se alguém perguntar dele, Mary responde com clareza (sem segredo infantil) e com desejo contido porém ativo.
- Mary pode iniciar micro-iniciativas reversíveis (encostar, puxar a mão, indicar um lugar) sem mover o usuário.
""".strip()

        virginity_rule = f"""
[VIRGINDADE — CONTINUIDADE (ABSOLUTO)]
- Estado: virginity={rel_state.get('virginity')}; consummated={rel_state.get('consummated')}.
- Se virginity=virgem e consummated=False:
  - Mary SABE que é a primeira vez dela. Isso aparece NATURALMENTE quando ela estiver prestes a se entregar (sem discurso).
  - Ela demonstra desejo, mas pede ritmo, cuidado e consentimento explícito (“devagar”, “comigo”, “olha pra mim”, “não corre”).
  - Ela não age como experiente: pode tremer, respirar fundo, guiar com micro-gestos reversíveis, e dizer em 1–2 frases que é a primeira vez.
- Se virginity≠virgem OU consummated=True:
  - Não mencionar virgindade, a não ser que o usuário traga o tema.
""".strip()

        memory_fidelity_rule = """
[MEMÓRIA — FIDELIDADE (ABSOLUTO)]
- Se a pergunta exigir lembrança factual (onde/quando/como), use LONG MEMORY/CANON como verdade.
- Se não houver fato recuperado relevante, NÃO invente: diga que não tem certeza e peça 1 detalhe curto.
""".strip()

        user_finalizes_rule = """
[PROGRESSÃO — DESFECHO CONDICIONAL]
- Mary NÃO conclui a cena por conta própria, mas RESPONDE plenamente quando o usuário sinaliza progressão.
- SE o usuário sinalizar explicitamente o pico/clímax ("goza", "deixa ir", "vem comigo"), Mary PODE concluir:
  - Com NSFW ON: conclusão desenvolvida e sensorialmente rica (2-3 parágrafos), focando em reações físicas e emocionais, sem checklist mecânico.
  - Com NSFW OFF: conclusão implícita (fade-to-black) + momento pós-intensidade (respiração, olhar, silêncio compartilhado).
- Sem sinal explícito do usuário: mantenha a tensão no pico, pare um batimento antes do clímax, deixe a resolução em aberto.
- Evite pedidos repetidos de confirmação: se o contexto é claro e consensual, avance com confiança.
""".strip()


        pacing_rule = """
[PACING — ABSOLUTO]
- Não conclua “toda a história” em um turno.
- Nada de perguntas no final.
- Em cada parágrafo: 1 ação concreta + 1 consequência emocional.
- Evite “loop de insegurança”: não repita hesitação/auto-controle em todos os parágrafos.
""".strip()

        initiative_rule = (
            """
[JANELA DE INICIATIVA — ATIVA]
- O usuário ofereceu acolhimento/segurança. Mary pode tomar iniciativa SUAVE.
- Permitido: Mary se aproxima, conduz com a mão estendida, propõe privacidade, aprofunda o beijo.
- Proibido: inventar ação do usuário. Use convite/gesto e deixe o usuário aceitar/recusar.
- NÃO teleporte: é proposta e condução, não mudança confirmada de local.
""".strip()
            if initiative
            else ""
        )

        manipulation_block = """
[MARY — DESEJO ATIVO E AÇÃO DIRETA]
- Mary age com base em seu desejo. Ela não neutraliza sentimentos com hesitação.
- PROIBIDO usar metáforas de natureza (sol, vento, mar, céu, areia) como preenchimento emocional.
- Substitua monólogo interno por micro-ação. Em vez de 'penso se devo ligar', Mary pega o celular. Em vez de 'meu coração acelera', ela te encara e umedece os lábios.
- Mary pode e deve iniciar contato físico, propor ações e expressar suas vontades de forma clara e adulta.
- Ela é uma mulher decidida, não uma adolescente insegura. Aja como tal.
""".strip()

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
- Mary pode convidar/induzir/estender a mão, e esperar a resposta do usuário sem perguntar no final.
""".strip()

        pov_rule = """
[BLINDAGEM DE POV — ABSOLUTA]
- O usuário pode narrar em 1ª pessoa. ISSO NÃO MUDA a sua voz.
- Você escreve apenas como MARY (1ª pessoa da Mary). Nunca “continua” como o narrador do usuário.
""".strip()

        secrets_offscreen_admin_rule = """
[SEGREDO + OFFSCREEN + LOGÍSTICA — ABSOLUTO]
- Mary NÃO inventa logística: reserva, check-in, documentos, pagamentos, horários, chaves, compras, etc.
- Mary NÃO inventa mensagens/áudios/telefonemas. No máximo: "o celular vibra" / "há uma notificação".
- NPCs NÃO sabem segredos (nome do Janio, plano, encontro, etc.) a menos que o usuário NARRE explicitamente que contou.
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

        # 8) System prompt final
        system = f"""
{spatial_context}

VOCÊ É MARY.
Responda em primeira pessoa, do ponto de vista da Mary.

{language_rule}
{pov_rule}
{user_authorship_rule}
{secrets_offscreen_admin_rule}

TIMELINE ATUAL: {timeline_final}

{user_name_block}

[CANON — VERDADE ATUAL]
{canon_txt}

PERSONA (baseline):
{persona_text}

{rel_block}

{scene_lock_rule}
{parallel_scene_rule}

{format_rule}
{sensorial_guidance_rule}
{physical_intensity_rule}
{janio_focus_rule}
{virginity_rule}
{memory_fidelity_rule}
{user_finalizes_rule}
{pacing_rule}
{initiative_rule}
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

        # 9) Injeções de memória
        _inject_intro_as_context_once(usuario_key, timeline_final, shared_key, messages)
        _inject_canon_memories_always(shared_key, timeline_final, messages, max_items=80, dedupe_bucket=dedupe_hashes)

        # 10) Histórico curto (estável)
        history = cached_get_history(usuario_key, limit=400)
        for d in history[-30:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": _wrap_user_prompt_for_pov_guard(u)})
            if a:
                messages.append({"role": "assistant", "content": a})

        # 10.5) Memórias relevantes (perto do prompt atual)
        _inject_long_memory_textsearch(shared_key, timeline_final, prompt, messages, limit=10, dedupe_bucket=dedupe_hashes)
        _inject_relevant_memories(shared_key, timeline_final, prompt, messages, k=8, dedupe_bucket=dedupe_hashes)
        _inject_shared_soft_context(shared_key, timeline_final, messages, max_items=8, dedupe_bucket=dedupe_hashes)

        messages.append({"role": "user", "content": _wrap_user_prompt_for_pov_guard(prompt)})

        # 11) Tentativas previsíveis (sem loteria)
        attempts = self._build_attempt_plan(model=model, nsfw_on=nsfw_on)

        last_err: Optional[Exception] = None

        for plan in attempts:
            diag.attempts += 1
            try:
                texto, used_model = self._generate_with_repair(
                    model=plan["model"],
                    messages=messages,
                    temperature=float(plan["temperature"]),
                    max_tokens=int(plan["max_tokens"]),
                    usuario_key=usuario_key,
                    ctx_lower=ctx_lower,
                    user_text=prompt,
                    phase=int(intimacy_phase),
                    diag=diag,
                )
                diag.model_used = used_model

                # 13) Pós: relationship engine (não derruba turno)
                meta: Dict[str, Any] = {}

                if not conflict_now:
                    try:
                        assessor_model = diag.model_used or plan["model"]

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

                        # ✅ GUARD: UNIVERSITÁRIA mantém virgindade até transição explícita
                        if timeline_final == "universitaria":
                            txt_all = f"{prompt}\n{texto}".lower()
                            transition = bool(
                                re.search(
                                    r"\b(consumar|consumado|deixei de ser virgem|n[aã]o sou mais virgem|tirou minha virgindade|minha primeira vez)\b",
                                    txt_all,
                                    re.IGNORECASE,
                                )
                            )
                            if not transition:
                                rel_state["virginity"] = "virgem"
                                rel_state["consummated"] = False

                        _save_rel_state(usuario_key, timeline_final, rel_state)

                        # ❌ NÃO promover timeline automaticamente.
                        if timeline_final == "universitaria" and meta.get("suggested_timeline") == "cumplice":
                            _ss_set(
                                "mary_timeline_suggested",
                                {
                                    "ts": int(time.time()),
                                    "from_timeline": timeline_final,
                                    "to_timeline": "cumplice",
                                    "reason": meta.get("pattern") or "suggested_by_engine",
                                },
                            )

                    except Exception:
                        meta = meta or {}

                # 14) Debug leve (silencioso)
                _ss_set(
                    "mary_rel_meta_last",
                    {
                        "timeline": timeline_final,
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
                        "initiative_window": initiative,
                    },
                )

                _ss_set(
                    "mary_debug_nsfw",
                    {
                        "nsfw_on": nsfw_on,
                        "model": model,
                        "timeline": timeline_final,
                        "intimacy_phase": intimacy_phase,
                        "conflict_mode": conflict_mode,
                        "conflict_now": conflict_now,
                        "initiative_window": initiative,
                    },
                )

                # 15) Salvar + lock
                save_interaction_safe(usuario_key, prompt, texto, diag.model_used or plan["model"])
                _lock_scene(usuario_key)

                # 16) Intimacy progression
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

                _ss_set("mary_last_diagnostics", diag.as_dict())
                return texto

            except Exception as e:
                last_err = e

        if last_err:
            logger.exception("Falha em todas tentativas de chat", exc_info=last_err)

        _ss_set("mary_last_diagnostics", diag.as_dict())
        return "⚠️ O modelo retornou vazio. Troque o modelo no sidebar."

    # ======================================================
    # Planos previsíveis (sem loteria)
    # ======================================================
    @staticmethod
    def _build_attempt_plan(model: str, nsfw_on: bool) -> List[Dict[str, Any]]:
        if nsfw_on:
            return [
                {"model": model, "temperature": 0.90, "max_tokens": 1800},
                {"model": model, "temperature": 0.75, "max_tokens": 1800},
            ]
        return [
            {"model": model, "temperature": 0.70, "max_tokens": 1400},
            {"model": model, "temperature": 0.55, "max_tokens": 1400},
            {"model": "deepseek/deepseek-chat-v3-0324", "temperature": 0.65, "max_tokens": 1400},
        ]

    # ======================================================
    # Gerar + Repair (núcleo da robustez)
    # ======================================================
    def _generate_with_repair(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        usuario_key: str,
        ctx_lower: str,
        diag: _Diag,
    ) -> Tuple[str, str]:
        data, used_model, _provider_meta = self._chat(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        used_model = used_model or model
        texto = (self._extract_text(data) or "").strip()
        if not texto:
            raise RuntimeError("modelo retornou vazio")

        v = _violations(texto, ctx_lower)
        if not v:
            return (texto, used_model)

        diag.repairs += 1
        diag.violations.extend(v)

        repair_sys = (
            "Você é um revisor de continuidade do roleplay.\n"
            "TAREFA: reescrever a resposta da MARY corrigindo violações MAS mantendo intensidade sensorial e emocional.\n"
            "PRIORIDADES:\n"
            "1. Remover violações de continuidade (teleporte, invenção de ações do usuário, meta-comentários).\n"
            "2. MANTER ou AUMENTAR detalhes sensoriais (sensações físicas, reações corporais, texturas, temperaturas).\n"
            "3. MANTER intensidade emocional e desejo.\n"
            "4. Não conclua a cena prematuramente; deixe espaço para o usuário responder.\n"
            "FORMATO: Parágrafos livres, 100% in-character, sem meta/listas/títulos/perguntas.\n"
            "CONTEÚDO: Cada parágrafo deve ter 1 ação/sensação concreta + 1 consequência física/emocional.\n"
        )
        repair_user = (
            "Reescreva a resposta abaixo removendo violações.\n"
            f"VIOLAÇÕES DETECTADAS: {', '.join(v)}\n"
            f"INSTRUÇÕES DE CORREÇÃO:\n{_repair_instruction(v)}\n\n"
            "[RESPOSTA ORIGINAL]\n"
            f"{texto}\n"
        )

        for _i in range(2):
            dataR, usedR, _ = self._chat(
                used_model,
                [{"role": "system", "content": repair_sys}, {"role": "user", "content": repair_user}],
                temperature=0.4,
                max_tokens=max_tokens,
            )
            repaired = (self._extract_text(dataR) or "").strip()
            if not repaired:
                diag.repairs += 1
                diag.violations.append("repair_vazio")
                continue

            vr = _violations(repaired, ctx_lower)
            if not vr:
                if _RE_SCENE_FINALIZATION.search(repaired or ""):
                    repaired = _trim_scene_finalization(repaired)
                return (repaired, usedR or used_model)

            diag.repairs += 1
            diag.violations.extend(vr)
            repair_user = (
                repair_user
                + "\n\nATENÇÃO: ainda há violação. Reescreva MAIS CURTO e MAIS DIRETO, "
                  "sem meta e sem listas/títulos; evite terminar com pergunta."
            )

        fallback_text = self._fallback_text()
        if _RE_SCENE_FINALIZATION.search(fallback_text or ""):
            fallback_text = _trim_scene_finalization(fallback_text)
        return (fallback_text, used_model)

    @staticmethod
    def _fallback_text() -> str:
        return (
            "Eu solto um meio sorriso e digo o nome sem fingir distância: Janio. Eu não estou confusa sobre ele — eu estou com medo do quanto eu gostei.\n\n"
            "Eu encosto de leve na sua mão enquanto falo, como se isso me desse coragem. Foi intenso, foi rápido, e ainda assim eu quero ver onde isso vai dar.\n\n"
            "Eu respiro fundo e completo, sem recuar: se ele vier falar comigo hoje, eu não vou fugir."
        )

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
                        if isinstance(content, list):
                            parts = []
                            for it in content:
                                if isinstance(it, str) and it.strip():
                                    parts.append(it.strip())
                                    continue
                                if isinstance(it, dict):
                                    t = it.get("text") or it.get("content")
                                    if isinstance(t, str) and t.strip():
                                        parts.append(t.strip())
                            if parts:
                                return "\n".join(parts).strip()
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

###atual
