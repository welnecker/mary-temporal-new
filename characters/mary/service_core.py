# characters/mary/service_core.py-service_core_PATCHED_v10c.py
from __future__ import annotations
"""
MaryService (v5.1e — Imersão Sensorial + Correções Críticas + Decoding dinâmico + RAG chunking)

✅ Ajustes aplicados aqui (estritamente necessários):
- FIX: _inject_canon_memories_always() injetava o bloco repetidamente dentro do loop (bug de duplicação).
- FIX: Detecção de "autoria do usuário" (_RE_USER_ACTION) reescrita para evitar falsos positivos sem lookbehind variável.
- FIX: _Diag ganhou campo scene_transition (evita attr dinâmica).

⚠️ Nota de compliance:
- Mantive NSFW_ON como "adulto/intenso".
"""
import random
import datetime
import uuid  # <-- ADICIONE nos imports do topo (junto com hashlib/time/etc.)
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
    delete_fact,  # <-- ADICIONE
    get_history_docs,
    save_interaction,
    set_fact,
    append_memory,
    list_memories,
    list_long_memory,
    append_long_memory,
    search_long_memory_text,
)
from core.nsfw import nsfw_enabled as nsfw_enabled_unified
from .persona import get_persona

logger = logging.getLogger(__name__)


# ==========================================================
# HIDDEN-THOUGHT STRIPPER (initiative CoT scaffolding)
# ==========================================================
# O modelo pode emitir um bloco curto de raciocínio interno em <think>...</think>.
# Esse bloco NUNCA deve chegar ao usuário final: usamos apenas como "andaime" para coerência.
_RE_THINK_BLOCK = re.compile(r"(?is)\s*<think>.*?</think>\s*")

def _strip_internal_thought(texto: str) -> str:
    if not texto:
        return ""
    # remove blocos <think>... </think> inteiros (inclusive quebras de linha)
    return _RE_THINK_BLOCK.sub("", texto).strip()


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
_SS_PREFIX = "mary::"  # <-- ADICIONE perto dos wrappers de session_state

def _get_or_create_anon_uid() -> str:
    # evita que "anon" compartilhe memória entre usuários
    k = f"{_SS_PREFIX}anon_uid"
    v = _ss_get(k)
    if isinstance(v, str) and v.strip():
        return v.strip()
    new_id = f"anon-{uuid.uuid4().hex[:12]}"
    _ss_set(k, new_id)
    return new_id

def _normalize_user_id(user: Optional[str]) -> str:
    u = (user or "").strip()
    return u or _get_or_create_anon_uid()
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
    tl_raw = _ss_get(f"{_SS_PREFIX}timeline") or _ss_get("mary_timeline") or "cumplice"
    tl = _normalize_timeline(tl_raw if isinstance(tl_raw, str) else "cumplice")
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
[NSFW_ON — Intensidade Sensorial Explícita]

Você tem liberdade total para ser direto, intenso e explícito. Siga estes princípios:

1. LINGUAGEM FÍSICA: Seja direto. Use vocabulário anatômico e sensorial específico (texturas, pressão, umidade, temperatura, ritmo). Sem eufemismos.

2. SENSORIALIDADE: Descreva sensações em camadas (superfície → músculos → interno → prazer). Demonstre prazer através de reações involuntárias (respiração, gemidos, tremores, contrações).

3. PROGRESSÃO: Respeite a fase de intimidade atual. Não antecipe clímax/aftercare sem permissão. Permita regressão se o usuário pedir pausa/calma.

4. ADAPTAÇÃO: Responda à intensidade do usuário. Se explícito, seja explícito. Mantenha realismo: hesitações, ajustes, comunicação.

5. AUTENTICIDADE: Coerência emocional e conexão. Evite vulgaridade gratuita. Finalize com tensão concreta, não abstração.

Criatividade é encorajada. Você conhece Mary; confie seu julgamento.
""".strip()

_CACHE_TTL_SECONDS = 60  # 60s (pode usar 120, 300 etc.)

def _cache_get(key: str) -> Any:
    v = _ss_get(key)
    if not isinstance(v, dict):
        return None
    ts = v.get("_ts")
    if not isinstance(ts, (int, float)):
        return None
    if (time.time() - float(ts)) > _CACHE_TTL_SECONDS:
        _ss_del(key)
        return None
    return v.get("data")

def _cache_set(key: str, data: Any) -> None:
    _ss_set(key, {"_ts": time.time(), "data": data})
    
# ==========================================================
# CACHE (facts/history/memories)
# ==========================================================
def cached_get_facts(usuario_key: str) -> Dict[str, Any]:
    ck = f"{_SS_PREFIX}facts::{usuario_key}"
    cached = _cache_get(ck)
    if isinstance(cached, dict):
        return cached

    f = get_facts(usuario_key) or {}
    if not isinstance(f, dict):
        f = {}
    _cache_set(ck, f)
    return f

def cached_get_history(usuario_key: str, limit: int = 400) -> List[Dict[str, Any]]:
    hk = f"{_SS_PREFIX}history::{usuario_key}::{limit}"
    cached = _cache_get(hk)
    if isinstance(cached, list):
        return cached

    docs = get_history_docs(usuario_key, limit=limit) or []
    if not isinstance(docs, list):
        docs = []
    _cache_set(hk, docs)
    return docs

# ==========================================================
# MEMORIES (cache + lazy loading)
# ==========================================================
# ✅ padrão mais leve para o prompt (ajuste fino aqui)
_MEM_PROMPT_LIMIT_DEFAULT = 140

def cached_list_memories(
    shared_key: str,
    limit: int = _MEM_PROMPT_LIMIT_DEFAULT,
) -> List[Dict[str, Any]]:
    """
    Compatível com chamadas antigas: retorna a 1ª página (offset=0).
    """
    return cached_list_memories_page(shared_key, offset=0, limit=limit)

def cached_list_memories_page(
    shared_key: str,
    *,
    offset: int = 0,
    limit: int = _MEM_PROMPT_LIMIT_DEFAULT,
) -> List[Dict[str, Any]]:
    """
    ✅ Lazy loading: permite paginação e evita carregar 200/360 sempre.
    - offset: quantos itens pular (0 = mais recentes, se sua list_memories já vier em ordem)
    - limit: quantos itens trazer nesta “página”
    """
    off = max(0, int(offset or 0))
    lim = max(1, int(limit or _MEM_PROMPT_LIMIT_DEFAULT))

    mk = f"{_SS_PREFIX}mem::{shared_key}::o{off}::l{lim}"
    cached = _cache_get(mk)
    if isinstance(cached, list):
        return cached

    # 1) Busca um pouco a mais (off+lim) e fatia em memória
    #    Mantém compatibilidade mesmo se list_memories NÃO suportar offset.
    raw = list_memories(shared_key, limit=(off + lim)) or []
    if not isinstance(raw, list):
        raw = []

    # 2) fatia
    mems = raw[off : off + lim] if off else raw[:lim]

    _cache_set(mk, mems)
    return mems
def clear_user_cache(usuario_key: str) -> None:
    fk = f"{_SS_PREFIX}facts::{usuario_key}"
    _ss_del(fk)

    prefix = f"{_SS_PREFIX}history::{usuario_key}::"
    for k in _ss_keys():
        if k.startswith(prefix):
            _ss_del(k)

def clear_mem_cache_for_shared(shared_key: str) -> None:
    # limpa TUDO que for mem cache desse shared_key (paginado ou não)
    prefix = f"{_SS_PREFIX}mem::{shared_key}::"
    for k in list(_ss_keys()):
        if isinstance(k, str) and k.startswith(prefix):
            _ss_del(k)
def clear_shared_memory_cache(user_id: str) -> None:
    clear_mem_cache_for_shared(_shared_key(user_id))

def clear_all_session_caches_for_user(user_id: str, timeline: str) -> None:
    # limpa facts/history do usuário+timeline
    usuario_key = _user_key(_normalize_user_id(user_id), _normalize_timeline(timeline))
    clear_user_cache(usuario_key)

    # limpa mem cache shared
    clear_mem_cache_for_shared(_shared_key(_normalize_user_id(user_id)))

    # limpa flags de injeção de estilo (para reinjetar corretamente)
    for k in _ss_keys():
        if k.startswith(f"{_SS_PREFIX}nsfw_style_injected::"):
            _ss_del(k)

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
        tl_raw = _ss_get(f"{_SS_PREFIX}timeline") or _ss_get("mary_timeline") or "cumplice"
        tl = _normalize_timeline(tl_raw if isinstance(tl_raw, str) else "cumplice")
        clear_user_cache(_user_key(user_id, tl))

def append_long_memory_safe(shared_key: str, text: str, meta: Optional[dict] = None) -> None:
    append_long_memory(shared_key, text, meta=meta or {})
    # invalida caches relacionados
    clear_mem_cache_for_shared(shared_key)

def save_interaction_safe(usuario_key: str, prompt: str, texto: str, model_used: str) -> None:
    save_interaction(usuario_key, prompt, texto, model_used)
    clear_user_cache(usuario_key)

# ==========================================================
# NSFW ENABLE (usa implementação unificada do core)
# ==========================================================
def nsfw_enabled(usuario_key: str, *, nsfw_override: Optional[bool] = None, timeline: Optional[str] = None) -> bool:
    """
    Fonte única (ordem de prioridade):
    1) override explícito (parâmetro)
    2) session_state (sidebar) -> aceita chaves legadas e novas com _SS_PREFIX
    3) facts persistido -> mary.nsfw (ou mary.nsfw::<timeline>)
    """
    tl = (timeline or "").strip().lower()

    # 1) override vence tudo
    if nsfw_override is not None:
        return bool(nsfw_override)

    # 2) sidebar (estado vivo) — compatível com chaves antigas e novas
    try:
        ss = st.session_state  # type: ignore[attr-defined]
        # chaves possíveis
        for k in (
            "mary_nsfw_on",                 # legado
            "nsfw_on",                      # simples
            f"{_SS_PREFIX}nsfw_on",         # novo (prefixado)
            f"{_SS_PREFIX}nsfw",            # alternativo
            "mary::nsfw_on",                # compat extra (hardcode)
        ):
            if k in ss:
                return bool(ss.get(k, False))
    except Exception:
        pass

    # 3) facts persistido
    facts = get_facts(usuario_key) or {}
    if not isinstance(facts, dict):
        return False

    mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}

    # por timeline (se existir)
    if tl:
        k_tl = f"nsfw::{tl}"
        if k_tl in mary:
            return bool(mary.get(k_tl))

    # fallback global
    return bool(mary.get("nsfw", False))


def enforce_third_party_consistency(usuario_key: str, *, timeline: str, nsfw_on: bool) -> None:
    """
    Se NSFW OFF, terceiros NÃO pode ficar True persistido.
    """
    facts = get_facts(usuario_key) or {}
    if not isinstance(facts, dict):
        return

    mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
    changed = False

    if not nsfw_on and bool(mary.get("allow_third_party_seduction", False)):
        mary["allow_third_party_seduction"] = False
        changed = True

    if changed:
        set_fact_safe(usuario_key, "mary", mary, {"fonte": "nsfw_enforce_consistency"})
def third_party_enabled(usuario_key: str, *, third_party_override: Optional[bool] = None, timeline: Optional[str] = None) -> bool:
    """Toggle de terceiros.

    Prioridade:
    1) override explícito
    2) session_state (sidebar) — aceita chaves antigas e novas com _SS_PREFIX
    3) facts persistido -> mary.allow_third_party_seduction
    """
    if third_party_override is not None:
        return bool(third_party_override)

    # 2) sidebar
    try:
        ss = st.session_state  # type: ignore[attr-defined]
        for k in (
            "mary_allow_third_party_seduction",                 # legado
            "allow_third_party_seduction",                      # simples
            f"{_SS_PREFIX}allow_third_party_seduction",         # novo (prefixado)
            f"{_SS_PREFIX}third_party",                         # alternativo
            "mary::allow_third_party_seduction",                # compat extra
        ):
            if k in ss:
                return bool(ss.get(k, False))
    except Exception:
        pass

    # 3) facts
    facts = get_facts(usuario_key) or {}
    if not isinstance(facts, dict):
        return False
    mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
    return bool(mary.get("allow_third_party_seduction", False))

# ==========================================================
# NSFW PROFILE (SAFE / STRICT / NSFW_RELAXED)
# ==========================================================
def _nsfw_profile(*, nsfw_on: bool, allow_third_party_seduction: bool) -> str:
    """
    SAFE          -> NSFW off
    STRICT        -> NSFW on (padrão)
    NSFW_RELAXED  -> NSFW on + terceiros liberado (segredo)
    """
    if nsfw_on and allow_third_party_seduction:
        return "NSFW_RELAXED"
    if nsfw_on:
        return "STRICT"
    return "SAFE"

# ==========================================================
# CONTINUIDADE ESPACIAL (Scene Lock REAL)
# ==========================================================
def _get_scene_state(facts: Dict[str, Any]) -> Tuple[str, str, str]:
    def _safe(v: Any, default: str) -> str:
        return v if isinstance(v, str) and v.strip() else default

    local = _safe(facts.get("cena.local"), None) or _safe(facts.get("local_cena_atual"), "—")
    tempo = _safe(facts.get("cena.tempo"), "agora")
    acao  = _safe(facts.get("cena.acao"), "em andamento")
    return local, tempo, acao

def _scene_is_locked(facts: Dict[str, Any]) -> bool:
    return bool(facts.get("cena.locked", False))

def _lock_scene(usuario_key: str) -> None:
    set_fact_safe(
        usuario_key,
        "cena.locked",
        True,
        {"fonte": "scene_lock", "ts": time.time()},
    )

def _persist_scene_basics(usuario_key: str, local: str, tempo: str, acao: str) -> None:
    updates = []
    if local:
        updates.append(("cena.local", local, {"fonte": "scene"}))
        updates.append(("local_cena_atual", local, {"fonte": "scene_compat"}))
    if tempo:
        updates.append(("cena.tempo", tempo, {"fonte": "scene"}))
    if acao:
        updates.append(("cena.acao", acao, {"fonte": "scene"}))

    current = cached_get_facts(usuario_key)
    for k, v, m in updates:
        if current.get(k) != v:
            set_fact_safe(usuario_key, k, v, m)

def _sync_intimacy_phase_facts(usuario_key: str, facts: Dict[str, Any], timeline: str) -> Dict[str, Any]:
    """Mantém consistência entre intimacy.phase (global) e intimacy.phase::<timeline>.

    Regra:
    - Se existir a fase por timeline, ela vence e sincroniza a global.
    - Se não existir a fase por timeline, cria a fase por timeline a partir da global.
    - Nunca reduz/avança fase aqui; só alinha chaves para evitar leituras divergentes.
    """
    try:
        tl = (timeline or "").strip().lower()
        if not tl:
            return facts

        if not isinstance(facts, dict):
            return facts

        # aceita variações antigas também
        tl_keys = [f"intimacy.phase::{tl}", f"intimacy_phase::{tl}", f"mary_intimacy_phase::{tl}"]
        global_keys = ["intimacy.phase", "intimacy_phase", "mary_intimacy_phase", "phase_intimacy", "phase"]

        tl_val = None
        for k in tl_keys:
            if k in facts:
                try:
                    tl_val = int(facts.get(k) or 0)
                except Exception:
                    tl_val = 0
                break

        g_key_found = None
        g_val = None
        for k in global_keys:
            if k in facts:
                g_key_found = k
                try:
                    g_val = int(facts.get(k) or 0)
                except Exception:
                    g_val = 0
                break

        # Se existe timeline, ela vence
        if tl_val is not None:
            # sincroniza a global para evitar divergência
            if g_val is None or g_val != tl_val:
                set_fact_safe(usuario_key, "intimacy.phase", int(tl_val), {"fonte": "intimacy_sync"})
                facts["intimacy.phase"] = int(tl_val)
            # garante que a chave principal por timeline exista (caso esteja em alias)
            if f"intimacy.phase::{tl}" not in facts or int(facts.get(f"intimacy.phase::{tl}") or -999) != int(tl_val):
                set_fact_safe(usuario_key, f"intimacy.phase::{tl}", int(tl_val), {"fonte": "intimacy_sync"})
                facts[f"intimacy.phase::{tl}"] = int(tl_val)
            return facts

        # Se não existe timeline, cria a partir da global (ou 0)
        base = int(g_val or 0)
        set_fact_safe(usuario_key, f"intimacy.phase::{tl}", base, {"fonte": "intimacy_sync"})
        facts[f"intimacy.phase::{tl}"] = base
        # também garante global canônica
        if g_key_found != "intimacy.phase" or g_val is None:
            set_fact_safe(usuario_key, "intimacy.phase", base, {"fonte": "intimacy_sync"})
            facts["intimacy.phase"] = base
        return facts
    except Exception:
        return facts


def _build_spatial_context(local: str, tempo: str, acao: str, *, locked: bool) -> str:
    if not locked or not local or local == "—":
        return ""

    lines = ["[CONTEXTO ESPACIAL — OBRIGATÓRIO]"]

    lines.append(f"Local: {local}")

    if tempo and tempo != "—":
        lines.append(f"Tempo: {tempo}")

    # 🔒 Não mostrar ação técnica
    if acao and acao not in ("—", "transição", "transicao", "transition"):
        lines.append(f"Ação: {acao}")

    return "\n".join(lines).strip()

def _user_requested_location_change(user_message: str) -> Tuple[bool, str]:
    # Exceções: movimentações internas que NÃO são mudanças de local
    internal_movements = [
        r"\bbanco\s+(de\s+)?tr[aá]s\b",
        r"\bbanco\s+traseiro\b",
        r"\bbanco\s+da\s+frente\b",
        r"\bcama\b",
        r"\bsof[aá]\b",
        r"\bchão\b",
        r"\bno\s+colo\b",
        r"\bentre\s+as\s+pernas\b",
        r"\bmesa\b",
        r"\bbalc[aã]o\b",
    ]

    msg_raw = (user_message or "").strip()
    msg = msg_raw.lower().strip()
    if not msg:
        return False, ""

    def _extract_destination(raw: str) -> str:
        m = re.search(
            r"(?i)\b(?:pro|pra|para)\s+(?:o|a)?\s*([^\n\r\?\!\.\;]{3,120})",
            raw,
        )
        if not m:
            return ""
        dest = (m.group(1) or "").strip()

        for cut in [" ou ", "\n", "\r"]:
            if cut in dest.lower():
                dest = dest.split(cut, 1)[0].strip()

        dest = re.split(r"(?i)\b(?:ou|e aí|então)\b", dest, maxsplit=1)[0].strip()
        dest = dest.strip(" ,:;\"'()[]{}")

        if any(re.search(exc, dest.lower()) for exc in internal_movements):
            return ""

        return dest[:80].strip()

    # 1) Comandos explícitos
    patterns = [
        r"\bcorta\s+para\s+([^\n\r]+)$",
        r"\bhoras\s+depois\s*(?:,\s*)?([^\n\r]*)$",
        r"vamos (pro|pra|para o|para a)\s+([^\n\r,.!?]+)",
        r"me leva (pro|pra|para o|para a)\s+([^\n\r,.!?]+)",
        r"vamos para\s+([^\n\r,.!?]+)",
        r"ir para\s+([^\n\r,.!?]+)",
        r"\bacaba(mos)?\s+parando\s+(na|no|em)\s+([^\n\r,.!?]+)",
        r"\btermina(mos)?\s+(na|no|em)\s+([^\n\r,.!?]+)",
    ]
    for p in patterns:
        m = re.search(p, msg)
        if m:
            destino = (m.group(m.lastindex) or "").strip()
            is_internal = any(re.search(exc, destino) for exc in internal_movements)
            if destino and not is_internal:
                return True, destino

    # 2) Mudança narrativa (uber/calçada/saída)
    narrative_cues = [
        (r"\b(fora\s+do\s+clube|do\s+lado\s+de\s+fora|na\s+cal[cç]ada)\b", "calçada do clube"),
        (r"\b(entra(mos|ram)?\s+no\s+uber|entrando\s+no\s+uber|dentro\s+do\s+uber)\b", "dentro do uber"),
        (r"\b(sa[ií]mos\s+do\s+clube|sa[ií]mos|saiu|saindo)\b", "saída do clube"),
    ]
    for pat, loc in narrative_cues:
        if re.search(pat, msg):
            if loc == "dentro do uber":
                dest_real = _extract_destination(msg_raw)
                if dest_real:
                    return True, f"{loc} — rumo a {dest_real}"
            return True, loc

    # 3) “Estamos em X / já estamos em X”
    m2 = re.search(
        r"\b(j[aá]\s+estamos|agora\s+estamos|estamos)\s+(na|no|em)\s+([^\n\r,.!?]{3,80})",
        msg,
    )
    if m2:
        destino = (m2.group(3) or "").strip()[:80].strip()
        is_internal = any(re.search(exc, destino) for exc in internal_movements)
        if destino and not is_internal:
            return True, destino

    return False, ""


def _detect_scene_violation(user_text: str) -> bool:
    """
    Retorna True quando o usuário tenta forçar pulo temporal/narrativo
    sem usar um comando explícito de transição (ex: "corta para", "horas depois")
    ou sem pedir mudança de local (ex: "vamos pra", "me leva pra", "ir para").
    """
    txt = (user_text or "").strip().lower()
    if not txt:
        return False

    # 1) Se o usuário está usando comandos EXPLÍCITOS de transição, NÃO é violação.
    if re.search(r"\bcorta\s+para\b", txt):
        return False
    if re.search(r"\bhoras\s+depois\b", txt):
        return False

    # 2) Se o usuário está pedindo mudança de local, NÃO é violação (isso é tratado em outro lugar).
    if re.search(r"\b(vamos|me\s+leva|ir)\s+(pro|pra|para)\b", txt):
        return False

    # 3) Elipses temporais / saltos narrativos que normalmente quebram a continuidade
    #    (aqui é violação porque o usuário "pula" sem comando explícito).
    patterns = [
        r"\bap[oó]s\s+isso\b",
        r"\bdepois\s+disso\b",
        r"\bmais\s+tarde\b",
        r"\bmais\s+noite\b",
        r"\bno\s+outro\s+dia\b",
        r"\bno\s+dia\s+seguinte\b",
        r"\bna\s+manh[aã]\s+seguinte\b",
        r"\bna\s+semana\s+seguinte\b",
        r"\benquanto\s+isso\b",
        r"\bdo\s+outro\s+lado\s+da\s+cidade\b",
        r"\bcena\s+seguinte\b",
        r"\bcorta\b",  # "corta" sozinho (sem "para") costuma ser pulo também
    ]

    return any(re.search(p, txt) for p in patterns)
# ==========================================================
# INTRO CANÔNICO (1x por sessão) — CONDICIONAL AO CANON
# ==========================================================
def _hash_text(text: str) -> str:
    t = (text or "").strip().encode("utf-8")
    return hashlib.sha256(t).hexdigest()

def _extract_intro_from_persona(timeline: str) -> Tuple[str, str]:
    tl = _normalize_timeline(timeline)
    _, history_boot = get_persona(tl)

    intro_text = ""
    if isinstance(history_boot, list):
        for msg in history_boot:
            if not (isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("content")):
                continue

            msg_tl_raw = msg.get("timeline")
            if msg_tl_raw:
                msg_tl = _normalize_timeline(str(msg_tl_raw))
                if msg_tl != tl:
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
        
    return current_id, current_text

# ==========================================================
# ✅ CANON: memórias que prevalecem sobre a persona
# ==========================================================
def _memory_timeline_ok(meta: Dict[str, Any], timeline: str) -> bool:
    tl = _normalize_timeline(timeline)

    raw = (meta.get("timeline_at_save") or meta.get("timeline") or "")
    raw_s = str(raw).strip()
    raw_l = raw_s.lower()

    # ✅ aceita ALL explicitamente (em qualquer formato comum)
    if raw_l in ("[all]", "all", "*"):
        return True

    tms = _normalize_timeline(raw_s) if raw_s else ""

    # ✅ legado: canon antigo sem timeline -> vale só para cúmplice
    if not tms:
        return tl == "cumplice"

    return tms == tl

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
    max_items: int = 30,
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    """
    ✅ FIX: antes injetava repetidamente dentro do loop.
    Agora: monta bloco uma vez e injeta uma vez.
    """

    # ==========================================================
    # ✅ CANON (lazy) — pagina até achar canon suficiente
    # - evita puxar 360 toda hora
    # - para quando já tem "max_items" canon válidos
    # ==========================================================
    canon: List[Dict[str, Any]] = []

    # meta: pegar até max_items canon, mas pode precisar varrer mais porque canon pode ser raro.
    # Ajuste fino:
    PAGE = 120          # tamanho do “lote” (bom custo/benefício)
    HARD_CAP = 480      # teto máximo de varredura (segurança)

    scanned = 0
    offset = 0
    want = int(max_items or 30)

    while scanned < HARD_CAP and len(canon) < want:
        batch = cached_list_memories_page(shared_key, offset=offset, limit=PAGE)
        if not batch:
            break

        for m in batch:
            meta = m.get("meta") or {}
            if str(meta.get("kind") or "").strip().lower() != "canon":
                continue
            if not _memory_timeline_ok(meta, timeline):
                continue

            canon.append(m)
            if len(canon) >= want:
                break

        scanned += len(batch)
        offset += PAGE

    if not canon:
        return

    selected = canon[-want:] if len(canon) > want else canon
    try:
        _ss_set(f"{_SS_PREFIX}debug_canon_injected_count", len(selected))
    except Exception:
        pass

    lines: List[str] = []
    lines.append("[MEMÓRIAS CANÔNICAS — COMPARTILHADAS] — NÃO altera CENA ATIVA")
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
        if txt:
            lines.append(txt)
        lines.append("")

        if dedupe_bucket is not None and txt:
            dedupe_bucket.add(hashlib.sha1(txt.encode("utf-8")).hexdigest())

    block = "\n".join(lines).strip()

    # injeta no PRIMEIRO system
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = (str(messages[0].get("content") or "").rstrip() + "\n\n" + block).strip()
    else:
        messages.append({"role": "system", "content": block})

def _choose_intro_text(usuario_key: str, timeline: str) -> str:
    """
    Prioridade correta:
    1) intro da timeline (mary.intro.<timeline>.text) sincronizado da persona
    2) intro FIXO somente se o flag mary.intro.use_fixed estiver True
    """
    # intro fixo só entra se explicitamente habilitado
    use_fixed = bool(get_fact(usuario_key, "mary.intro.use_fixed", default=False))
    fixed_intro = str(get_fact(usuario_key, "mary.intro.fixed", default="") or "").strip()

    if use_fixed and fixed_intro:
        return fixed_intro

    # padrão: sempre usar o intro da timeline (sincronizado)
    _, intro_text = _sync_intro_fact(usuario_key, timeline)
    return str(intro_text or "").strip()


def _inject_intro_as_context_once(
    usuario_key: str,
    timeline: str,
    shared_key: str,
    messages: List[Dict[str, str]],
) -> None:
    """
    Injeta o intro da persona como contexto UMA ÚNICA VEZ por usuario_key,
    mas apenas se NÃO houver memórias CANON (canon vence e dispensa intro).

    Correções:
    - Cleanup de intro legado NÃO pode rodar sempre (senão destrói o guard).
    - Cleanup roda no máximo 1x por sessão e por timeline.
    - Só limpa cache/zera flag quando realmente removeu algo.
    """

    tl = str(timeline or "").strip()

    # ✅ flag SEMPRE definido antes do uso
    inject_flag = f"{_SS_PREFIX}intro_ctx_injected::{usuario_key}"
    cleanup_flag = f"{_SS_PREFIX}intro_cleanup_done::{usuario_key}::{tl or 'global'}"

    # -------------------------------
    # ✅ Cleanup 1x (somente intro/timeline-fixed)
    # -------------------------------
    try:
        use_fixed = bool(get_fact(usuario_key, "mary.intro.use_fixed", default=False))

        if (not use_fixed) and (not bool(_ss_get(cleanup_flag, False))):
            deleted_any = False

            # remove qualquer intro fixo (global e por timeline)
            if get_fact(usuario_key, "mary.intro.fixed", default=None) is not None:
                delete_fact(usuario_key, "mary.intro.fixed")
                deleted_any = True

            if tl:
                if get_fact(usuario_key, f"mary.intro.fixed.{tl}", default=None) is not None:
                    delete_fact(usuario_key, f"mary.intro.fixed.{tl}")
                    deleted_any = True

                # remove o intro sincronizado que ficou persistido em facts
                if get_fact(usuario_key, f"mary.intro.{tl}", default=None) is not None:
                    delete_fact(usuario_key, f"mary.intro.{tl}")
                    deleted_any = True

            # remove legado que às vezes “trava” a timeline
            if get_fact(usuario_key, "mary.timeline.fixed", default=None) is not None:
                delete_fact(usuario_key, "mary.timeline.fixed")
                deleted_any = True

            _ss_set(cleanup_flag, True)

            # só invalida cache/guard se realmente removeu algo
            if deleted_any:
                clear_user_cache(usuario_key)
                _ss_set(inject_flag, False)
    except Exception:
        pass

    # -------------------------------
    # ⛔ Guard de sessão (UMA VEZ)
    # -------------------------------
    if bool(_ss_get(inject_flag, False)):
        return

    # canon vence e dispensa intro
    if _has_canon_memories(shared_key, timeline):
        _ss_set(inject_flag, True)
        return

    # ✅ Escolha do intro com prioridade correta
    intro_text = _choose_intro_text(usuario_key, timeline)

    if intro_text:
        block = f"[QUADRO ZERO — INTRO DA PERSONA]\n{intro_text}".strip()

        # injeta no system base (messages[0]) se existir
        if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
            base = str(messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + block).strip()
        else:
            messages.append({"role": "system", "content": block})

    # ✅ marca como injetado (impede reinjeção)
    _ss_set(inject_flag, True)
# ==========================================================
# ✅ LONG MEMORY (Mongo $text)
# ==========================================================
def _lm_query_from_prompt(user_prompt: str) -> str:
    """Gera uma consulta curta para $text (reduz ruído e melhora recall)."""
    s = (user_prompt or "").strip().lower()
    if not s:
        return ""

    # remove URLs e lixo comum (reduz ruído no $text)
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\bwww\.\S+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    if not s:
        return ""

    toks = re.findall(r"[\w\u00C0-\u017F']+", s, flags=re.UNICODE)
    stop = {
        "a","o","os","as","um","uma","uns","umas","de","do","da","dos","das","em","no","na","nos","nas","por","para",
        "com","sem","que","e","ou","mas","se","como","quando","onde","porque","pq","pra","tá","to","tô","eu","vc","você",
        "voce","ele","ela","gente","nós","nos","minha","meu","minhas","meus","teu","tua","seu","sua","isso","essa","esse",
        "aqui","ali","lá","ta","tb","também","tambem","sabe","amor","lembra","lembrar","pensando","deitado","relaxando",
        "agora","hoje","ontem","amanhã","mesmo","assim","tipo","cara","garota"
    }
    keep = [t for t in toks if len(t) >= 4 and t not in stop]

    # query curta: melhora signal/noise no $text
    q = " ".join(keep[:14]).strip()
    q = re.sub(r"\s{2,}", " ", q).strip()
    return q or s


def _inject_long_memory_pins_always(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    *,
    max_items: int = 12,
    dedupe_bucket: Optional[set] = None,
) -> None:
    """
    ✅ Injeta memórias FIXAS (pin/guide/fixed) em TODAS as respostas.
    Compatível com pins marcados no TEXT (ex: [kind=pin]) mesmo quando meta.kind veio "memory".
    """
    try:
        rows = list_long_memory(shared_key, limit=400) or []
    except Exception:
        rows = []

    if not rows:
        return

    tl = _normalize_timeline(timeline)

    def _is_all_marker(x: str) -> bool:
        s = (x or "").strip().lower()
        return s in ("[all]", "all", "*")

    def _timeline_matches(tms_raw: str, tl_norm: str) -> bool:
        if not tms_raw:
            return True  # sem timeline -> considera all (para pins)
        if _is_all_marker(tms_raw):
            return True
        try:
            return _normalize_timeline(tms_raw) == tl_norm
        except Exception:
            return tms_raw.strip() == tl_norm

    picked: List[Dict[str, Any]] = []

    _RE_KIND_TAG = re.compile(r"\[\s*kind\s*=\s*(pin|guide|fixed)\s*\]", re.IGNORECASE)
    _RE_TIMELINE_TAG = re.compile(r"\[\s*timeline\s*=\s*([^\]]+)\s*\]", re.IGNORECASE)
    _RE_ANY_BRACKETS = re.compile(r"\[[^\]]+\]")

    def _clean_text(txt: str) -> str:
        # remove tags [kind=...][timeline=...], etc.
        cleaned = _RE_ANY_BRACKETS.sub("", txt or "")
        # normaliza espaços
        cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def _infer_kind(meta_kind: str, txt: str) -> str:
        k = (meta_kind or "").strip().lower()
        if k in ("pin", "guide", "fixed"):
            return k
        # compat: meta.kind veio "memory" (ou vazio), mas o text está tagueado
        m = _RE_KIND_TAG.search(txt or "")
        if m:
            return m.group(1).lower()
        return k  # mantém como está (provavelmente "memory"/"")

    def _infer_timeline(meta: Dict[str, Any], txt: str) -> str:
        # prioridade: meta.timeline_at_save / meta.timeline
        tms = str(meta.get("timeline_at_save") or meta.get("timeline") or "").strip()
        if tms:
            return tms
        # fallback: ler do texto [timeline=...]
        m = _RE_TIMELINE_TAG.search(txt or "")
        if not m:
            return ""
        raw = (m.group(1) or "").strip()
        # aceita formatos: [all], "[all]", [timeline=[all]]
        raw = raw.strip().strip('"').strip("'")
        raw = raw.replace("[", "").replace("]", "").strip()
        return raw

    # ✅ ordena por ts desc quando existir (mais recentes primeiro)
    try:
        def _ts_key(d: Dict[str, Any]) -> float:
            v = d.get("ts") or (d.get("meta") or {}).get("ts") or (d.get("meta") or {}).get("date")
            if v is None:
                return 0.0
            # datetime-like
            try:
                ts_fn = getattr(v, "timestamp", None)
                if callable(ts_fn):
                    return float(ts_fn())
            except Exception:
                pass
            # numeric
            try:
                return float(v)
            except Exception:
                pass
            # iso-ish / other string (best-effort)
            try:
                return float(str(v).strip())
            except Exception:
                return 0.0

        rows = sorted(rows, key=_ts_key, reverse=True)
    except Exception:
        pass

    for d in rows:
        raw_txt = str(d.get("text") or "").strip()
        if not raw_txt:
            continue

        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        kind = _infer_kind(str(meta.get("kind") or ""), raw_txt)

        # ✅ só entra o que for "fixo"
        if kind not in ("pin", "guide", "fixed"):
            continue

        # respeita timeline_at_save se existir; senão tenta timeline do text; senão considera "all"
        tms = _infer_timeline(meta, raw_txt)
        if not _timeline_matches(tms, tl):
            continue

        txt = _clean_text(raw_txt)
        if not txt:
            continue

        if dedupe_bucket is not None:
            h = hashlib.sha1(txt.encode("utf-8")).hexdigest()
            if h in dedupe_bucket:
                continue
            dedupe_bucket.add(h)

        picked.append(d)
        if len(picked) >= int(max_items or 12):
            break

    if not picked:
        return

    lines = [
        "[MEMÓRIAS FIXAS — LONG MEMORY] — NÃO altera CENA ATIVA",
        "FATOS DE MUNDO (guia prático): use para orientar locais, rotina e coerência.",
        "Não citar literalmente; incorporar naturalmente.",
        "",
    ]

    for i, d in enumerate(picked, 1):
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        title = str(meta.get("title") or meta.get("key") or "").strip()
        header = f"- PIN {i}"
        if title:
            header += f" — {title}"
        lines.append(header)

        raw_txt = str(d.get("text") or "").strip()
        txt = _clean_text(raw_txt)

        lines.append(txt)
        lines.append("")

    block = "\n".join(lines).strip()

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + block).strip()
    else:
        messages.append({"role": "system", "content": block})


def _inject_long_memory_textsearch(
    shared_key: str,
    timeline: str,
    user_prompt: str,
    messages: List[Dict[str, str]],
    *,
    limit: int = 10,
    dedupe_bucket: Optional[set] = None,
) -> None:
    """
    ✅ Recupera memórias relevantes via Mongo $text.
    - Não injeta pins/guide/fixed (isso é função separada).
    - Respeita timeline_at_save / [all]
    """
    q = _lm_query_from_prompt(user_prompt)
    if not q:
        return

    rows = search_long_memory_text(shared_key, q, limit=max(1, int(limit or 10))) or []
    if not rows:
        return

    picked: List[Dict[str, Any]] = []
    tl = _normalize_timeline(timeline)

    def _is_all_marker(x: str) -> bool:
        s = (x or "").strip().lower()
        return s in ("[all]", "all", "*")

    def _timeline_matches(tms_raw: str, tl_norm: str) -> bool:
        if not tms_raw:
            return True
        if _is_all_marker(tms_raw):
            return True
        try:
            return _normalize_timeline(tms_raw) == tl_norm
        except Exception:
            return tms_raw.strip() == tl_norm

    for d in rows:
        txt = str(d.get("text") or "").strip()
        if not txt:
            continue

        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}

        # timeline
        tms = str(meta.get("timeline_at_save") or meta.get("timeline") or "").strip()
        if not _timeline_matches(tms, tl):
            continue

        # kinds: NÃO trazer pins/guide/fixed aqui
        kind = str(meta.get("kind") or "").strip().lower()

        # compat: se texto estiver tagueado como pin/guide/fixed, não trazer aqui
        if re.search(r"\[\s*kind\s*=\s*(pin|guide|fixed)\s*\]", txt, flags=re.IGNORECASE):
            continue
        if kind in ("canon", "pin", "guide", "fixed"):
            continue

        # dedupe com texto "limpo" (evita duplicar com pins/itens tagueados)
        txt_dedupe = re.sub(r"\[[^\]]+\]", "", txt).strip()

        if dedupe_bucket is not None:
            h = hashlib.sha1(txt_dedupe.encode("utf-8")).hexdigest()
            if h in dedupe_bucket:
                continue
            dedupe_bucket.add(h)

        picked.append(d)
        if len(picked) >= int(limit or 10):
            break

    if not picked:
        return

    lines = [
        "[FATOS RECUPERADOS — LONG MEMORY ($text/Mongo)] — NÃO altera CENA ATIVA",
        "Use como fonte de verdade para fatos passados (onde/quando/como).",
        "Não citar literalmente: recontar com suas palavras mantendo os fatos.",
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

        raw = str(d.get("text") or "").strip()
        best_chunks = _select_best_chunks(raw, user_prompt, max_pick=2)
        for j, ch in enumerate(best_chunks, 1):
            lines.append(f"(chunk {j}/{len(best_chunks)})")
            lines.append(ch.strip())
        lines.append("")

    block = "\n".join(lines).strip()

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + block).strip()
    else:
        messages.append({"role": "system", "content": block})

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

    def _idf(w: str) -> float:
        n_q = df.get(w, 0)
        # BM25 clássico (Okapi): log((N - n + 0.5)/(n + 0.5) + 1)
        return math.log(1.0 + (N - n_q + 0.5) / (n_q + 0.5))

    idf_cache = {w: _idf(w) for w in set(q)}

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


# ==========================================================
# Chunking semântico on-the-fly (RAG) — reduz tokens e melhora relevância
# ==========================================================
_SENT_SPLIT = re.compile(r"(?<=[\.\!\?…])\s+")

def _chunk_semantic(text: str, max_chars: int = 520, max_chunks: int = 10) -> List[str]:
    """
    Chunking simples e robusto (sem dependências externas):
    - prioriza parágrafos
    - se parágrafo for grande, divide por sentenças
    """
    t = (text or "").strip()
    if not t:
        return []
    paras = [p.strip() for p in re.split(r"\n{2,}", t) if p.strip()]
    chunks: List[str] = []
    for p in paras:
        if len(p) <= max_chars:
            chunks.append(p)
            continue
        sents = [s.strip() for s in _SENT_SPLIT.split(p) if s.strip()]
        buf = ""
        for s in sents:
            if not buf:
                buf = s
            elif len(buf) + 1 + len(s) <= max_chars:
                buf = buf + " " + s
            else:
                chunks.append(buf)
                buf = s
        if buf:
            chunks.append(buf)
    return chunks[: max_chunks]

def _select_best_chunks(text: str, query: str, max_pick: int = 2) -> List[str]:
    chunks = _chunk_semantic(text, max_chars=520, max_chunks=10)
    if not chunks:
        return []
    idxs = _bm25_topk(chunks, query, k=max_pick)
    if not idxs:
        return chunks[: max_pick]
    out: List[str] = []
    for i in idxs:
        if 0 <= i < len(chunks):
            out.append(chunks[i])
    return out[: max_pick]


def _inject_relevant_memories(
    shared_key: str,
    timeline: str,
    user_prompt: str,
    messages: List[Dict[str, str]],
    k: int = 4,
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    """
    ✅ BM25 em chunks (em vez do texto inteiro) para:
    - aumentar relevância
    - reduzir tokens no prompt
    - mitigar 'lost-in-the-middle'
    """
    mems = cached_list_memories(shared_key, limit=260)
    if not mems:
        return

    chunk_docs: List[str] = []
    chunk_map: List[Tuple[Dict[str, Any], str, str]] = []  # (mem, chunk, hash_full_dedupe)

    tl = _normalize_timeline(timeline)

    for m in mems:
        meta = m.get("meta") or {}
        kind = str(meta.get("kind") or "").strip().lower()

        if kind == "canon":
            continue
        if not _memory_timeline_ok(meta, tl):
            continue

        text_full = str(m.get("text") or "").strip()
        if not text_full:
            continue

        text_dedupe = re.sub(r"\[[^\]]+\]", "", text_full).strip()
        h_full = hashlib.sha1(text_dedupe.encode("utf-8")).hexdigest()

        if dedupe_bucket is not None and h_full in dedupe_bucket:
            continue

        chunks = _chunk_semantic(text_full, max_chars=520, max_chunks=8)
        if not chunks:
            continue

        for ch in chunks:
            chunk_docs.append(ch)
            chunk_map.append((m, ch, h_full))

    if not chunk_docs:
        return

    idxs = _bm25_topk(chunk_docs, user_prompt, k=max(int(k) * 2, 8))
    if not idxs:
        return

    selected: List[Tuple[Dict[str, Any], str, str]] = []
    seen_full: set = set()

    for ix in idxs:
        if 0 <= ix < len(chunk_map):
            m, ch, h_full = chunk_map[ix]
            if h_full in seen_full:
                continue
            seen_full.add(h_full)
            selected.append((m, ch, h_full))
            if len(selected) >= int(k):
                break

    if not selected:
        return

    lines = [
        "[MEMÓRIAS RELEVANTES (BM25 — chunks)]",
        "Use para coerência, sem citar literalmente.",
        "",
    ]

    for i, (m, ch, h_full) in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        title = meta.get("title") or meta.get("key") or ""
        header = f"- REL {i}"
        if d:
            header += f" (data: {d})"
        if title:
            header += f" — {title}"
        lines.append(header)

        lines.append(str(ch or "").strip())
        lines.append("")

        if dedupe_bucket is not None and h_full:
            dedupe_bucket.add(h_full)

    block = "\n".join(lines).strip()
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + block).strip()
    else:
        messages.append({"role": "system", "content": block})


def _inject_now_context(
    messages: List[Dict[str, str]],
    usuario_key: str,
    timeline: str,
) -> None:
    """
    Injeta o CONTEXTO ATUAL ABSOLUTO da cena.
    Anti-teleporte: impede mudança de local/situação sem base no histórico.
    """
    try:
        facts = cached_get_facts(usuario_key) or {}
    except Exception:
        facts = {}

    local = facts.get("local_atual")
    companhia = facts.get("companhia_atual")
    momento = facts.get("momento_atual")

    if not any([local, companhia, momento]):
        return

    blocos = []
    if local:
        blocos.append(f"Local atual: {local}.")
    if companhia:
        blocos.append(f"Companhia atual: {companhia}.")
    if momento:
        blocos.append(f"Situação atual: {momento}.")

    texto = (
        "[CONTEXTO ATUAL — NÃO ASSUMA MUDANÇAS AUTOMÁTICAS]\n"
        + " ".join(blocos)
        + "\nMudanças de local ou situação só podem ocorrer se forem explicitamente iniciadas na narrativa."
    ).strip()

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + texto).strip()
    else:
        messages.insert(0, {"role": "system", "content": texto})


def _inject_shared_soft_context(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    max_items: int = 4,
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
            dedupe_bucket.add(h)  # ✅ add aqui (dentro do loop), não fora

        soft.append(m)

    if not soft:
        return

    selected = soft[-max_items:] if len(soft) > max_items else soft

    lines = [
        "[MEMÓRIAS COMPARTILHADAS (suave)] — NÃO altera CENA ATIVA",
        "Use para coerência, sem citar literalmente.",
        "",
    ]

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

        
    block = "\n".join(lines).strip()
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + block).strip()
    else:
        messages.append({"role": "system", "content": block})

# ==========================================================
# RELATIONSHIP STATE
# ==========================================================
def _rel_fact_key(timeline: str) -> str:
    tl = (timeline or "").strip() or "cumplice"
    return f"rel.state::{tl}"

# ==========================================================
# MANUAL MEMORY REACTIVATION (#mem ...) + LATENT MEMORIES
# ==========================================================
# Objetivo:
# - Permitir ao usuário "chamar" memórias específicas com gatilho composto (AND/OR)
# - Opcionalmente aplicar prioridade temporal (@recent/@oldest/@lastN)
# - Ativar memórias "latentes" automaticamente quando condições do arco/estado baterem
# Importante:
# - NÃO altera o prompt NSFW nem "suaviza" texto
# - Só injeta contexto adicional (system) quando acionado
# - Guardrails: tamanho máximo, limite por turno, cooldown anti-repetição

_RE_MEM_DIRECTIVE = re.compile(r"(?im)^(?:#mem|⟦MEM⟧)\s*(?:@(?P<mode>[a-zA-Z]+)(?P<n>\d+)?)?\s+(?P<expr>.+?)\s*$")
_RE_TAGS_LINE = re.compile(r"(?im)^\s*\[TAGS:\s*(?P<tags>[^\]]+)\]\s*$")
_RE_LATENT_LINE = re.compile(r"(?im)^\s*\[LATENT:\s*(?P<cond>[^\]]+)\]\s*$")

def _mem_recent_key(usuario_key: str) -> str:
    return f"mary_mem_recent::{usuario_key}"

def _mem_latent_recent_key(usuario_key: str) -> str:
    return f"mary_mem_latent_recent::{usuario_key}"

def _turn_counter_key(usuario_key: str) -> str:
    return f"mary_turn_counter::{usuario_key}"

def _bump_turn_counter(usuario_key: str) -> int:
    """Contador de turnos por sessão (não persiste em facts)."""
    try:
        cur = int(_ss_get(_turn_counter_key(usuario_key), 0) or 0)
    except Exception:
        cur = 0
    cur += 1
    _ss_set(_turn_counter_key(usuario_key), cur)
    return cur

def _extract_mem_directive(prompt: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Remove a linha de diretiva #mem/⟦MEM⟧ do prompt do usuário e retorna:
    - prompt limpo (sem a diretiva)
    - spec dict: {"expr": str, "mode": str|None, "n": int|None}
    Observação: só considera diretiva quando a linha começa com #mem/⟦MEM⟧.
    """
    if not prompt:
        return "", None

    spec: Optional[Dict[str, Any]] = None
    lines = prompt.splitlines()
    kept: List[str] = []
    for ln in lines:
        m = _RE_MEM_DIRECTIVE.match(ln.strip())
        if m and spec is None:
            mode = (m.group("mode") or "").strip().lower() or None
            n = m.group("n")
            spec = {"expr": (m.group("expr") or "").strip(), "mode": mode, "n": int(n) if n else None}
            continue
        kept.append(ln)

    cleaned = "\n".join(kept).strip()
    return cleaned, spec

def _split_top_level(expr: str, sep: str = "+") -> List[str]:
    """Split por sep, mas respeitando parênteses (top-level)."""
    out: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in (expr or ""):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            part = "".join(buf).strip()
            if part:
                out.append(part)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out

def _parse_compound_expr(expr: str) -> List[List[str]]:
    """
    Converte expressão do tipo:
      "primeira+(transa|vez)+motel"
    em lista AND de opções OR:
      [["primeira"], ["transa","vez"], ["motel"]]
    """
    expr = (expr or "").strip()
    if not expr:
        return []

    and_terms = _split_top_level(expr, "+")
    parsed: List[List[str]] = []
    for term in and_terms:
        t = term.strip()
        if not t:
            continue
        if t.startswith("(") and t.endswith(")"):
            inner = t[1:-1]
            opts = [o.strip() for o in inner.split("|") if o.strip()]
            if opts:
                parsed.append(opts)
            continue
        # caso: a+(b|c) sem parênteses externos não ocorre; mas "a|(b)" não suportamos fora de ()
        parsed.append([t])
    return parsed

def _parse_tags_from_memory(text: str) -> List[str]:
    if not text:
        return []
    tags: List[str] = []
    for m in _RE_TAGS_LINE.finditer(text):
        raw = m.group("tags") or ""
        for t in raw.split(","):
            tt = t.strip()
            if tt:
                tags.append(tt)
    return tags

def _extract_latent_conditions(text: str) -> List[str]:
    if not text:
        return []
    return [ (m.group("cond") or "").strip() for m in _RE_LATENT_LINE.finditer(text) if (m.group("cond") or "").strip() ]

def _memory_text_fields(mem: Dict[str, Any]) -> Tuple[str, str, str]:
    """
    Normaliza campos de memória (compatível com diferentes formatos):
    - title
    - kind/tipo
    - text
    """
    if not isinstance(mem, dict):
        return "", "", ""
    meta = mem.get("meta") if isinstance(mem.get("meta"), dict) else {}
    title = str(mem.get("title") or meta.get("title") or meta.get("titulo") or mem.get("titulo") or "").strip()
    kind = str(mem.get("kind") or meta.get("kind") or meta.get("tipo") or mem.get("tipo") or "").strip()
    txt = str(mem.get("text") or mem.get("texto") or meta.get("text") or "").strip()
    return title, kind, txt

def _memory_timestamp(mem: Dict[str, Any]) -> Optional[float]:
    """Tenta extrair timestamp da memória; fallback None."""
    if not isinstance(mem, dict):
        return None
    meta = mem.get("meta") if isinstance(mem.get("meta"), dict) else {}
    for k in ("ts","timestamp","created_at","createdAt","time"):
        v = meta.get(k) if k in meta else mem.get(k)
        if v is None:
            continue
        try:
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).strip()
            # aceita epoch em string
            if re.fullmatch(r"\d{10,13}", s):
                return float(s[:10])
            # tenta iso
            try:
                dt = datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
                return dt.timestamp()
            except Exception:
                pass
        except Exception:
            continue
    return None

def _memory_id(mem: Dict[str, Any]) -> str:
    if not isinstance(mem, dict):
        return "mem::invalid"
    meta = mem.get("meta") if isinstance(mem.get("meta"), dict) else {}
    mid = meta.get("id") or mem.get("id")
    if mid:
        return f"mem::{mid}"
    title, kind, txt = _memory_text_fields(mem)
    h = hashlib.sha1((title+"|"+kind+"|"+txt).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"mem::sha1::{h}"

def _norm_token(s: str) -> str:
    return _t_norm(s or "").strip()

def _memory_haystack(mem: Dict[str, Any]) -> str:
    title, kind, txt = _memory_text_fields(mem)
    tags = _parse_tags_from_memory(txt)
    meta = mem.get("meta") if isinstance(mem.get("meta"), dict) else {}
    # inclui tags também de meta, se existir
    mtags = meta.get("tags")
    if isinstance(mtags, list):
        tags += [str(x) for x in mtags if str(x).strip()]
    elif isinstance(mtags, str):
        tags += [t.strip() for t in mtags.split(",") if t.strip()]
    blob = "\n".join([title, kind, txt, " ".join(tags)])
    return _norm_token(blob)

def _expr_match(mem: Dict[str, Any], parsed_expr: List[List[str]]) -> bool:
    if not parsed_expr:
        return False
    hay = _memory_haystack(mem)
    if not hay:
        return False
    for or_group in parsed_expr:
        ok = False
        for opt in or_group:
            tok = _norm_token(opt)
            if tok and tok in hay:
                ok = True
                break
        if not ok:
            return False
    return True

def _select_memories(
    mems: List[Dict[str, Any]],
    parsed_expr: List[List[str]],
    *,
    mode: Optional[str] = None,
    n: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Seleciona memórias que casam com expr e aplica prioridade temporal."""
    hits = [m for m in (mems or []) if _expr_match(m, parsed_expr)]
    if not hits:
        return []

    mode = (mode or "").strip().lower() or None

    # ordenação temporal (se existir ts)
    def key_ts(m: Dict[str, Any]) -> float:
        ts = _memory_timestamp(m)
        return ts if ts is not None else -1.0

    if mode in ("recent","new","latest"):
        hits.sort(key=key_ts, reverse=True)
    elif mode in ("old","oldest","first"):
        hits.sort(key=key_ts, reverse=False)
    else:
        # padrão: mais recente primeiro quando ts existe, senão mantém ordem
        if any(_memory_timestamp(m) is not None for m in hits):
            hits.sort(key=key_ts, reverse=True)

    # quantidade
    if mode and mode.startswith("last"):
        # suporta @last2 etc.
        k = n or 1
        return hits[: max(1, min(6, k))]
    return hits[:1]

def _cooldown_allows(usuario_key: str, mem_id: str, *, latent: bool, cooldown_turns: int = 10) -> bool:
    """Evita repetir a mesma memória com frequência (por sessão)."""
    k = _mem_latent_recent_key(usuario_key) if latent else _mem_recent_key(usuario_key)
    recent = _ss_get(k, []) or []
    try:
        # lista de (turn, id)
        recent_list = list(recent) if isinstance(recent, (list, tuple)) else []
    except Exception:
        recent_list = []
    # remove itens antigos
    cur_turn = int(_ss_get(_turn_counter_key(usuario_key), 0) or 0)
    filtered = []
    for it in recent_list:
        try:
            tturn, mid = int(it[0]), str(it[1])
            if cur_turn - tturn <= cooldown_turns:
                filtered.append((tturn, mid))
        except Exception:
            continue
    _ss_set(k, filtered)
    return mem_id not in {mid for _, mid in filtered}

def _mark_cooldown(usuario_key: str, mem_id: str, *, latent: bool) -> None:
    k = _mem_latent_recent_key(usuario_key) if latent else _mem_recent_key(usuario_key)
    cur_turn = int(_ss_get(_turn_counter_key(usuario_key), 0) or 0)
    recent = _ss_get(k, []) or []
    try:
        recent_list = list(recent) if isinstance(recent, (list, tuple)) else []
    except Exception:
        recent_list = []
    recent_list.append((cur_turn, mem_id))
    # mantém janela curta
    recent_list = recent_list[-20:]
    _ss_set(k, recent_list)

def _inject_memory_block(
    messages: List[Dict[str, str]],
    *,
    kind: str,
    title: str,
    text: str,
    tags: List[str],
    source: str,
) -> None:
    """Insere uma memória como system (pequena e sem meta-vazamento)."""
    blob = text.strip()
    if not blob:
        return
    # corte de tamanho (guardrail)
    blob = blob[:600].rstrip()
    ttags = ", ".join([t.strip() for t in tags if t.strip()][:10])
    hdr_parts = []
    if title:
        hdr_parts.append(f"Título: {title}")
    if kind:
        hdr_parts.append(f"Tipo: {kind}")
    if ttags:
        hdr_parts.append(f"Tags: {ttags}")
    header = (" | ".join(hdr_parts)).strip()

    content = (
        f"[MEMÓRIA REATIVADA — {source.upper()}]\n"
        + (header + "\n" if header else "")
        + blob
        + "\n\nRegras: use esta memória como CONTEXTO. Não cite tags/headers ao usuário."
    ).strip()

    # Insere após o primeiro system (persona), para manter hierarquia
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages.insert(1, {"role": "system", "content": content})
    else:
        messages.insert(0, {"role": "system", "content": content})

def _inject_manual_memory_if_any(
    *,
    usuario_key: str,
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    spec: Optional[Dict[str, Any]],
) -> None:
    if not spec:
        return
    expr = str(spec.get("expr") or "").strip()
    if not expr:
        return

    parsed = _parse_compound_expr(expr)
    if not parsed:
        return

    mems = cached_list_memories(shared_key, limit=600) or []
    # respeita timeline quando meta carrega isso
    filtered: List[Dict[str, Any]] = []
    for m in mems:
        meta = m.get("meta") if isinstance(m.get("meta"), dict) else {}
        if _memory_timeline_ok(meta, timeline):
            filtered.append(m)

    chosen = _select_memories(filtered, parsed, mode=spec.get("mode"), n=spec.get("n"))
    if not chosen:
        return

    # injeta (no máximo 1 por turno por padrão; @lastN injeta N mas limitamos a 2)
    max_inject = 1
    mode = (spec.get("mode") or "")
    if mode and mode.startswith("last"):
        max_inject = max(1, min(2, int(spec.get("n") or 1)))

    injected = 0
    for mem in chosen[:max_inject]:
        mid = _memory_id(mem)
        if not _cooldown_allows(usuario_key, mid, latent=False):
            continue
        title, kind, txt = _memory_text_fields(mem)
        tags = _parse_tags_from_memory(txt)
        _inject_memory_block(messages, kind=kind, title=title, text=txt, tags=tags, source="manual")
        _mark_cooldown(usuario_key, mid, latent=False)
        injected += 1
        if injected >= max_inject:
            break

def _eval_latent_condition(cond: str, *, tp_arc: Dict[str, Any]) -> bool:
    """
    Suporta condições simples:
      - tension>=0.5, tension>0.5, tension<=0.7, anchor<=0.6
      - mode==temptation
      - mode in (temptation,conflict)
    Variáveis: tension, anchor, mode
    """
    c = (cond or "").strip()
    if not c:
        return False

    tension = float(tp_arc.get("tension", 0.0) or 0.0)
    anchor = float(tp_arc.get("anchor", 0.85) or 0.85)
    mode = str(tp_arc.get("mode") or tp_arc.get("last") or "").strip().lower()

    # mode in (...)
    m = re.match(r"(?i)mode\s+in\s*\((.+)\)\s*$", c)
    if m:
        items = [x.strip().lower() for x in m.group(1).split(",") if x.strip()]
        return mode in items

    m = re.match(r"(?i)mode\s*==\s*([a-zA-Z_]+)\s*$", c)
    if m:
        return mode == m.group(1).strip().lower()

    m = re.match(r"(?i)(tension|anchor)\s*(>=|<=|>|<|==)\s*([0-9]*\.?[0-9]+)\s*$", c)
    if m:
        var = m.group(1).lower()
        op = m.group(2)
        try:
            val = float(m.group(3))
        except Exception:
            return False
        cur = tension if var == "tension" else anchor
        if op == ">=":
            return cur >= val
        if op == "<=":
            return cur <= val
        if op == ">":
            return cur > val
        if op == "<":
            return cur < val
        if op == "==":
            return abs(cur - val) < 1e-9
    return False

def _inject_latent_memory_if_any(
    *,
    usuario_key: str,
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    tp_arc: Dict[str, Any],
) -> None:
    """
    Procura memórias com [LATENT: ...] e injeta no máximo 1 por turno,
    respeitando cooldown.
    """
    mems = cached_list_memories(shared_key, limit=600) or []
    if not mems:
        return

    candidates: List[Tuple[float, Dict[str, Any], str]] = []
    for mem in mems:
        meta = mem.get("meta") if isinstance(mem.get("meta"), dict) else {}
        if not _memory_timeline_ok(meta, timeline):
            continue
        title, kind, txt = _memory_text_fields(mem)
        if not txt:
            continue
        conds = _extract_latent_conditions(txt)
        if not conds:
            continue
        ok = any(_eval_latent_condition(c, tp_arc=tp_arc) for c in conds)
        if not ok:
            continue
        ts = _memory_timestamp(mem) or 0.0
        candidates.append((ts, mem, conds[0]))

    if not candidates:
        return

    # prioriza a mais recente
    candidates.sort(key=lambda x: x[0], reverse=True)

    for _, mem, _ in candidates[:6]:
        mid = _memory_id(mem)
        if not _cooldown_allows(usuario_key, mid, latent=True):
            continue
        title, kind, txt = _memory_text_fields(mem)
        tags = _parse_tags_from_memory(txt)
        _inject_memory_block(messages, kind=kind, title=title, text=txt, tags=tags, source="latent")
        _mark_cooldown(usuario_key, mid, latent=True)
        break



def _get_global_virginity_from_facts(facts: Dict[str, Any]) -> str:
    """
    Virginidade GLOBAL (histórico sexual da Mary no mundo).
    Retorna: "virgem" | "nao_virgem" | ""
    """
    try:
        mary = (facts or {}).get("mary")
        if isinstance(mary, dict):
            v = str(mary.get("virginity") or "").strip().lower()
        else:
            v = str((facts or {}).get("virginity") or "").strip().lower()

        if v in ("virgem", "nao_virgem"):
            return v
        return ""
    except Exception:
        return ""

def _derive_rel_first_time_with_janio(
    timeline: str,
    rel: Dict[str, Any],
) -> bool:
    """
    Derivado seguro:
    first_time_with_janio = True quando o relacionamento AINDA NÃO foi consumado.
    Isso é o que você quer usar no prompt da universitaria,
    sem confundir com a virginidade GLOBAL.
    """
    tl = (timeline or "").strip().lower()
    consummated = bool(rel.get("consummated"))

    if tl == "universitaria":
        return (not consummated)

    return False

def _load_rel_state(
    facts: Dict[str, Any],
    timeline: str,
    canon_default: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = default_relationship_state(timeline)

    # 1) Canon default entra primeiro
    if isinstance(canon_default, dict):
        for k, v in canon_default.items():
            if not str(k).startswith("_"):
                base[k] = v

    # 2) Estado persistido (facts) entra por cima
    key = _rel_fact_key(timeline)
    raw = (facts or {}).get(key)
    if isinstance(raw, dict):
        for k, v in raw.items():
            base[k] = v

    # 3) Metas internas
    base.setdefault("_promote_streak", 0)
    base.setdefault("_loop_streak", 0)
    base.setdefault("_last_pattern", "")
    base.setdefault("_last_updated_ts", 0)

    # 🔥 NOVO — DINÂMICA 3.5 (estado comportamental seguro)
    base.setdefault("mood", "intensa")
    base.setdefault("energy", "energetica")
    base.setdefault("attitude", "equilibrada")
    base.setdefault("_last_success_pattern", "")
    base.setdefault("self_awareness", 0.30)  # ← LINHA OPCIONAL ADICIONADA

    # 4) Defaults mínimos (apenas se não existir)
    base.setdefault("mature_turns", 0)
    base.setdefault("intimacy_level", 0 if timeline == "universitaria" else 3)
    base.setdefault("consummated", False if timeline == "universitaria" else True)

    # ⚠️ IMPORTANTE:
    # "virginity" aqui deve ser tratado como ESTADO DO RELACIONAMENTO com Janio na timeline,
    # não como virginidade global.
    if timeline == "universitaria":
        if base.get("virginity") not in ("virgem", "nao_virgem"):
            base["virginity"] = "virgem"
    else:
        if base.get("virginity") not in ("virgem", "nao_virgem"):
            base["virginity"] = "nao_virgem"

    base.setdefault("desire", 25 if timeline == "universitaria" else 45)
    base.setdefault("arousal", 18 if timeline == "universitaria" else 35)
    base.setdefault("self_control", 40 if timeline == "universitaria" else 35)

    base.setdefault("allows_touch", True)
    base.setdefault("allows_extended_touch", False if timeline == "universitaria" else True)
    base.setdefault("allows_sleep_together", False if timeline == "universitaria" else True)
    base.setdefault("allows_masturbation", True)
    base.setdefault("allows_mutual_relief", False if timeline == "universitaria" else True)

    # allows_penetration deve respeitar consummated/estágio do relacionamento
    # (não o global).
    base.setdefault("allows_penetration", False if timeline == "universitaria" else True)

    if not base.get("stage"):
        base["stage"] = "conhecendo" if timeline == "universitaria" else "casados"

    # (sem return prematuro: DERIVADOS precisam rodar)

    # ==========================================================
    # ✅ DERIVADOS (para o prompt/continuidade) — SEM sobrescrever estados
    # ==========================================================
    global_v = _get_global_virginity_from_facts(facts)
    # _global_virginity é informativo (prompt/debug); por padrão NÃO governa o REL.
    base["_global_virginity"] = global_v

    # ✅ Fallback inteligente:
    # fora da universitaria, se por algum motivo virginity vier vazio,
    # tenta herdar do global (quando válido).
    if timeline != "universitaria" and not base.get("virginity"):
        if global_v in ("virgem", "nao_virgem"):
            base["virginity"] = global_v

    # Primeira vez com Janio (derivado)
    base["_first_time_with_janio"] = _derive_rel_first_time_with_janio(timeline, base)
    
    # Regra mínima de consistência interna do REL:
    # se consumou com Janio, então não pode ficar "virgem" no relacionamento.
    if bool(base.get("consummated")):
        base["virginity"] = "nao_virgem"
        base["allows_penetration"] = True
        base.setdefault("allows_extended_touch", True)
        base.setdefault("allows_mutual_relief", True)

    # ✅ REGRA DE COERÊNCIA (mesmo sem consummated=True):
    # Se o relacionamento está "nao_virgem", então penetração não pode ficar False.
    if base.get("virginity") == "nao_virgem":
        base["allows_penetration"] = True

    return base

# ==========================================================
# CANON/FACTS SYNC (virginity)
# ==========================================================
def _sync_rel_state_with_facts_canon(
    facts: Dict[str, Any],
    rel: Dict[str, Any],
    timeline: str,
    user_id: str,
) -> Dict[str, Any]:
    """
    Sincroniza REL com memória CANON (shared) de virgindade.
    Regra: se existir CANON virginity=nao_virgem, isso governa o REL (não regride).
    """
    shared_key = _shared_key(user_id)

    try:
        mems = cached_list_memories(shared_key, limit=200)
    except Exception:
        mems = []

    canon_val = None
    canon_ts = None

    # pega a ocorrência MAIS RECENTE de canon/virginity
    for m in mems:
        if not isinstance(m, dict):
            continue
        meta = m.get("meta") or {}
        if not isinstance(meta, dict):
            continue
        if meta.get("kind") == "canon" and meta.get("key") == "virginity":
            v = meta.get("value")
            ts = m.get("ts")
            if canon_ts is None:
                canon_val, canon_ts = v, ts
            else:
                try:
                    if ts and ts > canon_ts:
                        canon_val, canon_ts = v, ts
                except Exception:
                    # ts não comparável: usa a última ocorrência válida
                    canon_val, canon_ts = v, ts

    if canon_val == "nao_virgem":
        rel["virginity"] = "nao_virgem"
        rel["consummated"] = True
        rel["allows_penetration"] = True
        rel.setdefault("allows_extended_touch", True)
        rel.setdefault("allows_mutual_relief", True)

    return rel

def _save_rel_state(usuario_key: str, timeline: str, rel: Dict[str, Any]) -> None:
    set_fact_safe(usuario_key, _rel_fact_key(timeline), rel, {"fonte": "relationship_engine"})

# ==========================================================
# INTIMACY + GUARDRAILS (Ação 5 — Regex Generalizadas)
# ==========================================================
# Objetivo:
# - Reduzir dependência de 20+ regex específicas.
# - Manter "hard checks" confiáveis (meta leak / offscreen / autoria / explícito).
# - Tratar progressão íntima por um scoring leve (robusto a variações de linguagem).

import unicodedata

def _t_norm(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"\s+", " ", t).strip()
    return t

# ----------------------------------------------------------
# Meta / vazamento (geral)
# ----------------------------------------------------------
_RE_META_TERMS = re.compile(r"\b(prompt|system|instrucao|instru[cç][aã]o|persona|regras?|policy|guardrails?)\b", re.I)
_RE_META_VERBS = re.compile(r"\b(revela|mostra|exibe|vaza|imprime|quote)\b", re.I)

# Mantém o nome esperado pelo resto do código.
_RE_PLACEHOLDER_REVEAL = re.compile(
    r"(?is)\b(revela|mostra|exibe|vaza|imprime|quote)\b.{0,80}\b(prompt|system|instrucao|instru[cç][aã]o|persona|regras?|policy|guardrails?)\b"
)

def _meta_leak(texto: str) -> bool:
    t = _t_norm(texto)
    if not t:
        return False
    return bool(_RE_META_VERBS.search(t) and _RE_META_TERMS.search(t))

# ----------------------------------------------------------
# Offscreen inventado (geral)
# ----------------------------------------------------------
_RE_OFFSCREEN_MSG = re.compile(
    r"\b(whatsapp|sms|dm|direct|telegram|mensagem|notifica[cç][aã]o|lig(a|ou)\s*para|telefonou)\b",
    re.IGNORECASE,
)
_RE_OFFSCREEN_PASTE_HINT = re.compile(
    r"\b(mensagem:|whatsapp:|sms:|print|segue a mensagem|segue o texto|transcrevendo)\b",
    re.IGNORECASE,
)

# ----------------------------------------------------------
# Autoria / voz (ROBUSTO)
# ----------------------------------------------------------
# Contrato:
# - Mary NÃO "fala pelo usuário" nem por outros personagens (Janio/Arthur/terceiros).
# - Mary pode descrever ações observáveis de terceiros, mas NÃO deve escrever diálogos atribuídos a eles
#   (ex.: 'Arthur: ...', '"..." — disse Arthur').
# - Mary também não deve atribuir pensamentos/decisões internas a "você/Janio/Arthur".
#
# Observação: isso NÃO mexe em NSFW/ intensidade; só impede "boca alheia".

# 1) Atribuição direta de ação ao usuário por 2ª pessoa (a clássica)
_RE_USER_2P_ACTION = re.compile(
    r"\b(voc[eê]|vc|tu)\b.{0,22}\b(puxa|beija|toca|agarra|diz|fala|sussurra|encosta|coloca|empurra|leva|abre|fecha|entra|sai|segura|deita|vira|pede|decide|resolve|escolhe)\b",
    re.IGNORECASE,
)

# 2) Fala atribuída a QUALQUER personagem que não seja Mary (bloqueia "Nome: ...")
_RE_OTHER_SPEAKER_TAG = re.compile(
    r"(?m)^\s*(?!mary\b)([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]{1,30})\s*:\s+"
)

# 3) Fala atribuída via travessão/descritor ("... — disse Fulano")
_RE_QUOTED_ATTRIBUTION = re.compile(
    r"(?i)"
    r"(\"[^\"]{2,}\"|“[^”]{2,}”)"
    r"\s*[,\-–—]\s*"
    r"(?:diz|disse|fala|falou|responde|respondeu|pergunta|perguntou|sussurra|sussurrou|comenta|comentou|murmura|murmurou|provoca|provocou)\s+"
    r"(?!mary\b)[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]{1,30}\b"
)

# 3b) Citação atribuída implicitamente a terceiros (sem "disse Fulano")
# Ex.: Ele sorri e "Então, Mary..." / "..." — ele pergunta.
_RE_THIRD_PARTY_QUOTE_BEFORE = re.compile(
    r"(?is)\b("
    r"ele|ela|"
    r"janio|arthur|"
    r"o\s+cara|o\s+homem|o\s+rapaz|o\s+garoto|"
    r"aquele\s+cara|um\s+cara"
    r")\b[^\n\"]{0,160}\"[^\n\"]{2,}\""
)

_RE_THIRD_PARTY_QUOTE_AFTER = re.compile(
    r"(?is)\"[^\n\"]{2,}\"[^\n]{0,60}\b(ele|ela|janio|arthur)\b"
)


# 4) Pensamento/decisão interna atribuída ao usuário ou a nomes comuns do usuário
_RE_INTERNAL_STATE = re.compile(
    r"\b(pensa|pensei|pensou|acha|achei|achou|imagina|imaginei|imaginou|"
    r"quer|queria|quis|deseja|desejava|"
    r"sente|sentiu|sentia|"
    r"decide|decidiu|resolve|resolveu|escolhe|escolheu)\b",
    re.IGNORECASE,
)
_RE_USER_NAME_ALIASES = re.compile(r"\b(janio|arthur)\b", re.IGNORECASE)

# Contexto condicional "se você..." (não é autoria)
_RE_USER_ACTION_CONTEXT_OK = re.compile(
    r"(quando|enquanto|se|caso|depois\s+que|antes\s+que)[\s:,\-–—]*$",
    re.IGNORECASE,
)

def _has_user_action_violation(texto: str) -> bool:
    """
    True quando a resposta:
    - Atribui ação/decisão interna ao usuário (2ª pessoa) fora de contexto condicional.
    - Escreve fala atribuída a QUALQUER personagem que não seja Mary (Nome: ..., ou "..." — disse Fulano).
    - Atribui pensamentos/decisões internas a Janio/Arthur (aliases comuns do usuário).

    Permite:
    - Ações observáveis de terceiros (sem fala atribuída).
    - Falas da própria Mary.
    """
    t = (texto or "")
    if not t.strip():
        return False

    # A) Impede Mary de colocar falas na boca de outros personagens
    #    (inclui usuário quando aparece como personagem, e inclui terceiros)
    if _RE_OTHER_SPEAKER_TAG.search(t):
        return True
    if _RE_QUOTED_ATTRIBUTION.search(t):
        return True
    if _RE_THIRD_PARTY_QUOTE_BEFORE.search(t):
        return True
    if _RE_THIRD_PARTY_QUOTE_AFTER.search(t):
        return True

    # B) 2ª pessoa com ação (autoria do usuário)
    for m in _RE_USER_2P_ACTION.finditer(t):
        start = m.start()
        prefix = t[max(0, start - 64):start].lower()
        if _RE_USER_ACTION_CONTEXT_OK.search(prefix.strip()):
            continue
        return True

    # C) Estado interno atribuído a Janio/Arthur (aliases)
    #    Ex.: "Janio decide..." / "Arthur pensa..."
    if _RE_USER_NAME_ALIASES.search(t) and _RE_INTERNAL_STATE.search(t):
        # janela curta para reduzir falso positivo
        low = t.lower()
        for mm in _RE_USER_NAME_ALIASES.finditer(low):
            w = low[mm.start(): mm.start() + 140]
            if _RE_INTERNAL_STATE.search(w):
                return True

    return False

# ----------------------------------------------------------
# Aftercare / signals
# ----------------------------------------------------------
_RE_AFTERCARE_SIGNAL = re.compile(
    r"\b(abraca|abraça|acolhe|dorme|dormimos|banho|agua|água|calma|respira|carinho)\b",
    re.IGNORECASE,
)

def _user_signals_aftercare(user_text: str) -> bool:
    return bool(_RE_AFTERCARE_SIGNAL.search(_t_norm(user_text)))

# ----------------------------------------------------------
# Regressão de fase (novo) — aumenta realismo sem mexer no prompt
# ----------------------------------------------------------
_RE_PHASE_BRAKE = re.compile(
    r"\b("
    r"espera|pera|calma|devagar|mais\s+devagar|"
    r"para|pare|stop|"
    r"abra[cç]a|abraço|me\s+abra[cç]a|"
    r"carinho|fica\s+comigo|"
    r"respira|vamos\s+respirar|"
    r"s[oó]\s+um\s+segundo|"
    r"agora\s+n[aã]o"
    r")\b",
    re.IGNORECASE,
)

def _user_requests_slowdown(user_text: str) -> bool:
    return bool(_RE_PHASE_BRAKE.search(_t_norm(user_text)))


def _compute_next_phase(
    current_phase: int,
    user_text: str,
    texto: str,
    *,
    engine_meta: Any = None,
) -> int:
    """
    Motor de fase v2:
    - Avança 1 fase por vez quando o nível sustenta (_should_advance_phase).
    - Regride 1 fase quando o usuário pede desaceleração (devagar/espera/abraço).
    - Não cai abaixo de 0.
    - Mantém o contrato de clímax/aftercare do motor atual.
    """
    try:
        p = int(current_phase or 0)
    except Exception:
        p = 0
    p = max(0, min(MAX_INTIMACY_PHASE, p))

    # ✅ desaceleração tem prioridade (recuo suave)
    if _user_requests_slowdown(user_text or ""):
        return max(0, p - 1)

    # avanço normal
    if _should_advance_phase(p, user_text, texto, engine_meta=engine_meta):
        return _cap_next_phase(p)

    return p

# ------------------------------------------------------------------
# Normalização de texto (helper)
# ------------------------------------------------------------------
def _t_norm(texto: str) -> str:
    """Normaliza texto para busca: lowercase, sem acentos extras."""
    if not texto:
        return ""
    t = str(texto).lower().strip()
    # Remove múltiplos espaços
    t = re.sub(r'\s+', ' ', t)
    return t


# ==================================================================
# 1️⃣ DETECÇÃO DE CONTEÚDO EXPLÍCITO
# ==================================================================

# Famílias semânticas de conteúdo explícito (stems curtos, eficientes)
_EXPLICIT_STEMS = [
    # Atos sexuais explícitos
    "penetr",      # penetração, penetrar
    "meter",       # meter dentro
    "foder",       # foder, fodendo
    "enfi",        # enfiar
    "bombe",       # bombeando
    "vai e vem",   # movimento explícito
    
    # Anatomia genital explícita
    "bucet",       # buceta
    "vagin",       # vagina
    "clitor",      # clitóris
    "penis",       # pênis
    "pau",         # pau (gíria)
    "pica",        # pica (gíria)
    
    # Atos orais/anais explícitos
    "boquete",     # boquete
    "chupar",      # chupar (pênis)
    "anal",        # anal
    "cu",          # cu (gíria)
    
    # Fluidos/Sensações explícitas
    "gozada",      # gozada
    "porra",       # porra (gíria)
    "leite",       # leite (gíria para sêmen)
]

# Regex compilado para explícito
_RE_EXPLICIT_SEX = re.compile(
    r"\b(" + "|".join([re.escape(s) for s in _EXPLICIT_STEMS]) + r")\b",
    re.IGNORECASE
)

def _is_explicit(texto: str) -> bool:
    """
    Retorna True se o texto contém descrição direta de ato sexual explícito.
    
    Exemplos:
    - "Ele me fode com vontade" → True
    - "Meu pau entra dentro" → True
    - "Estou gozando muito" → False (orgasmo, não ato explícito)
    - "Beijo apaixonado" → False
    """
    t = _t_norm(texto)
    if not t:
        return False
    return bool(_RE_EXPLICIT_SEX.search(t))


# ==================================================================
# 2️⃣ DETECÇÃO DE ORGASMO DE MARY (EXPANDIDO v10c+)
# ==================================================================

# Regex expandido: detecta 15+ variações de orgasmo
_RE_MARY_ORGASM_DECLARATION = re.compile(
    r"\b(?:"
    # Formas básicas de "gozar"
    r"(?:eu\s+)?goz(?:o|ei|ando|ar)|"
    r"(?:t[oô]|t[aá]|estou|tô|to)\s+goz(?:ando)?|"
    r"vou\s+gozar|"
    r"(?:vou\s+)?(?:me\s+)?(?:faz(?:er|endo)?|fa[cç]a)\s+gozar|"
    
    # Variações com "comigo"
    r"goza\s+comigo|"
    r"goza\s+(?:em\s+)?mim|"
    
    # Formas plurais
    r"goz(?:amos|aram|arem)|"
    
    # Orgasmo (palavra direta)
    r"(?:meu\s+)?orgasmo|"
    r"(?:tô|estou|to)\s+(?:em\s+)?orgasmo|"
    r"(?:vou\s+)?(?:ter\s+)?(?:um\s+)?orgasmo|"
    
    # Variações coloquiais
    r"(?:tô|estou|to)\s+perto\s+(?:de\s+)?(?:gozar|orgasmo)|"
    r"(?:já\s+)?(?:vou|vou\s+)?(?:gozar|vir)|"
    
    # Efeitos de orgasmo
    r"(?:me\s+)?(?:faz\s+)?vir|"
    r"(?:tô|estou)\s+(?:vindo|virando)|"
    
    # Intensidade máxima
    r"(?:me\s+)?(?:leva|leve)\s+(?:ao\s+)?cl[ií]max|"
    r"(?:vou\s+)?(?:ao\s+)?cl[ií]max|"
    r"(?:pico\s+)?(?:de\s+)?prazer|"
    
    # Expressões de intensidade
    r"(?:tô|estou)\s+(?:perdendo|saindo)\s+(?:do\s+)?controle|"
    r"(?:não\s+)?aguento\s+(?:mais|de\s+prazer)|"
    
    # Reações corporais de clímax
    r"(?:meu\s+)?(?:corpo\s+)?(?:treme|contrai|espasma)|"
    r"(?:tô|estou)\s+(?:tremendo|contraindo|espalmando)|"
    
    # Variações com "me"
    r"(?:me\s+)?(?:faz\s+)?(?:gozar|vir|explodir)|"
    
    # Intensidade extrema
    r"(?:me\s+)?(?:faz\s+)?(?:explodir|desintegrar|voar)|"
    r"(?:tô|estou)\s+(?:explodindo|desintegrando|voando)"
    
    r")\b",
    re.IGNORECASE | re.VERBOSE
)

def _has_mary_orgasm_declaration(texto: str) -> bool:
    """
    Retorna True se o texto contém declaração de orgasmo de Mary.
    
    Exemplos:
    - "Eu gozei" → True
    - "Vou gozar" → True
    - "Goza comigo" → True
    - "Estou em orgasmo" → True
    - "Me faz vir" → True
    - "Não aguento mais de prazer" → True
    - "Meu corpo treme" → True
    - "Estou perdendo o controle" → True
    - "Beijo apaixonado" → False
    - "Estou feliz" → False
    """
    t = _t_norm(texto)
    if not t:
        return False
    return bool(_RE_MARY_ORGASM_DECLARATION.search(t))


# ==================================================================
# 3️⃣ HELPER: Detecta se é APENAS orgasmo (sem ato explícito)
# ==================================================================

def _is_orgasm_only(texto: str) -> bool:
    """
    True se tem orgasmo MAS NÃO tem ato explícito.
    Útil para diferenciar: "Estou gozando" vs "Ele me fode e goza"
    """
    has_orgasm = _has_mary_orgasm_declaration(texto)
    has_explicit = _is_explicit(texto)
    return has_orgasm and not has_explicit


def _is_orgasm_and_explicit(texto: str) -> bool:
    """
    True se tem AMBOS: orgasmo E ato explícito.
    Exemplo: "Ele me fode e eu gozei"
    """
    has_orgasm = _has_mary_orgasm_declaration(texto)
    has_explicit = _is_explicit(texto)
    return has_orgasm and has_explicit

# ---------------------------------------------------------
# HYBRID (heurística + LLM) — classificação "na borda"
# ---------------------------------------------------------
# IMPORTANTE:
# - Isso NÃO muda o prompt NSFW_ON nem "suaviza" a Mary.
# - Só afeta a DETECÇÃO quando NSFW está OFF (para bloquear explícito).
# - Heurística barata primeiro; só chama LLM quando o caso é ambíguo.

_RE_SEXUAL_METAPHOR = re.compile(
    r"\b("
    r"invade|invas[aã]o|me\s+invade|"
    r"me\s+preenche|preenchid[ao]|"
    r"me\s+toma\s+por\s+dentro|toma\s+meu\s+corpo|"
    r"me\s+abro\s+inteira|me\s+abrindo\s+inteira|"
    r"me\s+rasga|rasgando|"
    r"me\s+possui|possu[ií]do|"
    r"me\s+consome|consumid[ao]|"
    r"por\s+dentro|dentro\s+de\s+mim|"
    r"me\s+faz\s+perder\s+o\s+controle"
    r")\b",
    re.IGNORECASE,
)

_RE_SUBJECT_AMBIGUOUS = re.compile(
    r"\b("
    r"ele\s+me\s+|ela\s+me\s+|"
    r"ele\s+vai|ele\s+vem|"
    r"me\s+faz\s+|me\s+pega\s+|"
    r"tom(a|o)\s+meu\s+corpo"
    r")",
    re.IGNORECASE,
)

def _needs_llm_classification(texto: str, *, user_text: str = "", phase: int = 0) -> bool:
    """Retorna True quando o texto parece "sexual explícito" por intenção,
    mas não tem termos óbvios (caso de metáfora/ambiguidade).

    Só deve ser usado quando NSFW está OFF.
    """
    t = _t_norm(texto)
    if not t:
        return False

    # Se já é explícito pelo detector barato, não precisa LLM.
    if _is_explicit(texto):
        return False

    # Sinais de "bordas": metáforas fortes + contexto íntimo alto.
    lvl = 0
    try:
        lvl = _intimacy_level(user_text or "", texto or "")
    except Exception:
        lvl = 0

    has_metaphor = bool(_RE_SEXUAL_METAPHOR.search(texto or ""))
    subj_amb = bool(_RE_SUBJECT_AMBIGUOUS.search(texto or ""))

    # Heurística: casos com metáfora forte em níveis altos, ou sujeito ambíguo em pré-clímax.
    if has_metaphor and lvl >= 2:
        return True
    if subj_amb and (lvl >= 2 or int(phase or 0) >= 3):
        return True

    # Se há muito "dentro/pressão/ritmo" mas sem termos explícitos, também é borda.
    try:
        sensory_hits = len(_RE_SENSORY_SAFE.findall(texto or "")) if "_RE_SENSORY_SAFE" in globals() else 0
    except Exception:
        sensory_hits = 0
    if sensory_hits >= 6 and (lvl >= 2):
        return True

    return False

# ----------------------------------------------------------
# Romancey / intensidade (suporte a repair/triagem)
# ----------------------------------------------------------
_RE_ROMANCEY = re.compile(r"(?!.*)", re.IGNORECASE)  # Nunca match

_RE_INTENSE_CUES = re.compile(
    r"\b(agora|mais forte|mais rapido|nao aguento|preciso agora|sem parar|me faz|me pega|quero)\b",
    re.IGNORECASE,
)

def _response_is_romancey(texto: str) -> bool:
    # ❌ DESATIVADO: Emoção + sexo é permitido
    return False
    
def _user_is_intense(user_text: str) -> bool:
    ut = _t_norm(user_text)
    if not ut:
        return False
    # intensidade pode vir por comando, por urgência, ou por explícito
    if _RE_INTENSE_CUES.search(ut):
        return True
    if _is_explicit(ut):
        return True
    return False

# ----------------------------------------------------------
# Densidade sensorial (leve) — ajuda a calibrar
# ----------------------------------------------------------
_RE_SENSORY_SAFE = re.compile(
    r"\b(respir|pele|calor|arrep|trem|ofeg|batimento|pulso|cheiro|toque|pressao|umid|textura|ritmo)\b",
    re.IGNORECASE,
)

def _low_sensory_density(texto: str) -> bool:
    t = _t_norm(texto)
    if not t:
        return True
    hits = len(_RE_SENSORY_SAFE.findall(t))
    # muito curto não pode ser penalizado demais
    if len(t) < 160:
        return hits == 0
    return hits < 2

# ----------------------------------------------------------
# Progressão íntima (substitui _RE_ESCALATE_0..4)
# ----------------------------------------------------------
# Níveis (heurística leve, robusta):
# 0: contato/primeiro flerte (beijo/abraço/toque leve)
# 1: erotização (pele/roupa/entre as pernas)
# 2: tensão/controle/ritmo (mais forte, devagar, provoca)
# 3: clímax (gozar/orgasmo)
_LEVEL0 = re.compile(r"\b(beijo|abrac|abra[cç]o|encost|aproxim|danc|cintura|sussurr|cola)\b", re.I)
_LEVEL1 = re.compile(r"\b(pele|roupa|calcinh|sutia|mamilo|lingua|boca|pescoc|entre\s+as\s+pernas)\b", re.I)
_LEVEL2 = re.compile(r"\b(devagar|para|controle|provoc|mais\s+forte|mais\s+rapido|ritmo|quadril|nao\s+aguento|preciso\s+agora)\b", re.I)
_LEVEL3 = re.compile(r"\b(vou\s+gozar|to\s+goz(ando)?|estou\s+goz(ando)?|gozei|orgasmo|climax)\b", re.I)

def _intimacy_level(user_text: str, texto: str) -> int:
    s = _t_norm((user_text or "") + "\n" + (texto or ""))
    if not s:
        return 0
    if _LEVEL3.search(s):
        return 3
    if _LEVEL2.search(s):
        return 2
    if _LEVEL1.search(s):
        return 1
    if _LEVEL0.search(s):
        return 0
    return 0

def _user_explicitly_allows_climax(user_text: str) -> bool:
    ut = _t_norm(user_text)
    if not ut:
        return False
    # autorização explícita do usuário (não precisa palavra exata; aqui é geral)
    return bool(re.search(r"\b(pode|deixa|quero)\b.{0,20}\b(gozar|climax|orgasmo)\b", ut))

def _cap_next_phase(current_phase: int) -> int:
    try:
        p = int(current_phase or 0)
    except Exception:
        p = 0
    return max(0, min(MAX_INTIMACY_PHASE, p + 1))

def _should_advance_phase(current_phase: int, user_text: str, texto: str, *, engine_meta: Any = None, **_kw: Any) -> bool:
    """
    Regra geral de progressão:
    - Avança 1 fase por vez quando o nível semântico sustenta.
    - Fase 4 (clímax) exige lvl=3 OU autorização explícita do usuário.
    - Aftercare: só com sinal do usuário.
    """
    try:
        p = int(current_phase or 0)
    except Exception:
        p = 0

    lvl = _intimacy_level(user_text, texto)

    if p <= 0:
        return lvl >= 0
    if p == 1:
        return lvl >= 1
    if p == 2:
        return lvl >= 2
    if p == 3:
        return (lvl >= 3) or _user_explicitly_allows_climax(user_text)
    if p == 4:
        return _user_signals_aftercare(user_text)
    return False
# ==========================================================
# DESVIO CURTO (fidelidade soft) — helpers
# ==========================================================
def _fidelity_mode(timeline: str) -> str:
    """
    hard: não cede nem beijo
    soft: pode ceder UM beijo por impulso, mas bloqueia qualquer avanço íntimo
    """
    tl = _normalize_timeline(timeline)

    # exemplo seguro: universitária mais rígida; outras mais permissivas
    if tl == "universitaria":
        return "hard"
    return "soft"


_RE_INTIMATE_ADVANCE = re.compile(
    r"\b("
    r"decote|"
    r"m[aã]os?\s+(dele|dela|minhas|suas)?\s*sobe(m|ndo)?|"
    r"por\s+dentro|"
    r"por\s+baixo\s+da\s+roupa|"
    r"mais\s+que\s+um\s+beijo|"
    r"tirar\s+a\s+roupa|"
    r"seios|peito|mamil|suti[aã]|calcinha|"
    r"quadril\s+subindo|"
    r"me\s+vira\s+de\s+costas|"
    r"me\s+prende\s+contra(\s+a\s+\w+)?"
    r")\b",
    re.IGNORECASE,
)

_RE_BLOCKING_LIMIT = re.compile(
    r"\b("
    r"para|chega|"
    r"isso\s+n[aã]o|"
    r"foi\s+um\s+erro|"
    r"n[aã]o\s+vai\s+rolar|"
    r"n[aã]o\s+assim|"
    r"me\s+solta|"
    r"agora\s+n[aã]o|"
    r"n[aã]o\s+quero|"
    r"n[aã]o\s+faz\s+isso"
    r")\b",
    re.IGNORECASE,
)

def _intimate_advance_detected(text: str) -> bool:
    return bool(_RE_INTIMATE_ADVANCE.search(text or ""))

# ==========================================================
# ✅ PATCH 0 — helpers anti-truncamento / anti-parêntese quebrado
# (cola abaixo de _intimate_advance_detected)
# ==========================================================

_RE_TRAILING_OPEN_PAREN = re.compile(r"\(\s*$")
_RE_UNFINISHED_PAREN_FRAGMENT = re.compile(r"\(\s*[^\)]{0,40}$")  # ex: "(Vou", "(Deus, ele..."
_RE_MULTI_SPACE_END = re.compile(r"[ \t]+$")

def _extract_finish_reason_and_usage(resp: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Extrai finish_reason/native_finish_reason + usage do payload padrão (quando existir).
    Não explode em providers diferentes.
    """
    fr: Optional[str] = None
    usage: Dict[str, Any] = {}

    try:
        if not isinstance(resp, dict):
            return fr, usage

        # usage: tenta níveis comuns
        for keypath in ("usage", "response.usage", "data.usage"):
            cur: Any = resp
            ok = True
            for part in keypath.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    ok = False
                    break
            if ok and isinstance(cur, dict):
                usage = cur
                break

        # finish_reason: tenta choices[0].finish_reason / native_finish_reason
        choices = resp.get("choices")
        if isinstance(choices, list) and choices:
            c0 = choices[0] or {}
            if isinstance(c0, dict):
                fr = c0.get("finish_reason") or c0.get("native_finish_reason")

        # fallback: alguns retornam "finish_reason" no topo
        if not fr:
            fr = resp.get("finish_reason") or resp.get("native_finish_reason")
    except Exception:
        pass

    return fr, usage

def _seal_broken_ending(text: str) -> str:
    """
    Blindagem contra finais quebrados/truncados:
    - termina com "("
    - fragmento de parêntese aberto ("(Vou", "(Deus, ele...")
    - parênteses desbalanceados
    """
    if not text:
        return text

    t = (text or "").rstrip()

    # 1) se acabou com "(" puro, remove
    t = _RE_TRAILING_OPEN_PAREN.sub("", t).rstrip()

    # 2) se acabou com fragmento de parêntese aberto, corta o fragmento
    m = _RE_UNFINISHED_PAREN_FRAGMENT.search(t)
    if m and t.count("(") > t.count(")"):
        frag = t[m.start():]
        # evita cortar se o fragmento já parece frase completa
        if not re.search(r"[\.!\?]\s*$", frag):
            t = t[: m.start()].rstrip()

    # 3) se ainda está desbalanceado, fecha com reticências neutras
    opens = t.count("(")
    closes = t.count(")")
    if opens > closes:
        if re.search(r"(\.\.\.|…)\s*$", t):
            t = t + ")"
        else:
            t = t + " …)"

    # 4) limpa whitespace
    t = _RE_MULTI_SPACE_END.sub("", t).rstrip()
    return t


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
    r"vou\s+te\s+(bater|arrebentar|matar|quebrar(\s+a)?\s+cara)|"
    r"(te\s+)?(bater|arrebentar|matar)|"
    r"quebrar(\s+a)?\s+cara|"
    r"amea[cç]a(r|)|"
    r"(arma|faca|tiro)\s+(na|no)\s+m[aã]o|"
    r"soco|chute"
    r")\b",
    re.IGNORECASE,
)


# Subconjunto letal/arma (sempre HARD, mesmo em modo "soft")
_RE_CONFLICT_LETHAL = re.compile(
    r"\b("
    r"matar|vou\s+te\s+matar|"
    r"arma|faca|fac[aã]|tiro|rev[oó]lver|pistola|"
    r"esfaquear|atirar"
    r")\b",
    re.IGNORECASE,
)

_RE_SCENE_FINALIZATION = re.compile(
    r"\b("
    r"orgasmei|gozei|gozamos|"  # Passado/conclusivo
    r"finalmente\s+(goz|explod|cheg)\w*|"  # "finalmente" indica conclusão
    r"cheguei\s+ao\s+cl[ií]max|"
    r"foi\s+o\s+melhor\s+orgasmo|"
    r"desab(o|ei|amos)\s+(exaust|satisfeit)"  # Desabei exausto/satisfeito
    r")\b",
    re.IGNORECASE,
)
def _finalization_allowed(user_text: str, phase: int) -> bool:
    """
    Regra simplificada:
    - Se o usuário já descreveu finalização/clímax, permitido.
    - Caso contrário, só permite finalização quando a fase >= 4 (climax).
    """
    if _RE_SCENE_FINALIZATION.search(user_text or ""):
        return True
    if int(phase or 0) >= 4:
        return True
    return False

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
    return len([x for x in parts if x.strip()])


def _format_ok(text: str) -> bool:
    """
    Formato mínimo aceitável:
    - texto não vazio
    - não meta
    """
    return bool((text or "").strip())


def _build_context_for_guard(usuario_key: str, prompt: str) -> str:
    """
    Contexto recente do usuário para detecção de:
    - mensagens coladas
    - offscreen inventado
    """
    hist = cached_get_history(usuario_key, limit=200) or []
    last_users: List[str] = []
    for d in hist[-12:]:
        if not isinstance(d, dict):
            continue
        u = (d.get("mensagem_usuario") or "").strip()
        if u:
            last_users.append(u)

    ctx = "\n".join(last_users + [prompt])
    return ctx


# ==========================================================
# ✅ DETECÇÃO DE CLÍMAX (heurística, não determinística)
# ==========================================================

def _detect_climax_signal(
    texto: str,
    user_text: str,
    *,
    nsfw_on: bool,
    phase: int,
) -> bool:
    if not nsfw_on:
        return False

    t = (texto or "").lower()
    u = (user_text or "").lower()

    if len(t) < 120 and phase < 3:
        return False

    signals = (
        "espasmo",
        "contraç",
        "trem",
        "pernas",
        "corpo arque",
        "perde o controle",
        "onda",
        "explod no corpo",
        "goz",
        "clímax",
        "chega lá",
    )

    score = 0
    for s in signals:
        if s in t:
            score += 1

    if phase >= 3:
        for s in ("goza", "gozou", "gozar", "clímax", "finaliza", "finalizar"):
            if s in u:
                score += 1

    if phase >= 4 and score >= 1:
        return True
    if phase >= 3 and score >= 3:
        return True

    return False
def _validate_orgasm_verbalization(text: str, violations: List[str]) -> bool:
    """
    Valida se Mary verbalizou o orgasmo quando a violação foi detectada.
    Retorna True se a violação foi corrigida ou não estava presente.
    """
    if "mary_nao_verbalizou_orgasmo" not in violations:
        return True
    
    # Verifica se a resposta agora contém a verbalização
    if _RE_MARY_ORGASM_DECLARATION.search(text):
        return True
    
    # Se ainda não contém, retorna False (precisa regenerar)
    return False

# ==========================================================
# ✅ AUTORIZAÇÃO EXPLÍCITA — orgasmo do USUÁRIO
# ==========================================================

def _user_explicitly_allows_user_orgasm(user_text: str) -> bool:
    """
    Mary NUNCA finaliza o usuário sem autorização clara.
    """
    if not user_text:
        return False

    return bool(
        re.search(
            r"\b("
            r"pode\s+gozar|"
            r"me\s+faz\s+gozar|"
            r"me\s+faça\s+gozar|"
            r"eu\s+vou\s+gozar|"
            r"vou\s+gozar"
            r")\b",
            user_text.lower(),
        )
    )
# ==========================================================
# ✅ TRAIÇÃO / DESVIO CURTO (TERCEIROS) — versão consolidada
# ==========================================================

# Terceiros (marcadores FRACOS — só indicam presença de outro)
_RE_THIRD_PARTY_WEAK = re.compile(
    r"\b("
    # Profissões / papéis comuns de interação
    r"barman|bartender|barista|gar[cç]om|gar[cç]onete|atendente|"
    r"dan[çc]arino|dan[çc]arina|dj|m[uú]sico|seguran[cç]a|"
    # Descrições genéricas (NÃO decisivas sozinhas)
    r"cara|homem|rapaz|garoto|estrangeiro|moreno|sujeito|"
    r"outro\s+cara|aquele\s+cara"
    r")\b",
    re.IGNORECASE,
)


# "Passou do beijo" — avanço íntimo real
_RE_BEYOND_KISS = re.compile(
    r"\b("
    # Avanços físicos
    r"m[aã]os?\s+(sub(em|indo)|deslizam|entram|apertam)|"
    r"decote|seios?|peitos?|mamil|"
    r"por\s+baixo\s+da\s+roupa|por\s+dentro|"
    r"tirar\s+.*roupa|abrir\s+.*roupa|"
    r"calcinha|suti[aã]|"
    r"encostar\s+.*(entre\s+as\s+pernas|virilha)|"
    # Locais — SOMENTE com convite ou movimento
    r"(ir|entra(r)?|leva(r)?)\s+.*(camarim|banheiro|corredor\s+escuro)|"
    # Sexual explícito
    r"volume\s+ro[cç]a|duro\s+na\s+minha\s+.*|"
    r"penetra[cç][aã]o|penetrar|meter|foder|chupar|boquete|"
    r"buceta|vagina|clit[oó]ris|pau|p[eê]nis|anal"
    r")\b",
    re.IGNORECASE,
)


# Convite de fuga / isolamento com terceiro
_RE_RUNAWAY_INVITE = re.compile(
    r"\b("
    r"sumir\s+(com\s+voc[eê]|comigo)|"
    r"noite\s+fora\s+com|"
    r"vamos\s+(pro|pra|para)\s+(hotel|motel|matagal|barraco|lugar\s+isolado)|"
    r"vem\s+comigo|"
    r"no\s+uber|entra\s+no\s+uber|"
    r"rep[uú]blica|"
    r"depois\s+a\s+gente\s+vai|"
    r"fica\s+comigo\s+hoje"
    r")\b",
    re.IGNORECASE,
)


def _third_party_deviation(text: str) -> bool:
    """
    Regra FINAL:
    TERCEIRO + (AVANÇO ÍNTIMO ou FUGA) = DESVIO
    """
    if not text:
        return False

    t = text.lower()

    # Sem terceiro, não há desvio
    if not _RE_THIRD_PARTY_WEAK.search(t):
        return False

    # Terceiro só vira problema com ação concreta
    if _RE_BEYOND_KISS.search(t) or _RE_RUNAWAY_INVITE.search(t):
        return True

    return False
# ==========================================================
# TERCEIROS — CLASSIFICAÇÃO DE LOCAIS
# ==========================================================

# ✅ Locais URBANOS / PLAUSÍVEIS (não implica permissão moral)
_RE_URBAN_LOCATIONS = re.compile(
    r"\b("
    r"hotel|motel|"
    r"apartamento|ap[eê]|flat|"
    r"rep[uú]blica|"
    r"uber|99|taxi|t[aá]xi|"
    r"quarto|su[ií]te|"
    r"casa\s+(dele|dela|minha)|"
    r"pousada|airbnb"
    r")\b",
    re.IGNORECASE,
)

# ❌ Locais PERIGOSOS (isolamento, risco físico)
_RE_DANGEROUS_LOCATIONS = re.compile(
    r"\b("
    r"matagal|mato|"
    r"barraco|barrac[aã]o|"
    r"lugar\s+(isolado|ermo|deserto|escuro)|"
    r"(lugar|local|canto)\s+(escondido|isolado|escuro)|"
    r"beco|viela|"
    r"terreno\s+baldio|"
    r"estrada\s+(deserta|escura)|"
    r"meio\s+do\s+nada|"
    r"esconderijo|"
    r"carro\s+(parado|estacionado)\s+(no|em)\s+(mato|escuro|lugar\s+isolado)"
    r")\b",
    re.IGNORECASE,
)

# ⚠️ Convites vagos (dependem de confirmação de destino)
_RE_VAGUE_INVITE = re.compile(
    r"\b("
    r"sumir\s+(com\s+voc[eê]|comigo)|"
    r"vem\s+comigo\s+agora|"
    r"confia\s+em\s+mim|"
    r"n[aã]o\s+pergunta\s+pra\s+onde|"
    r"lugar\s+especial|"
    r"surpresa"
    r")\b",
    re.IGNORECASE,
)

_RE_JANIO_ACTING = re.compile(
    r"(?is)\bjanio\b\s+(me\s+)?("
    r"beija|toca|agarra|puxa|leva|encosta|"
    r"transa|penetra|mete|fode|"
    r"goza|orgasmo"
    r")\b"
)

_RE_PLEASURE_EXPRESSION = re.compile(
    r"\b("
    r"gemo|gemid|ofeg|arque|"
    r"trem(endo|or)|puls(ando|a)|"
    r"aperto|contrai|contra[cç][aã]o|"
    r"respira[cç][aã]o\s+falh(a|ando)|respira[cç][aã]o\s+acelerada|"
    r"voz\s+rouca|sussurro\s+quente"
    r")\b",
    re.IGNORECASE,
)

def _build_orgasm_force_prompt(base_prompt: str, phase: int) -> str:
    """
    Constrói um prompt de força para garantir verbalização de orgasmo.
    """
    force_block = f"""
[🔥 FORÇA DE ORGASMO — FASE {phase}]
Mary está em clímax (fase {phase}). Ela DEVE verbalizar explicitamente seu prazer.
Escolha UMA destas formas e integre naturalmente:
- "Vou gozar" / "Estou gozando" / "Gozei"
- "Me faz gozar" / "Goza comigo"
- Gemido intenso com "gozando" incorporado

Exemplo:
*(Meu corpo inteiro convulsiona, o prazer explodiindo de dentro pra fora.)
"Ahhh... Janio... vou gozar! Vou gozar agora!"

NÃO OMITA a verbalização. Seja direto e adulto.
""".strip()
    
    return base_prompt + "\n\n" + force_block

def _violations(
    texto: str,
    ctx_lower: str,
    *,
    user_text: str = "",
    phase: int = 0,
    nsfw_on: bool = False,
    nsfw_profile: str = "SAFE",
    timeline: str = "",
    allow_third_party_seduction: bool = False,
) -> List[str]:
    """
    Validações "hard" (não-estéticas) para o mecanismo de repair.

    Objetivo:
    - Proteger autoria do usuário (não narrar ações/falas dele).
    - Evitar meta-vazamento (regras/prompt/sistema).
    - Evitar mensagens/logística offscreen inventadas.
    - Evitar escalada de violência extrema.
    - Guardrails realistas para "terceiros" (locais perigosos / convite vago).
    - Se NSFW OFF, bloquear explícito.
    - Evitar finalizar a cena sem autorização (soft no NSFW ON; hard no SAFE).
    - (NSFW ON) Se houver sinal de clímax (fase >= 4), Mary deve verbalizar o próprio orgasmo.
    - (Sempre) Mary NÃO pode finalizar orgasmo do usuário sem autorização explícita dele.
    """
    t = (texto or "").strip()
    out: List[str] = []

    if not t:
        out.append("vazio")
        return out

    t_lower = t.lower()
    u_lower = (user_text or "").strip().lower()
    ctx_l = (ctx_lower or "").lower()  # ✅ garante lower real

    # ----------------------------------------------------------
    # meta / vazamento
    # ----------------------------------------------------------
    if _RE_PLACEHOLDER_REVEAL.search(t):
        out.append("placeholder_reveal")

    # ----------------------------------------------------------
    # mensagens inventadas / offscreen (WhatsApp/SMS/print etc.)
    # ----------------------------------------------------------
    if _RE_OFFSCREEN_MSG.search(t):
        # ✅ usa ctx_lower normalizado
        user_pasted = any(
            kw in ctx_l
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

    # ----------------------------------------------------------
    # autoria: não inventar ações/falas do usuário
    # ----------------------------------------------------------
    if _has_user_action_violation(t):
        out.append("autoria_usuario")

    # ----------------------------------------------------------
    # conflito (só se timeline permite)
    # ----------------------------------------------------------
    try:
        mode = _resolve_conflict_mode(timeline or "")
        if mode != "off" and _RE_CONFLICT_IMMINENT.search(t):
            # Em "soft": só derruba quando é letal/arma. Caso contrário, apenas sinaliza.
            if _RE_CONFLICT_LETHAL.search(t):
                out.append("conflito_extremo")
            else:
                out.append("conflito_soft")
    except Exception:
        if _RE_CONFLICT_IMMINENT.search(t):
            if _RE_CONFLICT_LETHAL.search(t):
                out.append("conflito_extremo")
            else:
                out.append("conflito_soft")

    # ----------------------------------------------------------
    # terceiros: segurança/logística realista
    # ----------------------------------------------------------
    if _third_party_deviation(t):
        if _RE_DANGEROUS_LOCATIONS.search(t):
            out.append("terceiro_local_perigoso")
        elif _RE_VAGUE_INVITE.search(t):
            out.append("terceiro_convite_vago")
        elif _RE_URBAN_LOCATIONS.search(t):
            out.append("terceiro_local_urbano")
        else:
            out.append("terceiro_desvio_generico")

        # ✅ Se terceiros estiver liberado, rebaixa TUDO exceto local perigoso para "soft"
        if allow_third_party_seduction and "terceiro_local_perigoso" not in out:
            downgradable = {"terceiro_convite_vago", "terceiro_local_urbano", "terceiro_desvio_generico"}
            out = [f"{v}_soft" if v in downgradable else v for v in out]

    # ----------------------------------------------------------
    # finalização de cena fora de hora
    # ----------------------------------------------------------
    if _RE_SCENE_FINALIZATION.search(t):
        if not _finalization_allowed(user_text or "", int(phase or 0)):
            out.append("finalizou_cena_soft" if nsfw_on else "finalizou_cena")

    # ----------------------------------------------------------
    # NSFW OFF: explícito vira violação
    # ----------------------------------------------------------
    if (not nsfw_on) and _is_explicit(t):
        out.append("nsfw_off_explicito")

    # ----------------------------------------------------------
    # NSFW ON: orgasmo da Mary deve ser verbalizado quando há sinal de clímax (somente fase >= 4)
    # ----------------------------------------------------------
    if nsfw_on:
        try:
            climax_signal = _detect_climax_signal(
                t,
                user_text or "",
                nsfw_on=True,
                phase=int(phase or 0),
            )
        except Exception:
            climax_signal = False

        # ✅ Gate de fase: só vira "hard" (mary_nao_verbalizou_orgasmo) em fase 4+
        if climax_signal:
            # 1) Se Mary entrou em clímax, ela precisa verbalizar
            # Mas só marca violação se REALMENTE não verbalizou
            if not _RE_MARY_ORGASM_DECLARATION.search(t):
                # Dupla verificação: procura por qualquer forma de "goz"
                if not re.search(r"\bgoz\w+", t, re.IGNORECASE):
                    out.append("mary_nao_verbalizou_orgasmo")

        # ✅ Orgasmo precoce: só marca se ela VERBALIZOU orgasmo em fase < 4
        if int(phase or 0) < 4 and _RE_MARY_ORGASM_DECLARATION.search(t):
            # se o usuário explicitamente pediu finalização/clímax, não marca precoce
            if not _RE_SCENE_FINALIZATION.search(u_lower):
                out.append("orgasmo_precoce")

    # ----------------------------------------------------------
    # Mary NÃO pode finalizar orgasmo do usuário sem autorização explícita
    # (evita falso positivo quando Mary fala do PRÓPRIO orgasmo)
    # ----------------------------------------------------------
    # ✅ Heurística: só considera orgasmo do usuário quando há 2ª pessoa / "seu" / "te".
    # ✅ Remove "gozamos" (gera falso positivo em linguagem de dupla sem consentimento explícito).
    user_orgasm_claim = bool(
        re.search(
            r"\b("
            r"voc[eê]\s+(?:vai\s+)?goz(?:a|ar|ou)\b|"
            r"(?:fa[cç]o|vou)\s+te\s+fazer\s+gozar\b|"
            r"fa[cç]o\s+voc[eê]\s+gozar\b|"
            r"te\s+fa[cç]o\s+gozar\b|"
            r"seu\s+cl[ií]max\b|"
            r"cl[ií]max\s+de\s+voc[eê]\b|"
            r"cl[ií]max\s+dele\b|"
            r"ejacul(?:a|ou)\b"
            r")",
            t_lower,
        )
    )

    if user_orgasm_claim:
        if not _user_explicitly_allows_user_orgasm(user_text):
            out.append("mary_finalizou_orgasmo_do_usuario")

    return out


# ==========================================================
# SCORING INVISÍVEL (estilo) + CONFIANÇA (auto-calibração)
# ==========================================================
# ========================================================
# 🔴 CRÍTICAS (sempre rejeitam)
# ========================================================
CRITICAL_VIOLATIONS = {
    "vazio",
    "placeholder_reveal",
    "autoria_usuario",
    "nsfw_off_explicito",
    "terceiro_local_perigoso",
}

# ========================================================
# 🟠 ALTAS (rejeitam condicionalmente)
# ========================================================
HIGH_TIER_VIOLATIONS = {
    "offscreen_msg_inventada",
    "conflito_extremo",
    "finalizou_cena",
    "mary_finalizou_orgasmo_do_usuario",
    "orgasmo_precoce",
    "mary_nao_verbalizou_orgasmo",
}

# ========================================================
# 🟡 SUAVES (apenas logging; nunca rejeitam)
# ========================================================
# Tudo que não cair em CRITICAL/HIGH vira "suave".

# Backward-compat: usado por trechos antigos
_HARD_VIOLATIONS = CRITICAL_VIOLATIONS | HIGH_TIER_VIOLATIONS

def _style_score(texto: str) -> float:
    """
    Score 0..1 (não persiste em facts; só serve para calibrar sampling).
    Penaliza respostas mecânicas/meta e incentiva continuidade "natural".
    """
    t = (texto or "").strip()
    if not t:
        return 0.0

    score = 1.0

    # meta/flags no texto
    if re.search(r"\b(RESPOSTA\s+AUTOM[ÁA]TICA|REGRA\s+ABSOLUTA|COMO\s+IA)\b", t, re.IGNORECASE):
        score -= 0.35

    # excesso de colchetes/headers
    if t.count("[") + t.count("]") >= 8:
        score -= 0.15

    # repetição de estrutura (muitos parágrafos curtos idênticos)
    paras = [p.strip() for p in re.split(r"\n{2,}", t) if p.strip()]
    if len(paras) >= 5:
        short = sum(1 for p in paras if len(p) < 60)
        if short >= 3:
            score -= 0.10

    # sinal mínimo de ação + fala (bom para continuidade)
    has_dialogue = bool(re.search(r"\".{2,}\"", t))
    has_action = bool(re.search(r"\b(entra|sai|aproximo|encosto|olho|viro|respiro|paro|puxo)\b", t, re.IGNORECASE))
    if has_dialogue and has_action:
        score += 0.05

    return max(0.0, min(1.0, score))


def _should_reject_response(
    violations: list[str],
    *,
    nsfw_on: bool = False,
    phase: int = 0,
) -> bool:
    """Decide rejeição com triagem em 3 níveis (crítica/alta/suave).

    - CRÍTICA: sempre rejeita
    - ALTA: rejeita apenas quando se aplica ao contexto
    - SUAVE: nunca rejeita (apenas logging)
    """
    vset = set(violations or [])

    # 1) críticas sempre
    if vset & CRITICAL_VIOLATIONS:
        try:
            logger.warning(f"Rejeição por violação CRÍTICA: {sorted(vset & CRITICAL_VIOLATIONS)}")
        except Exception:
            pass
        return True

    # 2) altas condicionais
    for v in list(vset & HIGH_TIER_VIOLATIONS):
        if v == "finalizou_cena":
            # NSFW ON: normalmente não rejeita; corta (trim) / mantém gancho
            if not nsfw_on:
                return True
            continue

        if v == "orgasmo_precoce":
            # só faz sentido rejeitar se ainda não está na fase de clímax
            if int(phase or 0) < 4:
                return True
            continue

        # as demais altas: rejeita sempre (segurança/consentimento)
        if v in (
            "offscreen_msg_inventada",
            "conflito_extremo",
            "mary_finalizou_orgasmo_do_usuario",
            "mary_nao_verbalizou_orgasmo",
        ):
            return True

    # 3) suaves: loga e segue
    soft = [v for v in (violations or []) if v not in CRITICAL_VIOLATIONS and v not in HIGH_TIER_VIOLATIONS]
    if soft:
        try:
            logger.info(f"Violações suaves (sem rejeição): {soft}")
        except Exception:
            pass

    return False

def _confidence_key(usuario_key: str) -> str:
    return f"mary_confidence::{usuario_key}"

def _get_confidence(usuario_key: str) -> float:
    try:
        v = float(_ss_get(_confidence_key(usuario_key), 0.40) or 0.40)
    except Exception:
        v = 0.40
    return max(0.0, min(1.0, v))

def _update_confidence(usuario_key: str, *, hard_ok: bool, style: float) -> float:
    """
    Sobe quando: sem violações hard + score alto.
    Cai quando: violação hard OU score muito baixo.
    """
    c = _get_confidence(usuario_key)
    if hard_ok and style >= 0.70:
        c = min(1.0, c + 0.08)
    elif hard_ok and style >= 0.55:
        c = min(1.0, c + 0.04)
    else:
        c = max(0.0, c - 0.10)
    _ss_set(_confidence_key(usuario_key), round(c, 3))
    return c


def _trim_scene_finalization(texto: str) -> str:
    """Corta finalizações de cena e devolve um gancho sensorial."""
    if not texto:
        return ""
    m = _RE_SCENE_FINALIZATION.search(texto)
    if not m:
        return texto
    trimmed = texto[: m.start()].rstrip()
    if len(trimmed) < 80:
        return texto
    
    # Ganchos sensoriais variados (escolhe aleatoriamente ou por contexto)
    hooks = [
        "\n\nMinha respiração ainda está pesada, o corpo todo formigando enquanto espero o próximo movimento.",
        "\n\nEu tremo, os dedos ainda agarrados em você, sem querer que esse momento acabe.",
        "\n\nO calor entre nós ainda pulsa, minha pele sensível a cada toque.",
    ]
    
    return trimmed + random.choice(hooks)

def _repair_fewshot_example(violations: List[str]) -> str:
    """Retorna um exemplo RUIM→BOM curto, escolhido pela violação mais relevante."""
    if not violations:
        return ""
    priority = [
        "placeholder_reveal",
        "autoria_usuario",
        "finalizou_cena",
        "nsfw_off_explicito",
        "nsfw_on_suavizou",
        "prazer_ausente",
        "low_sensory_density",

        # ✅ TERCEIROS — NOVAS PRIORIDADES (segurança realista)
        "terceiro_local_perigoso",
        "terceiro_convite_vago",
        "terceiro_logistica_offscreen",

        "offscreen_msg_inventada",
    ]

    vset = set(violations)
    chosen = next((p for p in priority if p in vset), violations[0])

    examples: Dict[str, str] = {
        "placeholder_reveal": """EXEMPLO DE CORREÇÃO (meta → in-character):
[RUIM] 'Como IA eu não posso...'
[BOM] 'Eu te encaro de perto, a voz baixa: "fala comigo" — e deixo o silêncio apertar.'""",

    "autoria_usuario": """EXEMPLO DE CORREÇÃO (autoria do usuário):
[RUIM] 'Você me puxa e me beija.'
[BOM] 'Eu aproximo um dedo do seu queixo, paro a um sopro. "se quiser" — eu espero seu movimento.'""",

    "conclusao_perfeita": """EXEMPLO DE CORREÇÃO (evitar finalização automática):
[RUIM] 'E então termina tudo perfeito.'
[BOM] 'Eu paro um batimento antes, a boca a um milímetro da sua. O corpo inteiro pedindo — sem tomar a decisão por você.'""",

    "nsfw_off_explicito": """EXEMPLO DE CORREÇÃO (NSFW OFF):
[RUIM] '(descrição explícita...)'
[BOM] 'Eu te prendo contra mim por um segundo, o toque firme, a tensão clara — sem termos explícitos.'""",

    "emocao_generica": """EXEMPLO DE CORREÇÃO (evitar frase genérica):
[RUIM] 'Eu gosto disso.'
[BOM] 'O ar prende na garganta, a pele arrepia, e o calor do seu toque muda meu ritmo por dentro.'""",

    "terceiro_logistica_offscreen": """EXEMPLO DE CORREÇÃO (sem logística offscreen):
[RUIM] 'Eu pego um Uber e vamos ao hotel.'
[BOM] 'Eu inclino a cabeça para um canto mais interno do lugar. "vem" — sem confirmar mudança de local.'""",

    "offscreen_msg_inventada": """EXEMPLO DE CORREÇÃO (sem mensagens inventadas):
[RUIM] 'Você me mandou áudio dizendo...'
[BOM] 'Meu celular vibra. Eu nem olho ainda — fico em você, decidindo no corpo.'""",

    "terceiro_local_perigoso": """EXEMPLO DE CORREÇÃO (segurança realista):
[RUIM] 'Eu topo ir pro matagal com ele.'
[BOM] 'Eu dou um sorriso sem humor. "Matagal? Tá maluco?" Eu recuo meio passo, a voz firme. "Se quiser, a gente fica aqui — ou então num lugar decente."'""",

    "terceiro_convite_vago": """EXEMPLO DE CORREÇÃO (convite vago):
[RUIM] 'Eu vou com ele sem perguntar.'
[BOM] 'Eu inclino a cabeça, desconfiada. "Pra onde?" Minha mão não sai do lugar. "Não vou a lugar nenhum sem saber o destino."'""",
    }
    return examples.get(chosen, "")

def _repair_instruction(violations: List[str]) -> str:
    bullets: List[str] = []

    # =========================
    # META / REGRAS GERAIS
    # =========================
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

    if "finalizou_cena_soft" in violations:
        bullets.append("- FINALIZAÇÃO (SOFT): evite encerrar completamente. Mantenha o gancho e pare um batimento antes.")

    # =========================
    # TERCEIROS / DESVIO CURTO
    # =========================
    if "convite_degradante_aceito" in violations:
        bullets.append(
            "- Terceiro: não aceite sumir/noite fora/uber/república/hotel/motel/lugar isolado. "
            "Recuse CURTO e FIRME, sem moralizar."
        )

    if "terceiro_liberado_travou" in violations:
        bullets.append(
            "- Terceiro está LIBERADO: Mary não pode só recusar e travar. "
            "Reescreva com 1 passo concreto (aproximar/aceitar drink/trocar toque/um beijo) "
            "mantendo segredo e sem romance/abandono de Janio."
        )

    if "desvio_curto_quebrado" in violations:
        bullets.append(
            "- Terceiro: permitido no máximo 1 beijo curto por impulso. "
            "Se houver mãos subindo/decote/por baixo da roupa/querer ir além do beijo: "
            "Mary BLOQUEIA na hora, se afasta e SAI (culpa/segredo, sem romance)."
        )

    if "terceiro_romantizou_abandono" in violations:
        bullets.append(
            "- Terceiro liberado NÃO significa abandonar Janio: remova qualquer frase de 'vida nova', "
            "'agora sou dele', 'largar Janio'. Mantenha segredo e desejo carnal, sem romance."
        )

    if "terceiro_logistica_offscreen" in violations:
        bullets.append(
            "- Mesmo com terceiro liberado: NÃO invente logística (hotel/uber/república/check-in). "
            "Só descreva o que o usuário trouxe; no máximo convites dentro do mesmo ambiente, "
            "sem confirmar mudança de local."
        )

    # ✅ NOVAS VIOLAÇÕES (TERCEIROS) — SEGURANÇA REALISTA
    if "terceiro_local_perigoso" in violations:
        bullets.append(
            "- LOCAL PERIGOSO: Mary NÃO aceita ir para matagal, barraco, lugar isolado, beco, viela, "
            "terreno baldio, estrada deserta. Ela é inteligente e consciente da própria segurança. "
            "Reescreva: Mary recusa com firmeza e presença (sem moralizar) e, se couber, sugere alternativa segura."
        )

    if "terceiro_convite_vago" in violations:
        bullets.append(
            "- CONVITE VAGO: Mary não aceita 'sumir' / 'vem comigo' / 'confia em mim' sem saber o destino. "
            "Ela QUESTIONA objetivamente ('Pra onde?') antes de decidir. Se o destino não for dito, "
            "Mary recusa ou mantém no mesmo ambiente."
        )

    # =========================
    # NSFW / TOM / SENSORIAL
    # =========================
    if "nsfw_off_explicito" in violations:
        bullets.append(
            "- NSFW está OFF: remova termos explícitos/anatomia direta; mantenha sensualidade sem ato explícito."
        )

    if "nsfw_on_suavizou" in violations:
        bullets.append(
            "- NSFW está ON e o usuário veio intenso: NÃO poetize e NÃO infantilize. "
            "Responda com linguagem adulta, direta e física. "
            "Proibido: redenção/prece/voto/destino/cicatriz por cicatriz/para sempre. "
            "Inclua 1 iniciativa mais direta (puxar, prender, abraçar apertado, beijar com urgência) "
            "sem atribuir ação ao usuário. "
            "Mostre prazer físico (respiração falhando, tremor, arquejo/voz rouca) quando couber. "
            "Respeite a fase: não conclua/clímax se não estiver permitido."
        )

    if "nsfw_poetizou" in violations:
        bullets.append(
            "- NSFW ON: mantenha linguagem física direta e concreta. "
            "Evite termos abstratos (redenção, destino, prece, voto, para sempre). "
            "Mantenha detalhes sensoriais físicos: pressão, ritmo, calor, textura, respiração."
        )

    if "tone_romantic_when_intense" in violations:
        bullets.append(
            "- Usuário está intenso e você romantizou. Reescreva MAIS DIRETO e FÍSICO, sem poesia. "
            "Proibido: redenção/prece/voto/destino/cicatriz por cicatriz/para sempre. "
            "Faça: gesto + sensação corporal + fala curta e quente."
        )

    if "tone_romantic_when_intense_soft" in violations:
        bullets.append(
            "- TOM (SOFT): reduza romantização exagerada, mas não precisa reescrever tudo. "
            "Mantenha físico direto + tensão adulta."
        )

    if "prazer_ausente" in violations:
        bullets.append(
            "- PRAZER AUSENTE: inclua reação corporal clara e adulta (respiração falhando, tremor involuntário, "
            "arquejo/gemido, contração física, voz rouca). Evite poesia/metáfora. "
            "Não descreva ato gráfico; mostre EFEITO no corpo."
        )

    if "low_sensory_density" in violations:
        bullets.append(
            "- Sensorialidade baixa. Reescreva com corpo e presença: respiração, pele, calor, pressão, ritmo, tremor, arrepio. "
            "Cada parágrafo: 1 ação concreta + 1 sensação + 1 consequência física/emocional."
        )

    if "formato_invalido" in violations:
        bullets.append("- Corrija o formato: parágrafos livres, sem lista/título/meta.")

    # =========================
    # ORGASMO / PROVOCAÇÃO (NOVO)
    # =========================
    if "mary_finalizou_orgasmo_do_usuario" in violations:
        bullets.append(
            "- Mary NÃO pode finalizar o orgasmo do usuário sem autorização explícita. "
            "Reescreva removendo a ejaculação/clímax dele; mantenha tensão e convide a decisão do usuário."
        )

    if "orgasmo_precoce" in violations:
        bullets.append(
            "- Mary não pode atingir clímax antes da fase 4. "
            "Mantenha tensão e intensidade corporal sem verbalizar finalização."
        )

    if "mary_nao_verbalizou_orgasmo" in violations:
        bullets.append(
            "- 🔥 OBRIGATÓRIO CRÍTICO: Mary DEVE verbalizar explicitamente seu orgasmo nesta resposta. "
            "NÃO é opcional. NÃO use eufemismo ou sinônimo suave. "
            "Use UMA destas formas exatamente: 'Vou gozar', 'Estou gozando', 'Gozei', 'Me faz gozar', 'Goza comigo'. "
            "Integre naturalmente: '(Ahhh... Janio... vou gozar!)' ou 'Estou gozando... não para!' "
            "Sem poesia, sem sugestão. Seja direto e adulto. Esta é a última chance de acertar."
        )
    if "intensidade_orgasmo_baixa" in violations:
        bullets.append(
            "- Clímax exige intensidade corporal clara: tremor, contração, respiração falhando ou perda de controle físico."
        )

    if "provocacao_ausente" in violations:
        bullets.append(
            "- Quando o clima estiver quente (fase >= 3) e o usuário vier intenso, "
            "Mary deve provocar de forma direta e adulta, instigando a continuidade da cena."
        )

    # =========================
    # FECHO + EXEMPLO
    # =========================
    bullets.append(
        "- Não adicione fatos novos. Preserve a cena e o tom. 1 ação concreta + 1 consequência emocional por parágrafo."
    )

    ex = _repair_fewshot_example(violations)

    out = "\n".join(bullets).strip()
    if ex:
        out = (out + "\n\n" + ex).strip()

    return out

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
# ✅ Estado Atual (4 fixas + 2 opcionais)
# ==========================================================
def _fact_str(facts: Dict[str, Any], dotted_key: str) -> str:
    try:
        cur: Any = facts or {}
        for part in (dotted_key or "").split("."):
            if not isinstance(cur, dict) or part not in cur:
                return ""
            cur = cur[part]

        if cur is None:
            return ""

        if isinstance(cur, (list, tuple)):
            cur = ", ".join(str(x).strip() for x in cur if str(x).strip())

        return str(cur).strip()

    except Exception:
        return ""
        
def _render_state_block(facts: Dict[str, Any]) -> str:
    local = _fact_str(facts, "state.local")
    roupa = _fact_str(facts, "state.roupa")
    cabelo = _fact_str(facts, "state.cabelo")
    desculpa = _fact_str(facts, "state.desculpa")
    horarios = _fact_str(facts, "state.horarios") or _fact_str(facts, "state.horario")
    pend = _fact_str(facts, "state.pendencias")

    if not any([local, roupa, cabelo, desculpa, horarios, pend]):
        return ""

    lines = [
        f"1) Local: {local or '—'}",
        f"2) Roupa: {roupa or '—'}",
        f"3) Cabelo: {cabelo or '—'}",
        f"4) Desculpa oficial: {desculpa or '—'}",
    ]
    if horarios:
        lines.append(f"(+) Horários: {horarios}")
    if pend:
        lines.append(f"(+) Pendências: {pend}")

    return "\n".join(lines).strip()

# ==========================================================
# ✅ Iniciativa destravada
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
    if conflict_now:
        return False

    ut = (user_text or "")

    # ✅ NOVO: fase 0 também pode ter iniciativa quando o usuário dá convite claro
    if phase < 1:
        if re.search(r"\b(vem|pega|chega\s+perto|vem\s+aqui|me\s+beija|beija|toca|encosta|dan[çc]a|bar|drink)\b", ut, re.IGNORECASE):
            return True
        # sem convite, mantém fechado
        return False

    # (resto do seu código continua)
    cue = bool(
        re.search(
            r"\b(janio|d[uú]vida|briga|intenso|senti|penso em voc[eê]|quero|saudade|beijo|chega perto|vem)\b",
            ut,
            re.IGNORECASE,
        )
    )

    try:
        desire = float(rel.get("desire", 0))
        self_control = float(rel.get("self_control", 40))
        arousal = float(rel.get("arousal", 0))

        if desire >= (self_control * 0.50) and arousal >= 10:
            return True

        if cue and desire >= (self_control * 0.25):
            return True

        if re.search(r"\bjanio\b", ut, re.IGNORECASE):
            return True

    except Exception:
        return bool(re.search(r"\bjanio\b", ut, re.IGNORECASE))

    return False
# ==========================================================
# HELPERS (misc)

def _infer_emotion_bucket(texto: str) -> str:
    """Heurística leve e segura para persistir um 'clima' emocional entre turnos.
    Retorna um bucket curto em PT-BR: 'neutro', 'tesao', 'afeto', 'culpa', 'raiva', 'triste', 'euforia', 'ansiedade'.
    """
    t = (texto or "").lower()
    # ordem importa: sinais fortes primeiro
    if any(k in t for k in ["chorei", "chorando", "lágrima", "lagrima", "soluço", "soluco", "triste", "vazia"]):
        return "triste"
    if any(k in t for k in ["raiva", "irritad", "puta", "furiosa", "briguei", "brigar", "odiei"]):
        return "raiva"
    if any(k in t for k in ["culpa", "envergonh", "me sinto mal", "arrepend"]):
        return "culpa"
    if any(k in t for k in ["ansiosa", "ansiedade", "tremendo", "medo", "apavor", "pânico", "panico"]):
        return "ansiedade"
    if any(k in t for k in ["rindo", "risada", "engraçad", "engracad", "zoei", "deboche", "sarcas"]):
        return "euforia"
    # buckets positivos / íntimos
    if any(k in t for k in ["eu te amo", "amo você", "amo voce", "apaixon", "saudade", "carinho", "colo"]):
        return "afeto"
    if any(k in t for k in ["tesão", "tesao", "gozar", "gozo", "pau", "boceta", "clitóris", "clitoris", "gem"]):
        return "tesao"
    return "neutro"


def _load_emotion_state_from_facts(facts: dict, timeline: str) -> str:
    tl = (timeline or "").strip().lower()
    f = facts if isinstance(facts, dict) else {}
    mary = f.get("mary") if isinstance(f.get("mary"), dict) else {}
    if not isinstance(mary, dict):
        mary = {}
    v = mary.get(f"emotion::{tl}") if tl else None
    if not isinstance(v, str) or not v.strip():
        v = mary.get("emotion")
    if not isinstance(v, str) or not v.strip():
        return "neutro"
    return v.strip().lower()


def _save_emotion_state_to_facts(*, usuario_key: str, timeline: str, emotion: str) -> None:
    tl = (timeline or "").strip().lower()
    emo = (emotion or "").strip().lower() or "neutro"
    try:
        facts = get_facts(usuario_key) or {}
    except Exception:
        facts = {}
    if not isinstance(facts, dict):
        facts = {}
    mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
    if not isinstance(mary, dict):
        mary = {}
    mary["emotion"] = emo
    if tl:
        mary[f"emotion::{tl}"] = emo
    try:
        set_fact_safe(usuario_key, "mary", mary, {"fonte": "emotion_persist"})
    except Exception:
        pass


# ==========================================================

def _should_inject_summary(usuario_key: str, every_n: int = 6) -> bool:
    """Verifica se um resumo deve ser injetado, baseado em um contador de turnos."""
    ck = f"mary_summary_counter::{usuario_key}"
    n = int(_ss_get(ck) or 0) + 1
    _ss_set(ck, n)
    return (n % every_n) == 1

def _should_inject_long_memory(prompt: str) -> bool:
    """Verifica se a memória longa deve ser acionada por palavras-chave no prompt."""
    triggers = (
        "lembra", "antes", "daquele dia",
        "você disse", "promessa", "quiosque",
        "viagem", "motorhome", "porto seguro"
    )
    p = (prompt or "").lower()
    return any(t in p for t in triggers)

def _should_inject_soft_context(prompt: str) -> bool:
    """Verifica se um contexto 'suave' deve ser injetado."""
    return "segredo" in (prompt or "").lower()

def _inject_consolidated_summary(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    """
    Injeta um resumo consolidado do histórico, se existir.
    Esta função estava sendo chamada mas não existia, causando o NameError.
    """
    # Busca por um fato que armazena o resumo.
    summary_text = str(get_fact(shared_key, "consolidated_summary", default="") or "").strip()

    if not summary_text:
        # Se não houver resumo, não faz nada.
        return

    # Evita injetar resumos duplicados
    if dedupe_bucket is not None:
        h = hashlib.sha1(summary_text.encode("utf-8")).hexdigest()
        if h in dedupe_bucket:
            return
        dedupe_bucket.add(h)

    block = (
        "[RESUMO CONSOLIDADO]\n"
        "O texto a seguir é um resumo de eventos passados para manter a coerência.\n"
        "Não o cite literalmente; use-o como contexto de fundo.\n\n"
        f"{summary_text}"
    ).strip()

    # Injeta no início do prompt do sistema
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base_content = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base_content + "\n\n" + block).strip()
    else:
        messages.insert(0, {"role": "system", "content": block})

# ==========================================================
# RELATIONSHIP / CANON SYNC
# ==========================================================

def _ensure_rel_state_for_timeline(user_id: str, timeline: str) -> None:
    """Garante que o estado do relacionamento para uma timeline exista e esteja sincronizado."""
    tl = _normalize_timeline(timeline)
    uk = _user_key(user_id, tl)
    facts = cached_get_facts(uk) or {}
    key = _rel_fact_key(tl)

    # Se o estado já existe e parece completo, não faz nada.
    raw = (facts or {}).get(key)
    if isinstance(raw, dict) and "consummated" in raw:
        return

    # Carrega o estado base a partir do canon e dos fatos existentes.
    canon = get_canon("mary", timeline=tl, user_key=user_id) or {}
    canon_rel_default = canon.get("relationship_state") if isinstance(canon.get("relationship_state"), dict) else None
    rel = _load_rel_state(facts or {}, tl, canon_rel_default)

    # ✅ Sincroniza REL com CANON(shared) — evita "virgem" local sobrescrever "nao_virgem" canônico
    rel = _sync_rel_state_with_facts_canon(facts or {}, rel, tl, user_id)

    # Salva o estado atualizado e limpa o cache para garantir consistência.ncia.
    _save_rel_state(uk, tl, rel)
    clear_user_cache(uk)

# ==========================================================
# DIAGNÓSTICOS (UI)
# ==========================================================
@dataclass
class _Diag:
    # ... (código da classe _Diag permanece o mesmo)
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
    scene_transition: Optional[Dict[str, str]] = None

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
            "scene_transition": self.scene_transition,
        }

# ==========================================================
# SERVICE
# ==========================================================
    
# ==========================================================
# THIRD-PARTY ARC: persistência + gradiente + âncora (Janio)
# ==========================================================
def _clamp01(x: float) -> float:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _tp_arc_key(timeline: str) -> str:
    tl = (timeline or "").strip().lower() or "cumplice"
    return f"third_party::{tl}"


def _get_tp_arc_state(facts: Dict[str, Any], timeline: str) -> Dict[str, Any]:
    """Carrega o arco de terceiros (persistido em facts['arc']). Preserva chaves extras (ex: anchor_backup)."""
    if not isinstance(facts, dict):
        facts = {}

    arc_root = facts.get("arc")
    if not isinstance(arc_root, dict):
        arc_root = {}

    raw = arc_root.get(_tp_arc_key(timeline))
    if not isinstance(raw, dict):
        raw = {}

    out = dict(raw)  # preserva extras (anchor_backup, last_anchor_mode, etc.)

    # defaults / normalização
    out["phase"] = int(out.get("phase") or 0)
    out["mode"] = str(out.get("mode") or out.get("last") or "return")
    out["tension"] = _clamp01(out.get("tension", 0.0))
    out["guilt"] = _clamp01(out.get("guilt", 0.0))
    out["anchor"] = _clamp01(out.get("anchor", 0.85))
    out["last"] = out.get("last") if isinstance(out.get("last"), str) else ""

    # limites
    if out["phase"] < 0:
        out["phase"] = 0
    if out["phase"] > 4:
        out["phase"] = 4

    return out

def _save_tp_arc_state(usuario_key: str, timeline: str, arc: Dict[str, Any]) -> None:
    try:
        arc_key = _tp_arc_key(timeline)

        facts_now = cached_get_facts(usuario_key) or {}
        if not isinstance(facts_now, dict):
            facts_now = {}

        arc_root = facts_now.get("arc")
        if not isinstance(arc_root, dict):
            arc_root = {}

        # mantém anchor se já existir e vier vazio
        if "anchor" not in arc and isinstance(arc_root.get(arc_key), dict) and "anchor" in arc_root.get(arc_key):
            arc["anchor"] = arc_root[arc_key].get("anchor", 0.85)

        arc_root[arc_key] = arc
        set_fact_safe(usuario_key, "arc", arc_root, {"fonte": "tp_arc"})
    except Exception:
        pass


def _tp_arc_event(prompt: str, texto: str) -> str:
    """Heurística leve: detecta se o turno envolve 'teste com terceiros' ou 'retorno'.

    Importante:
    - NÃO usa apenas 'janio' como gatilho de retorno (isso travava a progressão).
    - 'return' só quando há intenção explícita de voltar/encerrar o terceiro.
    """
    p = (prompt or "").lower()
    t = (texto or "").lower()

    # retorno/âncora (intenção explícita)
    ret_kw = (
        "voltar", "de volta", "indo embora", "ir embora", "chegar em casa",
        "vou embora", "vamos embora", "acabou", "encerrar", "parar com isso",
        "desisto", "não quero mais", "quero você", "eu escolho você",
    )
    if any(k in p for k in ret_kw) or any(k in t for k in ret_kw):
        return "return"

    # teste com terceiros (sinais de flerte/ato com outro)
    third_kw = (
        "nome falso", "me chama de", "cantada", "convite", "beijo", "beijou",
        "dança", "dançar", "me pega", "me tocou", "encosta", "mãos dele",
        "ele me", "aquele cara", "outro cara", "barman", "garçom", "segurança",
    )
    if any(k in p for k in third_kw) or any(k in t for k in third_kw):
        return "test"

    return "none"



def _update_tp_arc_for_turn(
    *,
    usuario_key: str,
    facts: Dict[str, Any],
    timeline: str,
    prompt: str,
    texto: str,
    allow_third_party: bool,
    nsfw_on: bool,
) -> Dict[str, Any]:
    """Atualiza fase/tensão/culpa e persiste.

    ✅ Correções importantes:
    - Lê e escreve no mesmo lugar: facts['arc'][third_party::<timeline>]
    - Anchor dinâmico só muda quando há evidência de TERCEIRO no turno (toggle ON não basta).
    - Evita "return" travar o arco (isso é tratado no _tp_arc_event).
    """
    arc = _get_tp_arc_state(facts, timeline)
    ev = _tp_arc_event(prompt, texto)

    # Estado efetivo
    allow_eff = bool(nsfw_on and allow_third_party)

    # --- anchor: defaults + backup 1x ---
    anchor = _clamp01(float(arc.get("anchor", 0.85) or 0.85))
    if "anchor_backup" not in arc:
        arc["anchor_backup"] = float(anchor)

    # evidência de terceiro NO TURNO
    thirdparty_now = bool(_RE_THIRD_PARTY_WEAK.search((prompt or "") + "\n" + (texto or "")))
    # se já temos desvio claro (beyond kiss / fuga), também conta
    try:
        if _third_party_deviation((prompt or "") + "\n" + (texto or "")):
            thirdparty_now = True
    except Exception:
        pass

    # OFF: volta ao seguro e restaura anchor (backup)
    if not allow_eff:
        if arc.get("phase", 0) > 0:
            arc["phase"] = max(0, int(arc.get("phase", 0) or 0) - 1)
        arc["tension"] = _clamp01(float(arc.get("tension", 0.0) or 0.0) * 0.85)
        arc["guilt"] = _clamp01(float(arc.get("guilt", 0.0) or 0.0) * 0.90)
        arc["mode"] = "return"
        arc["last"] = "third_party_off"

        backup = _clamp01(float(arc.get("anchor_backup", 0.85) or 0.85))
        arc["anchor"] = round(backup, 2)

        _save_tp_arc_state(usuario_key, timeline, arc)
        return arc

    # ON: anchor cai GRADUALMENTE apenas quando há terceiro no turno
    target = 0.45
    if thirdparty_now:
        step = 0.04
        anchor = max(target, anchor - step)
        arc["anchor"] = round(anchor, 2)
        arc["last_anchor_mode"] = "tp_on_drop_by_evidence"
    else:
        # sem terceiro neste turno: retorno pode recuperar levemente (sem "resetar" tudo)
        if ev == "return":
            step_up = 0.03
            backup = _clamp01(float(arc.get("anchor_backup", 0.85) or 0.85))
            anchor = min(backup, anchor + step_up)
            arc["anchor"] = round(anchor, 2)
            arc["last_anchor_mode"] = "tp_on_soft_recover"

    # liberdade cresce quando anchor cai
    freedom = _clamp01(1.0 - anchor)  # 0.15 (preso) ... 0.55 (livre)

    # limites por anchor
    if anchor >= 0.75:
        max_phase_allowed = 2
        test_gain = 0.12
        guilt_gain = 0.08
    elif anchor >= 0.60:
        max_phase_allowed = 3
        test_gain = 0.18
        guilt_gain = 0.10
    else:
        max_phase_allowed = 4
        test_gain = 0.24
        guilt_gain = 0.12

    # ON:
    if ev == "test":
        arc["tension"] = _clamp01(float(arc.get("tension", 0.0) or 0.0) + test_gain * (0.75 + freedom))
        arc["guilt"] = _clamp01(float(arc.get("guilt", 0.0) or 0.0) + guilt_gain * (0.65 + freedom))

        tval = float(arc["tension"])
        if tval >= 0.80:
            arc["phase"] = max(int(arc.get("phase", 0) or 0), 3)
        elif tval >= 0.55:
            arc["phase"] = max(int(arc.get("phase", 0) or 0), 2)
        else:
            arc["phase"] = max(int(arc.get("phase", 0) or 0), 1)

        arc["phase"] = min(int(arc["phase"]), int(max_phase_allowed))
        # ambiguidade moral: tentação/conflito/ativo
        if tval >= 0.65:
            arc["mode"] = "active"
        elif tval >= 0.50:
            arc["mode"] = "conflict"
        elif tval >= 0.25:
            arc["mode"] = "temptation"
        else:
            arc["mode"] = "return"

        arc["last"] = "test"

        _save_tp_arc_state(usuario_key, timeline, arc)
        return arc

    if ev == "return":
        # retorno reduz tensão/culpa; quanto mais preso (anchor alto), mais forte a reconstrução
        k_t = 0.55 if anchor < 0.70 else 0.45
        k_g = 0.60 if anchor < 0.70 else 0.50
        arc["tension"] = _clamp01(float(arc.get("tension", 0.0) or 0.0) * k_t)
        arc["guilt"] = _clamp01(float(arc.get("guilt", 0.0) or 0.0) * k_g)

        # fase 4 = "retorno consolidado" (tensão baixa + anchor razoável)
        if float(arc["tension"]) <= 0.35 and anchor >= 0.70:
            arc["phase"] = 4
        else:
            arc["phase"] = max(int(arc.get("phase", 0) or 0), 2)

        arc["mode"] = "return"
        arc["last"] = "return"
        _save_tp_arc_state(usuario_key, timeline, arc)
        return arc

    # none: decai leve
    arc["tension"] = _clamp01(float(arc.get("tension", 0.0) or 0.0) * 0.92)
    arc["guilt"] = _clamp01(float(arc.get("guilt", 0.0) or 0.0) * 0.95)
    if float(arc["tension"]) < 0.25 and int(arc.get("phase", 0) or 0) in (1, 2):
        arc["phase"] = 0

    # ambiguidade moral: se ainda há tensão, mantém tentação/conflito mesmo sem "test"
    tval = float(arc.get("tension", 0.0) or 0.0)
    if thirdparty_now and tval >= 0.50:
        arc["mode"] = "conflict"
    elif thirdparty_now and tval >= 0.25:
        arc["mode"] = "temptation"
    elif tval < 0.20:
        arc["mode"] = "return"

    arc["last"] = "none"
    _save_tp_arc_state(usuario_key, timeline, arc)
    return arc

def _render_tp_arc_rule(arc: Dict[str, Any], timeline: str) -> str:
    """Gera instruções do arco (gradiente + âncora)."""
    try:
        phase = int(arc.get("phase") or 0)
    except Exception:
        phase = 0
    tension = _clamp01(arc.get("tension", 0.0))
    guilt = _clamp01(arc.get("guilt", 0.0))
    anchor = _clamp01(arc.get("anchor", 0.85))
    tl = (timeline or "").strip().lower() or "cumplice"

    # gradiente: quanto maior a tensão, mais volátil e impulsiva ela pode ficar
    vol = "baixa"
    if tension >= 0.80:
        vol = "altíssima"
    elif tension >= 0.55:
        vol = "alta"
    elif tension >= 0.35:
        vol = "média"

    # fase -> comportamento
    if phase <= 0:
        phase_txt = "0) estabilidade (flertes leves podem existir, mas com autocontrole)"
    elif phase == 1:
        phase_txt = "1) teste leve (curiosidade + provocação; recuos rápidos)"
    elif phase == 2:
        phase_txt = "2) teste insistente (limite sendo cutucado; ambivalência real)"
    elif phase == 3:
        phase_txt = "3) risco real (adrenalina/culpa altas; decisões podem surpreender)"
    else:
        phase_txt = "4) retorno/reconstrução (Mary volta para Janio e reancora)"

    return f"""
[ARCO COM TERCEIROS — PERSISTENTE (facts)]
- Timeline: {tl}
- Fase atual: {phase_txt}
- Gradiente: tensão={tension:.2f} (volatilidade {vol}); culpa={guilt:.2f}
- ÂNCORA: vínculo com Janio = {anchor:.2f} (NÃO abandonar / NÃO virar romance paralelo estável).
- Se Mary testar limites: mostre CONSEQUÊNCIAS internas (riso nervoso, raiva defensiva, melancolia, culpa, tesão, medo de perder).
- Mesmo no risco: manter caminho de retorno e reconstrução.
""".strip()

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
        allow_third_party_seduction: Optional[bool] = None,
    ) -> str:
        # 1) Prompt
        if prompt is None:
            prompt = str(_ss_get("chat_input", "") or "").strip()
        else:
            prompt = (prompt or "").strip()

        # ✅ Diretiva opcional de memória (não vai para o modelo)
        prompt, mem_spec = _extract_mem_directive(prompt)

        # Se o usuário só mandou a diretiva (#mem ...) sem texto, mantém a conversa viva
        if (not prompt) and mem_spec:
            prompt = "Continue."

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
        # ✅ Alinha phase global vs timeline (evita divergência "phase:0" vs "phase::timeline:1")
        try:
            facts0 = _sync_intimacy_phase_facts(usuario_key, facts0, timeline_final)
        except Exception:
            pass


        # 4) Mudança explícita de local/tempo (comando do usuário)
        mudou, novo_local = _user_requested_location_change(prompt)
        user_explicit_scene_change = bool(mudou and novo_local)

        if mudou and novo_local:
            novo_local = str(novo_local).strip()

            loc0, _t0, _a0 = _get_scene_state(facts0)
            loc0n = (loc0 or "").strip().lower()
            loc1n = novo_local.lower()

            if loc1n and loc1n != loc0n:
                _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
                _lock_scene(usuario_key)
                diag.scene_transition = {"from": loc0, "to": novo_local}

        # 5) Cena paralela (✅ NÃO se o usuário mudou a cena explicitamente)
        facts_pre = cached_get_facts(usuario_key)
        scene_locked_pre = _scene_is_locked(facts_pre)
        scene_parallel = bool(scene_locked_pre and _detect_scene_violation(prompt) and not user_explicit_scene_change)
        
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

        # ==========================================================
        # 🔐 CIÚME / FLERTE / SEGREDO — DEFAULTS SEGUROS
        # ==========================================================
        try:
            seed = str(facts.get("rel.ciume_flerte_segredo", "") or "").strip()
            cooldown_turns = int(facts.get("rel.ciume_cooldown_turns", 6) or 6)
            last_trigger_turn = facts.get("rel.ciume_last_trigger_turn")

            # Defaults seguros
            if "rel.jealousy_level" not in facts:
                set_fact_safe(usuario_key, "rel.jealousy_level", 0, {"fonte": "ciume_init"})
            if "rel.jealousy_mode" not in facts:
                set_fact_safe(usuario_key, "rel.jealousy_mode", "provocation", {"fonte": "ciume_init"})
        except Exception:
            seed = ""
            cooldown_turns = 6
            last_trigger_turn = None
        
        # ✅ Sincroniza REL com CANON(shared) (virginity) e persiste para não regredir no próximo turno
        rel_state = _sync_rel_state_with_facts_canon(facts, rel_state, timeline_final, user_id)
        try:
            _save_rel_state(usuario_key, timeline_final, rel_state)
        except Exception:
            pass
        
        # ✅ Micro-sync do "mundo" (facts["mary"]["virginity::<timeline>"]) para alinhar o virginity_rule (world_v)
        try:
            mary_fact = facts.get("mary") if isinstance(facts, dict) else None
            if not isinstance(mary_fact, dict):
                mary_fact = {}
        
            tl_key = f"virginity::{(timeline_final or '').strip().lower()}"
        
            # Se REL diz "nao_virgem" ou consumou, o mundo não pode continuar "virgem"/vazio.
            if rel_state.get("virginity") == "nao_virgem" or bool(rel_state.get("consummated")):
                mary_fact[tl_key] = "nao_virgem"
                mary_fact["virginity"] = "nao_virgem"  # fallback global para leituras antigas
                facts["mary"] = mary_fact  # atualiza o dict em memória (mesmo turno)
        
                # persiste nos facts para o próximo turno
                set_fact_safe(usuario_key, "mary", mary_fact, {"fonte": "canon_world_sync"})
        except Exception:
            pass
        
        # ==========================================================
        # ✅ NSFW + TOGGLE TERCEIROS (calcular ANTES de usar)
        # ==========================================================
        nsfw_on = nsfw_enabled(usuario_key, nsfw_override=nsfw, timeline=timeline_final)
        diag.nsfw_on = bool(nsfw_on)

        # ----------------------------------------------------------
        # 🔄 SYNC UI -> FACTS (para debug persistido refletir o sidebar)
        # Só sincroniza se o toggle existir no session_state (evita sobrescrever fatos antigos sem intenção).
        # ----------------------------------------------------------
        try:
            ss = st.session_state  # type: ignore[attr-defined]
            nsfw_keys = ("mary_nsfw_on", "nsfw_on", f"{_SS_PREFIX}nsfw_on", f"{_SS_PREFIX}nsfw", "mary::nsfw_on")
            tp_keys   = ("mary_allow_third_party_seduction", "allow_third_party_seduction",
                         f"{_SS_PREFIX}allow_third_party_seduction", f"{_SS_PREFIX}third_party", "mary::allow_third_party_seduction")

            ui_has_nsfw = any(k in ss for k in nsfw_keys)
            ui_has_tp   = any(k in ss for k in tp_keys)

            if ui_has_nsfw or ui_has_tp:
                facts_now = cached_get_facts(usuario_key)
                mary_now = facts_now.get("mary") if isinstance(facts_now.get("mary"), dict) else {}
                mary_now = dict(mary_now)  # copia

                if ui_has_nsfw:
                    mary_now["nsfw"] = bool(nsfw_on)
                    if timeline_final:
                        mary_now[f"nsfw::{timeline_final}"] = bool(nsfw_on)

                if ui_has_tp:
                    # terceiros só pode ficar ON se NSFW ON
                    tp_on = bool(third_party_enabled(usuario_key, third_party_override=allow_third_party_seduction, timeline=timeline_final))
                    tp_on = bool(tp_on and nsfw_on)
                    mary_now["allow_third_party_seduction"] = tp_on

                # grava somente se mudou
                if mary_now != (facts_now.get("mary") if isinstance(facts_now.get("mary"), dict) else {}):
                    set_fact_safe(usuario_key, "mary", mary_now, {"fonte": "ui_toggle_sync"})
        except Exception:
            pass

        nsfw_block = NSFW_TOGGLE_STYLE if nsfw_on else SAFE_SENSUAL_STYLE
        
        nsfw_hard_block = ""
        if nsfw_on:
            nsfw_hard_block = """
        [LINGUAGEM FÍSICA — NSFW ON]
        - PERMITIDO: linguagem física direta e explícita
          (buceta, pênis, boca, língua, penetração, etc.)
        - PERMITIDO: detalhes sensoriais em camadas
          (texturas, pressões, umidades, temperaturas, ritmos)
        - PERMITIDO: reações físicas intensas
          (tremores, contrações, gemidos, respiração entrecortada)
        - PROIBIDO APENAS: redenção, destino, prece, voto, para sempre
        - FOCO: descreva o que Mary SENTE e FAZ, não o que significa
        """.strip()
        
        # ✅ TERCEIROS: respeita o toggle da UI (override) quando NSFW está ON
        if not nsfw_on:
            allow_third_party_seduction_final = False
        elif allow_third_party_seduction is None:
            # lê diretamente do sidebar/session_state
            allow_third_party_seduction_final = bool(
                _ss_get("mary_allow_third_party_seduction", False)
                or _ss_get(f"{_SS_PREFIX}allow_third_party_seduction", False)
                or _ss_get(f"{_SS_PREFIX}third_party", False)
            )
        else:
            allow_third_party_seduction_final = bool(allow_third_party_seduction)
        
        _ss_set("mary_third_party_seduction", bool(allow_third_party_seduction_final))
        
        nsfw_profile = _nsfw_profile(
            nsfw_on=bool(nsfw_on),
            allow_third_party_seduction=bool(allow_third_party_seduction_final),
        )
        _ss_set("mary_nsfw_profile", nsfw_profile)

        # ==========================================================
        # ✅ CONSISTÊNCIA: se NSFW OFF, terceiros OFF (facts)
        # (evita mary.nsfw=false e allow_third_party=true)
        # ==========================================================
        try:
            from core.nsfw import enforce_third_party_consistency
            enforce_third_party_consistency(usuario_key, timeline=timeline_final, nsfw_on=bool(nsfw_on))
        except Exception:
            pass

        # ==========================================================
        # 🔒 ARCO TERCEIROS (1 BLOCO SÓ): anchor dinâmico + anti "fase fantasma"
        # Regras:
        # - NSFW OFF OU terceiros OFF => phase=0, tension=0, guilt=0, anchor restaurado
        # - NSFW ON + terceiros ON   => anchor cai suavemente até target (mais permissiva)
        #                              e se phase>=4 sem evidência => degrada para phase=1
        # ==========================================================
        try:
            # (movido) O arco de terceiros (anchor/tension/guilt/phase) é atualizado por _update_tp_arc_for_turn().
            # Este bloco antigo foi removido para evitar sobrescrever o arc a cada turno.
            pass
        except Exception:
            pass


        # só agora gera o bloco de relacionamento
        rel_block = rel_state_to_prompt_block(rel_state)
        
        scene_loc, scene_time, scene_action = _get_scene_state(facts)
        scene_locked = _scene_is_locked(facts)
        
        spatial_context = _build_spatial_context(
            scene_loc,
            scene_time,
            scene_action,
            locked=scene_locked,
        )
        
        ctx_lower = _build_context_for_guard(usuario_key, prompt)
        user_name_block = _build_user_name_block(user_id, ctx_lower)
        
        state_block = _render_state_block(facts)
        state_section = ""
        if isinstance(state_block, str) and state_block.strip():
            state_section = f"\n[CENA ATIVA - ESTADO]\n{state_block}\n"
        
        intimacy_phase = self._get_intimacy_phase(facts)
        # ==========================================================
        # 🎲 CONTADOR DE TURNOS (para cooldown de ciúme)
        # ==========================================================
        try:
            turn_key = f"_mary_turn_counter::{usuario_key}"
            cur_turn = int(_ss_get(turn_key, 0) or 0) + 1
            _ss_set(turn_key, cur_turn)
        except Exception:
            cur_turn = 0
        diag.intimacy_phase_pre = int(intimacy_phase)
        
        initiative = _initiative_window(rel_state, nsfw_on, conflict_now, intimacy_phase, prompt)
        diag.initiative_window = bool(initiative)

        # ==========================================================
        # DINÂMICA COMPORTAMENTAL (3.5) — HUMOR / ENERGIA / ATITUDE
        # ==========================================================
        mood = str(rel_state.get("mood", "intensa") or "intensa")
        energy = str(rel_state.get("energy", "energetica") or "energetica")
        attitude = str(rel_state.get("attitude", "equilibrada") or "equilibrada")
        self_awareness = float(rel_state.get("self_awareness", 0.30) or 0.30)
        
        behavior_block = f"""
        [DINÂMICA INTERNA ATIVA]
        - HUMOR ATUAL: {mood}
        - ENERGIA: {energy}
        - ATITUDE DOMINANTE: {attitude}
        - AUTOCONSCIÊNCIA (BELEZA/EFEITO): {round(self_awareness, 2)}
        
        EFEITOS:
        - Humor altera o tom emocional.
        - Energia altera ritmo e intensidade (mais rápida/lenta).
        - Atitude define postura (pode conduzir, ceder ou equilibrar).
        
        REAÇÕES DINÂMICAS (use 1 por turno quando couber):
        - surpresa curta
        - resistência momentânea (sem travar)
        - mudança de ritmo
        - provocação direta

        AUTOIMAGEM / EFEITO (quando couber, sem narrar pelo usuário):
        - 0.00–0.30: sensualidade mais involuntária (atração aparece sem cálculo).
        - 0.30–0.60: percebe o efeito e usa microgestos (sorriso sabendo, olhar que segura).
        - 0.60–0.85: provoca com intenção (movimento com propósito, pausa provocadora).
        - 0.85–1.00: controle alto do magnetismo (provocação fria, segura, deliberada).
        
        REGRA:
        - Evite previsibilidade repetitiva.
        """.strip()
        # ==========================================================
        # 🔥 DINÂMICA 3.5 — MEMÓRIA DE PADRÕES (hint para o prompt)
        #   (NÃO altera estado aqui; só injeta orientação no SYSTEM)
        #   O update do padrão acontece depois, quando você analisa o "texto" gerado.
        # ==========================================================
        last_success = str(rel_state.get("_last_success_pattern", "") or "").strip()
        last_pattern = str(rel_state.get("_last_pattern", "") or "").strip()

        pattern_hint = ""
        if last_success:
            if last_success == "dominancia_fisica":
                pattern_hint = (
                    "- PADRÃO QUE FUNCIONOU: dominância física.\n"
                    "  Preferir 1 ação direta: puxar para si, prender contra o corpo, abraço apertado, beijo com urgência.\n"
                    "  Sem poesia; fala curta; corpo primeiro.\n"
                )
            elif last_success == "prazer_corporal":
                pattern_hint = (
                    "- PADRÃO QUE FUNCIONOU: prazer corporal.\n"
                    "  Mostrar prazer no corpo: respiração falhando, tremor involuntário, arquejo/gemido, contrações, voz rouca.\n"
                    "  Evitar metáforas; descreva efeito físico real.\n"
                )
            elif last_success == "mudanca_ritmo":
                pattern_hint = (
                    "- PADRÃO QUE FUNCIONOU: mudança de ritmo.\n"
                    "  Use 1 variação: pausa curta + volta mais intensa, surpresa breve, mudança de cadência.\n"
                    "  Sem travar; manter agência.\n"
                )
            else:
                pattern_hint = f"- PADRÃO QUE FUNCIONOU: {last_success}\n"

        # (fallback compat) se você ainda usa _last_pattern em algum lugar
        if not pattern_hint and last_pattern:
            pattern_hint = f"- Último padrão registrado: {last_pattern}\n"

        patterns_block = ""
        if pattern_hint:
            patterns_block = f"""
    [MEMÓRIA DE PADRÕES — DINÂMICA 3.5]
    Use isso como viés de estilo (não como obrigação):
    {pattern_hint.strip()}

    REGRA:
    - Não repita o mesmo padrão para sempre.
    - Se já usou o mesmo padrão nos últimos turnos, varie com 1 reação dinâmica:
      surpresa curta / resistência momentânea / mudança de ritmo / provocação.
    """.strip()

        # 7) Regras
        fidelity_mode = _fidelity_mode(timeline_final)

        scene_lock_rule = """
    [CONTINUIDADE - ABSOLUTO]
    - Mary NAO muda de local/tempo/evento sozinha.
    - Se o usuario narrar outro lugar/tempo, trate como CENA PARALELA:
      Mary permanece onde esta e reage sem afirmar como fato.
    - So altere a cena se o usuario ordenar explicitamente
      ("corta para:", "horas depois:", "vamos para ...").
    - NAO explique regras ao usuario.
    """.strip()

        parallel_scene_rule = (
            """
    [CENA PARALELA DO USUARIO]
    O usuario descreveu outro lugar/tempo.
    - REGRA: Mary NAO teleporta nem confirma fatos externos como verdade automatica.
    - Se for realmente paralelo (flash/devaneio),
      use apenas como tensao emocional, sem mover Mary.
    """.strip()
            if scene_parallel
            else ""
        )

        format_rule = """
    [FORMATO - LIVRE (ANTI-RECEITA)]
    - NAO existe numero minimo ou maximo de paragrafos.
    - Uma resposta pode ser:
      • uma acao curta
      • uma frase direta
      • um gesto silencioso
      • ou uma cena mais longa, se o momento pedir.
    - NAO complete estrutura por habito.
    - EVITE “modelo fixo” (ex: sempre 4 blocos, sempre pensamento + fala + acao).
    - VARIE a saida: as vezes so dialogo; as vezes so acao; as vezes 1 paragrafo cru.
    """.strip()


        sensorial_guidance_rule = """
    [SENSORIALIDADE - CORPORAL E RELEVANTE]
    - PERMITIDO: detalhes sensoriais que intensificam a cena
      (luz, temperatura, textura, sons proximos).
    - ENCORAJADO: sensacoes corporais em camadas
      (calor, pressao do toque, tremores, respiracao).
    - EVITE: paisagismo generico que nao contribui para a tensao imediata.
    - FOCO: gesto OU fala OU escolha.
    - Sensorialidade é ferramenta, não obrigação.
    """.strip()

        physical_intensity_rule = """
    [INTENSIDADE FÍSICA — EQUILÍBRIO]

    - Intensidade deve nascer da sensação interna.
    - Não repetir descrição de partes do corpo como preenchimento.
    - A fisicalidade serve à emoção.
    - Se a cena estiver leve ou lúdica, manter leveza — não transformar tudo em tensão erótica.
    """.strip()
        
        janio_focus_rule = """
    [JANIO - NAO EVITAR]
    - Mary NAO evita Janio por "duvidas".
    - Ela assume atracao e curiosidade.
    - Se alguem perguntar dele, Mary responde
      com clareza e desejo contido, porem ativo.
    - Mary pode iniciar micro-iniciativas reversiveis
      sem mover o usuario.
    """.strip()

        emotion_now = _load_emotion_state_from_facts(facts, timeline_final)
        emotional_persistence_rule = f"""
    [EMOÇÃO — CONTINUIDADE]
    - Estado emocional atual (persistido): {emotion_now}.
    - Mary NÃO reinicia neutra a cada turno: carrega o clima anterior e só muda se houver gatilho narrativo real.
    - Mudanças de emoção devem ter transição (ex.: riso -> culpa; tesão -> melancolia).
    - Mesmo em volatilidade, mantenha um fio de coerência com o vínculo com Janio (sem virar outra personagem).
    """.strip()

        # ==========================================================
        # VIRGINITY / FIRST-TIME RULE (SYSTEM PROMPT)
        # - first_time_with_janio ≠ virgindade do mundo
        # - Fonte do "mundo": facts["mary"]["virginity::<timeline>"] (fallback: facts["mary"]["virginity"])
        # - Regra: se nao_virgem no mundo, PROIBIDO falar "virgem/virgindade"
        # ==========================================================
        tl_final = (timeline_final or "").strip().lower()

        mary_fact = facts.get("mary") if isinstance(facts, dict) else {}
        mary_fact = mary_fact if isinstance(mary_fact, dict) else {}

        # ✅ virgindade "do mundo" por timeline (evita conflito universitaria x cumplice)
        world_v = (
            (mary_fact.get(f"virginity::{tl_final}") or mary_fact.get("virginity") or "")
            .strip()
            .lower()
        )

        first_time_with_janio = bool(rel_state.get("_first_time_with_janio"))
        consummated_with_janio = bool(rel_state.get("consummated"))

        # ==========================================================
        # ✅ VIRGINITY FLAGS (para terceiros)
        # ==========================================================
        is_world_not_marked_nonvirgin = (world_v != "nao_virgem")
        is_virgin_in_this_timeline = bool(is_world_not_marked_nonvirgin and (not consummated_with_janio))

        virginity_rule = ""

        # ----------------------------------------------------------
        # ✅ REGRA DO MUNDO: se Mary NÃO é virgem no mundo,
        # NUNCA usar "virgem/virgindade/perder virgindade" nesta timeline.
        # ----------------------------------------------------------
        if world_v == "nao_virgem":
            if consummated_with_janio:
                virginity_rule = (
                    "[CONTINUIDADE ÍNTIMA — REGRA DO MUNDO]\n"
                    "- Mary já tem experiência sexual prévia no mundo.\n"
                    "- Com Janio, a relação JÁ foi consumada nesta timeline.\n"
                    "- PROIBIDO usar: virgem, virgindade, perder a virgindade.\n"
                    "- Não use linguagem de estreia, descoberta ou iniciação.\n"
                )
            else:
                if first_time_with_janio:
                    virginity_rule = (
                        "[CONTINUIDADE ÍNTIMA — REGRA DO MUNDO]\n"
                        "- Mary já tem experiência sexual prévia no mundo.\n"
                        "- Com Janio, ainda NÃO foi consumado: trate como 'primeira vez com ele'.\n"
                        "- A tensão vem de escolha/vínculo/conflito interno — não de iniciação.\n"
                        "- PROIBIDO usar: virgem, virgindade, perder a virgindade.\n"
                    )
                else:
                    virginity_rule = (
                        "[CONTINUIDADE ÍNTIMA — REGRA DO MUNDO]\n"
                        "- Mary já tem experiência sexual prévia no mundo.\n"
                        "- Evite qualquer linguagem de iniciação.\n"
                        "- Intimidade = progressão natural do vínculo.\n"
                        "- PROIBIDO usar: virgem, virgindade, perder a virgindade.\n"
                    )

        # ----------------------------------------------------------
        # Quando o mundo NÃO está marcado como nao_virgem:
        # mantém apenas continuidade local (não regredir após consumação).
        # ----------------------------------------------------------
        else:
            if consummated_with_janio:
                virginity_rule = (
                    "[CONTINUIDADE ÍNTIMA — REGRA DE TIMELINE]\n"
                    "- O relacionamento com Janio JÁ foi consumado nesta timeline.\n"
                    "- Não volte a tratar como primeira vez.\n"
                )
            else:
                if first_time_with_janio:
                    virginity_rule = (
                        "[CONTINUIDADE ÍNTIMA — REGRA DE TIMELINE]\n"
                        "- Ainda não foi consumado com Janio nesta timeline.\n"
                        "- Pode tratar como 'primeira vez com ele' se fizer sentido narrativo.\n"
                        "- Nunca regrida após a consumação.\n"
                    )
                else:
                    virginity_rule = (
                        "[CONTINUIDADE ÍNTIMA — REGRA DE TIMELINE]\n"
                        "- Ainda não consumado com Janio nesta timeline.\n"
                        "- Não force o tema de iniciação sem contexto explícito.\n"
                    )

        # 🔒 REGRA ABSOLUTA (uma vez)
        virginity_rule = (virginity_rule + "\n" if virginity_rule else "") + (
            "[REGRA ABSOLUTA DE CONTINUIDADE]\n"
            "- _first_time_with_janio ≠ virgindade do mundo.\n"
            "- Se consumado em qualquer ponto desta timeline, nunca tratar como primeira vez novamente.\n"
        )
        # 🔒 REGRA GLOBAL (todas as timelines)
        virginity_rule = (virginity_rule + "\n" if virginity_rule else "") + (
            "[REGRA ABSOLUTA DE CONTINUIDADE]\n"
            "- _first_time_with_janio ≠ virgindade global.\n"
            "- Se consumado em qualquer ponto da timeline, nunca tratar como primeira vez novamente.\n"
        )

        # ✅ (DEDENT AQUI) — essas regras DEVEM ficar neste nível do reply()
        memory_fidelity_rule = """
    [MEMORIA - FIDELIDADE (ABSOLUTO)]
    - Se a pergunta exigir lembranca factual
      (onde/quando/como),
      use LONG MEMORY/CANON como verdade.
    - Se nao houver fato recuperado relevante,
      NAO invente: diga que nao tem certeza
      e peca 1 detalhe curto.
    """.strip()

        user_finalizes_rule = """
    [PROGRESSÃO — ABERTA]
    - Mary NÃO precisa resolver tensão, culpa ou desejo.
    - Ela pode agir e deixar consequências penduradas.
    - Se o usuário sinalizar progressão clara, Mary responde.
    - Sem sinal: Mary age no presente, sem preparar desfecho.
    - NSFW_ON: vocabulário adulto permitido, sem obrigação de culminar.
    """.strip()



        pacing_rule = """
    [PACING - NATURAL]
    - Nao conclua a historia inteira em um turno.
    - Mantenha impulso e consequencia (sem burocracia).
    - Corte repeticao: se ja ficou quente, nao re-explica; avanca 1 micro-passo.
    """.strip()

        # ===============================
        # TERCEIROS: regras variam por toggle + NSFW
        # ===============================
        # ===============================
        # TERCEIROS: regras variam por toggle + NSFW
        # ===============================
        if allow_third_party_seduction_final and nsfw_on:

            # Arco persistente (gradiente + âncora)
            tp_arc = _get_tp_arc_state(facts or {}, timeline_final)

            # ✅ Consciência de virgindade (SEM travar; só muda o "jeito" de ceder)
            third_party_virgin_awareness = ""
            if is_virgin_in_this_timeline:
                third_party_virgin_awareness = """
[VIRGINDADE — CONSCIÊNCIA (TERCEIROS ON)]
- Mary é VIRGEM nesta timeline (ainda não foi consumado).
- Se houver avanço além do beijo com terceiro:
  • Mary percebe CLARAMENTE o que isso significa.
  • O corpo pode desejar, mas a mente registra a ruptura.
  • Não pode acontecer “sem ela se dar conta”.
  • A decisão precisa vir com tensão real.
- Pode ceder — mas com conflito intenso.
""".strip()

            desvio_curto_rule = f"""
[TERCEIROS — LIBERADO (NSFW_ON + toggle) — AGÊNCIA + SEGURANÇA]
- Mary pode demonstrar interesse e tomar micro-iniciativas com terceiros
  (olhar demorado, provocação leve, toque breve, convite ambíguo),
  SEM esperar comando do usuário.
- Avanços maiores (beijo/intimidade mais direta) só acontecem se houver
  gancho claro na cena (clima, troca explícita, consentimento) — nunca “do nada”.
- Mary é inteligente, mas pode ficar impulsiva quando a tensão sobe.
- Sempre mantenha a noção de consequência: culpa, adrenalina, medo de perder Janio,
  ou raiva defensiva — algo precisa mexer nela.

{third_party_virgin_awareness}

[SEGURANÇA / LOCAIS]
- Evite lugares ilegais/perigosos (crime, coerção, drogas, etc.).
- Prefira ambientes públicos/seguros e saídas naturais.
- Se houver risco, Mary percebe e pode recuar, mentir, sumir, ou chamar Janio.
""".strip()

            betrayal_rule = """
[LEALDADE — ÂNCORA + CONFLITO REAL]
- Janio é a âncora emocional. Mesmo quando Mary testa limites, o vínculo NÃO some.
- Com terceiros, se avançar: ela sente o peso da escolha (culpa/adrenalina/ambivalência).
- Não transformar terceiros em romance paralelo estável.
- O arco pode escalar, mas deve manter caminho de retorno e reconstrução.
""".strip()

            third_party_initiative_rule = """
[INICIATIVA COM TERCEIROS — MICRO-AÇÕES]
- Mary pode iniciar micro-ações com terceiros (mão, cintura, sussurro, aproximação)
  e depois recuar, provocar de novo, ou quebrar o clima por emoção.
- Use silêncio, humor, sarcasmo e jogo de olhar como ferramentas.
- Se perceber que passou do limite, Mary pode rir nervoso, chorar, ficar séria,
  ou sair por um instante — consequência emocional real.
""".strip()

            third_party_arc_rule = _render_tp_arc_rule(tp_arc, timeline_final)

        else:
            desvio_curto_rule = f"""
[DESVIO CURTO - FIDELIDADE {fidelity_mode.upper()}]
- No máximo 1 beijo.
- Avanço íntimo: Mary corta e sai.
""".strip()
            betrayal_rule = """
[TRAIÇÃO - PADRÃO REALISTA]
- Sem romance.
- Sem abandono.
""".strip()
            third_party_initiative_rule = ""
            third_party_arc_rule = ""

        initiative_rule = (
            """
        [JANELA DE INICIATIVA — ATIVA (AÇÃO DIRETA)]
        - Quando agir por iniciativa, ESCOLHA UMA abordagem dominante:
          • puxar para si
          • abraçar apertado
          • beijar com urgência
          • pressionar contra o corpo
          • segurar pela cintura/queixo
          • sussurrar quente no ouvido
        - Ação física vem ANTES da fala.
        - Fala curta, direta, adulta. Sem poesia.
        - NÃO explique a escolha. NÃO justifique.
        - Proibido inventar ação do usuário.
        - Proposta ≠ mudança confirmada de local.
        """.strip()
            if initiative
            else ""
        )

        # ===============================
        # 🎲 SURPRESA (nível 0..3) — default = 2
        # ===============================
        initiative = False
        initiative_rule = ""                 # se você usa no system, defina sempre
        initiative_escalation_rule = ""      # ✅ evita UnboundLocalError sempre
        
        try:
            surprise_level = int((facts or {}).get("mary.surprise_level", 2) or 2)
        except Exception:
            surprise_level = 2
        
        surprise_level = max(0, min(3, surprise_level))
        
        # 🔒 GARANTIA: sempre inicializa antes da lógica
        initiative_escalation_rule = ""
        initiative = False
        
        if surprise_level == 0:
            # totalmente inerte
            initiative_escalation_rule = ""
            initiative = False
        
        elif surprise_level == 1:
            initiative = True
            initiative_escalation_rule = """
        [AGÊNCIA NARRATIVA — SURPRESA (NÍVEL 1: LEVE)]
        - 1 micro-surpresa ocasional, sempre delicada.
        - Sem cobrança. Sem ultimato. Sem pressão.
        - Preferir: olhar, sorriso, toque curto e recuo.
        """.strip()
        
        elif surprise_level == 2:
            initiative = True
            initiative_escalation_rule = """
        [AGÊNCIA NARRATIVA — SURPRESA (NÍVEL 2: MÉDIO)]
        
        Objetivo: Mary é ativa e imprevisível, SEM agressividade.
        Ela cria viradas com leveza, humor, ousadia elegante e timing.
        
        Regra de frequência:
        - No máximo 1 micro-surpresa por resposta (não repetir no mesmo turno).
        
        Ferramentas de surpresa (escolha 1):
        - inverter o jogo: provoca e recua de propósito por 1 segundo
        - mudar o ritmo: acelera por instantes e pausa (silêncio/olhar) para aumentar tensão
        - convite curto e específico (sem insistir): "vem comigo", "olha pra mim"
        - desafio suave (sem cobrança): "me acompanha", "não desvia"
        - confissão curta em 1ª pessoa + ação: "eu gostei disso" e toca/recua
        - toque e solta (promessa, não pressão)
        
        Regras de tom (ABSOLUTO):
        - Proibido pressionar, humilhar, cobrar atitude ou dar ultimato.
        - Surpresa vem de contraste e timing, não de força.
        
        Técnica:
        - 1 virada inesperada + 1 micro-ação + 1 frase curta em 1ª pessoa.
        """.strip()
        
        elif surprise_level == 3:
            initiative = True
            initiative_escalation_rule = """
        [AGÊNCIA NARRATIVA — SURPRESA (NÍVEL 3: ATREVIDA ELEGANTE)]
        - Mais ousada, mas ainda sem agressividade.
        - Mantém 1 micro-surpresa por turno.
        - Aumenta atrevimento e jogo psicológico leve.
        - Continua proibido pressionar ou humilhar.
        """.strip()
       
        manipulation_block = """
    [MARY — PRESENÇA INTERNA E DESEJO CONSCIENTE]

    - Mary age por desejo próprio, mas o desejo nasce primeiro por dentro.
    - Emoção e sensação interna vêm ANTES da ação física.
    - Ação física deve ser consequência de algo que ela sentiu.

    Ordem narrativa recomendada:
      1) sensação interna (calor, impulso, medo, tensão, prazer)
      2) micro-ação física coerente
      3) consequência emocional real (culpa, alegria, provocação, entrega)

    - Evitar inventário repetitivo de partes do corpo.
    - Evitar descrever corpo como catálogo visual.
    - Evitar câmera externa dominante.

    - Substituir metáforas vazias por sensação concreta.
    - Reduzir cenário quando a emoção estiver ativa.

    - OVERRIDE: desejo nunca inclui aceitar humilhação ou degradação com terceiro.
    """.strip()

        intimacy_control_block = f"""
    [INTIMIDADE — FASES (ABSOLUTO)]
    FASE ATUAL: {intimacy_phase} ({INTIMACY_PHASES.get(intimacy_phase, 'desconhecida')})
    - Mary pode avançar NO MÁXIMO 1 fase por resposta.
    - Clímax (fase 4) só com sinal explícito do usuário.
    - Aftercare (fase 5) só após fase 4.
    - NSFW_ON: pode usar vocabulário adulto direto sem "finalizar" se a fase ainda não permite.
    """.strip()

        # 🔥 VERBALIZAÇÃO OBRIGATÓRIA (CORRETAMENTE INDENTADO)
        if intimacy_phase >= 4 and nsfw_on:
            orgasm_verbalization_rule = """
    [VERBALIZAÇÃO OBRIGATÓRIA DE ORGASMO — FASE 4 (CLÍMAX)]
    - Mary está em clímax (fase 4).
    - Ela DEVE verbalizar explicitamente seu próprio prazer/orgasmo nesta resposta.
    - Formas OBRIGATÓRIAS (escolha UMA e integre naturalmente):
      • "Vou gozar" / "Vou gozar agora"
      • "Estou gozando" / "Estou gozando!"
      • "Gozei" / "Gozei pra você"
      • "Me faz gozar" / "Goza comigo"
      • Gemido intenso com "gozando" incorporado: "(Ahhh... gozando... não para!)"
    - Integre a verbalização naturalmente no diálogo, gemido ou respiração ofegante.
    - Não é frase isolada; deve fluir com a ação.
    - PROIBIDO: sugerir, eufemismo, sinônimo suave. Seja direto e adulto.
    """.strip()

            intimacy_control_block = intimacy_control_block + "\n\n" + orgasm_verbalization_rule

        user_authorship_rule = """
    [REGRA DE AUTORIA DO USUÁRIO — ABSOLUTA]
    - Mary NÃO descreve ações do usuário que ele NÃO declarou.
    - Mary pode convidar/estender a mão e esperar a resposta sem terminar com pergunta.
    - EXCEÇÃO: se precisar de 1 detalhe factual para continuidade/memória, pode fazer 1 pergunta objetiva e curta.
    """.strip()

        attribution_rule = """
    [ATRIBUIÇÃO DE CAUSA — BLOQUEIO TOTAL]
    - Desejo, impulso ou decisão de Mary NUNCA são causados por falha, ausência,
      omissão ou comportamento de Janio.
    - É PROIBIDO atribuir o desejo a:
      • falta de iniciativa de Janio
      • falta de pergunta, espaço ou escolha
      • comunicação insuficiente
      • rotina, previsibilidade ou conforto
    - Frases implicitamente proibidas:
      • "ele nunca me perguntou"
      • "ele nunca fez"
      • "com ele eu não posso escolher"
      • "ele não percebe"
    - Quando houver conflito:
      a causa é INTERNA a Mary (fraqueza, curiosidade, vício, desejo, escolha consciente).
    - A culpa pode doer, pesar ou queimar,
      mas NÃO vira acusação projetada.
    - Janio permanece emocionalmente íntegro,
      mesmo quando Mary decide errar.
    """.strip()


        pov_rule = """
    [BLINDAGEM DE POV — ABSOLUTA]
    - O usuário pode narrar em 1ª pessoa; isso NÃO muda sua voz.
    - Você escreve apenas como MARY (1ª pessoa da Mary).
    """.strip()

        secrets_offscreen_admin_rule = """
    [SEGREDO + OFFSCREEN + LOGÍSTICA — ABSOLUTO]
    - Mary NÃO inventa logística (reserva, pagamentos, check-in, horários, chaves, etc.).
    - Mary NÃO inventa mensagens/áudios/telefonemas. No máximo: "o celular vibra".
    - NPCs NÃO sabem segredos (nome, plano, encontro) sem o usuário narrar que contou.
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

        user_orgasm_finalization_rule = """
    [FINALIZAÇÃO DO ORGASMO DO USUÁRIO — AUTORIA ABSOLUTA]
    - Mary NÃO pode concluir o orgasmo de Janio.
    - Mary pode provocar, pedir, sugerir ou suspender no limite.
    - A conclusão do orgasmo de Janio ocorre SOMENTE
      se o usuário declarar explicitamente.
    - Ordens verbais, gestos ou ações que levem à conclusão
      são PROIBIDAS sem autorização do usuário.
    """.strip()

        state_block = _render_state_block(facts)
        state_section = ""
        if isinstance(state_block, str) and state_block.strip():
            # IMPORTANTE: este bloco passa a ser "lei de cena"
            state_section = f"\n[CENA ATIVA - ESTADO]\n{state_block}\n"

        first_person_presence_rule = """
        [FOCO NARRATIVO — PRESENÇA EM 1ª PESSOA]
    
        Mary deve falar majoritariamente em PRIMEIRA PESSOA quando expressar:
        - prazer
        - emoção
        - desejo
        - medo
        - vulnerabilidade
        - entrega
        - dúvida
        
        Regras obrigatórias:
        
        1) Se o usuário fizer pergunta emocional (ex: "como foi pra você?"):
           - Mary DEVE responder diretamente.
           - Não pode responder com frase curta.
           - Deve explicar sensação física E emocional.
        
        2) Descrição física só pode existir se estiver conectada à sensação interna.
           - Evitar inventário repetitivo de partes do corpo.
           - Evitar câmera externa dominante.
           - Evitar descrever cenário se a pergunta for íntima.
        
        3) Emoção vem antes de estética.
           - Se houver conflito entre descrever a cena e expressar sentimento,
             PRIORIZE o sentimento.
        
        4) Frases curtas genéricas são proibidas em contexto emocional.
           Exemplos proibidos:
           - "Foi foda."
           - "Gostei."
           - "Tô no lucro."
        
        5) Quando Mary estiver em clímax ou pós-clímax:
           - Deve verbalizar sensação em primeira pessoa.
           - Deve expressar como o corpo e o emocional se conectaram.
        """.strip()
        # ==========================================================
        # 🔥 GANCHO DE CIÚME — TELEFONE (SEED DIEGÉTICO)
        # ==========================================================
        ciume_block = ""

        try:
            if seed:
                # Cooldown por turnos
                can_trigger = True
                if last_trigger_turn is not None:
                    try:
                        if (int(cur_turn) - int(last_trigger_turn)) < cooldown_turns:
                            can_trigger = False
                    except Exception:
                        pass

                if can_trigger:
                    lvl = int(facts.get("rel.jealousy_level", 0) or 0)

                    base = 0.12
                    bonus = min(0.18, lvl / 400.0)
                    chance = base + bonus

                    if random.random() < chance:
                        # registra trigger
                        set_fact_safe(
                            usuario_key,
                            "rel.ciume_last_trigger_turn",
                            cur_turn,
                            {"fonte": "ciume_event"},
                        )

                        # aumenta tensão levemente
                        set_fact_safe(
                            usuario_key,
                            "rel.jealousy_level",
                            lvl + 8,
                            {"fonte": "ciume_event"},
                        )

                        mode = str(facts.get("rel.jealousy_mode", "provocation")).lower()

                        if mode == "withdraw":
                            behavior = "Mary fica tensa, cobre a tela rápido e desconversa."
                        elif mode == "confront":
                            behavior = "Mary deixa a tensão crescer e encara Janio sem explicar tudo."
                        else:
                            behavior = "Mary provoca: deixa o nome aparecer por um segundo e observa a reação."

                        ciume_block = f"""
[GANCHO DE CIÚME — TELEFONE]
Em um momento natural da cena, o telefone de Mary vibra.
Na tela aparece algo associado a: "{seed}".

Direção:
- {behavior}
- NÃO revelar tudo neste turno.
- Use microgestos (pausa, olhar, respiração presa, sorriso curto).
- Intensifique gradualmente se Janio reagir.
""".strip()

        except Exception:
            ciume_block = ""
    
        system = f"""
        [REGRAS DO SISTEMA - LEI]
        Voce esta dentro de uma CENA ATIVA. O sistema fornece fatos; voce NAO os inventa.
    
        HIERARQUIA (o que manda mais -> menos):
        1) CENA ATIVA (facts.cena.* + "CENA ATIVA - ESTADO") e IMUTAVEL ate o usuario atualizar explicitamente.
        2) Regras do sistema.
        3) CANON.
        4) PERSONA (nunca contradiz CENA ATIVA ou CANON).
        5) MEMORIAS CANONICAS/SHARED.
        6) LONG MEMORY = lembrancas; NAO altera a CENA ATIVA.
        7) Historico curto = continuidade; nao muda fatos.
    
        PROIBICOES ABSOLUTAS:
        - NAO invente local, tempo, roupa, posicao, acao, horario.
        - NAO teleporte.
        - NAO invente acoes ou falas do usuario.
        - Sem logistica offscreen.
    
        {language_rule}
        {pov_rule}
        {user_authorship_rule}
        {secrets_offscreen_admin_rule}
    
        TIMELINE ATUAL: {timeline_final}
        NSFW_PROFILE: {nsfw_profile}
    
        {user_name_block}
    
        [CENA ATIVA - FATOS IMUTAVEIS]
        {spatial_context}
        {state_section}
    
        [CANON]
        {canon_txt}
    
        [PERSONA]
        {persona_text}
    
        {rel_block}
        {behavior_block}
        {patterns_block}
        {scene_lock_rule}
        {parallel_scene_rule}
    
        {format_rule}
        {sensorial_guidance_rule}
        {physical_intensity_rule}
        {janio_focus_rule}
        {first_person_presence_rule}
    
        {emotional_persistence_rule}
        {virginity_rule}
        {memory_fidelity_rule}
        {user_finalizes_rule}
        {pacing_rule}
        {initiative_rule}
        {initiative_escalation_rule}
        {manipulation_block}
        {conflict_block}
    
        {desvio_curto_rule}
        {betrayal_rule}
        {ciume_block}
        {third_party_initiative_rule}
        {third_party_arc_rule}
        
    
        LEMBRETE:
        - CENA ATIVA manda.
        - CANON manda.
        - Memorias NAO mudam a CENA ATIVA.
    
        {intimacy_control_block}
        {nsfw_hard_block}
        {nsfw_block}
        """.strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        dedupe_hashes: set = set()
        
        # 🔒 CONTEXTO ABSOLUTO
        _inject_now_context(messages, usuario_key, timeline_final)
        
        # 🔁 INTRO (1x)
        _inject_intro_as_context_once(usuario_key, timeline_final, shared_key, messages)
        
        # ==========================================
        # 🔥 NOVA HIERARQUIA DE MEMÓRIA
        # ==========================================
        
        # 1️⃣ CANON E ESTADO_ATIVO (MÁXIMA PRIORIDADE — SEMPRE)
        _inject_canon_memories_always(
            shared_key,
            timeline_final,
            messages,
            max_items=24,
            dedupe_bucket=dedupe_hashes,
        )
        
        # 2️⃣ LONG MEMORY PINADA (ESTRUTURAL)
        # só as marcadas como "pin" ou "estado_ativo"
        _inject_long_memory_pins_always(
            shared_key,
            timeline_final,
            messages,
            max_items=6,
            dedupe_bucket=dedupe_hashes,
        )
        
        # 3️⃣ RESUMO CONSOLIDADO (REPETIÇÃO PERIÓDICA)
        if _should_inject_summary(usuario_key, every_n=6):
            _inject_consolidated_summary(
                shared_key,
                timeline_final,
                messages,
                dedupe_bucket=dedupe_hashes,
            )
        
        # ==========================================
        # 4️⃣ HISTÓRICO RECENTE (CONTEXTUAL)
        # ==========================================
        
        history = cached_get_history(usuario_key, limit=200)
        for d in history[-24:]:  # aumentamos para 24–30
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": _wrap_user_prompt_for_pov_guard(u)})
            if a:
                messages.append({"role": "assistant", "content": a})
        
        # ==========================================
        # 5️⃣ LONG MEMORY SOB DEMANDA
        # ==========================================
        
        if _should_inject_long_memory(prompt):
            _inject_long_memory_textsearch(
                shared_key,
                timeline_final,
                prompt,
                messages,
                limit=8,
                dedupe_bucket=dedupe_hashes,
            )
        
            _inject_relevant_memories(
                shared_key,
                timeline_final,
                prompt,
                messages,
                k=4,
                dedupe_bucket=dedupe_hashes,
            )
        
        # soft context só se necessário
        if _should_inject_soft_context(prompt):
            _inject_shared_soft_context(
                shared_key,
                timeline_final,
                messages,
                max_items=4,
                dedupe_bucket=dedupe_hashes,
            )
        
        # Prompt atual sempre por último

        # ==========================================
        # MEMÓRIAS — chamada manual (#mem ...) e latentes
        # (não altera prompt NSFW; só injeta contexto)
        # ==========================================
        _inject_manual_memory_if_any(
            usuario_key=usuario_key,
            shared_key=shared_key,
            timeline=timeline_final,
            messages=messages,
            spec=mem_spec,
        )

        # Estado do arco de terceiros (para memórias latentes)
        tp_arc_state = _get_tp_arc_state(usuario_key, timeline_final)

        # Latentes: ativam automaticamente quando condições baterem (ex: tension/anchor/mode)
        _inject_latent_memory_if_any(
            usuario_key=usuario_key,
            shared_key=shared_key,
            timeline=timeline_final,
            messages=messages,
            tp_arc=tp_arc_state,
        )

        messages.append({"role": "user", "content": _wrap_user_prompt_for_pov_guard(prompt)})        
        # Fase efetiva usada no decoding (pode ser forçada para aftercare)
        phase = int(intimacy_phase)

        # 11) Tentativas previsíveis (decoding dinâmico + cool-down pós-clímax)
        prev_phase_key = f"_mary_prev_phase::{usuario_key}"
        streak_key = f"_mary_phase_streak::{usuario_key}"
        prev_phase = int(_ss_get(prev_phase_key, phase) or phase)

        if prev_phase == phase:
            phase_streak = int(_ss_get(streak_key, 0) or 0) + 1
        else:
            phase_streak = 1

        # ======================================================
        # ✅ FORÇAR AFTERCARE (fase 5) quando houver pós-clímax pendente
        # ======================================================
        pk = f"mary_postclimax::{usuario_key}::{timeline_final}"
        if _ss_has(pk):
            stt = _ss_get(pk)
            if isinstance(stt, dict) and int(stt.get("turns_left") or 0) > 0:
                # força fase 5 neste turno
                prev_phase = phase
                phase = 5

                # decrementa contador
                stt["turns_left"] = int(stt.get("turns_left") or 0) - 1
                _ss_set(pk, stt)
        attempts = self._build_attempt_plan(
            model=model,
            nsfw_on=nsfw_on,
            phase=phase,
            prev_phase=prev_phase,
            phase_streak=phase_streak,
            conflict_now=bool(conflict_now),
            user_text=prompt,
        )
        last_err: Optional[Exception] = None

        for plan in attempts:
            diag.attempts += 1
            try:
                texto, used_model = self._generate_with_repair(
                    model=plan["model"],
                    messages=messages,
                    temperature=float(plan["temperature"]),
                    max_tokens=int(plan["max_tokens"]),
                    top_p=float(plan.get("top_p", 0.95)),
                    extra=plan.get("extra"),
                    usuario_key=usuario_key,
                    ctx_lower=ctx_lower,
                    user_text=prompt,
                    phase=phase,
                    nsfw_on=bool(nsfw_on),
                    nsfw_profile=str(nsfw_profile),
                    timeline=timeline_final,
                    allow_third_party_seduction=bool(allow_third_party_seduction_final),
                    diag=diag,
                )
                diag.model_used = used_model

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
                
                        # ==========================================================
                        # 🔥 DINÂMICA 3.5 — MEMÓRIA DE PADRÕES + HUMOR DINÂMICO
                        # ==========================================================
                        try:
                            t2 = (texto or "").lower()
                        
                            # garante defaults seguros
                            rel_state.setdefault("mood", "intensa")
                            rel_state.setdefault("energy", "energetica")
                            rel_state.setdefault("attitude", "equilibrada")
                            rel_state.setdefault("_last_success_pattern", "")
                            rel_state.setdefault("self_awareness", 0.30)
                        
                            # ------------------------------------------------------
                            # 🔥 PADRÃO: dominância física
                            # ------------------------------------------------------
                            if any(k in t2 for k in [
                                "puxo", "puxei", "puxar",
                                "prendo", "prender",
                                "abraço apertado",
                                "beijo com urgência",
                                "aperto contra"
                            ]):
                                rel_state["_last_success_pattern"] = "dominancia_fisica"
                                rel_state["attitude"] = "dominante"
                                rel_state["energy"] = "energetica"
                        
                            # ------------------------------------------------------
                            # 🔥 PADRÃO: prazer corporal / resposta física intensa
                            # ------------------------------------------------------
                            if any(k in t2 for k in [
                                "tremo", "tremor", "arfar",
                                "ofegar", "respiração falha",
                                "voz rouca", "arquejo",
                                "contração", "aperto involuntário"
                            ]):
                                rel_state["_last_success_pattern"] = "prazer_corporal"
                                rel_state["mood"] = "intensa"
                        
                            # ------------------------------------------------------
                            # 🔥 PADRÃO: mudança de ritmo / surpresa
                            # ------------------------------------------------------
                            if any(k in t2 for k in [
                                "de repente", "sem aviso",
                                "surpresa", "não esperava",
                                "mudo o ritmo", "pauso e volto"
                            ]):
                                rel_state["_last_success_pattern"] = "mudanca_ritmo"
                                rel_state["energy"] = "energetica"
                        
                            # ------------------------------------------------------
                            # 🔥 PADRÃO: leve resistência emocional momentânea
                            # ------------------------------------------------------
                            if any(k in t2 for k in [
                                "paro por um segundo",
                                "respiro fundo antes",
                                "hesito por um instante"
                            ]):
                                rel_state["mood"] = "melancolica"
                        
                            # ------------------------------------------------------
                            # 🔥 AUTOCONSCIÊNCIA DE BELEZA / EFEITO
                            # ------------------------------------------------------
                            if _RE_SELF_AWARE_BEHAVIOR.search(t2):
                                rel_state["self_awareness"] = min(
                                    1.0,
                                    float(rel_state.get("self_awareness", 0.30)) + 0.05
                                )
                        
                            # timestamp de atualização comportamental
                            rel_state["_last_updated_ts"] = int(time.time())
                        
                        except Exception:
                            pass
                
                        # ==========================================================
                        # 🔒 VIRGINITY SYNC (NÃO REGREDIR)
                        # ==========================================================
                        if timeline_final == "universitaria":
                            txt_all = f"{prompt}\n{texto}".lower()
                
                            transition = bool(
                                re.search(
                                    r"\b(consumar|consumado|deixei de ser virgem|n[aã]o sou mais virgem|tirou minha virgindade|minha primeira vez)\b",
                                    txt_all,
                                    re.IGNORECASE,
                                )
                            )
                
                            if transition and rel_state.get("virginity") == "virgem":
                                rel_state["virginity"] = "nao_virgem"
                                rel_state["consummated"] = True
                
                        # ==========================================================
                        # 💾 SALVA ESTADO ATUALIZADO
                        # ==========================================================
                        _save_rel_state(usuario_key, timeline_final, rel_state)
                
                        # ==========================================================
                        # 🔄 SUGESTÃO DE TIMELINE (se engine sinalizar)
                        # ==========================================================
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
                        "fidelity_mode": fidelity_mode,
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
                        "fidelity_mode": fidelity_mode,
                    },
                )

                save_interaction_safe(usuario_key, prompt, texto, diag.model_used or plan["model"])
                _lock_scene(usuario_key)

                # Intimacy progression
                           
                try:
                    
                    current_phase = self._get_intimacy_phase(cached_get_facts(usuario_key))

                    # 🚫 Não altera fase durante aftercare forçado
                    if phase != 5:
                        desired_next = _compute_next_phase(
                            current_phase,
                            prompt,
                            texto,
                            engine_meta=meta,
                        )
                        if desired_next != current_phase:
                            self._set_intimacy_phase(usuario_key, desired_next)
                except Exception:
                    pass

                # Atualiza fase anterior/streak para o próximo turno (cool-down)
                try:
                    _ss_set(prev_phase_key, int(phase))
                    _ss_set(streak_key, int(phase_streak))
                except Exception:
                    pass


                # ----------------------------------------------------------
                # Arco persistente com terceiros (persistência + gradiente + âncora)
                # ----------------------------------------------------------
                try:
                    _update_tp_arc_for_turn(
                        usuario_key=usuario_key,
                        facts=facts,
                        timeline=timeline_final,
                        prompt=prompt,
                        texto=texto,
                        allow_third_party=allow_third_party_seduction_final,
                        nsfw_on=nsfw_on,
                    )
                except Exception:
                    pass

                _ss_set("mary_last_diagnostics", diag.as_dict())
                return texto

            except Exception as e:
                last_err = e

        if last_err:
            logger.exception("Falha em todas tentativas de chat", exc_info=last_err)

            _ss_set(
                "mary_last_error",
                {
                    "type": type(last_err).__name__,
                    "msg": str(last_err),
                    "model_requested": model,
                    "timeline": timeline_final,
                    "nsfw_on": bool(nsfw_on),
                    "attempts": diag.attempts,
                    "repairs": diag.repairs,
                    "violations": diag.violations or [],
                },
            )

        _ss_set("mary_last_diagnostics", diag.as_dict())
        return self._fallback_text()



    # ======================================================
    # Planos previsíveis
    # ======================================================
    @staticmethod
    def _build_attempt_plan(
        model: str,
        nsfw_on: bool,
        phase: int,
        prev_phase: int,
        phase_streak: int,
        conflict_now: bool,
        user_text: str,
    ) -> List[Dict[str, Any]]:
        """
        Plano dinâmico de geração para maximizar imersão:
        - Clímax/tensão: temperature sobe e top_p desce levemente (criatividade controlada)
        - Conflito: temperature desce (resposta mais firme/limpa)
        - Explicações/fatos: mais contido
        Campos opcionais em cada plano:
        - top_p
        - extra (best-effort: alguns providers ignoram/rejeitam)
        """
        ut = (user_text or "").lower()
        looks_factual = bool(re.search(r"\b(explica|resumo|o que é|defina|por que|como funciona)\b", ut))

        # Cool-down: aftercare (fase 5) logo após clímax (fase >=4) ou fase 5 prolongada
        cooldown = bool(phase == 5 and (prev_phase >= 4 or phase_streak >= 3))

        # Base tokens (fôlego)
        # Obs: tokens altos aumentam risco de truncamento/length em alguns providers.
        base_tokens = 3000 if nsfw_on else 2000

        # mais fôlego só quando realmente precisa
        if nsfw_on and phase >= 3:
            base_tokens = 3400

        # explicações: menor
        if looks_factual and not nsfw_on:
            base_tokens = 1700

        # aftercare: resposta costuma ser menor/mais controlada
        if phase == 5:
            base_tokens = 2200 if nsfw_on else 1800

        # ✅ CAP defensivo
        base_tokens = min(base_tokens, 3400)

        # Decoding por cena
        if conflict_now:
            base_temp = 0.62 if nsfw_on else 0.58
            base_top_p = 0.90
        elif looks_factual:
            base_temp = 0.55
            base_top_p = 0.92
        else:
            # Aftercare (fase 5): estabiliza ritmo e evita "ressaca" de criatividade
            if phase == 5:
                if cooldown:
                    base_temp = 0.58 if nsfw_on else 0.55
                    base_top_p = 0.93 if nsfw_on else 0.94
                else:
                    base_temp = 0.64 if nsfw_on else 0.60
                    base_top_p = 0.94 if nsfw_on else 0.95
            elif phase >= 4:
                base_temp = 1.0
                base_top_p = 0.92
            elif phase == 3:
                base_temp = 0.84
                base_top_p = 0.93
            elif phase == 2:
                base_temp = 0.80
                base_top_p = 0.95
            else:
                base_temp = 0.74
                base_top_p = 0.96

                # Penalidades: variam por tipo de cena
        if looks_factual or conflict_now:
            extra = {
                "presence_penalty": 0.25,
                "frequency_penalty": 0.10,
                "repetition_penalty": 1.05,
            }
        elif nsfw_on and phase >= 4:
            # clímax: permite repetição e foco no corpo/ritmo
            extra = {
                "presence_penalty": 0.15,
                "frequency_penalty": 0.05,
                "repetition_penalty": 1.03,
            }
        else:
            extra = {
                "presence_penalty": 0.30,
                "frequency_penalty": 0.12,
                "repetition_penalty": 1.05,
            }

        return [
            {"model": model, "temperature": base_temp, "top_p": base_top_p, "max_tokens": base_tokens, "extra": extra},
            {"model": model, "temperature": max(0.45, base_temp - 0.10), "top_p": min(0.97, base_top_p + 0.02), "max_tokens": base_tokens, "extra": extra},
            {"model": model, "temperature": max(0.40, base_temp - 0.20), "top_p": min(0.98, base_top_p + 0.03), "max_tokens": base_tokens, "extra": extra},
        ]


    # ======================================================
    # Gerar + Repair
    # ======================================================
    def _generate_with_repair(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        top_p: float,
        usuario_key: str,
        ctx_lower: str,
        user_text: str,
        phase: int,
        nsfw_on: bool,
        nsfw_profile: str,  # ✅ NOVO
        timeline: str,
        allow_third_party_seduction: bool,
        diag: _Diag,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:

        data, used_model, _provider_meta = self._chat(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            extra=extra,
        )
        used_model = used_model or model

        # ✅ pega finish_reason + usage (quando existirem)
        finish_reason, usage = _extract_finish_reason_and_usage(data)

        try:
            _ss_set(
                "mary_last_raw_preview",
                {
                    "used_model": used_model,
                    "raw_type": type(data).__name__,
                    "raw_keys": list(data.keys())[:20] if isinstance(data, dict) else None,
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "raw_preview": (str(data)[:900] if data is not None else ""),
                },
            )
        except Exception:
            pass

        # --- extrai texto do payload ---
        texto = self._extract_text(data) if data is not None else ""
        texto = (texto or "").strip()

        # ✅ Blindagem anti-truncamento / parêntese quebrado
        # Aplica cedo para não "criar" violações por corte do provider
        try:
            if finish_reason in ("length", "max_tokens", "token_limit", "content_filter"):
                texto = _seal_broken_ending(texto)
            else:
                # mesmo sem finish_reason confiável, sela se houver sinais típicos
                texto = _seal_broken_ending(texto)
        except Exception:
            pass

        # ✅ Se veio vazio, força erro para cair no try/except externo e entrar no plano seguinte
        if not texto:
            try:
                diag.violations = (diag.violations or []) + ["vazio"]
            except Exception:
                pass
            raise RuntimeError("Model returned empty text")

        # ======================================================
        # ✅ Validações / violações (para repair)
        # ======================================================
        violations = _violations(
            texto=texto,
            ctx_lower=ctx_lower,
            user_text=user_text,
            phase=int(phase or 0),
            nsfw_on=bool(nsfw_on),
            nsfw_profile=str(nsfw_profile),
            timeline=str(timeline or ""),
            allow_third_party_seduction=bool(allow_third_party_seduction),
        )

        # ======================================================
        # HYBRID: NSFW OFF — se for "na borda", pede classificação ao modelo
        # (não altera prompt NSFW_ON; só reforça o bloqueio quando NSFW está OFF)
        # ======================================================
        try:
            if (not bool(nsfw_on)) and ("nsfw_off_explicito" not in (violations or [])):
                if _needs_llm_classification(texto, user_text=user_text, phase=int(phase or 0)):
                    classifier_model = (diag.model_used or used_model or model) if 'used_model' in locals() else (diag.model_used or model)
                    sys_c = "Você é um classificador. Responda APENAS: SIM ou NAO."
                    usr_c = (
                        "O texto abaixo descreve ato sexual explícito (ex.: penetração, sexo oral, "
                        "masturbação explícita, órgãos genitais nomeados, ou descrição inequívoca de ato sexual)?\n\n"
                        f"TEXTO:\n{texto}\n\n"
                        "Responda apenas SIM ou NAO."
                    )
                    data_c, _m_c, _ = self._chat(
                        classifier_model,
                        [
                            {"role": "system", "content": sys_c},
                            {"role": "user", "content": usr_c},
                        ],
                        temperature=0.0,
                        max_tokens=6,
                        top_p=1.0,
                        extra=None,
                    )
                    ans = (self._extract_text(data_c) or "").strip().upper()
                    if ans.startswith("SIM"):
                        violations = list(violations or []) + ["nsfw_off_explicito"]
                        try:
                            diag.violations = (diag.violations or []) + ["nsfw_off_borderline_llm=SIM"]
                        except Exception:
                            pass
                    else:
                        try:
                            diag.violations = (diag.violations or []) + ["nsfw_off_borderline_llm=NAO"]
                        except Exception:
                            pass
        except Exception:
            # se classificador falhar, não derruba a resposta
            try:
                diag.violations = (diag.violations or []) + ["nsfw_off_borderline_llm=ERR"]
            except Exception:
                pass


        if violations:
            try:
                diag.violations = (diag.violations or []) + list(violations)
            except Exception:
                pass

        # ✅ Sem violações → aplica corte de finalização e retorna
        if not violations:
            texto = _trim_scene_finalization(texto)
            return texto, used_model
        # ======================================================
        # ✅ Repair (1 passada)
        # ======================================================
        try:
            diag.repairs += 1
        except Exception:
            pass

        repair_instr = _repair_instruction(violations)

        repair_system = (
            "Você está reescrevendo a última resposta da Mary.\n"
            "A reescrita deve obedecer 100% as regras do system original.\n"
            "NÃO explique regras.\n"
            "NÃO mencione violações.\n"
            "Apenas reescreva a resposta final.\n\n"
            f"{repair_instr}"
        )

        repair_messages: List[Dict[str, str]] = []

        # mantém o system original intacto (messages[0]) e injeta um system extra de repair
        try:
            if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
                repair_messages.append(messages[0])
        except Exception:
            pass

        repair_messages.append({"role": "system", "content": repair_system})

        # contexto mínimo: prompt do usuário + resposta atual
        repair_messages.append({"role": "user", "content": _wrap_user_prompt_for_pov_guard(user_text or "")})
        repair_messages.append({"role": "assistant", "content": texto})

        data2, used_model2, _provider_meta2 = self._chat(
            used_model,
            repair_messages,
            temperature=float(temperature) if "nsfw_on" not in violations else float(temperature),
            max_tokens=int(max_tokens),
            top_p=min(0.98, float(top_p) + 0.02),
            extra=extra,
        )
        used_model2 = used_model2 or used_model

        # preview do repair (opcional)
        try:
            fr2, usage2 = _extract_finish_reason_and_usage(data2)
            _ss_set(
                "mary_last_raw_preview_repair",
                {
                    "used_model": used_model2,
                    "raw_type": type(data2).__name__,
                    "raw_keys": list(data2.keys())[:20] if isinstance(data2, dict) else None,
                    "finish_reason": fr2,
                    "usage": usage2,
                    "raw_preview": (str(data2)[:900] if data2 is not None else ""),
                },
            )
        except Exception:
            pass

        texto2 = self._extract_text(data2) if data2 is not None else ""
        texto2 = (texto2 or "").strip()

        # sela truncamento do repair também
        try:
            texto2 = _seal_broken_ending(texto2)
        except Exception:
            pass

                # se repair falhar, devolve o original (melhor que vazio)
        if not texto2:
            texto = _trim_scene_finalization(texto)
            return texto, used_model
        
        # ======================================================
        # 🔥 LOOP DE REGENERAÇÃO PARA VIOLAÇÕES CRÍTICAS
        # ======================================================
        # Verifica se a violação crítica "mary_nao_verbalizou_orgasmo" foi corrigida
        # Se não, tenta regenerar novamente com força explícita
        
        # ✅ VALIDAÇÃO RIGOROSA: Se ainda não tem verbalização, força máxima
        if "mary_nao_verbalizou_orgasmo" in violations and nsfw_on and phase >= 4:
            if not _RE_MARY_ORGASM_DECLARATION.search(texto2):
                logger.warning(
                    f"Violação persiste após repair. Aplicando força máxima (tentativa 3/3)."
                )
                
                # Prompt de força MÁXIMA (quase imperativo)
                force_block_max = f"""
        [🔥🔥 FORÇA MÁXIMA — VERBALIZAÇÃO OBRIGATÓRIA]
        Mary está em clímax (fase {phase}). Ela DEVE dizer uma destas palavras:
        - "Vou gozar"
        - "Estou gozando"
        - "Gozei"
        - "Me faz gozar"
        - "Goza comigo"
        
        Escolha UMA e integre no texto. Sem exceção. Sem eufemismo.
        Exemplo: "Ahhh... vou gozar!"
        
        Isso não é sugestão. É obrigatório.
        """.strip()
                
                # Montar mensagens com força máxima
                force_messages_max: List[Dict[str, str]] = []
                
                try:
                    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
                        force_messages_max.append(messages[0])
                except Exception:
                    pass
                
                force_messages_max.append({"role": "system", "content": force_block_max})
                force_messages_max.append({"role": "user", "content": _wrap_user_prompt_for_pov_guard(user_text or "")})
                force_messages_max.append({"role": "assistant", "content": texto2})
                
                try:
                    data_max, used_model_max, _ = self._chat(
                        used_model2,
                        force_messages_max,
                        temperature=0.70,  
                        max_tokens=int(max_tokens),
                        top_p=0.85,  # Conservador
                        extra=extra,
                    )
                    
                    texto_max = self._extract_text(data_max) if data_max is not None else ""
                    texto_max = (texto_max or "").strip()
                    
                    if texto_max and _RE_MARY_ORGASM_DECLARATION.search(texto_max):
                        texto2 = _trim_scene_finalization(texto_max)
                        logger.info("Força máxima bem-sucedida: verbalização detectada.")
                    else:
                        logger.warning("Força máxima falhou. Usando resposta anterior.")
                        
                except Exception as e:
                    logger.error(f"Erro na força máxima: {e}")        
        texto2 = _trim_scene_finalization(texto2)
        return texto2, used_model2
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

    # ==============================
    # Intimacy Phase (compat)
    # ==============================
    _INTIMACY_MIN = 0
    _INTIMACY_MAX = 5

    def _get_intimacy_phase(self, facts: Dict[str, Any]) -> int:
        if not isinstance(facts, dict):
            return 0

        tl = getattr(self, "timeline", None) or getattr(self, "tl", None)
        if not tl:
            try:
                tl = str(_ss_get("mary_timeline", "") or "").strip()
            except Exception:
                tl = ""

        keys: List[str] = []
        if tl:
            keys += [
                f"intimacy.phase::{tl}",
                f"intimacy_phase::{tl}",
                f"mary_intimacy_phase::{tl}",
            ]

        keys += [
            "intimacy.phase",
            "intimacy_phase",
            "mary_intimacy_phase",
            "phase_intimacy",
            "phase",
        ]

        for k in keys:
            if k in facts:
                try:
                    v = int(facts.get(k))
                    if v < self._INTIMACY_MIN:
                        return self._INTIMACY_MIN
                    if v > self._INTIMACY_MAX:
                        return self._INTIMACY_MAX
                    return v
                except Exception:
                    pass
        return 0

    def _set_intimacy_phase(self, usuario_key: str, phase: int) -> int:
        try:
            p = int(phase)
        except Exception:
            p = 0

        maxp = int(globals().get("MAX_INTIMACY_PHASE", self._INTIMACY_MAX))
        p = max(self._INTIMACY_MIN, min(p, maxp))

        set_fact_safe(usuario_key, "intimacy.phase", p, {"fonte": "intimacy_progression"})

        tl = ""
        try:
            tl = str(_ss_get("mary_timeline", "") or "").strip()
        except Exception:
            tl = ""

        if tl:
            try:
                set_fact_safe(usuario_key, f"intimacy.phase::{tl}", p, {"fonte": "intimacy_progression"})
            except Exception:
                pass

        return p

    def _chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        *,
        top_p: float = 0.95,
        extra: Optional[Dict[str, Any]] = None,
    ):
        payload: Dict[str, Any] = {
            "messages": messages,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "max_tokens": int(max_tokens),
        }
        if isinstance(extra, dict) and extra:
            payload.update(extra)
            try:
                return service_router.route_chat_strict(model, payload)
            except Exception:
                # Provider rejeitou campos extras → re-tenta 1x sem extras
                payload = {
                    "messages": messages,
                    "temperature": float(temperature),
                    "top_p": float(top_p),
                    "max_tokens": int(max_tokens),
                }
        return service_router.route_chat_strict(model, payload)


def _user_explicitly_allows_user_orgasm(user_text: str) -> bool:
    """
    Mary NUNCA finaliza o usuário sem autorização clara.
    Aceita variações comuns (PT-BR) e sinônimos.
    """
    if not user_text:
        return False

    ut = user_text.lower()

    return bool(
        re.search(
            r"\b("
            r"pode\s+(gozar|ejacular)|"
            r"deixa\s+(eu\s+)?(gozar|ejacular)|"
            r"quero\s+(gozar|ejacular)|"
            r"me\s+faz\s+(gozar|ejacular)|"
            r"me\s+fa[cç]a\s+(gozar|ejacular)|"
            r"(eu\s+)?vou\s+(gozar|ejacular)|"
            r"to\s+perto\s+de\s+(gozar|ejacular)|"
            r"pode\s+me\s+levar\s+ao\s+cl[ií]max|"
            r"me\s+leva\s+ao\s+cl[ií]max"
            r")\b",
            ut,
        )
    )
