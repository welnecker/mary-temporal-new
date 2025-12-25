from __future__ import annotations

"""
MaryService (v3.10 – Timeline-Aware + Canon + RelationshipEngine v2 (virginidade dinâmica + anti-loop)
            + Continuidade Espacial + Memórias Permanentes Compartilhadas (CANON) + Salvamento Dinâmico)

PONTOS-CHAVE (o que foi ajustado aqui):
1) Integração correta com o relationship_engine.py novo:
   - rel_state agora inclui: virginity, consummated, intimacy_level, mature_turns
   - evolve_relationship retorna meta com: hazard_p, mature_turns, virginity_changed, virginity_reason

2) Persistência robusta:
   - _load_rel_state garante que todos os campos necessários existam SEM resetar
   - _save_rel_state salva no fact rel.state::{timeline}

3) Promoção universitária -> cúmplice:
   - quando meta sugerir "cumplice", o service:
     a) muda st.session_state["mary_timeline"]
     b) garante que exista rel_state inicial para "cumplice" (sem depender do usuário)
     c) limpa cache do usuário atual (universitária), e também prepara o próximo

4) Corrigida a parte “duplicada/indentada” do engine dentro do loop de tentativas.
"""

import logging
import re
import hashlib
from typing import Any, Dict, List, Tuple, Optional

import streamlit as st

from core.common.base_service import BaseCharacter
from core.service_router import route_chat_strict
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
    # memórias (compartilhadas)
    append_memory,
    list_memories,
)

from characters.registry import _SERVICE_CACHE
from .persona import get_persona

logger = logging.getLogger(__name__)
_SERVICE_CACHE.clear()


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
    timeline = _normalize_timeline(str(st.session_state.get("mary_timeline") or "cumplice"))
    return _user_key(uid, timeline)


def _shared_memory_key() -> str:
    uid = _current_user_id_fallback()
    return _shared_key(uid)


# ==========================================================
# NSFW TOGGLE
# ==========================================================
SAFE_SENSUAL_STYLE = """
[NSFW_OFF]
Estilo: romance adulto, tensão, intimidade e sugestão.
Evite detalhes gráficos.
""".strip()

NSFW_TOGGLE_STYLE = """
[NSFW_ON]
ESTILO: SEXUALMENTE EXPLÍCITO, GRÁFICO, DIRETO E SEM CENSURA.
""".strip()


# ==========================================================
# CACHE (limit seguro)
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
    hk = f"history::{usuario_key}"
    if hk in st.session_state:
        return st.session_state[hk]
    try:
        docs = get_history_docs(usuario_key, limit=limit) or []
    except Exception:
        docs = []
    st.session_state[hk] = docs
    return docs


def clear_user_cache(usuario_key: str) -> None:
    for k in (f"facts::{usuario_key}", f"history::{usuario_key}"):
        if k in st.session_state:
            del st.session_state[k]


# ==========================================================
# NSFW ENABLE (respeita override)
# ==========================================================
def nsfw_enabled(usuario_key: str, nsfw_override: Optional[bool] = None) -> bool:
    if isinstance(nsfw_override, bool):
        return nsfw_override

    if "mary_nsfw_on" in st.session_state:
        return bool(st.session_state["mary_nsfw_on"])

    facts = cached_get_facts(usuario_key) or {}
    v = facts.get("mary.nsfw")
    if isinstance(v, bool):
        return v
    return True


# ==========================================================
# CONTINUIDADE ESPACIAL
# ==========================================================
def _get_scene_state(facts: Dict[str, Any]) -> Tuple[str, str, str]:
    local = str(facts.get("cena.local") or facts.get("local_cena_atual") or "—")
    tempo = str(facts.get("cena.tempo") or "agora")
    acao = str(facts.get("cena.acao") or "em andamento")
    return local, tempo, acao


def _persist_scene_basics(usuario_key: str, local: str, tempo: str, acao: str) -> None:
    if local:
        set_fact(usuario_key, "cena.local", local, {"fonte": "scene"})
        set_fact(usuario_key, "local_cena_atual", local, {"fonte": "scene_compat"})
    if tempo:
        set_fact(usuario_key, "cena.tempo", tempo, {"fonte": "scene"})
    if acao:
        set_fact(usuario_key, "cena.acao", acao, {"fonte": "scene"})


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
    id_key = f"{prefix}.id"
    text_key = f"{prefix}.text"
    hash_key = f"{prefix}.hash"

    current_id, current_text = _extract_intro_from_persona(timeline)
    current_hash = current_id

    try:
        stored_hash = str(get_fact(usuario_key, hash_key, default="") or "").strip()
        stored_text = str(get_fact(usuario_key, text_key, default="") or "").strip()

        if (not stored_hash) or (stored_hash != current_hash) or (not stored_text):
            set_fact(usuario_key, id_key, current_id, {"fonte": "persona_intro_sync"})
            set_fact(usuario_key, hash_key, current_hash, {"fonte": "persona_intro_sync"})
            set_fact(usuario_key, text_key, current_text, {"fonte": "persona_intro_sync"})
            clear_user_cache(usuario_key)

        return current_id, current_text
    except Exception:
        return current_id, current_text


# ==========================================================
# ✅ CANON: memórias que prevalecem sobre a persona
# ==========================================================
def _get_all_memories(shared_key: str, limit: int = 200) -> List[Dict[str, Any]]:
    try:
        return list_memories(shared_key, limit=limit) or []
    except Exception:
        return []


def _has_canon_memories(shared_key: str) -> bool:
    mems = _get_all_memories(shared_key, limit=80)
    for m in mems:
        meta = m.get("meta") or {}
        if str(meta.get("kind") or "").strip().lower() == "canon":
            return True
    return False


def _extract_canon_overrides(mems: List[Dict[str, Any]]) -> List[Tuple[str, Any, str]]:
    out: List[Tuple[str, Any, str]] = []
    for m in mems or []:
        meta = m.get("meta") or {}
        if str(meta.get("kind") or "").strip().lower() != "canon":
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
    lines = ["[FATOS CANÔNICOS — OVERRIDES (prevalecem sobre a persona)]"]
    for key, value, date_iso in overrides:
        if isinstance(value, bool):
            v = "true" if value else "false"
        elif value is None:
            v = "null"
        else:
            v = str(value)
        if date_iso:
            lines.append(f"- {key} = {v} (desde {date_iso})")
        else:
            lines.append(f"- {key} = {v}")
    return "\n".join(lines).strip()


def _inject_canon_memories_always(shared_key: str, messages: List[Dict[str, str]], max_items: int = 80) -> None:
    mems = _get_all_memories(shared_key, limit=300)
    if not mems:
        return

    canon = []
    for m in mems:
        meta = m.get("meta") or {}
        if str(meta.get("kind") or "").strip().lower() == "canon":
            canon.append(m)

    if not canon:
        return

    selected = canon[-max_items:] if len(canon) > max_items else canon
    overrides = _extract_canon_overrides(selected)
    overrides_block = _build_overrides_block(overrides)

    lines: List[str] = []
    lines.append("[MEMÓRIAS CANÔNICAS — COMPARTILHADAS]")
    lines.append("Estas memórias são fatos do universo e DEVEM ser seguidas.")
    lines.append("Se a persona contradizer, as memórias vencem.")
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
        lines.append(str(m.get("text") or "").strip())
        lines.append("")

    messages.append({"role": "system", "content": "\n".join(lines).strip()})


def _inject_intro_as_context_once(usuario_key: str, timeline: str, shared_key: str, messages: List[Dict[str, str]]) -> None:
    flag = f"intro_ctx_injected::{usuario_key}"
    if st.session_state.get(flag):
        return

    if _has_canon_memories(shared_key):
        st.session_state[flag] = True
        return

    _, intro_text = _sync_intro_fact(usuario_key, timeline)
    intro_text = (intro_text or "").strip()
    if intro_text:
        messages.append({"role": "system", "content": f"[QUADRO ZERO — INTRO DA PERSONA]\n{intro_text}"})
    st.session_state[flag] = True


# ==========================================================
# MEMÓRIAS PERMANENTES — comandos e parsing
# ==========================================================
_SAVE_RE = re.compile(r"^\s*(?:mary\s*,?\s*)?(?:salve|salvar|guarde)\b", re.IGNORECASE)
_REMEMBER_RE = re.compile(r"^\s*(?:mary\s*,?\s*)?(?:você\s+)?(?:lembra|recorda)\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})\b")
_SUMMARY_HINT_RE = re.compile(r"\b(resumo|resuma|resumir|resumindo)\b", re.IGNORECASE)

_RANGE_RE = re.compile(
    r"\bde\s+(?P<start>.+?)\s+at[ée]\s+(?P<end>.+?)(?:\s*,?\s*em\s+\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4})?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _is_save_memory_command(user_text: str) -> bool:
    return bool(_SAVE_RE.search(user_text or ""))


def _is_memory_question(user_text: str) -> bool:
    return bool(_REMEMBER_RE.search(user_text or ""))


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


# ==========================================================
# ✅ SALVAMENTO DINÂMICO DE RESUMO (de X até Y) — apenas MARY
# ==========================================================
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
        transcript = "\n\n".join([f"[MARY #{i+1}]\n{m}" for i, m in enumerate(sliced)])
        meta = {
            "mode": "dynamic_range",
            "debug": dbg,
            "start_hint": start_hint,
            "end_hint": end_hint,
            "mary_msgs_used": len(sliced),
        }
        return transcript.strip(), meta

    sliced = mary_msgs[-10:]
    transcript = "\n\n".join([f"[MARY #{i+1}]\n{m}" for i, m in enumerate(sliced)])
    meta = {
        "mode": "fallback_last10",
        "debug": "no_range_in_prompt",
        "mary_msgs_used": len(sliced),
    }
    return transcript.strip(), meta


# ==========================================================
# Injeção de memórias relevantes (Q&A)
# ==========================================================
def _select_relevant_memories(mems: List[Dict[str, Any]], query: str, k: int = 3) -> List[Dict[str, Any]]:
    q = (query or "").lower()
    words = [w for w in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", q) if len(w) >= 4]
    date_iso = _extract_date_iso(query)

    scored = []
    for m in mems or []:
        txt = str(m.get("text") or "")
        low = txt.lower()
        score = 0
        for w in words[:10]:
            if w in low:
                score += 2
        meta = m.get("meta") or {}
        if date_iso and str(meta.get("date") or "") == date_iso:
            score += 5
        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [m for s, m in scored if s > 0][:k]
    if not picked:
        return (mems or [])[:k]
    return picked


def _inject_memories_context(shared_key: str, user_prompt: str, messages: List[Dict[str, str]]) -> None:
    try:
        mems = list_memories(shared_key, limit=200) or []
    except Exception:
        mems = []

    if not mems:
        return

    picked = _select_relevant_memories(mems, user_prompt, k=3)
    if not picked:
        return

    lines: List[str] = []
    for i, m in enumerate(picked, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        title = meta.get("title") or ""
        header = f"- MEMÓRIA {i}"
        if d:
            header += f" (data: {d})"
        if title:
            header += f" — {title}"
        lines.append(header)
        lines.append(str(m.get("text") or "").strip())
        lines.append("")

    mem_block = "\n".join(lines).strip()

    messages.append(
        {
            "role": "system",
            "content": (
                "[MEMÓRIAS PERMANENTES (selecionadas)]\n"
                "Use como fatos canônicos quando aplicável.\n"
                "Responda interpretando com coerência (não cole literal).\n\n"
                f"{mem_block}"
            ),
        }
    )


def _inject_shared_soft_context(shared_key: str, messages: List[Dict[str, str]], max_items: int = 8) -> None:
    try:
        mems = list_memories(shared_key, limit=120) or []
    except Exception:
        mems = []

    if not mems:
        return

    soft = []
    for m in mems:
        meta = m.get("meta") or {}
        kind = str(meta.get("kind") or "").strip().lower()
        if kind == "canon":
            continue
        soft.append(m)

    if not soft:
        return

    selected = soft[-max_items:] if len(soft) > max_items else soft

    lines = ["[MEMÓRIAS COMPARTILHADAS (contexto suave)]", "Use para manter coerência, sem citar literalmente.", ""]
    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        header = f"- MEM {i}"
        if d:
            header += f" (data: {d})"
        lines.append(header)
        lines.append(str(m.get("text") or "").strip())
        lines.append("")

    messages.append({"role": "system", "content": "\n".join(lines).strip()})


# ==========================================================
# RELATIONSHIP STATE (facts > canon default > fallback)
# ==========================================================
def _rel_fact_key(timeline: str) -> str:
    tl = (timeline or "").strip() or "cumplice"
    return f"rel.state::{tl}"


def _load_rel_state(
    facts: Dict[str, Any],
    timeline: str,
    canon_default: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Carrega estado de relação.

    Prioridade:
    1) facts['rel.state::{timeline}'] (persistido)
    2) canon_default (canon.py -> relationship_state)
    3) default_relationship_state(timeline) (fallback seguro)

    Importante: garante campos do engine novo (anti-loop / virgindade dinâmica).
    """
    base = default_relationship_state(timeline)

    # aplica defaults do canon por cima do fallback (sem apagar internos)
    if isinstance(canon_default, dict):
        for k, v in canon_default.items():
            if not str(k).startswith("_"):
                base[k] = v

    key = _rel_fact_key(timeline)
    raw = (facts or {}).get(key)

    if isinstance(raw, dict):
        for k, v in raw.items():
            base[k] = v

    # garante internos usados pelo engine
    base.setdefault("_promote_streak", 0)
    base.setdefault("_regress_streak", 0)

    # novos campos (engine v2)
    base.setdefault("mature_turns", 0)
    base.setdefault("intimacy_level", 0 if timeline == "universitaria" else 3)
    base.setdefault("consummated", False if timeline == "universitaria" else True)
    base.setdefault("virginity", "virgem" if timeline == "universitaria" else "nao_virgem")

    if not base.get("stage"):
        base["stage"] = "conhecendo" if (timeline or "") == "universitaria" else "casados"

    return base


def _save_rel_state(usuario_key: str, timeline: str, rel: Dict[str, Any]) -> None:
    key = _rel_fact_key(timeline)
    set_fact(usuario_key, key, rel, {"fonte": "relationship_engine"})


def _ensure_rel_state_for_timeline(user_id: str, timeline: str) -> None:
    """
    Quando o engine sugerir migrar para outra timeline, garantimos que exista um rel_state inicial
    persistido para a timeline destino, para não “parecer reset/confusão” no primeiro turno.
    """
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
        # 1) Mudança explícita de local
        # ----------------------------------------------------------
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou and novo_local:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            clear_user_cache(usuario_key)
            return f"_Eu te puxo comigo até {novo_local}…_"

        # ----------------------------------------------------------
        # 2) Comando: salvar memória (texto direto OU resumo dinâmico)
        # ----------------------------------------------------------
        if _is_save_memory_command(prompt):
            raw_body = _strip_save_prefix(prompt)
            date_iso = _extract_date_iso(prompt) or _extract_date_iso(raw_body)

            if _wants_auto_summary(prompt):
                transcript, dbg_meta = _build_dynamic_mary_transcript(usuario_key, prompt)
                if not transcript.strip():
                    return "⚠️ Não encontrei histórico suficiente da Mary para resumir. Converse mais um pouco e peça novamente."

                summary_system = (
                    "Você é a personagem Mary, mas sua tarefa agora é gerar um RESUMO FACTUAL para memória.\n"
                    "REGRAS ABSOLUTAS:\n"
                    "- Use SOMENTE as informações presentes em [TRANSCRIÇÃO].\n"
                    "- NÃO invente, NÃO complete lacunas, NÃO crie fatos fora do texto.\n"
                    "- Texto corrido, sem bullets, sem listagem.\n"
                    "- Escreva com clareza e sequência temporal.\n"
                    "- Foque nos fatos (o que aconteceu e por quê), sem floreios.\n"
                    "- 8 a 16 linhas.\n"
                    "- Se o pedido do usuário delimitar recorte, não avance além.\n"
                    "- Idioma: PT-BR.\n"
                )

                summary_user = (
                    "Gere um resumo factual para memória permanente.\n"
                    f"Data (se houver): {date_iso or '—'}\n"
                    "Recorte: conforme pedido do usuário (se presente).\n\n"
                    f"[TRANSCRIÇÃO — APENAS FALAS DA MARY]\n{transcript}"
                )

                try:
                    data, used_model, _ = self._chat(
                        model,
                        [
                            {"role": "system", "content": summary_system},
                            {"role": "user", "content": summary_user},
                        ],
                        temperature=0.2,
                        max_tokens=850,
                    )

                    resumo = self._extract_text(data)
                    if not resumo:
                        return "⚠️ Não consegui gerar o resumo (modelo retornou vazio). Tente novamente."

                    meta = {
                        "kind": "dynamic_summary",
                        "date": date_iso or "",
                        "timeline_at_save": timeline_final,
                        "model_used": used_model or model,
                        **(dbg_meta or {}),
                    }

                    append_memory(shared_key, resumo.strip(), meta=meta)

                    return (
                        "✅ **Resumo salvo na memória permanente** (compartilhado entre as duas Marys)\n\n"
                        f"📌 **Data:** `{date_iso or '—'}`\n"
                        f"🧭 **Recorte:** `{(dbg_meta or {}).get('mode','—')}`\n\n"
                        "---\n\n"
                        f"{resumo.strip()}"
                    )

                except Exception as e:
                    logger.exception("Falha ao gerar/salvar resumo dinâmico", exc_info=e)
                    return f"⚠️ Falha ao gerar/salvar resumo: {type(e).__name__}: {e}"

            # salvamento direto
            body = raw_body
            if len(body.strip()) < 40:
                captured = _fallback_capture_recent_history(usuario_key, turns=10)
                if captured:
                    body = f"{body}\n\n[FONTE: recorte do histórico]\n{captured}".strip()

            if not body.strip():
                return "⚠️ Não consegui salvar: cole o texto do momento (ou descreva com detalhes) e informe a data (dd/mm/aaaa)."

            meta = {
                "kind": "user_request",
                "date": date_iso or "",
                "timeline_at_save": timeline_final,
            }

            try:
                append_memory(shared_key, body.strip(), meta=meta)
            except Exception as e:
                logger.exception("Falha ao salvar memória", exc_info=e)
                return f"⚠️ Falha ao salvar memória: {type(e).__name__}: {e}"

            return "✅ Memória permanente salva (compartilhada entre as duas Marys)."

        # ----------------------------------------------------------
        # 3) Persona + sistema
        # ----------------------------------------------------------
        persona_text, _ = get_persona(timeline_final)
        facts = cached_get_facts(usuario_key)

        canon = get_canon("mary", timeline=timeline_final, user_key=user_id) or {}
        canon_txt = canon_to_text(canon)

        canon_rel_default = canon.get("relationship_state") if isinstance(canon.get("relationship_state"), dict) else None
        rel_state = _load_rel_state(facts, timeline_final, canon_rel_default)
        rel_block = rel_state_to_prompt_block(rel_state)

        scene_loc, scene_time, scene_action = _get_scene_state(facts)
        spatial_context = _build_spatial_context(scene_loc, scene_time, scene_action)
        nsfw_block = NSFW_TOGGLE_STYLE if nsfw_enabled(usuario_key, nsfw_override=nsfw) else SAFE_SENSUAL_STYLE

        system = f"""
{spatial_context}

VOCÊ É A PERSONAGEM MARY.

TIMELINE ATUAL: {timeline_final}

[CANON — VERDADE ATUAL]
{canon_txt}

PERSONA (baseline):
{persona_text}

{rel_block}

REGRAS ABSOLUTAS:
- NÃO misture timelines.
- Nunca contradiga o ESTADO DE RELAÇÃO (CANÔNICO) e a timeline ativa.
- A timeline define o tom macro; o estágio da relação (stage) define o quanto existe de vínculo/entrega.
- Se MEMÓRIA CANÔNICA contradizer a persona, a MEMÓRIA vence.

{nsfw_block}
""".strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]

        # ----------------------------------------------------------
        # 4) Intro 1x por sessão (só se NÃO houver CANON)
        # ----------------------------------------------------------
        _inject_intro_as_context_once(usuario_key, timeline_final, shared_key, messages)

        # ----------------------------------------------------------
        # 5) ✅ CANON sempre injetado (continuidade forte)
        # ----------------------------------------------------------
        _inject_canon_memories_always(shared_key, messages, max_items=80)

        # 5.1) Continuidade suave (não-canon)
        _inject_shared_soft_context(shared_key, messages, max_items=8)

        # 6) Pergunta de memória: injeta relevantes
        if _is_memory_question(prompt):
            _inject_memories_context(shared_key, prompt, messages)

        # ----------------------------------------------------------
        # 7) Histórico (timeline atual)
        # ----------------------------------------------------------
        history = cached_get_history(usuario_key, limit=400)
        for d in history[-30:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": u})
            if a:
                messages.append({"role": "assistant", "content": a})

        messages.append({"role": "user", "content": prompt})

              # ----------------------------------------------------------
        # 8) Chat com retry/fallback
        # ----------------------------------------------------------
        attempts = [
            {"model": model, "temperature": 0.7},
            {"model": model, "temperature": 0.4},
            {"model": "deepseek/deepseek-chat-v3-0324", "temperature": 0.6},
        ]

        last_err: Optional[Exception] = None

        for attempt in attempts:
            try:
                data, used_model, _ = self._chat(
                    attempt["model"],
                    messages,
                    temperature=attempt["temperature"],
                    max_tokens=1200,
                )
                texto = self._extract_text(data)
                if not texto:
                    continue

                # ----------------------------------------------------------
                # ✅ Relationship Engine (pós-resposta):
                # - avalia o turno e atualiza estado canônico persistido
                # - pode sugerir migração universitária -> cúmplice
                # ----------------------------------------------------------
                try:
                    assessor_model = used_model or attempt["model"]

                    def _assessor(system_prompt: str, user_prompt: str) -> str:
                        data2, _, _ = self._chat(
                            assessor_model,
                            [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            temperature=0.0,
                            max_tokens=260,
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

                    # Promoção automática de timeline: universitária -> cúmplice
                    promoted = False
                    if (
                        timeline_final == "universitaria"
                        and (meta or {}).get("suggested_timeline") == "cumplice"
                    ):
                        promoted = True

                        # 1) troca timeline no app (UI)
                        st.session_state["mary_timeline"] = "cumplice"

                        # 2) garante rel_state inicial da timeline destino (persistido)
                        _ensure_rel_state_for_timeline(user_id, "cumplice")

                        # 3) limpa cache da timeline atual (universitária)
                        clear_user_cache(usuario_key)

                        # 4) IMPORTANTÍSSIMO:
                        #    daqui em diante, o usuario_key correto para salvar é o da timeline destino
                        usuario_key = _user_key(user_id, "cumplice")

                    # (Opcional) debug rápido no session_state — útil pra você verificar “loop”
                    debug_tl = "cumplice" if promoted else timeline_final
                    st.session_state["mary_rel_meta_last"] = {
                        "timeline": debug_tl,
                        "stage": rel_state.get("stage"),
                        "virginity": rel_state.get("virginity"),
                        "consummated": rel_state.get("consummated"),
                        "mature_turns": rel_state.get("mature_turns"),
                        "hazard_p": (meta or {}).get("hazard_p"),
                        "virginity_changed": (meta or {}).get("virginity_changed"),
                        "virginity_reason": (meta or {}).get("virginity_reason"),
                    }

                except Exception:
                    # Se o engine falhar, não derruba o chat.
                    pass

                save_interaction(usuario_key, prompt, texto, used_model or attempt["model"])
                clear_user_cache(usuario_key)
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
    def _extract_text(resp: dict) -> str:
        try:
            return (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        except Exception:
            return ""

    def _chat(self, model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: int):
        return route_chat_strict(
            model,
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": max_tokens,
            },
        )
