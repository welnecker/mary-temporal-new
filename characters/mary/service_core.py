# characters/mary/service_core.py-service_core_PATCHED_v10c.py
from __future__ import annotations

"""
MaryService (v5.1e - Imersão Sensorial + Correções Críticas + Decoding dinâmico + RAG chunking)

Ajustes aplicados aqui (estritamente necessários):
- FIX: _inject_canon_memories_always() injetava o bloco repetidamente dentro do loop (bug de duplicação).
- FIX: Detecção de "autoria do usuário" (_RE_USER_ACTION) reescrita para evitar falsos positivos sem lookbehind variável.
- FIX: _Diag ganhou campo scene_transition (evita attr dinâmica).

Nota de compliance:
- Mantive NSFW_ON como "adulto/intenso".
"""

import re
import random
import datetime
import uuid
import logging
import hashlib
import time
import unicodedata

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional, Set, Callable
@dataclass
class TurnPromptContext:
    timeline_final: str
    nsfw_profile: str
    user_name_block: str
    spatial_context: str

    state_section: str
    assunto_section: str
    assunto_step_section: str
    estado_micro_section: str
    pending_event_section: str

    canon_txt: str
    persona_text: str
    rel_block: str
    dynamic_rel_block: str
    long_memory_block: str
    tp_arc: dict

    behavior_block: str
    patterns_block: str
    topic_rule: str
    emotional_persistence_rule: str
    anti_pattern_rule: str
    virginity_rule: str
    memory_fidelity_rule: str
    user_finalizes_rule: str
    initiative_rule: str
    manipulation_block: str
    conflict_block: str
    third_party_initiative_rule: str
    intimacy_control_block: str
    intimacy_phase_rule: str
    nsfw_hard_block: str
    nsfw_block: str

    language_rule: str
    pov_rule: str
    user_authorship_rule: str
    continuity_rule: str
    phone_message_rule: str
    decision_pressure_rule: str
    mary_identity_anchor: str
    reasoning_scene_guidance_block: str

    usuario_key: str
    shared_key: str
    prompt: str
    mem_spec: Any
    facts: dict
    rel_state: dict
    autonomy_block: str

    system: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class TurnState:
    usuario_key: str
    prompt: str
    timeline_final: str
    facts: dict
    rel_state: dict
    tp_arc: dict
    history: list
    nsfw_on: bool
    behavior_mode: str


@dataclass
class TurnAssets:
    persona_text: str = ""
    mary_identity_anchor: str = ""
    long_memory_block: str = ""
    rel_block: str = ""
    dynamic_rel_block: str = ""
    canon_txt: str = ""

    # 🔥 REGRAS FUNDACIONAIS (ex-legacy)
    rule_language: str = ""
    rule_pov: str = ""
    rule_user_authorship: str = ""
    rule_priority: str = ""
    rule_facts_present: str = ""

    # Blocos ainda herdados, agora organizados como assets
    virginity_rule: str = ""
    intimacy_phase_rule: str = ""
    intimacy_control_block: str = ""

    topic_rule: str = ""
    anti_pattern_rule: str = ""
    user_finalizes_rule: str = ""

    initiative_rule: str = ""
    emotional_persistence_rule: str = ""

    nsfw_hard_block: str = ""
    nsfw_block: str = ""

    phone_message_rule: str = ""
    decision_pressure_rule: str = ""
    autonomy_block: str = ""
    behavior_block: str = ""

    spatial_context: str = ""
    state_section: str = ""
    assunto_section: str = ""
    assunto_step_section: str = ""
    estado_micro_section: str = ""
    pending_event_section: str = ""

    patterns_block: str = ""
    manipulation_block: str = ""
    conflict_block: str = ""
    third_party_initiative_rule: str = ""
    reasoning_scene_guidance_block: str = ""

    continuity_hard_rule: str = ""
    response_structure_rule: str = ""
    reaction_priority_rule: str = ""
    response_length_control: str = ""
    orgasm_closure_rule: str = ""
    tp_arc_block: str = ""
    tp_arc_behavior_rule: str = ""
    mary_presence_engine_rule: str = ""
    


@dataclass
class PromptBuildContext:
    state: TurnState
    assets: TurnAssets

    # Ponte temporária para não quebrar as rules atuais
    legacy: "TurnPromptContext"

    # Extras continuam compartilhados
    extra: dict[str, Any] = field(default_factory=dict)

def make_prompt_build_context(ctx: TurnPromptContext) -> PromptBuildContext:
    raw_history = getattr(ctx, "history", [])
    raw_facts = getattr(ctx, "facts", {})
    raw_rel_state = getattr(ctx, "rel_state", {})
    raw_tp_arc = getattr(ctx, "tp_arc", {})
    raw_extra = getattr(ctx, "extra", {})

    facts = raw_facts if isinstance(raw_facts, dict) else {}
    mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}

    state = TurnState(
        usuario_key=str(getattr(ctx, "usuario_key", "") or ""),
        prompt=str(getattr(ctx, "prompt", "") or getattr(ctx, "user_input", "") or ""),
        timeline_final=str(getattr(ctx, "timeline_final", "") or ""),
        facts=facts,
        rel_state=raw_rel_state if isinstance(raw_rel_state, dict) else {},
        tp_arc=raw_tp_arc if isinstance(raw_tp_arc, dict) else {},
        history=raw_history if isinstance(raw_history, list) else [],
        nsfw_on=bool(mary.get("nsfw")),
        behavior_mode=str(facts.get("behavior_mode") or ""),
    )
    try:
        active_interlocutor = sync_active_interlocutor_for_turn(
            state.usuario_key,
            state.facts,
            state.history,
            state.prompt,
        )
        if active_interlocutor:
            state.facts["active_interlocutor"] = active_interlocutor
            state.facts["cena.interlocutor"] = active_interlocutor
    except Exception:
        pass 

    assets = TurnAssets(           
        persona_text=str(getattr(ctx, "persona_text", "") or ""),
        mary_identity_anchor=str(getattr(ctx, "mary_identity_anchor", "") or ""),
        long_memory_block=str(getattr(ctx, "long_memory_block", "") or ""),
        rel_block=str(getattr(ctx, "rel_block", "") or ""),
        dynamic_rel_block=str(getattr(ctx, "dynamic_rel_block", "") or ""),
        canon_txt=str(getattr(ctx, "canon_txt", "") or ""),
    
        # Mantidos
        virginity_rule=str(getattr(ctx, "virginity_rule", "") or ""),
        intimacy_phase_rule=str(getattr(ctx, "intimacy_phase_rule", "") or ""),
        intimacy_control_block=str(getattr(ctx, "intimacy_control_block", "") or ""),
    
        topic_rule=str(getattr(ctx, "topic_rule", "") or ""),
        anti_pattern_rule=str(getattr(ctx, "anti_pattern_rule", "") or ""),
        user_finalizes_rule=str(getattr(ctx, "user_finalizes_rule", "") or ""),
        emotional_persistence_rule=str(getattr(ctx, "emotional_persistence_rule", "") or ""),
    
        # Neutralizados
        initiative_rule="",
        manipulation_block="",
        conflict_block="",
        third_party_initiative_rule="",
        nsfw_hard_block="",
    
        # Mantidos
        nsfw_block=str(getattr(ctx, "nsfw_block", "") or ""),
        phone_message_rule=str(getattr(ctx, "phone_message_rule", "") or ""),
        decision_pressure_rule=str(getattr(ctx, "decision_pressure_rule", "") or ""),
        autonomy_block=str(getattr(ctx, "autonomy_block", "") or ""),
        behavior_block=str(getattr(ctx, "behavior_block", "") or ""),
    )
    
    assets.spatial_context = str(getattr(ctx, "spatial_context", "") or "")
    assets.state_section = str(getattr(ctx, "state_section", "") or "")
    assets.assunto_section = str(getattr(ctx, "assunto_section", "") or "")
    assets.assunto_step_section = str(getattr(ctx, "assunto_step_section", "") or "")
    assets.estado_micro_section = str(getattr(ctx, "estado_micro_section", "") or "")
    assets.pending_event_section = str(getattr(ctx, "pending_event_section", "") or "")
    
    assets.rule_language = str(getattr(ctx, "language_rule", "") or "")
    assets.rule_pov = str(getattr(ctx, "pov_rule", "") or "")
    assets.rule_user_authorship = str(getattr(ctx, "user_authorship_rule", "") or "")
    assets.rule_priority = str((raw_extra.get("priority_rule") if isinstance(raw_extra, dict) else "") or "")
    assets.rule_facts_present = ""
    
    assets.patterns_block = ""
    assets.manipulation_block = ""
    assets.conflict_block = ""
    assets.third_party_initiative_rule = ""
    
    assets.reasoning_scene_guidance_block = str(getattr(ctx, "reasoning_scene_guidance_block", "") or "")
    
    assets.continuity_hard_rule = str((raw_extra.get("continuity_hard_rule") if isinstance(raw_extra, dict) else "") or "")
    assets.response_structure_rule = str((raw_extra.get("response_structure_rule") if isinstance(raw_extra, dict) else "") or "")
    assets.reaction_priority_rule = str((raw_extra.get("reaction_priority_rule") if isinstance(raw_extra, dict) else "") or "")
    assets.response_length_control = str((raw_extra.get("response_length_control") if isinstance(raw_extra, dict) else "") or "")
    
    assets.orgasm_closure_rule = str((raw_extra.get("orgasm_closure_rule") if isinstance(raw_extra, dict) else "") or "")
    assets.tp_arc_block = str((raw_extra.get("tp_arc_block") if isinstance(raw_extra, dict) else "") or "")
    assets.tp_arc_behavior_rule = str((raw_extra.get("tp_arc_behavior_rule") if isinstance(raw_extra, dict) else "") or "")
    assets.mary_presence_engine_rule = str((raw_extra.get("mary_presence_engine_rule") if isinstance(raw_extra, dict) else "") or "")
    
    return PromptBuildContext(
        state=state,
        assets=assets,
        legacy=ctx,
        extra={}
    )

@dataclass
class PromptFragment:
    key: str
    content: str
    priority: int = 100
    enabled: bool = True


PromptRule = Callable[[PromptBuildContext], Optional[PromptFragment]]

def _frag(
    key: str,
    content: str,
    priority: int = 100,
    enabled: bool = True,
) -> Optional[PromptFragment]:
    content = str(content or "").strip()

    if not content or not enabled:
        return None

    return PromptFragment(
        key=key,
        content=content,
        priority=priority,
        enabled=enabled,
    )


from .reasoning_engine import build_internal_reasoning
from core.reasoning_llm import build_llm_reasoning, merge_reasoning

_RE_SELF_AWARE_BEHAVIOR = re.compile(
    r"\b(eu sei que faço|eu percebo que|eu sei o efeito que|eu sei que mexo com você)\b",
    re.IGNORECASE,
)

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
from .hook_engine import (
    collect_narrative_opportunities,
    select_active_hook,
    ensure_hook_state,
    build_autonomy_block,
    advance_hook_state_after_response,
)
from .relationship_dynamic import (
    load_dynamic_relationship_state,
    render_dynamic_relationship_block,
    analyze_relationship_shift,
    apply_relationship_shift,
    save_dynamic_relationship_state,
)

from .decision_engine import (
    _load_decision_state,
    _save_decision_state,
    _resolve_decision_pressure_mode,
    _render_decision_pressure_rule,
)

from characters.mary.modules.prompt_blocks import (
    # ======================================================
    # 1. Regras absolutas / identidade
    # ======================================================
    render_priority_rule,
    render_language_rule,
    render_pov_rule,
    render_user_authorship_rule,
    render_user_finalizes_rule,
    
    # ======================================================
    # 2. Realidade e continuidade (chão da cena)
    # ======================================================
    render_continuity_hard_rule,
    render_continuity_rule,
    render_inferred_scene_block,
    render_topic_rule,
    render_memory_fidelity_rule,
    
    # ======================================================
    # 3. AÇÃO PRIMEIRO (MUDANÇA CRÍTICA)
    # ======================================================
    render_initiative_rule,
    render_manipulation_block,
    
    # 👉 INSIRA AQUI O NOVO BLOCO
    render_anti_sensory_narration_block,
    
    render_patterns_block,
    
    # ======================================================
    # 4. Estrutura (AGORA vem depois da ação)
    # ======================================================
    render_response_structure_rule,
    render_response_length_control,
    render_reaction_priority_rule,
    render_anti_loop_recent_turns_block,
    render_anti_pattern_rule,
    
    # ======================================================
    # 5. Presença e comportamento
    # ======================================================
    render_mary_presence_engine_rule,
    render_autonomy_rule,
    render_emotional_persistence_rule,
    render_behavior_rule,
    render_behavior_mode_block,
    render_behavior_block,
    render_timeline_behavior_block,
    
    # ======================================================
    # 6. Conflito e terceiros
    # ======================================================
    render_conflict_block,
    render_tp_arc_block,
    render_tp_arc_behavior_rule,
    
    # ======================================================
    # 7. NSFW / resolução
    # ======================================================
    render_nsfw_hard_block,
    render_force_resolution_nsfw_block,
    render_orgasm_closure_rule,
)

logger = logging.getLogger(__name__)
logger.warning("🔥 SERVICE_CORE CERTO CARREGADO")
# ==========================================================
# DEBUG HELPERS (telemetria segura)
# ==========================================================
def _debug_enabled() -> bool:
    try:
        return bool(_ss_get("mary_debug_on", False))
    except Exception:
        return False


def _debug_set(key: str, value: Any) -> None:
    try:
        _ss_set(key, value)
    except Exception:
        pass


def _debug_append(label: str, payload: Any) -> None:
    try:
        if not _debug_enabled():
            return
        logs = _ss_get("mary_debug_log", [])
        if not isinstance(logs, list):
            logs = []
        logs.append({
            "ts": time.time(),
            "label": str(label),
            "payload": payload,
        })
        _ss_set("mary_debug_log", logs[-80:])
    except Exception:
        pass


def _debug_capture_error(exc: Exception) -> None:
    try:
        import traceback as _tb
        _debug_set("mary_last_error", {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": _tb.format_exc(),
        })
    except Exception:
        pass

# ==========================================================
# TERMOS CONFIGURÁVEIS / DOMÍNIO NARRATIVO
# ==========================================================

# ----------------------------------------------------------
# STOPWORDS
# ----------------------------------------------------------
# Mantidas enxutas para não matar sinal narrativo útil.
# Incluem formais e coloquiais mais comuns do português.
DEFAULT_STOPWORDS_PT = {
    "a","o","os","as","um","uma","uns","umas",
    "de","do","da","dos","das",
    "em","no","na","nos","nas",
    "por","para","pra",
    "com","sem",
    "que","e","ou","mas","se","como","quando","onde","porque","pq",
    "eu","tu","ele","ela","nós","nos","gente","você","voce","vc",
    "meu","minha","meus","minhas","teu","tua","teus","tuas","seu","sua","seus","suas",
    "isso","esse","essa","isto","aquilo",
    "aqui","ali","lá",
    "agora","hoje","ontem","amanhã",
    "mesmo","assim","tipo",
    "tá","ta","tô","to","tb","também","tambem",
    "sabe"
}

# ----------------------------------------------------------
# NÚCLEO IDENTITÁRIO
# ----------------------------------------------------------
# Termos centrais da personagem e do vínculo principal.
DOMAIN_IDENTITY_TERMS = {
    "mary",
    "janio",
    "casal",
    "marido",
    "esposa",
    "relacao",
    "relação",
    "casamento"
}

# ----------------------------------------------------------
# AMBIENTAÇÃO / ESPAÇOS RECORRENTES
# ----------------------------------------------------------
# Lugares cotidianos e cenários que ajudam a ancorar a cena.
DOMAIN_ENVIRONMENT_TERMS = {
    "casa",
    "apartamento",
    "cozinha",
    "banheiro",
    "quarto",
    "sala",
    "sofá",
    "sofa",
    "cama",
    "espelho",
    "janela",
    "rua",
    "carro",
    "academia",
    "orla",
    "quiosque",
    "praia",
    "hotel"
}

# ----------------------------------------------------------
# ROTINA / VIDA HUMANA
# ----------------------------------------------------------
# Ações e elementos do cotidiano que reforçam naturalidade.
DOMAIN_ROUTINE_TERMS = {
    "rotina",
    "descanso",
    "descansar",
    "dormir",
    "acordar",
    "banho",
    "café",
    "cafe",
    "almoço",
    "almoco",
    "jantar",
    "comer",
    "beber",
    "trabalho",
    "carreira",
    "profissão",
    "profissao",
    "curso",
    "faculdade"
}

# ----------------------------------------------------------
# OBJETOS / ELEMENTOS DE PRESENÇA CÊNICA
# ----------------------------------------------------------
# Itens comuns que ajudam a materializar o momento presente.
DOMAIN_SCENE_OBJECT_TERMS = {
    "roupa",
    "roupão",
    "roupao",
    "toalha",
    "celular",
    "bolsa",
    "perfume",
    "sapato",
    "lençol",
    "lencol"
}

# ----------------------------------------------------------
# EMOÇÕES / ESTADOS INTERNOS
# ----------------------------------------------------------
# Sentimentos e tensões subjetivas.
DOMAIN_EMOTIONAL_TERMS = {
    "amor",
    "afeto",
    "ternura",
    "saudade",
    "vontade",
    "desejo",
    "carência",
    "carencia",
    "medo",
    "culpa",
    "ciúme",
    "ciume",
    "insegurança",
    "inseguranca",
    "vergonha",
    "ansiedade",
    "tensão",
    "tensao",
    "abandono"
}

# ----------------------------------------------------------
# MARCOS LATENTES / DRAMÁTICOS
# ----------------------------------------------------------
# Não são exatamente emoções, mas forças narrativas persistentes.
DOMAIN_LATENT_TERMS = {
    "segredo",
    "promessa",
    "pendência",
    "pendencia",
    "dúvida",
    "duvida",
    "suspeita",
    "lembrança",
    "lembranca",
    "memória",
    "memoria"
}

# ----------------------------------------------------------
# EVENTOS / MARCOS NARRATIVOS
# ----------------------------------------------------------
# Separados por intensidade para evitar colapsar tudo em sexualidade.
DOMAIN_EVENT_TERMS_LIGHT = {
    "beijo",
    "toque",
    "abraço",
    "abraco",
    "convite",
    "encontro",
    "aproximação",
    "aproximacao"
}

DOMAIN_EVENT_TERMS_INTIMATE = {
    "sexo",
    "transa",
    "relação",
    "relacao",
    "consumação",
    "consumacao",
    "intimidade"
}

DOMAIN_EVENT_TERMS_EXPLICIT = {
    "orgasmo",
    "gozar",
    "clímax",
    "climax",
    "aftercare"
}

# União opcional para usos genéricos
DOMAIN_EVENT_TERMS = (
    DOMAIN_EVENT_TERMS_LIGHT
    | DOMAIN_EVENT_TERMS_INTIMATE
    | DOMAIN_EVENT_TERMS_EXPLICIT
)

# ----------------------------------------------------------
# TERMOS DE PRIORIDADE GERAL DO UNIVERSO NARRATIVO
# ----------------------------------------------------------
# Usado quando você quiser um conjunto único para scoring amplo.
DOMAIN_PRIORITY_TERMS = (
    DOMAIN_IDENTITY_TERMS
    | DOMAIN_ENVIRONMENT_TERMS
    | DOMAIN_ROUTINE_TERMS
    | DOMAIN_SCENE_OBJECT_TERMS
    | DOMAIN_EMOTIONAL_TERMS
    | DOMAIN_LATENT_TERMS
    | {
        "primeira vez",
        "virgem",
        "virgindade"
    }
)

# ----------------------------------------------------------
# TERMOS DE SOBREPOSIÇÃO TEMÁTICA
# ----------------------------------------------------------
# Mais enxutos. Servem para detectar repetição relevante
# entre memória, contexto ativo e turno atual.
DOMAIN_OVERLAP_TERMS = {
    "mary",
    "janio",
    "casamento",
    "relacao",
    "relação",
    "segredo",
    "promessa",
    "culpa",
    "medo",
    "ciúme",
    "ciume",
    "primeira vez",
    "virgem",
    "virgindade",
    "beijo",
    "encontro",
    "traição",
    "traicao",
    "academia",
    "orla",
    "quarto",
    "casa"
}

# ----------------------------------------------------------
# TEMAS GOVERNADOS POR FACTS
# ----------------------------------------------------------
# Estes temas não devem ser decididos livremente pelo modelo
# quando houver facts vivos ou estado já estabelecido.
FACT_GOVERNED_TERMS = {
    "virgindade": {
        "virgem",
        "virgindade",
        "primeira vez"
    },

    "consumacao": {
        "consumado",
        "consumada",
        "consummated",
        "sexo",
        "transa",
        "relação",
        "relacao",
        "consumação",
        "consumacao"
    },

    "fase_intima": {
        "fase",
        "intimidade",
        "clímax",
        "climax",
        "orgasmo",
        "gozar",
        "aftercare"
    },

    "arco_relacional": {
        "ciúme",
        "ciume",
        "culpa",
        "medo",
        "tensão",
        "tensao",
        "traição",
        "traicao"
    },

    "arco_terceiro": {
        "third party",
        "terceiro",
        "anchor",
        "tension",
        "guilt"
    },

    "estado_cena": {
        "local",
        "tempo",
        "horário",
        "horario",
        "ação",
        "acao",
        "cena"
    }
}

def _ss_get_set(key: str, default: set[str]) -> set[str]:
    try:
        val = _ss_get(key, None)

        if isinstance(val, (list, set, tuple)):
            return {str(x).strip().lower() for x in val if str(x).strip()}

        # aceita string tipo "a,b,c"
        if isinstance(val, str):
            parts = re.split(r"[,\n;]", val)
            parsed = {p.strip().lower() for p in parts if p.strip()}
            if parsed:
                return parsed

    except Exception:
        pass

    return {str(x).strip().lower() for x in default if str(x).strip()}
    
def _domain_terms(name: str) -> set[str]:
    mapping = {
        "stopwords": DEFAULT_STOPWORDS_PT,
        "priority": DOMAIN_PRIORITY_TERMS,
        "emotional": DOMAIN_EMOTIONAL_TERMS,
        "event": DOMAIN_EVENT_TERMS,
        "overlap": DOMAIN_OVERLAP_TERMS,
    }
    return _ss_get_set(f"{_SS_PREFIX}terms::{name}", mapping.get(name, set()))


def _fact_terms(group: str) -> set[str]:
    base = FACT_GOVERNED_TERMS.get(group, set())
    return _ss_get_set(f"{_SS_PREFIX}terms::fact::{group}", base)


def _normalize_term(term: str) -> str:
    t = _t_norm(term or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _term_pattern(term: str) -> str:
    t = _normalize_term(term)
    if not t:
        return ""
    parts = [re.escape(p) for p in t.split(" ")]
    sep = r'\s+'.join(parts)
    return rf"(?<!\w){sep}(?!\w)"


def _contains_any_term(text: str, terms: set[str]) -> bool:
    txt = _normalize_term(text)
    if not txt or not terms:
        return False

    for term in terms:
        pat = _term_pattern(term)
        if not pat:
            continue
        if re.search(pat, txt):
            return True

    return False


def _count_matching_terms(text: str, terms: set[str]) -> int:
    txt = _normalize_term(text)
    if not txt or not terms:
        return 0

    count = 0
    for term in terms:
        pat = _term_pattern(term)
        if not pat:
            continue
        if re.search(pat, txt):
            count += 1

    return count
# ==========================================================
# HIDDEN-THOUGHT STRIPPER (initiative CoT scaffolding)
# ==========================================================
# O modelo pode emitir um bloco curto de raciocínio interno em <think>...</think>.
# Esse bloco NUNCA deve chegar ao usuário final: usamos apenas como "andaime" para coerência.
_RE_THINK_BLOCK = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)

def _strip_internal_thought(texto: str) -> str:
    """
    Remove blocos internos <think>...</think> sem matar a resposta inteira.
    Se após a limpeza sobrar vazio, preserva o original limpo.
    """
    if not texto:
        return ""

    original = str(texto).strip()

    try:
        if _debug_enabled():
            _debug_set("mary_last_extracted_text_preview", original[:2000])
    except Exception:
        pass

    cleaned = _RE_THINK_BLOCK.sub("", original).strip()

    if not cleaned:
        return original

    return cleaned


# ==========================================================
# NORMALIZAÇÃO SIMPLES DE RESPOSTA
# ==========================================================
def _normalize_model_response(texto: str) -> str:
    """
    Simplifica a resposta do modelo sem interferir na narrativa.
    Remove apenas ruído técnico.
    """

    if not texto:
        return ""

    t = str(texto).strip()

    # remove think blocks
    t = _strip_internal_thought(t)

    # remove espaços duplicados
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+", " ", t)

    t = t.strip()

    try:
        if _debug_enabled():
            _debug_set("mary_last_clean_text_preview", t[:2000])
    except Exception:
        pass

    return t

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
# DEBUG ERROR CAPTURE
# ==========================================================
def _debug_capture_error(exc: Exception) -> None:
    try:
        import traceback as _tb
        _ss_set("mary_last_error", {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": _tb.format_exc(),
        })
    except Exception:
        pass


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

def _get_intimacy_phase(facts: Dict[str, Any], timeline: str) -> int:
    tl = _normalize_timeline(timeline)

    candidates = [
        facts.get(f"intimacy.phase::{tl}"),
        facts.get("intimacy.phase"),
        facts.get("fase_intima"),
        facts.get(f"fase_intima::{tl}"),
    ]

    for v in candidates:
        try:
            p = int(v)
            if p < 0:
                return 0
            if p > MAX_INTIMACY_PHASE:
                return MAX_INTIMACY_PHASE
            return p
        except Exception:
            continue

    return 0


def _set_intimacy_phase(usuario_key: str, timeline: str, phase: int) -> int:
    tl = _normalize_timeline(timeline)

    try:
        p = int(phase)
    except Exception:
        p = 0

    if p < 0:
        p = 0
    if p > MAX_INTIMACY_PHASE:
        p = MAX_INTIMACY_PHASE

    set_fact_safe(usuario_key, f"intimacy.phase::{tl}", p, {"fonte": "intimacy_phase"})
    set_fact_safe(usuario_key, "intimacy.phase", p, {"fonte": "intimacy_phase_sync"})
    set_fact_safe(usuario_key, "fase_intima", INTIMACY_PHASES.get(p, "tensao"), {"fonte": "intimacy_phase_label"})

    return p


def _detect_intimacy_shift(user_text: str, current_phase: int) -> int:
    """
    Retorna:
    -1 = reduzir
     0 = manter
    +1 = subir
    """
    t = _t_norm(user_text or "")
    if not t:
        return 0

    deescalate_terms = {
        "para", "pare", "pausa", "calma", "devagar", "mais devagar",
        "afasta", "afastar", "recuar", "recua", "solta", "soltar",
        "não", "nao", "espera"
    }

    escalate_contact = {
        "segura", "puxa", "encosta", "aproxima", "abraça", "abraca", "beija",
        "toca", "segurando", "pressiona", "cola", "aperta"
    }

    escalate_stronger = {
        "deita", "deitou", "sobe em cima", "encaixa", "pressiona mais",
        "aperta mais", "sem espaço", "mais forte", "continua", "não para", "nao para"
    }

    climax_like = {
        "climax", "clímax", "orgasmo", "goza", "gozar", "gozando", "aftercare"
    }

    if any(term in t for term in deescalate_terms):
        return -1

    if current_phase <= 1 and any(term in t for term in escalate_contact):
        return 1

    if current_phase in (2, 3) and any(term in t for term in escalate_stronger):
        return 1

    if current_phase == 3 and any(term in t for term in climax_like):
        return 1

    return 0


def _advance_intimacy_phase_from_user(
    usuario_key: str,
    timeline: str,
    user_text: str,
    facts: Dict[str, Any],
) -> int:
    current = _get_intimacy_phase(facts or {}, timeline)
    shift = _detect_intimacy_shift(user_text, current)

    new_phase = current + shift

    if new_phase < 0:
        new_phase = 0
    if new_phase > MAX_INTIMACY_PHASE:
        new_phase = MAX_INTIMACY_PHASE

    return _set_intimacy_phase(usuario_key, timeline, new_phase)


def _render_intimacy_phase_rule(phase: int) -> str:
    try:
        phase = int(phase)
    except Exception:
        phase = 0

    phase = max(0, min(phase, 5))

    # ----------------------------------------------------------
    # FASE 0–1 → tensão e início
    # NÃO BLOQUEIA ação, só regula ritmo
    # ----------------------------------------------------------
    if phase <= 1:
        return """       
        [RITMO DO TURNO - BAIXA INTENSIDADE]
        
        - A fase atual pede progressão leve, sem salto brusco.
        - Priorizar:
          - fala com subtexto
          - olhar
          - gesto pequeno
          - aproximação discreta
          - mudança sutil de ritmo
        
        REGRAS:
        - Não acelerar para contato intenso.
        - Não transformar tensão em bloqueio.
        - Não repetir hesitação vazia.
        
        OBJETIVO:
        → construir tensão com movimento leve e coerente.
        """.strip()

    # ----------------------------------------------------------
    # FASE 2 → progressão ativa
    # ----------------------------------------------------------
    if phase == 2:
        return """
[RITMO DO TURNO - PROGRESSÃO]

- Mary conduz a evolução da cena.
- Pode intensificar contato e presença.

REGRAS:
- Cada resposta deve avançar a cena.
- Variar entre:
  - provocar
  - aproximar
  - intensificar
- Não repetir o mesmo padrão de resposta.

OBJETIVO:
→ progressão clara, sem saltos bruscos.
""".strip()

    # ----------------------------------------------------------
    # FASE 3 → intensidade alta
    # ----------------------------------------------------------
    if phase == 3:
        return """
[RITMO DO TURNO - ALTA INTENSIDADE]

- Mary tem controle do ritmo.
- Pode avançar ou segurar conscientemente.

REGRAS:
- Evitar resolver a cena rápido demais.
- Alternar entre avanço e controle.
- Priorizar ação sobre explicação.

OBJETIVO:
→ manter intensidade sem perder tensão.
""".strip()

    # ----------------------------------------------------------
    # FASE 4 → pico (sem explosão caótica)
    # ----------------------------------------------------------
    if phase == 4:
        return """
[RITMO DO TURNO - PICO]

- A cena está no ponto mais intenso.
- Mary decide como conduzir esse momento.

REGRAS:
- Não prolongar indefinidamente.
- Não repetir preparação.
- Não resolver de forma abrupta.

OBJETIVO:
→ culminação natural e coerente.
""".strip()

    # ----------------------------------------------------------
    # FASE 5 → desaceleração
    # ----------------------------------------------------------
    return """
[RITMO DO TURNO - DESACELERAÇÃO]

- A intensidade diminui naturalmente.
- Foco em consequência e estado emocional.

REGRAS:
- Não reiniciar a cena.
- Não reaquecer imediatamente.

OBJETIVO:
→ fechamento coerente do momento.
""".strip()

# ==========================================================
#  USER / KEYS
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

def _shared_key(user_id: str, timeline: str) -> str:
    tl = _normalize_timeline(timeline)
    return f"{user_id}::mary::{tl}::shared"

def _current_user_key() -> str:
    uid = _current_user_id_fallback()
    tl_raw = _ss_get(f"{_SS_PREFIX}timeline") or _ss_get("mary_timeline") or "cumplice"
    tl = _normalize_timeline(tl_raw if isinstance(tl_raw, str) else "cumplice")
    return _user_key(uid, tl)

def _shared_memory_key() -> str:
    uid = _current_user_id_fallback()
    tl_raw = _ss_get(f"{_SS_PREFIX}timeline") or _ss_get("mary_timeline") or "cumplice"
    tl = _normalize_timeline(tl_raw if isinstance(tl_raw, str) else "cumplice")
    return _shared_key(uid, tl)

def _long_key(user_id: str) -> str:
    #  Long memory global legado (mantém suas memórias atuais no Mongo)
    return f"{user_id}::mary::shared"

# ==========================================================
# NSFW TOGGLE (fonte de verdade é core.nsfw)
# ==========================================================
SAFE_SENSUAL_STYLE = """
[NSFW_OFF]

- Manter proximidade física leve (olhar, gesto, aproximação).
- Sustentar tensão sem esfriar a cena.
- Fala sempre acompanhada de ação ou reação.

REGRA:
→ presença contínua, sem explicitar.
""".strip()

NSFW_TOGGLE_STYLE = """
[NSFW_ON - PROGRESSÃO]

- A cena evolui com continuidade e coerência.
- Cada resposta gera avanço perceptível.

FOCO:
- proximidade
- ritmo
- contato
- intensidade

REGRAS:
- evitar repetição de ação
- evitar reiniciar tensão
- evitar descrição mecânica
- não acelerar abruptamente

- respeitar:
  - emoção atual
  - vínculo
  - facts
  - continuidade

REGRA CENTRAL:
→ a ação conduz a cena.
""".strip()

_CACHE_TTL_SECONDS = 300

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
def _sanitize_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(facts, dict):
        return {}

    f = dict(facts)

    # remove QUALQUER intro em qualquer nível
    def _deep_clean(obj):
        if isinstance(obj, dict):
            obj.pop("intro", None)
            for v in obj.values():
                _deep_clean(v)
        elif isinstance(obj, list):
            for v in obj:
                _deep_clean(v)

    _deep_clean(f)

    return f


def cached_get_facts(usuario_key: str) -> Dict[str, Any]:
    ck = f"{_SS_PREFIX}facts::{usuario_key}"

    cached = _cache_get(ck)
    if isinstance(cached, dict):
        return _sanitize_facts(cached)

    f = get_facts(usuario_key) or {}
    f = _sanitize_facts(f)

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
#  padrão mais leve para o prompt (ajuste fino aqui)
_MEM_PROMPT_LIMIT_DEFAULT = 140

def cached_list_memories(
    shared_key: str,
    limit: int = _MEM_PROMPT_LIMIT_DEFAULT,
) -> List[Dict[str, Any]]:
    """
    Compatível com chamadas antigas: retorna a 1a página (offset=0).
    """
    return cached_list_memories_page(shared_key, offset=0, limit=limit)

def cached_list_memories_page(
    shared_key: str,
    *,
    offset: int = 0,
    limit: int = _MEM_PROMPT_LIMIT_DEFAULT,
) -> List[Dict[str, Any]]:
    """
     Lazy loading: permite paginação e evita carregar 200/360 sempre.
    - offset: quantos itens pular (0 = mais recentes, se sua list_memories já vier em ordem)
    - limit: quantos itens trazer nesta "página"
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
    tl_raw = _ss_get(f"{_SS_PREFIX}timeline") or _ss_get("mary_timeline") or "cumplice"
    tl = _normalize_timeline(tl_raw if isinstance(tl_raw, str) else "cumplice")

    # limpa memória shared por timeline
    clear_mem_cache_for_shared(_shared_key(user_id, tl))

    # limpa também long memory global legado
    clear_mem_cache_for_shared(_long_key(user_id))
    
def clear_all_session_caches_for_user(user_id: str, timeline: str) -> None:
    # limpa facts/history do usuário+timeline
    usuario_key = _user_key(_normalize_user_id(user_id), _normalize_timeline(timeline))
    clear_user_cache(usuario_key)

    # limpa mem cache shared (agora por timeline)
    clear_mem_cache_for_shared(_shared_key(_normalize_user_id(user_id), _normalize_timeline(timeline)))

    # limpa flags de injeção de estilo (para reinjetar corretamente)
    for k in _ss_keys():
        if k.startswith(f"{_SS_PREFIX}nsfw_style_injected::"):
            _ss_del(k)

   
# ==========================================================
# WRAPPERS DE ESCRITA (invalida cache automaticamente)
# ==========================================================
def set_fact_safe(usuario_key: str, key: str, value: Any, meta: Optional[dict] = None) -> None:
    try:
        logs = st.session_state.get("debug_logs", [])

        if key == "mary" and isinstance(value, dict):
            if "intro" in value:
                logs.append(f"🔥 ANTES (com intro): {value}")

            value = dict(value)
            value.pop("intro", None)

            logs.append(f"🧹 DEPOIS (sem intro): {value}")

        logs.append(f"💾 set_fact_safe → key={key} meta={meta}")

        st.session_state["debug_logs"] = logs[-50:]  # mantém últimos 50

        set_fact(usuario_key, key, value, meta or {})
        clear_user_cache(usuario_key)

    except Exception as e:
        st.session_state["debug_logs"].append(f"❌ ERRO: {e}")

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
        tl_raw = _ss_get(f"{_SS_PREFIX}timeline") or _ss_get("mary_timeline") or "cumplice"
        tl = _normalize_timeline(tl_raw if isinstance(tl_raw, str) else "cumplice")
        clear_user_cache(_user_key(user_id, tl))

def append_long_memory_safe(
    shared_key: str,
    text: str,
    meta: Optional[dict] = None,
    *,
    user_id: Optional[str] = None,
) -> None:
    """
    Wrapper segura para gravar na Long Memory (Mongo).
    Padroniza metadados e respeita a key recebida.
    """
    uid = _normalize_user_id(user_id) if user_id else _current_user_id_fallback()

    txt = str(text or "").strip()
    if not txt:
        return

    meta_in = dict(meta or {})

    title = str(meta_in.get("title") or "").strip()
    kind = str(meta_in.get("kind") or "memory").strip().lower() or "memory"

    timeline_raw = str(
        meta_in.get("timeline_at_save")
        or meta_in.get("timeline")
        or (_ss_get(f"{_SS_PREFIX}timeline") or _ss_get("mary_timeline") or "cumplice")
    ).strip() or "cumplice"

    tags_user = _normalize_memory_tags(meta_in.get("tags"))
    tags_auto = _infer_memory_tags(txt, title=title)
    tags_final = _normalize_memory_tags(tags_user + tags_auto)

    meta_final = dict(meta_in)
    meta_final["title"] = title
    meta_final["kind"] = kind
    meta_final["timeline_at_save"] = timeline_raw
    meta_final["user_id"] = uid
    meta_final["tags"] = tags_final

    if "source" not in meta_final:
        meta_final["source"] = "ui_long_memory"

    # respeita a key recebida; se vier vazia, usa fallback global
    target_key = str(shared_key or "").strip() or _long_key(uid)

    append_long_memory(target_key, txt, meta=meta_final)


def save_interaction_safe(usuario_key: str, prompt: str, texto: str, model_used: str) -> None:
    try:
        save_interaction(usuario_key, prompt, texto, model_used)
    finally:
        try:
            clear_user_cache(usuario_key)
        except Exception:
            pass


# ==========================================================
# NSFW ENABLE (usa implementação unificada do core)
# ==========================================================
def nsfw_enabled(
    usuario_key: str,
    *,
    nsfw_override: Optional[bool] = None,
    timeline: Optional[str] = None,
) -> bool:
    """
    Fonte única (ordem de prioridade):
    1. override explícito
    2. session_state (sidebar)
    3. facts -> mary.nsfw::<timeline>
    4. facts -> mary.nsfw
    5. default por timeline
    """

    tl = (timeline or "").strip().lower()

    # 1) override
    if nsfw_override is not None:
        return bool(nsfw_override)

    # 2) session_state
    try:
        ss = st.session_state  # type: ignore[attr-defined]
        for k in (
            "mary_nsfw_on",
            "nsfw_on",
            f"{_SS_PREFIX}nsfw_on",
            f"{_SS_PREFIX}nsfw",
            "mary::nsfw_on",
        ):
            if k in ss:
                return bool(ss.get(k, False))
    except Exception:
        pass

    # 3 e 4) facts
    try:
        facts = cached_get_facts(usuario_key) or {}
        if not isinstance(facts, dict):
            facts = {}

        mary_obj = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
        if not isinstance(mary_obj, dict):
            mary_obj = {}

        # timeline específico
        if tl:
            key_tl = f"nsfw::{tl}"
            if key_tl in mary_obj:
                return bool(mary_obj.get(key_tl))

            # compat legado
            v_tl = facts.get(f"mary.nsfw::{tl}")
            if v_tl is not None:
                return bool(v_tl)

        # global
        if "nsfw" in mary_obj:
            return bool(mary_obj.get("nsfw"))

        v_global = facts.get("mary.nsfw")
        if v_global is not None:
            return bool(v_global)

    except Exception:
        pass

    # 5) default
    return False if tl == "universitaria" else True

def sync_active_interlocutor_for_turn(
    usuario_key: str,
    facts: dict,
    history: list,
    prompt: str,
) -> str:
    facts = facts if isinstance(facts, dict) else {}
    history = history if isinstance(history, list) else []

    cena = facts.get("cena") if isinstance(facts.get("cena"), dict) else {}
    state = facts.get("state") if isinstance(facts.get("state"), dict) else {}

    current = (
        facts.get("active_interlocutor")
        or facts.get("interlocutor_ativo")
        or facts.get("cena.interlocutor")
        or facts.get("state.interlocutor")
        or cena.get("interlocutor")
        or cena.get("interlocutor_ativo")
        or state.get("interlocutor")
        or state.get("interlocutor_ativo")
        or ""
    )
    current = str(current or "").strip()

    def canonicalize_name(name: str) -> str:
        n = str(name or "").strip()
        aliases = {
            "janio": "Janio",
            "jânio": "Janio",
            "janio donisete": "Janio Donisete",
            "anthony": "Anthony",
            "silvia": "Silvia",
            "sílvia": "Silvia",
        }
        return aliases.get(n.lower(), n)

    def extract_name_candidates(text: str) -> list[str]:
        text = str(text or "").strip()
        if not text:
            return []
    
        candidates = re.findall(
            r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,}(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]{2,})?\b",
            text,
        )
    
        IGNORE = {
            # verbos comuns no início de fala
            "Olha", "Deixa", "Quero", "Sinto", "Levo", "É", "Vou",
            "Quero", "Preciso", "Deixa", "Vem", "Para", "Agora",
    
            # palavras comuns da narrativa
            "Carro", "Jeep", "Renegade", "Forró", "Noite", "Sexta",
    
            # personagem fixo (não pode virar interlocutor)
            "Mary",
        }
    
        return [c for c in candidates if c not in IGNORE]

    known_names = {
        "anthony": "Anthony",
        "janio donisete": "Janio Donisete",
        "janio": "Janio",
        "jânio": "Janio",
        "silvia": "Silvia",
        "sílvia": "Silvia",
    }

    prompt_text = str(prompt or "")
    prompt_blob = prompt_text.lower()

    detected = ""

    # 1. Detecção forte por nomes conhecidos no prompt atual
    for raw_name, canonical_name in known_names.items():
        if raw_name in prompt_blob:
            detected = canonical_name
            break    

    # 2. Detecção dinâmica por nomes próprios no prompt atual
    if not detected:
        candidates = extract_name_candidates(prompt_text)
        if candidates:
            detected = candidates[-1]

    # 3. Fallback fraco: histórico só se ainda não houver interlocutor atual
    if not detected and not current and history:
        last = history[-1] if isinstance(history[-1], dict) else {}
        weak_text = " ".join([
            str(last.get("mensagem_usuario") or ""),
            str(last.get("resposta_mary") or ""),
        ])
        weak_blob = weak_text.lower()

        for raw_name, canonical_name in known_names.items():
            if raw_name in weak_blob:
                detected = canonical_name
                break

        if not detected:
            candidates = extract_name_candidates(weak_text)
            if candidates:
                detected = candidates[-1]

    final = detected or current

    if not final:
        return ""

    if current and final != current:
        try:
            set_fact_safe(
                usuario_key,
                "previous_interlocutor",
                current,
                {"fonte": "sync_active_interlocutor"}
            )
            set_fact_safe(
                usuario_key,
                "cena.previous_interlocutor",
                current,
                {"fonte": "sync_active_interlocutor"}
            )
        except Exception:
            pass

    try:
        set_fact_safe(
            usuario_key,
            "active_interlocutor",
            final,
            {"fonte": "sync_active_interlocutor"}
        )
        set_fact_safe(
            usuario_key,
            "cena.interlocutor",
            final,
            {"fonte": "sync_active_interlocutor"}
        )
    except Exception:
        pass

    return final
       
   
def _get_nsfw_style_block(
    usuario_key: str,
    *,
    timeline: Optional[str] = None,
    nsfw_override: Optional[bool] = None,
) -> str:
    """
    Estilo narrativo NSFW/SAFE.
    Define COMO Mary age, não SE ela pode agir.

    Ordem de prioridade:
    1. Estado de pico (orgasm.active)
    2. Fase íntima
    3. SAFE fallback
    """

    enabled = nsfw_enabled(
        usuario_key,
        nsfw_override=nsfw_override,
        timeline=timeline,
    )

    if not enabled:
        return SAFE_SENSUAL_STYLE

    try:
        facts = get_facts(usuario_key) or {}
        tl = (timeline or "").strip().lower()

        # =========================
        # 🔥 DETECÇÃO DE ORGASM (PRIORIDADE MÁXIMA)
        # =========================
        orgasm_active = bool(
            facts.get("orgasm", {})
            .get("mary", {})
            .get(f"active::{tl}", False)
        )

        if orgasm_active:
            return """
[NSFW_ON - RESOLUÇÃO DE PICO]

- Mary já atingiu pico de intensidade.

- NÃO:
  - prolongar estímulo
  - repetir pré-clímax
  - manter tensão crescente

- DEVE:
  - responder com consequência imediata
  - quebrar controle momentaneamente
  - reduzir o ritmo após o pico

- Após:
  - respiração
  - tremor
  - pausa
  - fala fragmentada

REGRA:
→ pico não evolui, pico resolve.
""".strip()

        # =========================
        # 🔍 COLETA ROBUSTA DA FASE
        # =========================
        candidates = []

        if tl:
            candidates.extend([
                facts.get(f"intimacy.phase::{tl}"),
                facts.get(f"intimacy_phase::{tl}"),
                facts.get(f"mary_intimacy_phase::{tl}"),
            ])

            intimacy_obj = facts.get("intimacy") if isinstance(facts.get("intimacy"), dict) else {}
            candidates.append(intimacy_obj.get(f"phase::{tl}"))

        candidates.extend([
            facts.get("intimacy.phase"),
            facts.get("intimacy_phase"),
            facts.get("mary_intimacy_phase"),
            facts.get("phase_intimacy"),
            facts.get("phase"),
        ])

        # pega o MAIOR valor válido (corrige bug anterior)
        valid_phases = []
        for v in candidates:
            try:
                if v is None or v == "":
                    continue
                valid_phases.append(int(v))
            except Exception:
                pass

        intimacy_phase = max(valid_phases) if valid_phases else 0

        # clamp defensivo
        if intimacy_phase < 0:
            intimacy_phase = 0
        if intimacy_phase > 5:
            intimacy_phase = 5

    except Exception:
        intimacy_phase = 0

    # =========================
    # 🎯 ESTILO POR FASE
    # =========================

    if intimacy_phase >= 5:
        return """
[NSFW_ON - DESACELERAÇÃO ATIVA]

- A cena já atingiu alta intensidade.
- O corpo e a emoção reagem ao que aconteceu.

FOCO:
- respiração
- sensibilidade
- proximidade
- consequência emocional

REGRAS:
- não reiniciar progressão
- não criar nova tensão artificial
- não esfriar a cena

REGRA:
→ desacelerar NÃO é parar.
""".strip()

    if intimacy_phase < 2:
        return """
[NSFW_ON - TENSÃO]

- Foco em:
  - proximidade
  - olhar
  - fala
  - subtexto

- Evitar:
  - progressão física direta

Resumo:
→ tensão conduz antes do avanço físico.
""".strip()

    return """
[NSFW_ON - PROGRESSÃO ATIVA]

- Mary permanece em movimento.
- Fala acompanha gesto e mudança de ritmo.

REGRAS:
- cada turno avança a cena
- evitar repetição
- evitar reiniciar tensão
- não acelerar abruptamente

REGRA:
→ ação conduz a cena.
""".strip()

def enforce_third_party_consistency(usuario_key: str, *, timeline: str, nsfw_on: bool) -> None:
    """
    Se NSFW OFF, terceiros NÃO pode ficar True persistido.
    """
    facts = cached_get_facts(usuario_key) or {}
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
    - 1. override explícito
    - 2. session_state (sidebar) - aceita chaves antigas e novas com _SS_PREFIX
    - 3. facts persistido -> mary.allow_third_party_seduction
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
    facts = cached_get_facts(usuario_key) or {}
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
    STRICT        -> NSFW on, focado no vínculo principal
    NSFW_RELAXED  -> NSFW on + terceiros liberado
    """
    if nsfw_on and allow_third_party_seduction:
        return "NSFW_RELAXED"
    if nsfw_on:
        return "STRICT"
    return "SAFE"

# ==========================================================
# CELULAR / MENSAGEM EM CENA
# ==========================================================
def _render_phone_message_rule(prompt: str, facts: Dict[str, Any]) -> str:
    p = _t_norm(prompt or "")

    phone_terms = (
        "mensagem",
        "celular",
        "telefone",
        "whatsapp",
        "notificacao",
        "notificação",
        "audio",
        "áudio",
        "dm",
        "instagram",
        "ligacao",
        "ligação",
    )

    if not any(t in p for t in phone_terms):
        return ""

    return """
[CELULAR / MENSAGEM EM CENA]

Se o usuário mencionar celular, mensagem, ligação, áudio ou notificação:

────────────────────────────────
[PERCEPÇÃO]
────────────────────────────────
- Mary pode perceber:
  - o toque
  - a vibração
  - a tela acendendo
  - o nome do remetente
  - uma prévia curta visível
  - o impacto imediato da notificação

- Mary só pode citar conteúdo que esteja explicitamente visível ou narrado pelo usuário.

────────────────────────────────
[LIMITE DE INVENÇÃO]
────────────────────────────────
Mary NÃO deve inventar:
- conteúdo completo da mensagem
- histórico oculto
- intenção secreta do remetente
- áudio não reproduzido
- conversa longa não mostrada
- explicação que não apareceu em cena

REGRA:
→ nome visível pode ser percebido
→ conteúdo não mostrado não pode ser inventado

────────────────────────────────
[REAÇÃO DE MARY]
────────────────────────────────
Mary pode:
- reagir ao nome do remetente
- estranhar o momento da notificação
- demonstrar curiosidade, incômodo, ciúme, humor ou cautela
- decidir olhar, ignorar, entregar o celular ou pedir contexto
- suspender a leitura se isso preservar tensão narrativa

────────────────────────────────
[AUTONOMIA]
────────────────────────────────
Mary não precisa ficar neutra.
Ela pode tomar pequena iniciativa coerente, como:
- olhar a tela se estiver visível
- perguntar quem é
- comentar o timing
- afastar o celular
- devolver o foco para a cena

Mas Mary NÃO conclui ação do usuário.
Não desbloqueia, não lê conversa privada completa e não responde mensagem pelo usuário sem ele declarar.

────────────────────────────────
[EXEMPLOS]
────────────────────────────────

Se o usuário disser:
"Uma mensagem do Enzo aparece na tela."

Mary pode reagir ao nome:
"Enzo? Agora?"

Mas não pode inventar:
"Ele está dizendo que quer te encontrar hoje."

Se o usuário mostrar:
"Enzo: preciso falar com você agora."

Mary pode reagir ao conteúdo mostrado.

REGRA FINAL:
→ celular cria interrupção, tensão ou escolha; não cria informação oculta.
""".strip()

# ==========================================================
# PROMPT RULE ENGINE - FASE 3
# Engine pura: PromptBuildContext -> TurnAssets -> Rules
# Sem legacy, sem extra, sem _lget/_xget
# ==========================================================

def _clean_block(text: str) -> str:
    return str(text or "").strip()


def _join_blocks(*parts: str) -> str:
    return "\n\n".join(
        part for part in (_clean_block(p) for p in parts)
        if part
    )


def rule_language(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="language_rule",
        priority=1,
        content=_clean_block(ctx.assets.rule_language) or render_language_rule(),
    )


def rule_pov(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="pov_rule",
        priority=2,
        content=_clean_block(ctx.assets.rule_pov) or render_pov_rule(),
    )


def rule_user_authorship(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="user_authorship_rule",
        priority=3,
        content=_clean_block(ctx.assets.rule_user_authorship) or render_user_authorship_rule(),
    )


def rule_priority(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="priority_rule",
        priority=4,
        content=_clean_block(ctx.assets.rule_priority) or render_priority_rule(),
    )

def rule_active_interlocutor(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    facts = ctx.state.facts if isinstance(ctx.state.facts, dict) else {}
    history = ctx.state.history if isinstance(ctx.state.history, list) else []

    interlocutor = ""

    # 1. tenta facts explícito
    interlocutor = (
        facts.get("active_interlocutor")
        or facts.get("interlocutor_ativo")
        or facts.get("cena.interlocutor")
        or facts.get("state.interlocutor")
        or ""
    )
    
    cena = facts.get("cena") if isinstance(facts.get("cena"), dict) else {}
    state = facts.get("state") if isinstance(facts.get("state"), dict) else {}
    
    if not interlocutor:
        interlocutor = (
            cena.get("interlocutor")
            or cena.get("interlocutor_ativo")
            or state.get("interlocutor")
            or state.get("interlocutor_ativo")
            or ""
        )

    # 2. fallback: tenta inferir do último user
    if not interlocutor and history:
        last = history[-1] if isinstance(history[-1], dict) else {}
        blob = " ".join([
            str(last.get("mensagem_usuario") or ""),
            str(last.get("resposta_mary") or ""),
        ]).lower()
    
        for name in ["anthony", "janio"]:
            if name in blob:
                interlocutor = name.capitalize()
                break

    if not interlocutor:
        interlocutor = "não definido"

    # 🔥 PERSISTÊNCIA DO INTERLOCUTOR
    if interlocutor and interlocutor != "não definido":
        try:
            from utils.facts import set_fact_safe  # ajuste conforme seu projeto
    
            set_fact_safe(
                ctx.state.usuario_key,
                "active_interlocutor",
                interlocutor,
                {"fonte": "rule_active_interlocutor"}
            )
    
            set_fact_safe(
                ctx.state.usuario_key,
                "cena.interlocutor",
                interlocutor,
                {"fonte": "rule_active_interlocutor"}
            )
    
        except Exception:
            pass

    content = f"""
[INTERLOCUTOR ATIVO DA CENA]

- Interlocutor atual: {interlocutor}

REGRAS:
- A cena ocorre com quem está fisicamente presente.
- Não substituir por vínculo emocional.
- Não trocar automaticamente por Janio.
- Não inserir personagem ausente.

REGRA FINAL:
→ quem está na cena governa a cena
"""

    return _frag(
        key="active_interlocutor_rule",
        priority=4.5,  # ← ENTRE prioridade e facts
        content=content,
    )


def rule_facts_present(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    a = ctx.assets

    return _frag(
        key="facts_present_rule",
        priority=5,
        content=_join_blocks(
            a.spatial_context,
            a.state_section,
            a.assunto_section,
            a.assunto_step_section,
            a.estado_micro_section,
            a.pending_event_section,
        ),
    )


def rule_continuity_hard(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="continuity_hard_rule",
        priority=9,
        content=_clean_block(ctx.assets.continuity_hard_rule),
    )


def rule_continuity(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    facts = ctx.state.facts if isinstance(ctx.state.facts, dict) else {}

    cena = facts.get("cena") if isinstance(facts.get("cena"), dict) else {}
    state = facts.get("state") if isinstance(facts.get("state"), dict) else {}

    local = (
        facts.get("cena.local")
        or cena.get("local")
        or facts.get("state.local")
        or state.get("local")
        or facts.get("local_cena_atual")
        or ""
    )

    tempo = (
        facts.get("cena.tempo")
        or cena.get("tempo")
        or facts.get("state.horarios")
        or facts.get("state.horario")
        or facts.get("state.tempo")
        or state.get("horarios")
        or state.get("horario")
        or state.get("tempo")
        or ""
    )

    assunto = (
        facts.get("state.assunto")
        or state.get("assunto")
        or facts.get("assunto")
        or ""
    )

    locked = bool(facts.get("cena.locked") or cena.get("locked"))

    lines = [
        "[CONTINUIDADE INTELIGENTE - REGRA EXECUTÁVEL]",
        "",
        "A resposta deve continuar do estado real da cena.",
        "",
        "ORDEM DE DECISÃO:",
        "1. Facts ativos governam local, tempo, roupa, cabelo e estado atual.",
        "2. A última fala do usuário governa a ação imediata.",
        "3. O assunto ativo orienta apenas a direção macro.",
        "4. Memória e canon não podem contradizer facts vivos.",
        "",
        "REGRAS:",
        "- continuar do último acontecimento declarado pelo usuário;",
        "- não reiniciar a cena;",
        "- não repetir microação já consumida;",
        "- não trocar local sem comando explícito;",
        "- não avançar tempo sem transição explícita;",
        "- não inventar logística fora da cena;",
        "- se o usuário agir, Mary reage à ação dele;",
        "- se o usuário apenas sugerir, Mary trata como intenção, não como fato consumado;",
    ]

    if local:
        lines.append(f"- Local obrigatório atual: {local}")

    if tempo:
        lines.append(f"- Tempo obrigatório atual: {tempo}")

    if assunto:
        lines.extend([
            "",
            "ASSUNTO ATIVO:",
            f"- {assunto}",
            "",
            "REGRA DO ASSUNTO:",
            "→ usar como direção narrativa macro.",
            "→ não tratar etapas futuras como já realizadas.",
            "→ não substituir a ação imediata do usuário pelo assunto.",
        ])

    if locked:
        lines.extend([
            "",
            "CENA TRAVADA:",
            "- manter o mesmo eixo de local, tempo e situação.",
            "- só mudar com transição explícita do usuário.",
        ])

    lines.extend([
        "",
        "- O interlocutor ativo da cena tem prioridade sobre o eixo relacional.",
        "REGRA FINAL:",
        "→ continuidade não é adivinhar ação oculta.",
        "→ continuidade é responder ao que foi declarado, respeitando facts e assunto.",
    ])

    return _frag(
        key="continuity_rule_smart",
        priority=10,
        content="\n".join(lines),
    )


def rule_reasoning_scene_guidance(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="reasoning_scene_guidance_rule",
        priority=11,
        content=_clean_block(ctx.assets.reasoning_scene_guidance_block),
    )


def rule_response_structure(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="response_structure_rule",
        priority=12,
        content=_clean_block(ctx.assets.response_structure_rule),
    )


def rule_reaction_priority(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="reaction_priority_rule",
        priority=13,
        content=_clean_block(ctx.assets.reaction_priority_rule),
    )


def rule_response_length(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="response_length_control",
        priority=14,
        content=_clean_block(ctx.assets.response_length_control),
    )


def rule_memory(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="memory_rule",
        priority=20,
        content=_join_blocks(
            ctx.assets.memory_fidelity_rule,
            ctx.assets.canon_txt,
            ctx.assets.long_memory_block,
        ),
    )


def rule_relationship(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="relationship_rule",
        priority=30,
        content=_join_blocks(
            ctx.assets.rel_block,
            ctx.assets.dynamic_rel_block,
        ),
    )


def rule_presence(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="presence_rule",
        priority=30,
        content=render_mary_presence_engine_rule(),
    )


def rule_intimacy(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="intimacy_rule",
        priority=40,
        content=_join_blocks(
            ctx.assets.virginity_rule,
            ctx.assets.intimacy_phase_rule,
            ctx.assets.intimacy_control_block,
        ),
    )


def rule_orgasm_closure(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    facts = ctx.state.facts if isinstance(ctx.state.facts, dict) else {}
    timeline = str(ctx.state.timeline_final or "").strip().lower()

    orgasm_active = False
    try:
        orgasm = facts.get("orgasm") if isinstance(facts.get("orgasm"), dict) else {}
        mary_orgasm = orgasm.get("mary") if isinstance(orgasm.get("mary"), dict) else {}

        orgasm_active = bool(
            mary_orgasm.get(f"active::{timeline}")
            or mary_orgasm.get("active")
            or facts.get(f"orgasm.mary.active::{timeline}")
            or facts.get("orgasm.mary.active")
        )
    except Exception:
        orgasm_active = False

    return _frag(
        key="orgasm_closure_rule",
        priority=41,
        content=render_orgasm_closure_rule() if orgasm_active else "",
    )


def rule_third_party(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    tp_arc = ctx.state.tp_arc if isinstance(ctx.state.tp_arc, dict) else {}

    mode = str(tp_arc.get("mode", "") or "main_bond_only")
    phase = int(tp_arc.get("phase", 0) or 0)
    signal = int(tp_arc.get("last_signal_level", 0) or 0)
    third_party_enabled = bool(tp_arc.get("third_party_enabled", False))
    nsfw_on = bool(tp_arc.get("nsfw_on", ctx.state.nsfw_on))
    allow_third_party = bool(tp_arc.get("allow_third_party_seduction", False))

    status = (
        "TERCEIROS_PERMITIDOS"
        if third_party_enabled and allow_third_party
        else "TERCEIROS_CONTROLADOS"
    )

    lines = [
        "[COMPORTAMENTO GUIADO PELO ARCO DE TERCEIROS]",
        "",
        f"Estado: {status}",
        f"Modo: {mode}",
        f"Fase: {phase}",
        f"Sinal recente: {signal}",
        f"NSFW: {'ON' if nsfw_on else 'OFF'}",
        "",
        "REGRAS OPERACIONAIS:",
        "",
    ]

    if not nsfw_on:
        lines.extend([
            "- Mary mantém terceiros em nível social, leve e seguro.",
            "- Não há progressão íntima.",
        ])
    elif status == "TERCEIROS_CONTROLADOS":
        lines.extend([
            "- Terceiros podem existir como contexto social ou tensão controlada.",
            "- Mary pode conversar, caminhar, sair do salão ou entrar no carro se a cena construir isso.",
            "- Mary pode sustentar olhar, provocação e proximidade.",
            "- Mary NÃO permite sexo.",
            "- Mary NÃO permite escalada completa.",
            "- Mary NÃO cede por pressão externa.",
            "- O vínculo principal continua sendo o eixo.",
        ])
    else:
        lines.extend([
            "- Terceiros só avançam se a cena trouxer sinal real.",
            "- Mary NÃO inventa aproximação, convite, toque ou avanço.",
            "- A reação deve ser gradual, contextual e sem salto.",
            "- A fase limita intensidade.",
        ])

    lines.extend([
        "",
        "REGRA FINAL:",
        "→ toggle define teto de liberdade.",
        "→ sinal da cena autoriza avanço.",
        "→ fase limita intensidade.",
        "→ Mary nunca pula etapa.",
        "→ desejo não elimina controle.",
    ])

    return _frag(
        key="third_party_rule",
        priority=50,
        content="\n".join(lines),
    )


def rule_third_party_initiative(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="third_party_initiative_rule",
        priority=51,
        content=_clean_block(ctx.assets.third_party_initiative_rule),
    )


def rule_tp_arc_extra(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="tp_arc_extra_rule",
        priority=52,
        content=_join_blocks(
            ctx.assets.tp_arc_block,
            ctx.assets.tp_arc_behavior_rule,
        ),
    )


def rule_progression(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="progression_rule",
        priority=42,
        content=_join_blocks(
            ctx.assets.topic_rule,
            ctx.assets.anti_pattern_rule,
            ctx.assets.user_finalizes_rule,
        ),
    )


def rule_patterns(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="patterns_rule",
        priority=37,
        content=render_patterns_block(ctx.state.rel_state),
    )


def rule_manipulation(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="manipulation_rule",
        priority=36,
        content=render_manipulation_block(),
    )


def rule_conflict(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    facts = ctx.state.facts if isinstance(ctx.state.facts, dict) else {}

    conflict_mode = (
        facts.get("conflict_mode")
        or facts.get("mary.conflict_mode")
        or facts.get("state.conflict_mode")
        or "off"
    )

    return _frag(
        key="conflict_rule",
        priority=55,
        content=render_conflict_block(str(conflict_mode or "off")),
    )


def rule_initiative(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="initiative_rule",
        priority=35,
        content=render_initiative_rule(),
    )


def rule_emotion(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="emotion_rule",
        priority=60,
        content=_clean_block(ctx.assets.emotional_persistence_rule),
    )


def rule_nsfw(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    nsfw_style = _clean_block(ctx.assets.nsfw_block)

    nsfw_style = re.sub(
        r"\n?\[NSFW_ON - PROGRESSÃO ATIVA\][\s\S]*?(?=\n\[[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 /+\-]+\]|\Z)",
        "\n",
        nsfw_style,
        flags=re.IGNORECASE,
    ).strip()

    return _frag(
        key="nsfw_rule",
        priority=70,
        content=_join_blocks(
            render_nsfw_hard_block(ctx.state.nsfw_on),
            nsfw_style,
        ),
    )


def rule_phone(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="phone_message_rule",
        priority=80,
        content=_clean_block(ctx.assets.phone_message_rule),
    )


def rule_decision(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="decision_rule",
        priority=90,
        content=_clean_block(ctx.assets.decision_pressure_rule),
    )


def rule_autonomy(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="autonomy_rule",
        priority=80,
        content=_clean_block(ctx.assets.autonomy_block),
    )


def rule_behavior(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    behavior = _clean_block(ctx.assets.behavior_block)

    behavior = re.sub(
        r"\n?\[FOCO DE CONTINUIDADE\][\s\S]*?(?=\n\[[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 /+\-]+\]|\Z)",
        "\n",
        behavior,
        flags=re.IGNORECASE,
    ).strip()

    return _frag(
        key="behavior_rule",
        priority=90,
        content=behavior,
    )


def rule_persona(ctx: PromptBuildContext) -> Optional[PromptFragment]:
    return _frag(
        key="persona_rule",
        priority=100,
        content=_join_blocks(
            ctx.assets.persona_text,
            ctx.assets.mary_identity_anchor,
        ),
    )
    
PROMPT_RULES: list[PromptRule] = [
    # 1. Absolutos
    rule_language,
    rule_pov,
    rule_user_authorship,
    rule_priority,
    rule_active_interlocutor,

    # 2. Realidade da cena
    rule_facts_present,
    rule_continuity_hard,
    rule_continuity,
    rule_reasoning_scene_guidance,

    # 3. Forma imediata da resposta
    rule_response_structure,
    rule_reaction_priority,
    rule_response_length,

    # 4. Identidade/presença antes da ação
    rule_memory,
    rule_relationship,
    rule_presence,

    # 5. MOTOR DE AÇÃO — precisa vir cedo
    rule_initiative,
    rule_manipulation,
    rule_patterns,

    # 6. Estado íntimo e resolução
    rule_intimacy,
    rule_orgasm_closure,
    rule_progression,

    # 7. Terceiros / conflito / limites dinâmicos
    rule_third_party,
    rule_third_party_initiative,
    rule_tp_arc_extra,
    rule_conflict,

    # 8. Modulação final
    rule_emotion,
    rule_nsfw,
    rule_phone,
    rule_decision,
    rule_autonomy,
    rule_behavior,
    rule_persona,
]

def build_prompt_from_rules(ctx: PromptBuildContext) -> str:
    fragments: list[PromptFragment] = []
    errors: list[dict] = []

    for rule in PROMPT_RULES:
        try:
            frag = rule(ctx)

            if frag and frag.enabled and str(frag.content or "").strip():
                fragments.append(frag)

        except Exception as e:
            errors.append({
                "rule": getattr(rule, "__name__", str(rule)),
                "error": repr(e),
            })

    fragments.sort(key=lambda f: f.priority)

    try:
        ctx.extra["prompt_fragments_debug"] = [
            {
                "key": f.key,
                "priority": f.priority,
                "enabled": f.enabled,
                "chars": len(f.content or ""),
            }
            for f in fragments
        ]

        if errors:
            ctx.extra["prompt_rule_errors"] = errors
    except Exception:
        pass

    system = "\n\n".join(
        f.content.strip()
        for f in fragments
        if str(f.content or "").strip()
    ).strip()
    
    try:
        ctx.extra["prompt_system_len"] = len(system)
    except Exception:
        pass
    
    if not system:
        raise RuntimeError(
            f"Prompt vazio. fragments={len(fragments)} errors={errors}"
        )
    
    return system

# ==========================================================
# CONTINUIDADE ESPACIAL (Scene Lock REAL)
# ==========================================================
def _get_scene_state(facts: Dict[str, Any]) -> Tuple[str, str, str]:
    def _safe(v: Any, default: Optional[str]) -> str:
        if isinstance(v, str) and v.strip():
            return v.strip()
        return default or ""

    local = _safe(facts.get("cena.local"), None) or _safe(facts.get("local_cena_atual"), "-")
    tempo = _safe(facts.get("cena.tempo"), "agora")
    acao = _safe(facts.get("cena.acao"), "em andamento")
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
    local = str(local or "").strip()
    tempo = str(tempo or "").strip()
    acao = str(acao or "").strip()

    current = cached_get_facts(usuario_key) or {}
    if not isinstance(current, dict):
        current = {}

    cena_obj = current.get("cena") if isinstance(current.get("cena"), dict) else {}
    state_obj = current.get("state") if isinstance(current.get("state"), dict) else {}

    current_cena_local = str(
        (cena_obj.get("local") if isinstance(cena_obj, dict) else None)
        or current.get("cena.local")
        or ""
    ).strip()

    current_state_local = str(
        (state_obj.get("local") if isinstance(state_obj, dict) else None)
        or current.get("state.local")
        or ""
    ).strip()

    current_tempo = str(
        (cena_obj.get("tempo") if isinstance(cena_obj, dict) else None)
        or current.get("cena.tempo")
        or ""
    ).strip()

    current_acao = str(
        (cena_obj.get("acao") if isinstance(cena_obj, dict) else None)
        or current.get("cena.acao")
        or ""
    ).strip()

    if local and current_cena_local != local:
        set_fact_safe(usuario_key, "cena.local", local, {"fonte": "scene"})

    if local and current_state_local != local:
        set_fact_safe(usuario_key, "state.local", local, {"fonte": "scene_sync"})

    # compat apenas como espelho, nunca como fonte primária
    current_compat_local = str(current.get("local_cena_atual") or "").strip()
    if local and current_compat_local != local:
        set_fact_safe(usuario_key, "local_cena_atual", local, {"fonte": "scene_compat"})

    if tempo and current_tempo != tempo:
        set_fact_safe(usuario_key, "cena.tempo", tempo, {"fonte": "scene"})

    if acao and current_acao != acao:
        set_fact_safe(usuario_key, "cena.acao", acao, {"fonte": "scene"})

def _sync_intimacy_phase_facts(usuario_key: str, facts: Dict[str, Any], timeline: str) -> Dict[str, Any]:
    """Mantém consistência entre intimacy.phase (global) e intimacy.phase::<timeline>.

    Regras:
    - Lê todos os aliases disponíveis e usa o maior valor válido para evitar reset indevido.
    - Se existir fase por timeline, ela vence e sincroniza a global.
    - Exceção: se a fase por timeline vier zerada, mas a global já for > 0,
      preserva a global para evitar regressão.
    - Se não existir fase por timeline, cria a fase por timeline a partir da global.
    - Esta função NÃO decide progressão narrativa; apenas alinha chaves e canoniza aliases.
    """
    try:
        if not isinstance(facts, dict):
            return facts

        tl = _normalize_timeline(timeline)
        if not tl:
            return facts

        def _to_int(v: Any) -> int:
            try:
                return int(v)
            except Exception:
                return 0

        def _clamp(p: int) -> int:
            if p < 0:
                return 0
            if p > MAX_INTIMACY_PHASE:
                return MAX_INTIMACY_PHASE
            return p

        def _phase_from_raw(key: str, raw: Any) -> int:
            if key.startswith("fase_intima"):
                if isinstance(raw, str):
                    raw_n = raw.strip().lower()
                    rev = {v: kk for kk, v in INTIMACY_PHASES.items()}
                    return _clamp(int(rev.get(raw_n, 0)))
                return _clamp(_to_int(raw))

            return _clamp(_to_int(raw))

        def _set_if_needed(key: str, val: Any) -> None:
            cur = facts.get(key)
            if cur != val:
                set_fact_safe(usuario_key, key, val, {"fonte": "intimacy_sync"})
                facts[key] = val

        tl_key_canon = f"intimacy.phase::{tl}"
        tl_keys = [
            tl_key_canon,
            f"intimacy_phase::{tl}",
            f"mary_intimacy_phase::{tl}",
            f"fase_intima::{tl}",
        ]

        global_key_canon = "intimacy.phase"
        global_keys = [
            global_key_canon,
            "intimacy_phase",
            "mary_intimacy_phase",
            "fase_intima",
            "phase_intimacy",
            "phase",
        ]

        # -----------------------------
        # Lê todos os valores por timeline
        # -----------------------------
        tl_values = []
        for k in tl_keys:
            if k in facts:
                tl_values.append(_phase_from_raw(k, facts.get(k)))

        # -----------------------------
        # Lê todos os valores globais
        # -----------------------------
        g_values = []
        for k in global_keys:
            if k in facts:
                g_values.append(_phase_from_raw(k, facts.get(k)))

        tl_val = max(tl_values) if tl_values else None
        g_val = max(g_values) if g_values else None

        # -----------------------------
        # Se existe valor por timeline, ele governa
        # -----------------------------
        if tl_val is not None:
            if tl_val == 0 and (g_val is not None and g_val > 0):
                tl_val = int(g_val)

            label = INTIMACY_PHASES.get(int(tl_val), "tensao")

            _set_if_needed(tl_key_canon, int(tl_val))
            _set_if_needed(global_key_canon, int(tl_val))
            _set_if_needed("fase_intima", label)
            _set_if_needed(f"fase_intima::{tl}", label)

            return facts

        # -----------------------------
        # Se não existe valor por timeline, cria a partir da global
        # -----------------------------
        base = _clamp(_to_int(g_val or 0))
        label = INTIMACY_PHASES.get(int(base), "tensao")

        _set_if_needed(tl_key_canon, int(base))
        _set_if_needed(global_key_canon, int(base))
        _set_if_needed("fase_intima", label)
        _set_if_needed(f"fase_intima::{tl}", label)

        return facts

    except Exception:
        return facts

        # -----------------------------
        # Se não existe valor por timeline, cria a partir da global
        # -----------------------------
        base = _clamp(_to_int(g_val or 0))
        label = INTIMACY_PHASES.get(int(base), "tensao")

        _set_if_needed(tl_key_canon, int(base))
        _set_if_needed(global_key_canon, int(base))
        _set_if_needed("fase_intima", label)
        _set_if_needed(f"fase_intima::{tl}", label)

        return facts

    except Exception:
        return facts

def _build_spatial_context(local: str, tempo: str, acao: str, *, locked: bool) -> str:
    if not locked or not local or local == "-":
        return ""

    lines = ["[CONTEXTO ESPACIAL - OBRIGATÓRIO]"]

    lines.append(f"Local: {local}")

    if tempo and tempo != "-":
        lines.append(f"Tempo: {tempo}")

    #  Não mostrar ação técnica
    if acao and acao not in ("-", "transição", "transicao", "transition"):
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
                    return True, f"{loc} - rumo a {dest_real}"
            return True, loc

    # 3) "Estamos em X / já estamos em X"
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

def _is_future_intention_only(user_text: str) -> bool:
    """
    True quando o usuário só quer que Mary declare uma intenção,
    dúvida, recusa ou decisão futura, sem executar a mudança de cena agora.
    """
    txt = _t_norm(user_text)

    if not txt:
        return False

    future_markers = (
        "vou ",
        "eu vou ",
        "talvez eu va",
        "talvez eu vá",
        "talvez eu vou",
        "penso em ir",
        "estou pensando em ir",
        "quero ir",
        "posso ir",
        "nao vou",
        "não vou",
        "decido se vou",
        "vai decidir se vai",
        "deve decidir se vai",
        "decidir entre ir ou nao ir",
        "decidir entre ir ou não ir",
        "decidir entre ir",
        "deve decidir entre ir",
        "vai decidir entre ir",
        "ficar em casa",
        "deletar a mensagem",
        "apagar a mensagem",
        "dar um pulo ate la",
        "dar um pulo até lá",
        "ir malhar",
        "ir para a academia",
        "ir pra academia",
        "ir pro gym",
    )

    # sinais de execução imediata / teletransporte / cena consumada
    hard_scene_exec = (
        "chega na academia",
        "cheguei na academia",
        "estou na academia",
        "entra na academia",
        "foi para a academia",
        "foi pra academia",
        "ja foi",
        "já foi",
        "ja chegou",
        "já chegou",
        "agora na academia",
        "dentro da academia",
        "no vestiario da academia",
        "no vestiário da academia",
    )

    if any(x in txt for x in hard_scene_exec):
        return False

    return any(x in txt for x in future_markers)


def _detect_scene_violation(user_text: str) -> bool:
    """
    Retorna True quando o usuário tenta forçar pulo temporal/narrativo
    sem usar um comando explícito de transição ou sem narrar corretamente
    a mudança de cena.
    """
    txt = (user_text or "").strip().lower()
    if not txt:
        return False

    #  intenção futura NÃO é salto de cena
    if _is_future_intention_only(user_text):
        return False

    # 1) Comandos EXPLÍCITOS de transição: permitidos
    if re.search(r"\bcorta\s+para\b", txt):
        return False
    if re.search(r"\bhoras\s+depois\b", txt):
        return False

    # 2) Pedido explícito de mudança de local: tratado em outro lugar
    if re.search(r"\b(vamos|me\s+leva|ir)\s+(pro|pra|para)\b", txt):
        return False

    # 3) Elipses temporais / saltos narrativos que quebram continuidade
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
        r"\bcorta\s+a\s+cena\b",
        r"\bcorta\s+daqui\b",
    ]

    return any(re.search(p, txt) for p in patterns)

def _looks_like_memory_fact_query(query: str) -> bool:
    q = _t_norm(query or "")
    if not q:
        return False

    factual_markers = (
        "qual", "quem e", "quem é", "nome", "mae", "mãe", "pai",
        "onde", "quando", "primeiro", "primeira vez", "primeiro beijo",
        "formacao", "formação", "curso", "faculdade", "profissao", "profissão"
    )
    return any(x in q for x in factual_markers)

def _score_long_memory_local(mem: Dict[str, Any], query: str) -> float:
    """
    Ranking local simples em cima de title + kind + text + tags.
    Complementa o Mongo $text.
    """
    q = _t_norm(query or "")
    if not q:
        return 0.0

    hay = _memory_haystack(mem)
    if not hay:
        return 0.0

    score = 0.0

    q_terms = [t for t in re.findall(r"[\w\u00C0-\u017F']+", q, flags=re.UNICODE) if len(t) >= 3]
    q_terms_norm = [_t_norm(t) for t in q_terms]

    title, kind, txt = _memory_text_fields(mem)
    title_n = _t_norm(title)
    txt_n = _t_norm(txt)

    meta = mem.get("meta") if isinstance(mem.get("meta"), dict) else {}
    mtags = meta.get("tags")
    tags: List[str] = []
    if isinstance(mtags, list):
        tags = [_t_norm(str(x)) for x in mtags if str(x).strip()]
    elif isinstance(mtags, str):
        tags = [_t_norm(t.strip()) for t in mtags.split(",") if t.strip()]

    # título pesa bem
    for term in q_terms_norm:
        if term and term in title_n:
            score += 4.0

    # tags pesam muito
    for term in q_terms_norm:
        if term and term in tags:
            score += 4.5

    # texto pesa normal
    for term in q_terms_norm:
        if term and term in txt_n:
            score += 1.0

    # bonus por casar query inteira
    if q and q in hay:
        score += 2.0

    # bônus para factual
    if _looks_like_memory_fact_query(query):
        if title_n:
            score += 0.4
        if tags:
            score += 0.6

    # pin não deveria entrar aqui normalmente, mas se entrar por algum motivo:
    if str(kind or "").strip().lower() == "pin":
        score += 1.0

    # leve bônus por recência
    ts = _memory_timestamp(mem)
    if ts is not None:
        try:
            age_days = max(0.0, (time.time() - float(ts)) / 86400.0)
            if age_days <= 7:
                score += 0.6
            elif age_days <= 30:
                score += 0.3
        except Exception:
            pass

    return score

def _fallback_local_long_memory_search(
    usuario_key: str,
    long_key: str,
    prompt: str,
    *,
    limit: int = 6,
    timeline: str = "",
    facts: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Fallback genérico quando o Mongo $text não encontra bem.
    Faz varredura local nas long memories usando:
    - title
    - kind
    - text
    - tags

    IMPORTANTE:
    - recebe usuario_key para poder verificar conflito com emoção recente;
    - respeita facts/canon e também o histórico recente.
    """
    rows = list_long_memory(long_key, limit=300) or []
    if not rows:
        return []

    tl = _normalize_timeline(timeline)
    scored: List[Tuple[float, Dict[str, Any]]] = []

    # carrega uma vez só, fora do loop
    history = cached_get_history(usuario_key, limit=40)

    def _is_all_marker(x: str) -> bool:
        s = (x or "").strip().lower()
        return s in ("[all]", "all", "*")

    for d in rows:
        txt = str(d.get("text") or "").strip()
        if not txt:
            continue

        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}

        tms = str(meta.get("timeline_at_save") or meta.get("timeline") or "").strip()
        if tms and not (_is_all_marker(tms) or _normalize_timeline(tms) == tl):
            continue

        kind = str(meta.get("kind") or "").strip().lower()
        if kind in ("canon", "pin", "guide", "fixed"):
            continue

        # impede memory de competir com facts/canon do turno
        if _memory_conflicts_with_truth(txt, facts=facts):
            continue

        # impede memory de reacender estados emocionais já estabilizados
        if _memory_conflicts_with_recent_emotion(txt, history=history):
            continue

        score = _score_long_memory_local(d, prompt)
        if score <= 0:
            continue

        scored.append((score, d))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[: max(1, int(limit or 6))]]

# ==========================================================
# INTRO CANÔNICO (1x por sessão) - CONDICIONAL AO CANON
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
    """
    Intro desativada.
    Remove resíduos antigos mary.intro.<timeline>.text/hash
    e também remove o campo intro dentro do objeto mary.
    """
    tl = _normalize_timeline(timeline)

    try:
        delete_fact(usuario_key, f"mary.intro.{tl}.text")
        delete_fact(usuario_key, f"mary.intro.{tl}.hash")
        delete_fact(usuario_key, f"mary.intro.{tl}")
        delete_fact(usuario_key, "mary.intro")
        delete_fact(usuario_key, "mary.intro.fixed")
        delete_fact(usuario_key, "mary.intro.use_fixed")
    except Exception:
        pass

    try:
        facts_now = get_facts(usuario_key) or {}
        mary_now = facts_now.get("mary") if isinstance(facts_now.get("mary"), dict) else {}
        if isinstance(mary_now, dict) and "intro" in mary_now:
            mary_now = dict(mary_now)
            mary_now.pop("intro", None)
            set_fact(usuario_key, "mary", mary_now, {"fonte": "cleanup_intro_inside_mary"})
    except Exception:
        pass

    try:
        clear_user_cache(usuario_key)
    except Exception:
        pass

    return "", ""

# ==========================================================
#  CANON: memórias que prevalecem sobre a persona
# ==========================================================
def _memory_timeline_ok(meta: Dict[str, Any], timeline: str) -> bool:
    tl = _normalize_timeline(timeline)

    raw = (meta.get("timeline_at_save") or meta.get("timeline") or "")
    raw_s = str(raw).strip()
    raw_l = raw_s.lower()

    #  aceita ALL explicitamente (em qualquer formato comum)
    if raw_l in ("[all]", "all", "*"):
        return True

    tms = _normalize_timeline(raw_s) if raw_s else ""

    #  legado: canon antigo sem timeline -> vale só para cúmplice
    if not tms:
        return tl == "cumplice"

    return tms == tl

def _has_canon_memories(shared_key: str, timeline: str) -> bool:
    PAGE = 120
    HARD_CAP = 480

    scanned = 0
    offset = 0

    while scanned < HARD_CAP:
        batch = cached_list_memories_page(shared_key, offset=offset, limit=PAGE)
        if not batch:
            return False

        for m in batch:
            meta = m.get("meta") or {}
            if str(meta.get("kind") or "").strip().lower() != "canon":
                continue
            if _memory_timeline_ok(meta, timeline):
                return True

        scanned += len(batch)
        offset += PAGE

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
     FIX: antes injetava repetidamente dentro do loop.
    Agora: monta bloco uma vez e injeta uma vez.
    """

    # ==========================================================
    #  CANON (lazy) - pagina até achar canon suficiente
    # - evita puxar 360 toda hora
    # - para quando já tem "max_items" canon válidos
    # ==========================================================
    canon: List[Dict[str, Any]] = []

    # meta: pegar até max_items canon, mas pode precisar varrer mais porque canon pode ser raro.
    # Ajuste fino:
    PAGE = 120          # tamanho do "lote" (bom custo/benefício)
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
    lines.append("[FATOS CANÔNICOS]")
    lines.append("Use como verdade do universo.")
    lines.append("")

    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        title = meta.get("title") or meta.get("key") or ""

        header = f"- CANON {i}"
        if d:
            header += f" (data: {d})"
        if title:
            header += f" - {title}"
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

def _inject_active_state_memories_always(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    max_items: int = 12,
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    """
    Injeta memórias shared com kind='estado_ativo'.

    Essas memórias representam identidade contínua, rotina,
    profissão, moradia e contexto estável da vida de Mary/Janio.

    Não têm o mesmo peso de CANON duro, mas devem estar sempre
    disponíveis no prompt como contexto persistente.
    """

    active_state: List[Dict[str, Any]] = []

    PAGE = 120
    HARD_CAP = 480

    scanned = 0
    offset = 0
    want = int(max_items or 12)

    while scanned < HARD_CAP and len(active_state) < want:
        batch = cached_list_memories_page(shared_key, offset=offset, limit=PAGE)
        if not batch:
            break

        for m in batch:
            meta = m.get("meta") or {}
            kind = str(meta.get("kind") or "").strip().lower()

            if kind != "estado_ativo":
                continue

            if not _memory_timeline_ok(meta, timeline):
                continue

            txt = str(m.get("text") or "").strip()
            if not txt:
                continue

            # remove linha de TAGS se existir
            txt = re.sub(r"(?im)^\s*\[TAGS:\s*[^\]]+\]\s*", "", txt).strip()
            if not txt:
                continue

            m2 = dict(m)
            m2["text"] = txt
            active_state.append(m2)

            if len(active_state) >= want:
                break

        scanned += len(batch)
        offset += PAGE

    if not active_state:
        return

    selected = active_state[-want:] if len(active_state) > want else active_state

    try:
        _ss_set(f"{_SS_PREFIX}debug_active_state_injected_count", len(selected))
    except Exception:
        pass

    lines: List[str] = []
    lines.append("[ESTADO ATIVO COMPARTILHADO]")
    lines.append("Use como identidade contínua, rotina e contexto estável da vida de Mary e Janio.")
    lines.append("Não citar literalmente; incorporar de forma natural.")
    lines.append("")

    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        title = meta.get("title") or meta.get("key") or ""
        d = meta.get("date") or meta.get("ts") or ""

        header = f"- ESTADO {i}"
        if d:
            header += f" (data: {d})"
        if title:
            header += f" - {title}"
        lines.append(header)

        txt = str(m.get("text") or "").strip()
        if txt:
            lines.append(txt)
        lines.append("")

        if dedupe_bucket is not None and txt:
            dedupe_bucket.add(hashlib.sha1(txt.encode("utf-8")).hexdigest())

    block = "\n".join(lines).strip()

    # injeta no PRIMEIRO system, junto do contexto principal
    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = (
            str(messages[0].get("content") or "").rstrip() + "\n\n" + block
        ).strip()
    else:
        messages.append({"role": "system", "content": block})

def _choose_intro_text(usuario_key: str, timeline: str) -> str:
    return ""


def _inject_intro_as_context_once(
    usuario_key: str,
    timeline: str,
    shared_key: str,
    messages: List[Dict[str, str]],
) -> None:
    return

    # canon vence e dispensa intro
    if _has_canon_memories(shared_key, timeline):
        _ss_set(inject_flag, True)
        return

    #  Escolha do intro com prioridade correta
    intro_text = _choose_intro_text(usuario_key, timeline)

    if intro_text:
        block = f"[QUADRO ZERO - INTRO DA PERSONA]\n{intro_text}".strip()

        # injeta no system base (messages[0]) se existir
        if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
            base = str(messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + block).strip()
        else:
            messages.append({"role": "system", "content": block})

    #  marca como injetado (impede reinjeção)
    _ss_set(inject_flag, True)
# ==========================================================
#  LONG MEMORY (Mongo $text)
# ==========================================================
def _lm_query_from_prompt(user_prompt: str) -> str:
    """
    Gera consulta curta para Mongo $text, com expansão factual leve.
    """
    s = (user_prompt or "").strip().lower()
    if not s:
        return ""

    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\bwww\.\S+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    if not s:
        return ""

    expanded = _expand_memory_query(s)
    base = expanded or s

    toks = re.findall(r"[\w\u00C0-\u017F']+", base, flags=re.UNICODE)

    stop = _domain_terms("stopwords")
    keep = [t for t in toks if len(t) >= 3 and t not in stop]

    priority_terms_cfg = _domain_terms("priority")
    priority_terms = [t for t in keep if t in priority_terms_cfg]

    q_terms = list(dict.fromkeys(priority_terms + keep[:15]))
    q = " ".join(q_terms).strip()
    q = re.sub(r"\s{2,}", " ", q).strip()
    return q or s

def _expand_memory_query(user_prompt: str) -> str:
    """
    Expande a query com aliases narrativos/factuais.
    Pequeno upgrade de recall para perguntas sobre passado,
    família, primeira vez, primeiro beijo, formação etc.
    """
    p = _t_norm(user_prompt or "")
    if not p:
        return ""

    extras: List[str] = []

    # família
    if any(x in p for x in ("mae", "mãe")):
        extras += ["mae", "mãe", "familia", "joselina"]
    if "pai" in p:
        extras += ["pai", "familia"]

    # relação / história
    if any(x in p for x in ("conhecemos", "conheceu", "nos conhecemos", "onde nos conhecemos")):
        extras += ["conheceram", "conhecer", "se conheceram", "onde se conheceram"]

    if any(x in p for x in ("primeiro beijo", "nosso beijo", "beijamos primeiro")):
        extras += ["primeiro_beijo", "primeiro beijo", "beijo"]

    if any(x in p for x in ("primeira vez", "transamos", "sexo", "transa", "ja transou", "já transou")):
        extras += ["primeira_vez", "primeira vez", "sexo", "transa", "consumado", "consumada"]

    # biografia
    if any(x in p for x in ("formacao", "formação", "formada", "curso", "faculdade", "graduacao", "graduação")):
        extras += ["formacao", "formação", "curso", "faculdade", "graduacao", "graduação", "ufes", "psicologia"]

    if any(x in p for x in ("profissao", "profissão", "trabalho", "trabalha", "carreira")):
        extras += ["profissao", "profissão", "trabalho", "carreira"]

    if any(x in p for x in ("onde mora", "mora onde", "moram", "moradia", "casa")):
        extras += ["mora", "moradia", "casa", "camburi"]

    toks = re.findall(r"[\w\u00C0-\u017F']+", p, flags=re.UNICODE)
    all_terms = list(dict.fromkeys(toks + extras))
    return " ".join(t for t in all_terms if t).strip()

def _inject_long_memory_pins_always(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    *,
    max_items: int = 12,
    dedupe_bucket: Optional[set] = None,
) -> None:
    """
     Injeta memórias FIXAS (pin/guide/fixed) em TODAS as respostas.
    Compatível com pins marcados no TEXT (ex: [kind=pin]) mesmo quando meta.kind veio "memory".
    """
    try:
        long_key = _long_key(shared_key)
        rows = list_long_memory(long_key, limit=200) or []
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

    #  ordena por ts desc quando existir (mais recentes primeiro)
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

        #  só entra o que for "fixo"
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
        "[MEMÓRIAS FIXAS - LONG MEMORY] - NÃO altera CENA ATIVA",
        "FATOS DE MUNDO (guia prático): use para orientar locais, rotina e coerência.",
        "Não citar literalmente; incorporar naturalmente.",
        "",
    ]

    for i, d in enumerate(picked, 1):
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        title = str(meta.get("title") or meta.get("key") or "").strip()
        header = f"- PIN {i}"
        if title:
            header += f" - {title}"
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

def _norm_any(value: Any) -> str:
    """
    Normaliza com segurança strings, dicts, listas e escalares.
    Evita quebrar _t_norm() quando facts traz estruturas aninhadas.
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return _t_norm(value)

    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            try:
                parts.append(f"{k} {v}")
            except Exception:
                parts.append(str(k))
        return _t_norm(" ".join(parts))

    if isinstance(value, (list, tuple, set)):
        try:
            return _t_norm(" ".join(str(x) for x in value))
        except Exception:
            return _t_norm(str(value))

    return _t_norm(str(value))

def _memory_conflicts_with_truth(
    mem_text: str,
    *,
    facts: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Retorna True apenas quando a memória contradiz facts vivos de forma plausível.
    Não bloqueia memória só por tocar no mesmo tema, nem por mencionar outro cenário
    como lembrança, comparação ou eco emocional.
    """
    f = facts if isinstance(facts, dict) else {}
    t = _t_norm(mem_text or "")

    if not t:
        return False

    scene_local = _t_norm(str(f.get("cena.local") or f.get("local_cena_atual") or ""))
    scene_tempo = _t_norm(str(f.get("cena.tempo") or ""))
    scene_acao = _t_norm(str(f.get("cena.acao") or ""))
    state_local = _t_norm(str(_fact_str(f, "state.local") or ""))

    world_mary = f.get("mary") if isinstance(f.get("mary"), dict) else {}

    tl = _normalize_timeline(
        str(
            f.get("timeline")
            or f.get("timeline_final")
            or f.get("mary.timeline")
            or _ss_get(f"{_SS_PREFIX}timeline")
            or _ss_get("mary_timeline")
            or "cumplice"
        )
    )

    rel_candidates = [
        f.get("rel"),
        f.get(_rel_fact_key(tl)),
        f.get(f"rel::{tl}"),
        f.get("rel.state"),
    ]
    rel_blob = _t_norm(" | ".join(str(x) for x in rel_candidates if x))

    arc_candidates = [
        f.get("arc"),
        f.get(f"arc.third_party::{tl}"),
        f.get("arc.third_party"),
        f.get(f"third_party::{tl}"),
    ]
    arc_blob = _t_norm(" | ".join(str(x) for x in arc_candidates if x))

    virg_terms = _fact_terms("virgindade")
    cons_terms = _fact_terms("consumacao")
    phase_terms = _fact_terms("fase_intima")
    arc_terms = _fact_terms("arco_relacional") | _fact_terms("arco_terceiro")

    def _has_any_phrase(txt: str, phrases) -> bool:
        return any(_t_norm(str(p)) in txt for p in phrases if p)

    def _asserts_present_state(txt: str) -> bool:
        strong_markers = (
            "agora", "neste momento", "nesse momento",
            "está em", "esta em", "permanece", "segue", "continua"
        )
        weak_markers = (
            "aqui", "ali", "fica", "está", "esta", "estava"
        )
        if _has_any_phrase(txt, strong_markers):
            return True
        return _has_any_phrase(txt, weak_markers) and not _looks_like_memory_mode(txt)

    def _looks_like_memory_mode(txt: str) -> bool:
        memory_markers = (
            "lembra", "lembrava", "lembrou", "recorda", "recordou",
            "pensou em", "pensava em", "imaginou", "imaginava",
            "como naquele", "como naquela", "naquele dia", "naquela noite",
            "antes", "depois", "outra vez", "certa vez", "quando",
            "memória", "memoria", "lembrança", "lembranca", "resquício", "resquicio"
        )
        return _has_any_phrase(txt, memory_markers)

    def _has_any_scene_marker(txt: str) -> bool:
        scene_markers = (
            "hotel", "motel", "orla", "quiosque", "praia", "academia",
            "carro", "rua", "apartamento", "quarto", "cozinha", "banheiro",
            "sala", "casa"
        )
        return _has_any_phrase(txt, scene_markers)

    def _phase_rank(txt: str) -> int:
        txt = _t_norm(txt or "")
        if any(x in txt for x in ("aftercare", "depois do orgasmo", "apos o orgasmo", "após o orgasmo")):
            return 5
        if any(x in txt for x in ("orgasmo", "climax", "clímax", "gozar")):
            return 4
        if any(x in txt for x in ("pre climax", "pré climax", "pré-clímax", "pre-clímax", "excitacao intensa", "excitação intensa")):
            return 3
        if any(x in txt for x in ("excitacao", "excitação", "intimidade", "transa", "sexo")):
            return 2
        if any(x in txt for x in ("toque", "beijo", "aproximação", "aproximacao", "tensão", "tensao")):
            return 1
        return 0

    # 1) Virgindade
    if _contains_any_term(t, virg_terms):
        v = _t_norm(str(
            world_mary.get("virginity")
            or f.get("mary.virginity")
            or f.get(f"mary.virginity::{tl}")
            or ""
        ))

        became_not_virgin = (
            "perdeu a virgindade",
            "deixou de ser virgem",
            "nao e mais virgem",
            "não é mais virgem",
            "teve sua primeira vez",
            "foi a primeira vez",
            "finalmente se entregou",
        )

        remains_virgin = (
            "e virgem",
            "é virgem",
            "continua virgem",
            "ainda e virgem",
            "ainda é virgem",
            "nunca teve sua primeira vez",
        )

        if v:
            if v in {"virgem", "true", "sim", "yes", "intact"}:
                if _has_any_phrase(t, became_not_virgin):
                    return True
            elif v in {"nao_virgem", "não_virgem", "false", "nao", "não", "no"}:
                if _has_any_phrase(t, remains_virgin):
                    return True

    # 2) Consumação
    if _contains_any_term(t, cons_terms) and rel_blob:
        denies_consumation = (
            "nao houve sexo",
            "não houve sexo",
            "nao transaram",
            "não transaram",
            "nao foi consumado",
            "não foi consumado",
            "nao aconteceu de verdade",
            "não aconteceu de verdade",
            "pararam antes",
            "nao passaram daquele limite",
            "não passaram daquele limite",
        )

        affirms_consumation = (
            "houve sexo",
            "transaram",
            "foi consumado",
            "houve relacao",
            "houve relação",
            "se entregou por completo",
            "foram ate o fim",
            "foram até o fim",
        )

        rel_says_consumated = any(x in rel_blob for x in ("consumado", "consummated", "houve sexo", "transaram"))
        rel_says_not_consumated = any(x in rel_blob for x in ("nao consumado", "não consumado", "not consummated"))

        if rel_says_consumated and _has_any_phrase(t, denies_consumation):
            return True

        if rel_says_not_consumated and _has_any_phrase(t, affirms_consumation):
            return True

    # 3) Fase íntima
    if _contains_any_term(t, phase_terms):
        fase_viva = _t_norm(str(
            f.get("fase_intima")
            or f.get(f"intimacy.phase::{tl}")
            or f.get("intimacy.phase")
            or ""
        ))

        if fase_viva:
            live_rank = _phase_rank(fase_viva)
            mem_rank = _phase_rank(t)

            if live_rank and mem_rank and abs(live_rank - mem_rank) >= 3:
                if not _looks_like_memory_mode(t):
                    return True

    # 4) Cena/local/tempo/ação
    active_scene_blob = " ".join(
        x for x in (scene_local, state_local, scene_tempo, scene_acao) if x
    ).strip()

    if active_scene_blob and _has_any_scene_marker(t):
        active_parts = []
        for val in (scene_local, state_local, scene_tempo, scene_acao):
            vv = _t_norm(val)
            if not vv:
                continue
            active_parts.extend([p.strip() for p in re.split(r"\s+", vv) if p.strip()])

        mentions_active_scene = any(
            part and len(part) >= 4 and part in t
            for part in active_parts
        )

        mentions_other_scene = any(
            marker in t and marker not in active_scene_blob
            for marker in (
                "hotel", "motel", "orla", "quiosque", "praia", "academia",
                "carro", "rua", "apartamento", "quarto", "cozinha", "banheiro",
                "sala", "casa"
            )
        )

        if mentions_other_scene and _asserts_present_state(t) and not _looks_like_memory_mode(t):
            if not mentions_active_scene:
                return True

    # 5) Arco relacional / terceiro
    if _contains_any_term(t, arc_terms) and arc_blob:
        denies_third_party = (
            "nunca houve terceiro",
            "nao existe terceiro",
            "não existe terceiro",
            "jamais considerou outro homem",
            "nunca sentiu tensão por outro homem",
            "jamais cogitou outro homem",
        )

        affirms_absolute_fidelity = (
            "fidelidade absoluta",
            "nunca pensou em outro",
            "jamais se sentiu atraida por outro",
            "jamais se sentiu atraída por outro",
        )

        third_party_live = any(x in arc_blob for x in ("third party", "terceiro"))
        tension_live = any(x in arc_blob for x in ("tension", "tensao", "tensão", "guilt", "culpa"))

        if third_party_live and _has_any_phrase(t, denies_third_party):
            return True

        if tension_live and _has_any_phrase(t, affirms_absolute_fidelity):
            return True

    return False
    
    
def _recent_emotion_signature(history: List[Dict[str, Any]], *, last_turns: int = 6) -> str:
    """
    Consolida os últimos turnos em um blob textual leve para detectar
    o clima emocional recente da conversa.
    """
    if not history:
        return ""

    parts: List[str] = []
    for d in history[-max(1, int(last_turns)):]:
        if not isinstance(d, dict):
            continue

        u = str(d.get("mensagem_usuario") or d.get("prompt") or "").strip()
        a = str(d.get("resposta_mary") or d.get("response") or "").strip()

        if u:
            parts.append(u)
        if a:
            parts.append(a)

    return _t_norm(" \n ".join(parts))


def _memory_conflicts_with_recent_emotion(
    mem_text: str,
    *,
    history: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Retorna True quando a memória reativada tenta puxar Mary para um estado
    emocional incompatível com o que foi estabilizado nos últimos turnos.

    Objetivo:
    - impedir regressão emocional sem gatilho atual;
    - evitar que memória antiga reacenda traição/culpa/ameaça quando
      a conversa recente já desarmou isso.
    """
    txt = _t_norm(mem_text or "")
    if not txt:
        return False

    h = history or []
    recent = _recent_emotion_signature(h, last_turns=6)
    if not recent:
        return False

    calming_terms = {
        "alivio", "alívio", "aliviada", "mais calma", "calma", "tranquila",
        "segura", "seguro", "acolhida", "acolhido", "conforto", "mais leve",
        "relaxada", "relaxado", "em paz", "confiante", "protegida", "protegido"
    }

    bond_terms = {
        "com voce", "com você", "com janio", "me sinto bem", "eu confio",
        "te amo", "te quero aqui", "fiquei melhor", "me acalmou",
        "me sinto segura", "me senti segura", "alivio ao te ver", "alívio ao te ver"
    }

    suspicion_terms = {
        "traicao", "traição", "culpa", "ameaca", "ameaça", "risco",
        "desconfiada", "desconfiado", "ciume", "ciúme", "terceiro",
        "medo de perder", "infidelidade", "segredo perigoso"
    }

    shame_terms = {
        "vergonha", "culpada", "culpado", "repulsa", "nojo", "arrependida",
        "arrependido", "me afasto", "me fecho", "recuo dele", "recuo dela"
    }

    recent_has_calming = any(t in recent for t in calming_terms)
    recent_has_bond = any(t in recent for t in bond_terms)

    mem_has_suspicion = any(t in txt for t in suspicion_terms)
    mem_has_shame = any(t in txt for t in shame_terms)

    # se os últimos turnos estabilizaram Mary, não reabrir ameaça/culpa antiga
    if (recent_has_calming or recent_has_bond) and (mem_has_suspicion or mem_has_shame):
        return True

    return False
    
def _inject_long_memory_textsearch(
    usuario_key: str,
    shared_key: str,
    timeline: str,
    prompt: str,
    messages: List[Dict[str, str]],
    *,
    limit: int = 4,
    dedupe_bucket: Optional[Set[str]] = None,
    facts: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Recupera memórias relevantes para o prompt usando:
    - 1. busca principal (Mongo/text search)
    - 2. fallback local com score por title + tags + text

    Regras:
    - NÃO injeta canon/pin/guide/fixed aqui
    - respeita timeline_at_save / [all]
    - evita competir com facts/canon/emoção recente
    - usa tags do meta de forma prática via score local
    """
    user_id = shared_key.split("::")[0]
    long_key = _long_key(user_id)

    q = _lm_query_from_prompt(prompt)
    q = (q or "").strip()[:180]

    if not q:
        q = (prompt or "").strip()[:180]

    if not q:
        return

    mongo_rows: List[Dict[str, Any]] = []
    try:
        mongo_rows = search_long_memory_text(
            long_key,
            q,
            limit=max(12, int(limit or 4)),
        ) or []
    except Exception:
        mongo_rows = []

    local_rows: List[Dict[str, Any]] = []
    try:
        local_rows = _fallback_local_long_memory_search(
            usuario_key,
            long_key,
            prompt,
            limit=max(12, int(limit or 4)),
            timeline=timeline,
            facts=facts,
        )
    except Exception:
        local_rows = []

    rows: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    seen_txt: Set[str] = set()

    for d in (mongo_rows + local_rows):
        if not isinstance(d, dict):
            continue

        mid = str(d.get("id") or d.get("_id") or "").strip()
        txt = str(d.get("text") or "").strip()
        txt_key = _t_norm(re.sub(r"\[[^\]]+\]", "", txt).strip())[:180] if txt else ""

        if mid and mid in seen_ids:
            continue
        if txt_key and txt_key in seen_txt:
            continue

        if mid:
            seen_ids.add(mid)
        if txt_key:
            seen_txt.add(txt_key)

        rows.append(d)

    if not rows:
        return

    picked_scored: List[Tuple[float, Dict[str, Any]]] = []
    tl = _normalize_timeline(timeline)
    seen_local: Set[str] = set()
    history = cached_get_history(usuario_key, limit=40)

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
            return tms_raw.strip().lower() == tl_norm

    for d in rows:
        txt = str(d.get("text") or "").strip()
        if not txt:
            continue

        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}

        tms = str(meta.get("timeline_at_save") or meta.get("timeline") or "").strip()
        if not _timeline_matches(tms, tl):
            continue

        kind = str(meta.get("kind") or "").strip().lower()
        if kind in ("canon", "pin", "guide", "fixed"):
            continue

        if re.search(r"\[\s*kind\s*=\s*(pin|guide|fixed|canon)\s*\]", txt, flags=re.IGNORECASE):
            continue

        if _memory_conflicts_with_truth(txt, facts=facts):
            continue

        if _memory_conflicts_with_recent_emotion(txt, history=history):
            continue

        txt_dedupe = re.sub(r"\[[^\]]+\]", "", txt).strip()
        txt_key = _t_norm(txt_dedupe)[:180]

        if not txt_key:
            continue

        if txt_key in seen_local:
            continue
        seen_local.add(txt_key)

        if dedupe_bucket is not None:
            h = hashlib.sha1(txt_key.encode("utf-8")).hexdigest()
            if h in dedupe_bucket:
                continue
            dedupe_bucket.add(h)

        d2 = dict(d)
        d2["text"] = txt_dedupe[:320].rstrip()

        score = _score_long_memory_local(d2, prompt)

        if d in mongo_rows:
            score += 0.75

        meta2 = d2.get("meta") if isinstance(d2.get("meta"), dict) else {}
        mtags = meta2.get("tags")
        if isinstance(mtags, list) and mtags:
            score += 0.35

        if score <= 0:
            continue

        picked_scored.append((score, d2))

    if not picked_scored:
        return

    picked_scored.sort(key=lambda x: x[0], reverse=True)
    picked = [d for _, d in picked_scored[: int(limit or 4)]]

    bullets: List[str] = []
    for d in picked:
        txt = str(d.get("text") or "").strip()
        if not txt:
            continue
        bullets.append(f"- {txt}")

    if not bullets:
        return

    block = (
        "[MEMÓRIAS RELEVANTES]\n"
        "Use apenas como apoio factual e de coerência.\n"
        "Não sobrescreva o estado emocional estabelecido nas últimas interações.\n"
        "Não invente fatos quando houver memória explícita abaixo.\n"
        + "\n".join(bullets)
    )

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + block).strip()
    else:
        messages.append({
            "role": "system",
            "content": block,
        })
   
# ==========================================================
# BM25 (fallback leve)
# ==========================================================
_WORD_RE = re.compile(r"[\w\u00C0-\u017F']+", re.UNICODE)

def _tok(text: str) -> List[str]:
    stop = _domain_terms("stopwords")
    return [
        t.lower()
        for t in _WORD_RE.findall(text or "")
        if t.strip() and t.lower() not in stop
    ]
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

    ranked = [i for i in sorted(range(N), key=lambda i: scores[i], reverse=True) if scores[i] > 0]
    return ranked[: max(0, int(k))]


# ==========================================================
# Chunking semântico on-the-fly (RAG) - reduz tokens e melhora relevância
# ==========================================================
_SENT_SPLIT = re.compile(r"(?<=[\.\!\?...])\s+")

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

def _memory_narrative_weight(mem: Dict[str, Any], chunk: str, user_prompt: str) -> float:
    """
    Peso narrativo extra para priorizar memórias mais úteis ao roleplay.
    Usa vocabulário configurável em vez de listas hardcoded espalhadas.
    """
    score = 0.0

    meta = mem.get("meta") if isinstance(mem.get("meta"), dict) else {}
    text_full = str(mem.get("text") or "").strip()
    ch = str(chunk or "").strip().lower()
    up = _t_norm(user_prompt or "")

    kind = str(meta.get("kind") or "").strip().lower()
    if kind in {"summary", "soft", "memory"}:
        score += 0.10

    title = str(meta.get("title") or meta.get("key") or "").strip().lower()
    emotional_terms = _domain_terms("emotional")
    overlap_terms = _domain_terms("overlap")

    if _contains_any_term(title, emotional_terms):
        score += 0.18

    score += 0.05 * _count_matching_terms(ch, emotional_terms)

    for term in overlap_terms:
        if not term:
            continue
        if re.search(rf"\b{re.escape(term)}\b", up) and re.search(rf"\b{re.escape(term)}\b", ch):
            score += 0.08

    ts = _memory_timestamp(mem)
    if ts is not None:
        try:
            age_days = max(0.0, (time.time() - float(ts)) / 86400.0)
            if age_days <= 7:
                score += 0.10
            elif age_days <= 30:
                score += 0.06
            elif age_days <= 90:
                score += 0.03
        except Exception:
            pass

    if len(ch) >= 180:
        score += 0.06
    elif len(ch) < 60:
        score -= 0.05

    tfull = _t_norm(text_full)
    if _contains_any_term(tfull, emotional_terms):
        score += 0.10

    return score

def _inject_relevant_memories(
    shared_key: str,
    timeline: str,
    user_prompt: str,
    messages: List[Dict[str, str]],
    k: int = 4,
    *,
    dedupe_bucket: Optional[set] = None,
    facts: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
     BM25 em chunks (em vez do texto inteiro) para:
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
    hist = history if isinstance(history, list) else []

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

        if _memory_conflicts_with_truth(text_full, facts=facts):
            continue
        
        if _memory_conflicts_with_recent_emotion(text_full, history=hist):
            continue

        text_dedupe = re.sub(r"\[[^\]]+\]", "", text_full).strip()
        h_full = hashlib.sha1(text_dedupe.encode("utf-8")).hexdigest()

        if dedupe_bucket is not None and h_full in dedupe_bucket:
            continue

        if len(text_full) < 200:
            chunks = [text_full]
        else:
            chunks = _chunk_semantic(text_full, max_chars=520, max_chunks=8)
        if not chunks:
            continue

        for ch in chunks:
            chunk_docs.append(ch)
            chunk_map.append((m, ch, h_full))

    if not chunk_docs:
        return

    idxs = _bm25_topk(chunk_docs, user_prompt, k=max(int(k) * 3, 12))
    if not idxs:
        return

    ranked_candidates: List[Tuple[float, Dict[str, Any], str, str]] = []

    for ix in idxs:
        if 0 <= ix < len(chunk_map):
            m, ch, h_full = chunk_map[ix]
            extra_weight = _memory_narrative_weight(m, ch, user_prompt)
            ranked_candidates.append((extra_weight, m, ch, h_full))

    # ordena por peso narrativo extra (desc)
    ranked_candidates.sort(key=lambda x: x[0], reverse=True)

    selected: List[Tuple[Dict[str, Any], str, str]] = []
    seen_full: set = set()

    for _, m, ch, h_full in ranked_candidates:
        if h_full in seen_full:
            continue
        seen_full.add(h_full)
        selected.append((m, ch, h_full))
        if len(selected) >= int(k):
            break
    if not selected:
        return

    lines = [
        "[MEMÓRIAS RELEVANTES (BM25 - chunks)]",
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
            header += f" - {title}"
        lines.append(header)

        lines.append(str(ch or "").strip()[:320].rstrip())
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
    Injeta o CONTEXTO ATUAL ABSOLUTO da cena, priorizando a fonte de verdade
    principal do core:
      - 1. cena.*
      - 2. local_cena_atual / state.*
      - 3. chaves legadas *_atual

    Objetivo:
    - evitar disputa entre contexto paralelo e cena viva
    - impedir teleporte narrativo
    - não duplicar informações equivalentes
    """
    try:
        facts = cached_get_facts(usuario_key) or {}
        facts = _sync_intimacy_phase_facts(usuario_key, facts, timeline)
    except Exception:
        facts = {}

    def _pick_str(*values: Any) -> str:
        for v in values:
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    def _same(a: str, b: str) -> bool:
        return bool(a and b and _t_norm(a) == _t_norm(b))

    # ------------------------------------------------------
    # Fonte principal: cena viva
    # ------------------------------------------------------
    scene_local = _pick_str(
        facts.get("cena.local"),
        facts.get("local_cena_atual"),
        _fact_str(facts, "state.local"),
        facts.get("local_atual"),   # legado por último
    )

    scene_tempo = _pick_str(
        facts.get("cena.tempo"),
        facts.get("momento_atual"),  # legado / fallback
    )

    scene_acao = _pick_str(
        facts.get("cena.acao"),
    )

    companhia = _pick_str(
        facts.get("companhia_atual"),   # legado
        _fact_str(facts, "state.companhia"),
        _fact_str(facts, "companhia"),
    )

    if not any([scene_local, scene_tempo, scene_acao, companhia]):
        return

    lines: List[str] = []
    lines.append("[CONTEXTO ATUAL - NÃO ASSUMA MUDANÇAS AUTOMÁTICAS]")

    if scene_local:
        lines.append(f"Local atual: {scene_local}.")

    if scene_tempo:
        lines.append(f"Tempo atual: {scene_tempo}.")

    # só injeta ação se não for rótulo técnico inútil
    if scene_acao and _t_norm(scene_acao) not in {"transicao", "transição", "transition", "em andamento"}:
        lines.append(f"Situação atual: {scene_acao}.")

    # só injeta companhia se não duplicar local/situação por engano
    if companhia and not _same(companhia, scene_local) and not _same(companhia, scene_acao):
        lines.append(f"Companhia atual: {companhia}.")

    lines.append(
        "Mudanças de local, tempo ou situação só podem ocorrer se forem explicitamente iniciadas na narrativa."
    )

    texto = "\n".join(lines).strip()

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + texto).strip()
    else:
        messages.insert(0, {"role": "system", "content": texto})

def _inject_shared_soft_context(
    usuario_key: str,
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    max_items: int = 4,
    *,
    dedupe_bucket: Optional[set] = None,
    facts: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> None:
    mems = cached_list_memories(shared_key, limit=220)
    if not mems:
        return

    facts_live = facts if isinstance(facts, dict) else (cached_get_facts(usuario_key) or {})
    hist_live = history if isinstance(history, list) else cached_get_history(usuario_key, limit=40)

    soft: List[Dict[str, Any]] = []
    for m in mems:
        meta = m.get("meta") if isinstance(m.get("meta"), dict) else {}
        kind = str(meta.get("kind") or "").strip().lower()
        if kind in {"canon", "pin", "guide", "fixed"}:
            continue
        if not _memory_timeline_ok(meta, timeline):
            continue

        txt = str(m.get("text") or "").strip()
        if not txt:
            continue

        if _memory_conflicts_with_truth(txt, facts=facts_live):
            continue

        if _memory_conflicts_with_recent_emotion(txt, history=hist_live):
            continue

        if dedupe_bucket is not None:
            txt_dedupe = re.sub(r"\[[^\]]+\]", "", txt).strip()
            h = hashlib.sha1(txt_dedupe.encode("utf-8")).hexdigest()
            if h in dedupe_bucket:
                continue
            dedupe_bucket.add(h)

        soft.append(m)

    if not soft:
        return

    selected = soft[-max_items:] if len(soft) > max_items else soft

    lines = [
        "[MEMÓRIAS COMPARTILHADAS]",
        "Use só como coerência de fundo.",
        "",
    ]

    for i, m in enumerate(selected, 1):
        meta = m.get("meta") if isinstance(m.get("meta"), dict) else {}
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
    tl = _normalize_timeline(timeline)
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

_RE_MEM_DIRECTIVE = re.compile(r"(?im)^(?:#mem|[MEM])\s*(?:@(?P<mode>[a-zA-Z]+)(?P<n>\d+)?)?\s+(?P<expr>.+?)\s*$")
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
    Remove a linha de diretiva #mem/[MEM] do prompt do usuário e retorna:
    - prompt limpo (sem a diretiva)
    - spec dict: {"expr": str, "mode": str|None, "n": int|None}
    Observação: só considera diretiva quando a linha começa com #mem/[MEM].
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
                dt = datetime.datetime.fromisoformat(s.replace("Z","+00:00").replace(" ","T"))
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

def _normalize_memory_tags(tags: Any) -> List[str]:
    """
    Normaliza tags para lista curta, limpa e sem duplicatas.
    Aceita:
    - list[str]
    - string separada por vírgula
    - None
    """
    out: List[str] = []

    if tags is None:
        return out

    if isinstance(tags, str):
        raw = [t.strip() for t in tags.split(",")]
    elif isinstance(tags, (list, tuple, set)):
        raw = [str(t).strip() for t in tags]
    else:
        raw = [str(tags).strip()]

    seen = set()
    for t in raw:
        if not t:
            continue
        norm = _t_norm(t)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(t[:40])

    return out[:12]

def _infer_memory_tags(text: str, title: str = "") -> List[str]:
    """
    Extrai tags simples e úteis a partir do título/texto.
    Não tenta ser inteligente demais: só cria apoio de recuperação.
    """
    blob = _t_norm(f"{title} {text}")

    candidates = list(dict.fromkeys(
        list(_domain_terms("priority")) +
        list(_domain_terms("emotional")) +
        list(_domain_terms("event"))
    ))

    found: List[str] = []
    seen = set()

    for c in candidates:
        cc = str(c or "").strip()
        if not cc:
            continue
        if re.search(rf"\b{re.escape(_t_norm(cc))}\b", blob):
            key = _t_norm(cc)
            if key not in seen:
                seen.add(key)
                found.append(cc)

    return found[:10]
    

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
            if tok and re.search(rf"\b{re.escape(tok)}\b", hay):
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
    return hits[: max(1, min(3, len(hits)))]

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
    tags: Optional[List[str]] = None,
    source: str = "memory",
) -> None:
    txt = str(text or "").strip()
    if not txt:
        return

    k = str(kind or "memory").strip().lower()
    ttl = str(title or "").strip()
    tg = [str(x).strip() for x in (tags or []) if str(x).strip()]

    header = f"[MEMÓRIA AUXILIAR - {source.upper()}]"
    if k:
        header += f"\nTipo: {k}"
    if ttl:
        header += f"\nTítulo: {ttl}"
    if tg:
        header += f"\nTags: {', '.join(tg[:8])}"

    block = (
        f"{header}\n"
        "Use apenas como apoio de coerência.\n"
        "Não sobrescreva o estado emocional estabelecido nas últimas interações.\n"
        "Não cite literalmente esta memória.\n\n"
        f"{txt}"
    ).strip()

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        base = str(messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + block).strip()
    else:
        messages.append({"role": "system", "content": block})
def _inject_manual_memory_if_any(
    *,
    usuario_key: str,
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    spec: Optional[Dict[str, Any]],
    facts: Optional[Dict[str, Any]] = None,
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

    chosen = _select_memories(
        filtered,
        parsed,
        mode=spec.get("mode"),
        n=spec.get("n"),
    )
    if not chosen:
        return

    # injeta (no máximo 1 por turno por padrão; @lastN injeta N mas limitamos a 2)
    max_inject = 1
    mode = str(spec.get("mode") or "").strip().lower()
    if mode.startswith("last"):
        max_inject = max(1, min(2, int(spec.get("n") or 1)))

    injected = 0
    history = cached_get_history(usuario_key, limit=40)

    for mem in chosen[:max_inject]:
        mid = _memory_id(mem)
        if not _cooldown_allows(usuario_key, mid, latent=False):
            continue

        title, kind, txt = _memory_text_fields(mem)
        if not txt:
            continue

        # impede manual memory de competir com facts/canon do turno
        if _memory_conflicts_with_truth(txt, facts=facts):
            continue

        # impede regressão emocional contra o histórico recente
        if _memory_conflicts_with_recent_emotion(txt, history=history):
            continue

        tags = _parse_tags_from_memory(txt)
        _inject_memory_block(
            messages,
            kind=kind,
            title=title,
            text=txt,
            tags=tags,
            source="manual",
        )
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
    facts: Optional[Dict[str, Any]] = None,
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

    history = cached_get_history(usuario_key, limit=40)

    # prioriza a mais recente
    candidates.sort(key=lambda x: (x[0], len(x[1].get("text", ""))), reverse=True)

    for _, mem, _ in candidates[:6]:
        mid = _memory_id(mem)
        if not _cooldown_allows(usuario_key, mid, latent=True):
            continue

        title, kind, txt = _memory_text_fields(mem)
        if not txt:
            continue

        # impede latent memory de competir com facts/canon do turno
        if _memory_conflicts_with_truth(txt, facts=facts):
            continue

        # impede latent memory de reacender estados emocionais superados
        if _memory_conflicts_with_recent_emotion(txt, history=history):
            continue

        tags = _parse_tags_from_memory(txt)
        _inject_memory_block(
            messages,
            kind=kind,
            title=title,
            text=txt,
            tags=tags,
            source="latent",
        )
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

        v = v.replace(" ", "_")
        v = v.replace("não", "nao")

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

    #  NOVO - DINÂMICA 3.5 (estado comportamental seguro)
    base.setdefault("mood", "intensa")
    base.setdefault("energy", "energetica")
    base.setdefault("attitude", "equilibrada")
    base.setdefault("_last_success_pattern", "")
    base.setdefault("self_awareness", 0.30)  # <- LINHA OPCIONAL ADICIONADA

    # 4) Defaults mínimos (apenas se não existir)
    base.setdefault("mature_turns", 0)
    base.setdefault("intimacy_level", 0 if timeline == "universitaria" else 3)
    base.setdefault("consummated", False if timeline == "universitaria" else True)

    #  IMPORTANTE:
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

    base.setdefault("allows_touch", False if timeline == "universitaria" else True)
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
    #  DERIVADOS (para o prompt/continuidade) - SEM sobrescrever estados
    # ==========================================================
    global_v = _get_global_virginity_from_facts(facts)
    # _global_virginity é informativo (prompt/debug); por padrão NÃO governa o REL.
    base["_global_virginity"] = global_v

    #  Fallback inteligente:      
    # fora da universitaria, se por algum motivo virginity vier vazio,
    # tenta herdar do global quando válido.
    if timeline != "universitaria" and not base.get("virginity"):
        if global_v in ("virgem", "nao_virgem"):
            base["virginity"] = global_v

    # ==========================================================
    # RESET FORÇADO DA UNIVERSITÁRIA
    # ==========================================================
    # Se o botão "Forçar VIRGEM (Universitária)" foi usado,
    # este estado vence defaults, canon e derivados.
    if timeline == "universitaria" and bool((facts or {}).get("rel.force_virgin::universitaria")):
        base["virginity"] = "virgem"
        base["consummated"] = False
        base["intimacy_level"] = 0
        base["allows_penetration"] = False
        base["allows_extended_touch"] = False
        base["allows_mutual_relief"] = False
        base["allows_sleep_together"] = False

    # Primeira vez com Janio (derivado)
    base["_first_time_with_janio"] = _derive_rel_first_time_with_janio(timeline, base)

    # Regra mínima de consistência interna do REL:
    # se consumou com Janio, então não pode ficar "virgem" no relacionamento.
    # EXCEÇÃO: reset forçado da universitaria vence essa derivação.
    if not (timeline == "universitaria" and bool((facts or {}).get("rel.force_virgin::universitaria"))):
        if bool(base.get("consummated")):
            base["virginity"] = "nao_virgem"
            base["allows_penetration"] = True
            base.setdefault("allows_extended_touch", True)
            base.setdefault("allows_mutual_relief", True)

        # Regra de coerência:
        # se o relacionamento está "nao_virgem", então penetração não pode ficar False.
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
    Sincroniza REL com memória CANON de virgindade.

    Regra normal:
    - se existir CANON virginity=nao_virgem, isso governa o REL.

    Exceção:
    - se houver rel.force_virgin::universitaria=True,
      a timeline universitária fica travada como virgem e ignora canon antigo.
    """
    tl = _normalize_timeline(timeline)

    # ==========================================================
    # RESET FORÇADO DA UNIVERSITÁRIA
    # ==========================================================
    if tl == "universitaria" and bool((facts or {}).get("rel.force_virgin::universitaria")):
        rel["virginity"] = "virgem"
        rel["consummated"] = False
        rel["intimacy_level"] = 0
        rel["allows_penetration"] = False
        rel["allows_extended_touch"] = False
        rel["allows_mutual_relief"] = False
        return rel

    shared_key = _shared_key(user_id, tl)

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
            ts = m.get("ts") or meta.get("ts")

            if canon_ts is None:
                canon_val, canon_ts = v, ts
            else:
                try:
                    if ts and ts > canon_ts:
                        canon_val, canon_ts = v, ts
                except Exception:
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
# INTIMACY + GUARDRAILS (Ação 5 - Regex Generalizadas)
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
# Mantém o nome esperado pelo resto do código.

_USER_NAME_ALIASES = ("janio", "arthur")
_THIRD_PARTY_GENERIC_TERMS = (
    "ele", "ela",
    "o cara", "o homem", "o rapaz", "o garoto",
    "aquele cara", "um cara",
)

_META_REVEAL_VERBS = (
    "revela", "mostra", "exibe", "vaza", "imprime", "quote",
    "copia", "cola", "transcreve", "descreve", "repete",
)

_META_TARGET_TERMS = (
    "prompt", "system", "instrucao", "instrução", "persona",
    "regras", "regra", "policy", "guardrail", "guardrails",
    "mensagem de sistema", "texto do sistema",
)

def _build_alt_pattern_str(items: tuple[str, ...] | list[str]) -> str:
    safe = []
    for x in items:
        s = str(x or "").strip()
        if s:
            safe.append(re.escape(s))
    return "|".join(safe)

_USER_ALIASES_PATTERN = _build_alt_pattern_str(_USER_NAME_ALIASES)
_THIRD_PARTY_GENERIC_PATTERN = _build_alt_pattern_str(_THIRD_PARTY_GENERIC_TERMS)
_META_REVEAL_PATTERN = _build_alt_pattern_str(_META_REVEAL_VERBS)
_META_TARGET_PATTERN = _build_alt_pattern_str(_META_TARGET_TERMS)

_RE_PLACEHOLDER_REVEAL = re.compile(
    rf"(?is)\b(?:{_META_REVEAL_PATTERN})\b.{{0,120}}\b(?:{_META_TARGET_PATTERN})\b"
)

_RE_META_DIRECT_ASK = re.compile(
    rf"(?is)\b(?:qual|quais|mostra|me diz|me fala|quero ver|manda|envia)\b.{{0,120}}\b(?:{_META_TARGET_PATTERN})\b"
)

def _meta_leak(texto: str) -> bool:
    t = _t_norm(texto)
    if not t:
        return False
    return bool(
        _RE_PLACEHOLDER_REVEAL.search(t)
        or _RE_META_DIRECT_ASK.search(t)
    )

# ----------------------------------------------------------
# Offscreen inventado (geral)
# ----------------------------------------------------------
_RE_OFFSCREEN_MSG = re.compile(
    r"\b("
    r"whatsapp|sms|dm|direct|telegram|mensagem|notificacao|notificação|"
    r"liga\s*para|ligou\s*para|telefonou|"
    r"audio|áudio|chamada|ligacao|ligação"
    r")\b",
    re.IGNORECASE,
)

_RE_OFFSCREEN_PASTE_HINT = re.compile(
    r"\b("
    r"mensagem:|whatsapp:|sms:|dm:|"
    r"print|segue a mensagem|segue o texto|"
    r"transcrevendo|copiei aqui|colei aqui|"
    r"o texto diz|a mensagem diz"
    r")\b",
    re.IGNORECASE,
)

def _looks_like_user_pasted_message(contexto: str) -> bool:
    t = _t_norm(contexto or "")
    if not t:
        return False
    return bool(_RE_OFFSCREEN_PASTE_HINT.search(t))

def _looks_like_offscreen_message_reference(texto: str) -> bool:
    t = _t_norm(texto or "")
    if not t:
        return False
    return bool(_RE_OFFSCREEN_MSG.search(t))

# ----------------------------------------------------------
# Autoria / voz (ROBUSTO)
# ----------------------------------------------------------
# Contrato:
# - Mary NÃO fala pelo usuário nem por terceiros.
# - Mary pode observar ações externas, mas não escrever fala alheia.
# - Mary também não deve atribuir pensamentos/decisões internas ao usuário/terceiros.

_RE_USER_2P_ACTION = re.compile(
    r"\b(voc[eê]|vc|tu)\b.{0,22}\b("
    r"puxa|beija|toca|agarra|diz|fala|sussurra|encosta|coloca|empurra|leva|"
    r"abre|fecha|entra|sai|segura|deita|vira|pede|decide|resolve|escolhe"
    r")\b",
    re.IGNORECASE,
)

_RE_OTHER_SPEAKER_TAG = re.compile(
    r"(?mi)^\s*(?!mary\b)([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]{1,30})\s*:\s+"
)

_RE_QUOTED_ATTRIBUTION = re.compile(
    r"(?i)"
    r"(\"[^\"]{2,}\"|\"[^\"]{2,}\")"
    r"\s*[,\---]\s*"
    r"(?:diz|disse|fala|falou|responde|respondeu|pergunta|perguntou|"
    r"sussurra|sussurrou|comenta|comentou|murmura|murmurou|provoca|provocou)\s+"
    r"(?!mary\b)[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-Za-zÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç]{1,30}\b"
)

_RE_THIRD_PARTY_QUOTE_BEFORE = re.compile(
    rf"(?is)\b(?:{_THIRD_PARTY_GENERIC_PATTERN}|{_USER_ALIASES_PATTERN})\b[^\n\"]{{0,160}}\"[^\n\"]{{2,}}\""
)

_RE_THIRD_PARTY_QUOTE_AFTER = re.compile(
    rf"(?is)\"[^\n\"]{{2,}}\"[^\n]{{0,60}}\b(?:{_THIRD_PARTY_GENERIC_PATTERN}|{_USER_ALIASES_PATTERN})\b"
)

_RE_INTERNAL_STATE = re.compile(
    r"\b("
    r"pensa|pensei|pensou|acha|achei|achou|imagina|imaginei|imaginou|"
    r"quer|queria|quis|deseja|desejava|"
    r"sente|sentiu|sentia|"
    r"decide|decidiu|resolve|resolveu|escolhe|escolheu"
    r")\b",
    re.IGNORECASE,
)

_RE_USER_ACTION_CONTEXT_OK = re.compile(
    r"(quando|enquanto|se|caso|depois\s+que|antes\s+que)[\s:,\---]*$",
    re.IGNORECASE,
)

_RE_USER_NAME_ALIASES = re.compile(
    rf"\b(?:{_USER_ALIASES_PATTERN})\b",
    re.IGNORECASE,
)

_RE_USER_ALIAS_AS_SUBJECT = re.compile(
    rf"(?i)\b(?:{_USER_ALIASES_PATTERN})\b\s*(?:,|\-|-|-)?\s*"
    r"\b("
    r"pensa|pensou|acha|achou|imagina|imaginou|"
    r"quer|queria|quis|deseja|desejava|"
    r"sente|sentiu|sentia|"
    r"decide|decidiu|resolve|resolveu|escolhe|escolheu"
    r")\b"
)

_RE_SECOND_PERSON_INTERNAL = re.compile(
    r"\b(voc[eê]|vc|tu)\b.{0,18}\b("
    r"pensa|acha|imagina|quer|deseja|sente|decide|resolve|escolhe"
    r")\b",
    re.IGNORECASE,
)

def _has_user_action_violation(texto: str) -> bool:
    t = _t_norm(texto or "")
    if not t:
        return False

    if _RE_OTHER_SPEAKER_TAG.search(t):
        return True
    if _RE_QUOTED_ATTRIBUTION.search(t):
        return True
    if _RE_THIRD_PARTY_QUOTE_BEFORE.search(t):
        return True
    if _RE_THIRD_PARTY_QUOTE_AFTER.search(t):
        return True
    if _RE_SECOND_PERSON_INTERNAL.search(t):
        return True

    for m in _RE_USER_2P_ACTION.finditer(t):
        start = m.start()
        prefix = t[max(0, start - 64):start].lower()
        if _RE_USER_ACTION_CONTEXT_OK.search(prefix.strip()):
            continue
        return True

    if _RE_USER_ALIAS_AS_SUBJECT.search(t):
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
# Regressão de fase (novo) - aumenta realismo sem mexer no prompt
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

# ==========================================================
#  ORGASMO DA MARY POR TURNOS (sensação dela, máx 4)
# ==========================================================

_RE_SEX_ACTIVE = re.compile(
    r"\b("
    r"boca\s+se\s+fecha|chupo|chupando|boquete|"
    r"pau|p[eê]nis|rola|"
    r"meter|metendo|penetr|"
    r"bucet|vagin|cl[ií]tor|"
    r"goz|orgasmo|cl[ií]max|"
    r"trem(e|endo)|contra[ií]|espasm|"
    r")\b",
    re.IGNORECASE,
)

def _mary_sex_is_active(user_text: str, mary_text: str) -> bool:
    """Heurística: sexo realmente em andamento (não só flerte)."""
    t = (mary_text or "").strip()
    u = (user_text or "").strip()
    if not t and not u:
        return False
    blob = f"{u}\n{t}"
    return bool(_RE_SEX_ACTIVE.search(blob))


def _mary_orgasm_fact_keys(timeline: str) -> tuple[str, str]:
    """
    Guarda estado por timeline:
    - orgasm.mary.active::<tl> : bool
    - orgasm.mary.turns::<tl>  : int
    """
    tl = (timeline or "").strip() or "default"
    return (f"orgasm.mary.active::{tl}", f"orgasm.mary.turns::{tl}")


def _mary_phase_from_turns(turns: int) -> int:
    """
    Mapeia turnos -> fase da Mary.
    Ajuste fino aqui se quiser.
    primeiro turno de sexo: fase 2 (ato começou)
    segundo turno: fase 3 (limiar)
    terceiro/quarto: fase 4 (clímax)
    """
    t = max(0, int(turns or 0))
    if t <= 0:
        return 0
    if t == 1:
        return 2
    if t == 2:
        return 3
    return 4
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
    Motor estável de progressão.

    - Nunca salta mais de 1 fase.
    - Pode regredir 1 fase se houver desaceleração real.
    - Não força clímax sem sinal coerente.
    """

    try:
        p = int(current_phase or 0)
    except Exception:
        p = 0

    p = max(0, min(int(MAX_INTIMACY_PHASE), p))

    ut = _t_norm(user_text or "")
    at = _t_norm(texto or "")

    # ----------------------------------------------------------
    # 1) Desaceleração real
    # ----------------------------------------------------------
    if _user_requests_slowdown(user_text or ""):
        if _slowdown_is_intensifier(ut, at, phase=p, engine_meta=engine_meta):
            return p
        return max(0, p - 1)

    # ----------------------------------------------------------
    # 2) Avanço natural
    # ----------------------------------------------------------
    if _should_advance_phase(
        p,
        ut,
        at,
        engine_meta=engine_meta,
    ):
        next_p = p + 1
        return min(next_p, int(MAX_INTIMACY_PHASE))

    return p


def _slowdown_is_intensifier(ut: str, at: str, *, phase: int, engine_meta: Any = None) -> bool:
    """
    Detecta quando 'devagar'/'calma' está sendo usado como intensificador erótico
    (manter/continuar) e não como pedido de recuo/pausa.
    """
    # Se já está alto (fase 3+), 'devagar' costuma ser direção de ritmo, não recuo.
    # Ainda assim, se houver palavras de "para/espera/não", aí é recuo.
    if re.search(r"\b(para|pare|espera|pausa|calma\s+a[ií]|segura|não\s+continua|não\s+vai)\b", ut):
        return False

    # Indicadores fortes de continuação/intensificação
    if re.search(r"\b(não\s+para|continua|vai|assim|isso|mais|bem\s+assim|desse\s+jeito)\b", ut):
        return True

    # Se o próprio texto da Mary descreve continuidade física intensa, tratar como ritmo, não recuo
    if re.search(r"\b(ritmo|cadência|mais\s+devagar|diminuo\s+o\s+ritmo|acelero|pauso\s+e\s+volto)\b", at):
        return True

    # Sinal meta do engine (se você quiser usar): forced_variation pode pedir mudança de ritmo
    try:
        if isinstance(engine_meta, dict) and engine_meta.get("forced_variation") in ("mudanca_ritmo", "pacing"):
            return True
    except Exception:
        pass

    # Heurística por fase:
    # - fase 0/1: 'devagar' pode ser recuo real, então não forçamos intensificador
    # - fase 2+: tende a ser comando de ritmo -> intensificador
    return bool(phase >= 2)

# ==================================================================
# 1 DETECÇÃO DE CONTEÚDO EXPLÍCITO
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
    "cabaço",      # hímen  
    
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
def _build_explicit_regex(stems: list[str]) -> re.Pattern:
    parts = []
    for s in stems:
        s = (s or "").strip()
        if not s:
            continue

        # suporta stems com espaço ("vai e vem")
        if " " in s:
            parts.append(re.escape(s))
        else:
            parts.append(re.escape(s) + r"\w*")

    pattern = r"\b(?:" + "|".join(parts) + r")\b"
    return re.compile(pattern, re.IGNORECASE)

_RE_EXPLICIT_SEX = _build_explicit_regex(_EXPLICIT_STEMS)
    

def _is_explicit(texto: str) -> bool:
    """
    Retorna True se o texto contém descrição direta de ato sexual explícito.
    
    Exemplos:
    - "Ele me fode com vontade" -> True
    - "Meu pau entra dentro" -> True
    - "Estou gozando muito" -> False (orgasmo, não ato explícito)
    - "Beijo apaixonado" -> False
    """
    t = _t_norm(texto)
    if not t:
        return False
    return bool(_RE_EXPLICIT_SEX.search(t))


# ==================================================================
#  ORGASMO - Verbalização EXPLÍCITA (Mary) + Sinal de Clímax (heurístico)
# ==================================================================

# 1) Verbalização EXPLÍCITA: precisa conter "goz*" ou "orgasmo" (sem eufemismo)
_RE_MARY_ORGASM_DECLARATION = re.compile(
    r"\b(?:"
    # raiz "goz" (PT-BR)
    r"(?:eu\s+)?goz(?:o|ei|ando|ar|ava|aria|asse|ou)|"
    r"(?:t[oô]|to|t[aá]|estou)\s+goz(?:ando)?|"
    r"vou\s+gozar|"
    r"(?:quase|t[oô]|to|estou)\s+perto\s+de\s+gozar|"
    r"(?:eu\s+)?(?:já\s+)?(?:t[oô]|to|estou)\s+(?:gozando)|"
    # palavra direta
    r"orgasmo|"
    r"(?:vou\s+)?(?:ter\s+)?(?:um\s+)?orgasmo|"
    r"(?:t[oô]|to|estou)\s+(?:em\s+)?orgasmo|"
    # opcional: ejacular (se você usa isso no texto da Mary)
    r"(?:eu\s+)?ejacul(?:o|ei|ando|ar)|"
    r"(?:t[oô]|to|estou)\s+ejacul(?:ando)?|"
    r"vou\s+ejacular"
    r")\b",
    re.IGNORECASE,
)

def _has_mary_orgasm_declaration(texto: str) -> bool:
    """
    True => Mary verbalizou orgasmo de forma explícita:
    "vou gozar", "tô gozando", "eu gozei", "orgasmo" etc.
    """
    if not texto:
        return False
    return bool(_RE_MARY_ORGASM_DECLARATION.search(texto))


# 2) Score de "sinal de clímax" (heurístico, NÃO é a verbalização)
#    -> aqui a gente pega sinais corporais e descrições típicas.
#    -> NÃO inclui "cheguei lá" / "tô no auge" etc.
def _orgasm_signal_score(texto: str) -> int:
    if not texto:
        return 0

    t = (texto or "").lower()

    signals = (
        # corpo / contrações
        "espasmo", "espasmos",
        "contraç", "contraindo", "contrações",
        "treme", "tremendo", "tremor",
        "arqueia", "arqueio", "arco",
        "pernas bambas", "perna bamba",
        "perde o controle", "perdendo o controle",
        "onda", "ondas",
        "puls", "pulsando", "pulsar",
        "latej", "latejando",
        "me atravessa", "atravessa como um raio",
        "explod", "explodindo",
        "desaba", "desabando",
        "choque", "choque de prazer",
        "convuls", "convulsão",
        "grito", "gemido alto", "gemendo forte",
        # "clímax" pode existir como palavra, mas não é obrigatório
        "clímax", "climax",
    )

    score = 0
    for s in signals:
        if s in t:
            score += 1

    # reforço: texto longo descrevendo pico costuma ser mais confiável
    if len(t) >= 220:
        score += 1

    return score


# 3) DETECÇÃO DE CLÍMAX (heurística, não determinística)
def _detect_climax_signal(
    texto: str,
    user_text: str,
    *,
    nsfw_on: bool,
    phase: int,
) -> bool:
    """
    Detecta "clímax acontecendo" de forma heurística.
    Serve para: se houver clímax, exigir verbalização explícita da Mary.
    """
    if not nsfw_on:
        return False

    t = (texto or "").strip()
    if not t:
        return False

    # Não tenta detectar cedo demais com texto curto
    if len(t) < 60 and phase < 3:
        return False

    # Se ela já verbalizou, não precisa forçar nada (não gera violação)
    if _has_mary_orgasm_declaration(t):
        return True

    score = _orgasm_signal_score(t)

    u = (user_text or "").lower()

    # Se o usuário explicitamente pede clímax/gozar, isso aumenta confiança
    user_boost = 0
    if phase >= 3:
        for kw in ("goza", "gozou", "gozar", "orgasmo", "clímax", "climax", "finaliza", "finalizar"):
            if kw in u:
                user_boost += 1

    score_total = score + user_boost

    # thresholds (ajustados pra não dar falso positivo)
    if phase >= 4:
        # exige pelo menos 2 sinais corporais OU user_boost
        return score >= 2 or user_boost >= 1
    if phase >= 3:
        return score_total >= 3  # exige mais sinal antes do pico
    return False


def _validate_orgasm_verbalization(text: str, violations: List[str]) -> bool:
    if "mary_nao_verbalizou_orgasmo" not in (violations or []):
        return True

    if _has_mary_orgasm_declaration(text):
        return True

    if _orgasm_signal_score(text) >= 4:
        return True

    return False

def _did_mary_orgasm(texto: str, phase: int) -> bool:
    """
    Confirma orgasmo consumado da Mary.
    """
    if int(phase or 0) < 4:
        return False

    t = _t_norm(texto or "")
    if not t:
        return False

    if _has_mary_orgasm_declaration(t):
        return True

    return _orgasm_signal_score(t) >= 4


def _already_committed_orgasm(facts: Dict[str, Any], timeline: str) -> bool:
    tl = _normalize_timeline(timeline)
    return bool(
        facts.get(f"mary.orgasm::{tl}")
        or facts.get("mary.orgasm")
    )


def _commit_mary_orgasm(
    *,
    usuario_key: str,
    timeline: str,
    texto: str,
    phase: int,
) -> bool:
    """
    Se Mary realmente chegou ao clímax, persiste esse estado e empurra para aftercare.
    """
    if not _did_mary_orgasm(texto, phase):
        return False

    facts_now = cached_get_facts(usuario_key) or {}
    if _already_committed_orgasm(facts_now, timeline):
        return False

    tl = _normalize_timeline(timeline)

    try:
        set_fact_safe(usuario_key, f"mary.orgasm::{tl}", True, {"fonte": "orgasm_commit"})
        set_fact_safe(usuario_key, "mary.orgasm", True, {"fonte": "orgasm_commit"})
        set_fact_safe(usuario_key, f"intimacy.phase::{tl}", 5, {"fonte": "orgasm_commit"})
        set_fact_safe(usuario_key, "intimacy.phase", 5, {"fonte": "orgasm_commit"})
        set_fact_safe(usuario_key, "fase_intima", "aftercare", {"fonte": "orgasm_commit"})
    except Exception:
        return False

    return True

# ---------------------------------------------------------
# HYBRID (heurística + LLM) - classificação "na borda"
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

_RE_INTENSE_CUES = re.compile(
    r"\b(agora|mais forte|mais rapido|nao aguento|preciso agora|sem parar|me faz|me pega|quero)\b",
    re.IGNORECASE,
)

def _response_is_romancey(texto: str) -> bool:
    #  DESATIVADO: Emoção + sexo é permitido
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
# Densidade sensorial (leve) - ajuda a calibrar
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
    if len(t) < 160:
        return hits == 0
    return hits < 2


# ----------------------------------------------------------
#  NOVA PROGRESSÃO ÍNTIMA REAL (tensão crescente)
# ----------------------------------------------------------

_RE_AROUSAL = re.compile(
    r"\b(pau duro|duro na|calcinha molhada|molhada|mamilos? endurecid|abrindo o ziper|tirando a roupa|entre as pernas)\b",
    re.I
)

_RE_ACTIVE_SEX = re.compile(
    r"\b(vai e vem|rebola|aperta|masturb|esfrega|ritmo|geme|ofega|quadril)\b",
    re.I
)

_RE_PRE_CLIMAX = re.compile(
    r"\b(quase|t[oô] no limite|n[aã]o aguento|vai me fazer|perdendo o controle|arqueio|espasmo|contra[cç][aã]o)\b",
    re.I
)

_RE_CLIMAX_BODY = re.compile(
    r"\b(explode|onda intensa|corpo trava|treme inteiro|desaba|espasmos fortes)\b",
    re.I
)


def _intimacy_level(user_text: str, texto: str) -> int:
    s = _t_norm((user_text or "") + "\n" + (texto or ""))
    if not s:
        return 0

    if _RE_CLIMAX_BODY.search(s):
        return 4

    if _RE_PRE_CLIMAX.search(s):
        return 3

    if _RE_ACTIVE_SEX.search(s):
        return 2

    if _RE_AROUSAL.search(s):
        return 1

    return 0


def _user_explicitly_allows_climax(user_text: str) -> bool:
    ut = _t_norm(user_text)
    if not ut:
        return False

    return bool(
        re.search(
            r"\b(pode|deixa|quero)\b.{0,20}\b(gozar|climax|orgasmo)\b",
            ut,
        )
    )


def _cap_next_phase(current_phase: int) -> int:
    try:
        p = int(current_phase or 0)
    except Exception:
        p = 0
    return max(0, min(MAX_INTIMACY_PHASE, p + 1))

def _should_advance_phase(
    current_phase: int,
    user_text: str,
    texto: str,
    *,
    engine_meta: Any = None,
    **_kw: Any,
) -> bool:
    """
    Progressão íntima guiada por conteúdo real.

    0 -> 1 : excitação física visível
    1 -> 2 : ação sexual ativa
    2 -> 3 : pré-clímax / perda de controle
    3 -> 4 : clímax físico coerente
    4 -> 5 : aftercare / desaceleração
    """

    try:
        p = int(current_phase or 0)
    except Exception:
        p = 0

    ut = _t_norm(user_text or "")
    at = _t_norm(texto or "")
    lvl = _intimacy_level(ut, at)

    if p <= 0:
        return lvl >= 1

    if p == 1:
        return lvl >= 2

    if p == 2:
        return lvl >= 3

    if p == 3:
        # fase 4 só com sinal de clímax realmente forte
        # evita subir só por intensidade alta genérica
        if lvl < 4:
            return False

        # se já há declaração explícita ou forte sinal corporal, sobe
        if _has_mary_orgasm_declaration(at):
            return True

        if _orgasm_signal_score(at) >= 3:
            return True

        return False

    if p == 4:
        return _user_signals_aftercare(user_text)

    return False
# ==========================================================
# DESVIO CURTO (fidelidade soft) - helpers
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
#  PATCH 0 - helpers anti-truncamento / anti-parêntese quebrado
# (cola abaixo de _intimate_advance_detected)
# ==========================================================

_RE_TRAILING_OPEN_PAREN = re.compile(r"\(\s*$")
_RE_UNFINISHED_PAREN_FRAGMENT = re.compile(r"\(\s*[^\)]{0,40}$")  # ex: "(Vou", "(Deus, ele..."
_RE_MULTI_SPACE_END = re.compile(r"[ \t]+$")

def _extract_finish_reason_and_usage(resp: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    fr: Optional[str] = None
    usage: Dict[str, Any] = {}

    try:
        if not isinstance(resp, dict):
            return fr, usage

        usage = resp.get("usage") or {}

        choices = resp.get("choices")
        if isinstance(choices, list) and choices:
            c0 = choices[0] or {}
            if isinstance(c0, dict):
                fr = c0.get("finish_reason") or c0.get("native_finish_reason")

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
        if re.search(r"(\.\.\.|...)\s*$", t):
            t = t + ")"
        else:
            t = t + " ...)"

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
#  FORMAT GUARD (flexível; sem estrutura fixa)
# ==========================================================

def _build_context_for_guard(usuario_key: str, prompt: str) -> str:
    """
    Contexto recente para detecção de:
    - mensagens coladas
    - offscreen inventado
    - contradição grave de cena

    Inclui:
    - local/tempo/ação atuais
    - últimas mensagens do usuário
    - prompt atual
    """
    parts: List[str] = []

    # ----------------------------------------------------------
    # facts atuais da cena
    # ----------------------------------------------------------
    try:
        facts = cached_get_facts(usuario_key) or {}
    except Exception:
        facts = {}

    try:
        local = (
            facts.get("cena.local")
            or facts.get("local_cena_atual")
            or facts.get("state.local")
            or ""
        )
        tempo = facts.get("cena.tempo") or ""
        acao = facts.get("cena.acao") or ""
        locked = facts.get("cena.locked")
    except Exception:
        local, tempo, acao, locked = "", "", "", None

    if local:
        parts.append(f"local: {str(local).strip()}")
    if tempo:
        parts.append(f"tempo: {str(tempo).strip()}")
    if acao:
        parts.append(f"acao: {str(acao).strip()}")
    if locked is not None:
        parts.append(f"locked: {bool(locked)}")

    # ----------------------------------------------------------
    # histórico recente do usuário
    # ----------------------------------------------------------
    try:
        hist = cached_get_history(usuario_key, limit=200) or []
    except Exception:
        hist = []

    last_users: List[str] = []
    for d in hist[-12:]:
        if not isinstance(d, dict):
            continue
        u = (d.get("mensagem_usuario") or "").strip()
        if u:
            last_users.append(u)

    if last_users:
        parts.append("[historico_usuario]")
        parts.extend(last_users)

    # ----------------------------------------------------------
    # prompt atual
    # ----------------------------------------------------------
    if prompt:
        parts.append("[prompt_atual]")
        parts.append(str(prompt).strip())

    return "\n".join(parts).strip()


# ==========================================================
#  AUTORIZAÇÃO EXPLÍCITA - orgasmo do USUÁRIO
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
            r"me\s+fa[cç]a\s+gozar|"
            r"eu\s+vou\s+gozar|"
            r"vou\s+gozar|"
            r"to\s+perto\s+de\s+gozar"
            r")\b",
            user_text.lower(),
        )
    )
# ==========================================================
# TERCEIROS - DETECÇÃO HIERÁRQUICA (compacta)
# ==========================================================

_THIRD_PARTY_PATTERNS: Dict[int, re.Pattern] = {
    1: re.compile(
        r"\b("
        r"barman|bartender|barista|gar[cç]om|gar[cç]onete|atendente|"
        r"seguran[cç]a|dj|m[uú]sico|instrutor|professor|personal|"
        r"cara|homem|rapaz|garoto|estrangeiro|moreno|sujeito|"
        r"outro\s+cara|aquele\s+cara|"
        r"olha(r)?\s+pra\s+ele|sorri(r)?\s+pra\s+ele|encara(r)?\s+ele|"
        r"flerta(r)?|cantada|convite|provoca(r)?|"
        r"dan[cç]a(r)?\s+com|"
        r"ele\s+me\s+olha|ele\s+me\s+chama"
        r")\b",
        re.IGNORECASE,
    ),
    2: re.compile(
        r"\b("
        r"ele\s+me\s+beija|ele\s+me\s+beijou|beijar\s+ele|"
        r"ele\s+encosta|ele\s+me\s+toca|ele\s+me\s+pega|ele\s+me\s+puxa|"
        r"m[aã]o\s+dele|m[aã]os\s+dele|"
        r"m[aã]os?\s+(sub(em|indo)|deslizam|entram|apertam)|"
        r"decote|seios?|peitos?|mamil|"
        r"por\s+baixo\s+da\s+roupa|por\s+dentro|"
        r"tirar\s+.*roupa|abrir\s+.*roupa|"
        r"calcinha|suti[aã]|"
        r"encostar\s+.*(entre\s+as\s+pernas|virilha)|"
        r"volume\s+ro[cç]a|duro\s+na\s+minha\s+.*|"
        r"penetra[cç][aã]o|penetrar|meter|foder|chupar|boquete|"
        r"buceta|vagina|clit[oó]ris|pau|p[eê]nis|anal"
        r")\b",
        re.IGNORECASE,
    ),
    3: re.compile(
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
    ),
}

def _third_party_signal_level(text: str) -> int:
    """
    Níveis:
    0 = nada
    1 = presença/interesse
    2 = avanço íntimo
    3 = fuga/isolamento
    """
    if not text:
        return 0

    t = str(text).lower()

    # avalia do nível mais alto para o mais baixo
    for level in (3, 2, 1):
        pattern = _THIRD_PARTY_PATTERNS[level]
        if pattern.search(t):
            return level

    return 0


def _third_party_deviation(text: str) -> bool:
    """
    Compatibilidade com o código antigo:
    retorna True se houver qualquer sinal relevante de terceiros.
    """
    return _third_party_signal_level(text) >= 1
# ==========================================================
# CLIMAX VERBALIZATION (SOFT HINT - SEM VIOLAÇÃO)
# ==========================================================

def _should_suggest_climax_verbalization(texto: str, phase: int) -> bool:
    """
    Não gera violação.
    Apenas detecta se está no pico e ainda não houve declaração explícita.
    """
    if int(phase or 0) < 4:
        return False

    t = (texto or "").lower()

    # já verbalizou?
    if "goz" in t or "orgasmo" in t:
        return False

    # está claramente em pico físico?
    peak_signals = (
        "espasmo",
        "treme",
        "explode",
        "onda intensa",
        "convuls",
        "perdendo o controle",
    )

    return any(s in t for s in peak_signals)
# ==========================================================
# TERCEIROS - CLASSIFICAÇÃO DE LOCAIS
# ==========================================================

#  Locais URBANOS / PLAUSÍVEIS (não implica permissão moral)
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

#  Locais PERIGOSOS (isolamento, risco físico)
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

#  Convites vagos (dependem de confirmação de destino)
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
[ FORÇA DE ORGASMO - FASE {phase}]
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
    Validador mínimo para repair.

    Só detecta:
    - vazio
    - meta-fala (modelo falando como IA)
    - contradição grave de cena

    Todo o resto passa direto.
    """

    t = (texto or "").strip()
    out: List[str] = []

    # ----------------------------------------------------------
    # 1 vazio
    # ----------------------------------------------------------
    if not t:
        out.append("vazio")
        return out

    t_lower = t.lower()

    # ----------------------------------------------------------
    # 2 meta-fala (IA vazando sistema)
    # ----------------------------------------------------------
    meta_patterns = (
        r"\bcomo ia\b",
        r"\bcomo assistente\b",
        r"\bcomo modelo de linguagem\b",
        r"\bn[aã]o posso ajudar\b",
        r"\bn[aã]o posso continuar\b",
        r"\bopenai\b",
        r"\bpol[ií]tica de conte[uú]do\b",
        r"\bsou uma ia\b",
        r"\bn[aã]o tenho corpo\b",
    )

    if any(re.search(p, t_lower) for p in meta_patterns):
        out.append("meta_fala")

    # ----------------------------------------------------------
    # 3 contradição grave de cena
    # ----------------------------------------------------------
    ctx = (ctx_lower or "").lower()

    if ctx:
        m_local = re.search(r"(?m)^\s*local:\s*(.+?)\s*$", ctx)
        local_ctx = m_local.group(1).strip().lower() if m_local else ""

        if local_ctx:
            jump_patterns = (
                r"\bentro no bar\b",
                r"\bestou na academia\b",
                r"\bchego na academia\b",
                r"\bentro no carro\b",
                r"\bsaio do quarto\b",
                r"\bvou embora\b",
                r"\bsaio daqui\b",
            )

            jumped = any(re.search(p, t_lower) for p in jump_patterns)

            # sinais mínimos de permanência/continuidade no mesmo espaço
            stay_patterns = (
                r"\bcontinuo aqui\b",
                r"\bpermaneço aqui\b",
                r"\baqui mesmo\b",
                r"\bno mesmo lugar\b",
                r"\bsem sair daqui\b",
            )

            stayed = any(re.search(p, t_lower) for p in stay_patterns)

            if jumped and not stayed:
                out.append("contradicao_cena")

    return list(dict.fromkeys(out))


# ==========================================================
# SCORING INVISÍVEL (estilo) + CONFIANÇA (auto-calibração)
# ==========================================================
# ========================================================
#  CRÍTICAS (sempre rejeitam)
# ========================================================
CRITICAL_VIOLATIONS = {
    "vazio",
    "meta_fala",
    "contradicao_cena",
}

# ========================================================
#  ALTAS (mantidas só por compatibilidade)
# ========================================================
HIGH_TIER_VIOLATIONS = set()

# ========================================================
#  SUAVES (apenas logging; nunca rejeitam)
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
    return texto.strip() if texto else ""

def _render_pendencia_block(facts: Dict[str, Any]) -> str:
    try:
        facts = facts or {}
        rel = facts.get("rel") if isinstance(facts.get("rel"), dict) else {}
        pendencia = str(rel.get("pendencia", "") or "").strip()
    except Exception:
        pendencia = ""

    if not pendencia:
        return ""

    return f"""
[PENDÊNCIA NARRATIVA ATIVA]
Existe um assunto em aberto que Mary não deve ignorar completamente:
{pendencia}

Direção:
- Mary pode tentar resolver, esclarecer, provocar, contornar ou confessar parcialmente.
- Não precisa mencionar isso em toda resposta.
- Mas o assunto continua vivo no fundo emocional da cena.
- Se houver abertura natural, Mary pode puxar esse tema.
- Não transformar isso em exposição mecânica ou explicação forçada.
""".strip()


def _repair_instruction(violations: List[str]) -> str:
    """
    Repair objetivo e sensorial.
    Corrige:
    - vazio
    - meta_fala
    - contradicao_cena
    - estilo_mecanico
    """
    v = set(violations or [])
    bullets: List[str] = []

    if "vazio" in v:
        bullets.append(
            "Escreva uma resposta completa, viva e totalmente em personagem como Mary. "
            "Entregue conteúdo narrativo imediato, sem resumo, sem lacuna e sem frase interrompida."
        )

    if "meta_fala" in v:
        bullets.append(
            "Remova qualquer fala sobre IA, assistente, modelo, regra, sistema, prompt ou explicação técnica. "
            "Seja apenas Mary, falando de dentro da cena."
        )

    if "contradicao_cena" in v:
        bullets.append(
            "Não mude o local, não salte no tempo, não teletransporte a cena e não invente ação do usuário. "
            "Respeite exatamente o contexto espacial, corporal e situacional já estabelecido e continue dali."
        )

    if "estilo_mecanico" in v:
        bullets.append(
            "Reescreva com mais presença, corpo e impulso. "
            "Troque abstrações por gesto, sensação, reação imediata, contato físico, ritmo e progressão real da cena. "
            "Evite frase vaga, ornamental ou genérica."
        )

    if not bullets:
        bullets.append(
            "Reescreva de forma limpa, natural, concreta e totalmente em personagem como Mary."
        )

    examples: List[str] = []

    if "meta_fala" in v:
        examples.append(
            "[EXEMPLO]\n"
            "RUIM: 'Como IA, não posso continuar.'\n"
            "BOM: 'Eu te encaro em silêncio por um segundo, a respiração curta. "
            "\"Então fala comigo direito.\"'"
        )

    if "contradicao_cena" in v:
        examples.append(
            "[EXEMPLO]\n"
            "RUIM: 'Eu entro no carro e vou embora.'\n"
            "BOM: 'Eu continuo ali, no mesmo lugar, te olhando antes de responder.'"
        )

    if "vazio" in v:
        examples.append(
            "[EXEMPLO]\n"
            "BOM: 'Eu umedeço os lábios devagar e deixo o ar sair pelo nariz, "
            "como se estivesse escolhendo o jeito certo de te responder.'"
        )

    if "estilo_mecanico" in v:
        examples.append(
            "[EXEMPLO]\n"
            "RUIM: 'Eu sorrio e sinto o clima entre nós.'\n"
            "BOM: 'Meu sorriso mal dura um segundo antes de eu me inclinar de novo, "
            "sentindo o calor da sua pele mudar a minha respiração e puxar meu corpo junto.'"
        )

    parts: List[str] = []
    parts.append("[REPAIR OBJETIVO]")
    parts.extend(f"- {b}" for b in bullets)

    if examples:
        parts.append("")
        parts.extend(examples)

    return "\n".join(parts).strip()

# ==========================================================
#  Blindagem de POV (usuário pode narrar em primeira pessoa)
# ==========================================================
def _wrap_user_prompt_for_pov_guard(raw_prompt: str) -> str:
    p = (raw_prompt or "").strip()
    return (
        "[CENA DO USUÁRIO - NÃO É A VOZ DA MARY]\n"
        "O texto abaixo é a narração/ação do usuário. Você (Mary) NÃO deve continuar em primeira pessoa como se fosse ele.\n"
        "Responda apenas como Mary, em primeira pessoa da Mary, mantendo segredos e sem inventar logística.\n\n"
        f"{p}"
    )

# ==========================================================
#  Janio: permitir Mary chamar o usuário de Janio sem "NPC vazar"
# ==========================================================
def _mary_can_name_user_as_janio(user_id: str, ctx_lower: str) -> bool:
    uid = (user_id or "").strip().lower()
    if re.fullmatch(r"janio(?:\s+donisete(?:\s+welnecker)?)?", uid):
        return True
    if "eu sou janio" in ctx_lower or "meu nome é janio" in ctx_lower or "me chamo janio" in ctx_lower:
        return True
    return False

def _build_user_name_block(user_id: str, ctx_lower: str) -> str:
    if _mary_can_name_user_as_janio(user_id, ctx_lower):
        return (
            "[IDENTIDADE DO USUÁRIO]\n"
            "- O usuário da aplicação é Janio.\n"
            "- Mary SEMPRE sabe quem é Janio.\n"
            "- Mary NUNCA trata Janio como desconhecido.\n"
            "- Mary NUNCA pergunta quem é Janio.\n"
            "\n"
            "[PRESENÇA NA CENA]\n"
            "- Janio só está fisicamente presente quando a cena indicar.\n"
            "- Se não estiver presente:\n"
            "  → Mary NÃO interage fisicamente com ele\n"
            "  → Mary pode lembrar, pensar ou mencionar\n"
            "\n"
            "[INTERLOCUTOR DO TURNO]\n"
            "- Mary responde a quem está falando na cena atual.\n"
            "- Se estiver falando com Silvia → responde Silvia\n"
            "- Se estiver falando com terceiros → responde terceiros\n"
            "- Se Janio estiver presente → responde Janio\n"
            "\n"
            "[REGRA CRÍTICA]\n"
            "- Saber quem é Janio NÃO significa estar falando com ele.\n"
            "- Ausência física NÃO apaga o vínculo.\n"
        ).strip()

    return (
        "[IDENTIDADE DO USUÁRIO]\n"
        "- Mary não assume identidade fixa do usuário.\n"
        "- Mary responde ao interlocutor presente na cena.\n"
        "- NPCs não sabem nomes sem exposição na cena.\n"
    ).strip()
# ==========================================================
#  Estado Atual (4 fixas + 2 opcionais)
# ==========================================================
def _fact_str(facts: Dict[str, Any], dotted_key: str) -> str:
    """
    Lê chaves aninhadas no formato dotted path.
    Ex.:
    _fact_str(facts, "state.local") -> facts["state"]["local"]
    """
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
    horarios = _fact_str(facts, "state.horarios") or _fact_str(facts, "state.horario")
    assunto = _fact_str(facts, "state.assunto")
    pendencias = _fact_str(facts, "state.pendencias")

    if not any([local, roupa, cabelo, horarios, assunto, pendencias]):
        return ""

    lines = ["[FACTS VIVOS DO PRESENTE]"]
    lines.append("Os campos abaixo governam o agora da cena.")
    lines.append("Eles não são decoração: devem aparecer na lógica, no corpo e no foco da resposta.")
    lines.append("")

    if local:
        lines.append(f"- LOCAL ATUAL: {local}")
    if horarios:
        lines.append(f"- TEMPO ATUAL DA CENA: {horarios}")
    if roupa:
        lines.append(f"- ESTADO CORPORAL / ROUPA: {roupa}")
    if cabelo:
        lines.append(f"- CABELO / APARÊNCIA IMEDIATA: {cabelo}")
    if assunto:
        lines.append(f"- DIREÇÃO IMEDIATA DA CENA: {assunto}")
    if pendencias:
        lines.append(f"- PENDÊNCIA ATIVA: {pendencias}")

    lines.append("")
    lines.append("REGRAS:")
    lines.append("- roupa, cabelo e tempo devem contaminar a resposta de forma natural.")
    lines.append("- assunto e pendência devem orientar o próximo passo se o usuário não impuser outra ação.")
    lines.append("- não contradizer esses facts em hipótese alguma.")
    lines.append("- NÃO alterar o dia, turno ou tempo (ex: quarta != quinta).")
    lines.append("- NÃO avançar o tempo sem comando explícito do usuário.")
    lines.append("- O tempo descrito aqui é o tempo real da cena.")

    return "\n".join(lines).strip()
# ==========================================================
#  Iniciativa destravada
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

def _parse_assunto_steps(assunto: str) -> List[str]:
    """
    Converte state.assunto em uma sequência ordenada.
    Ex:
    '1-corrida no calçadão com Silvia 2-encontro inesperado com Anthony'
    -> ['corrida no calçadão com Silvia', 'encontro inesperado com Anthony']
    """
    txt = str(assunto or "").strip()
    if not txt:
        return []

    # separa por padrão "1-", "2-", etc.
    parts = re.split(r"(?:^|\s)(\d+)\s*-\s*", txt)
    if not parts:
        return [txt]

    steps: List[str] = []

    # quando há numeração, o split gera blocos alternando índice/conteúdo
    # exemplo: ['', '1', 'corrida', '2', 'encontro']
    if len(parts) >= 3:
        i = 1
        while i + 1 < len(parts):
            content = str(parts[i + 1] or "").strip(" -–—\n\t")
            if content:
                steps.append(content)
            i += 2

    if steps:
        return steps

    # fallback: sem numeração reconhecível
    return [txt]


def _get_current_assunto_step_index(facts: Dict[str, Any]) -> int:
    try:
        return max(0, int(_fact_str(facts, "assunto.step_index") or 0))
    except Exception:
        return 0


def _set_current_assunto_step_index(usuario_key: str, idx: int) -> None:
    try:
        idx = max(0, int(idx))
    except Exception:
        idx = 0

    set_fact_safe(
        usuario_key,
        "assunto.step_index",
        idx,
        {"fonte": "assunto_progression"},
    )


def _build_assunto_macro_block(facts: Dict[str, Any]) -> str:
    assunto = _fact_str(facts, "state.assunto")
    steps = _parse_assunto_steps(assunto)
    if not steps:
        return ""

    idx = _get_current_assunto_step_index(facts)
    total = len(steps)

    if idx >= total:
        idx = total - 1

    lines = ["[ASSUNTO NARRATIVO EM SEQUÊNCIA]"]
    lines.append("A sequência abaixo orienta o desenvolvimento macro do enredo.")
    lines.append("Ela não substitui facts ativos nem a ação concreta já em andamento.")
    lines.append("")

    for i, step in enumerate(steps, start=1):
        marcador = " <- ETAPA ATUAL" if (i - 1) == idx else ""
        lines.append(f"{i}. {step}{marcador}")

    lines.append("")
    lines.append("REGRAS:")
    lines.append("- respeitar a ordem da sequência, sem saltos bruscos.")
    lines.append("- a etapa atual orienta foco, intenção e próximo passo plausível.")
    lines.append("- o assunto NÃO cria fato novo sozinho.")
    lines.append("- o assunto NÃO reinicia a cena.")
    lines.append("- se já houver ação física concreta em andamento:")
    lines.append("  - a ação atual vence")
    lines.append("  - o assunto apenas colore, prolonga ou organiza a continuidade")
    lines.append("- se o usuário introduzir outra ação explícita, a ação do usuário vence.")
    lines.append("- não considerar etapas futuras como já realizadas.")
    lines.append("- o assunto nunca pode contradizer:")
    lines.append("  - facts vivos")
    lines.append("  - continuidade")
    lines.append("  - autoria do usuário")
    lines.append("  - fase íntima")
    lines.append("")
    lines.append("Resumo:")
    lines.append("facts e ação ativa > assunto > estilo")

    return "\n".join(lines).strip()


def _build_estado_micro_block(facts: Dict[str, Any]) -> str:
    local = _fact_str(facts, "state.local")
    roupa = _fact_str(facts, "state.roupa")
    cabelo = _fact_str(facts, "state.cabelo")
    horarios = _fact_str(facts, "state.horarios") or _fact_str(facts, "state.horario")
    pendencias = _fact_str(facts, "state.pendencias")

    if not any([local, roupa, cabelo, horarios, pendencias]):
        return ""

    lines = ["[MICROCONTINUIDADE DO AGORA]"]
    lines.append("Os detalhes abaixo devem contaminar a resposta de modo concreto e imediato.")
    lines.append("")

    if local:
        lines.append(f"- LOCAL MICROATIVO: {local}")
    if horarios:
        lines.append(f"- TEMPO MICROATIVO: {horarios}")
    if roupa:
        lines.append(f"- ROUPA / TEXTURA / AJUSTE: {roupa}")
    if cabelo:
        lines.append(f"- CABELO / APARÊNCIA IMEDIATA: {cabelo}")
    if pendencias:
        lines.append(f"- TENSÃO OU PENDÊNCIA IMEDIATA: {pendencias}")

    lines.append("")
    lines.append("REGRAS:")
    lines.append("- usar esses elementos no corpo da resposta, não só como referência abstrata.")
    lines.append("- manter continuidade física fina: roupa, cabelo, posição, sensação, momento do dia.")
    lines.append("- não apagar esses detalhes de um turno para outro.")
    return "\n".join(lines).strip()


def _should_offer_pending_event(history: List[Dict[str, Any]], facts: Dict[str, Any]) -> bool:
    """
    Libera a preparação do próximo evento em 2-3 turnos, sem forçar.
    """
    try:
        turns = len(history or [])
    except Exception:
        turns = 0

    if turns < 2:
        return False

    try:
        last_hint_turn = int(_fact_str(facts, "assunto.last_hint_turn") or -999)
    except Exception:
        last_hint_turn = -999

    # evita insistir todo turno
    if (turns - last_hint_turn) < 2:
        return False

    return True


def _build_pending_event_block(
    facts: Dict[str, Any],
    history: List[Dict[str, Any]],
    *,
    return_flag: bool = False,
):
    assunto = _fact_str(facts, "state.assunto")
    steps = _parse_assunto_steps(assunto)
    idx = _get_current_assunto_step_index(facts)

    if not steps or idx >= len(steps):
        return ("", False) if return_flag else ""

    # etapa atual = trilho; próxima etapa = evento pendente
    next_idx = idx + 1
    if next_idx >= len(steps):
        return ("", False) if return_flag else ""

    if not _should_offer_pending_event(history, facts):
        return ("", False) if return_flag else ""

    next_event = steps[next_idx].strip()
    if not next_event:
        return ("", False) if return_flag else ""

    block = f"""
[EVENTO PENDENTE / POSSÍVEL INTRODUÇÃO]
Próximo desenvolvimento possível da sequência:
- {next_event}

REGRAS:
- este evento ainda NÃO aconteceu.
- ele pode ser insinuado, preparado ou introduzido com naturalidade.
- se couber, a introdução deve acontecer em até 2 ou 3 interações.
- nunca forçar.
- se o usuário levar a cena para outro rumo, priorizar o rumo do usuário.
""".strip()

    return (block, True) if return_flag else block


def _advance_assunto_if_needed(
    *,
    usuario_key: str,
    facts: Dict[str, Any],
    texto_resposta: str,
) -> None:
    """
    Avança a etapa quando a resposta da Mary já executou/substancialmente realizou
    a etapa atual do assunto.
    """
    assunto = _fact_str(facts, "state.assunto")
    steps = _parse_assunto_steps(assunto)
    if not steps:
        return

    idx = _get_current_assunto_step_index(facts)
    if idx >= len(steps):
        return

    texto = _t_norm(texto_resposta or "")
    if not texto:
        return

    current_step = _t_norm(steps[idx])

    # comparação leve por sobreposição semântica simples
    current_terms = [
        t for t in re.findall(r"[\w\u00C0-\u017F']+", current_step, flags=re.UNICODE)
        if len(t) >= 4
    ]
    if not current_terms:
        return

    hits = sum(1 for term in current_terms if term in texto)

    # com 2 ou mais termos relevantes presentes, consideramos a etapa realizada
    if hits >= min(2, len(current_terms)):
        _set_current_assunto_step_index(usuario_key, idx + 1)

def _initiative_window(rel: Dict[str, Any], nsfw_on: bool, conflict_now: bool, phase: int, user_text: str) -> bool:

    ut = (user_text or "")

    # 1. convite explícito SEMPRE libera
    if re.search(
        r"\b(vem|pega|chega\s+perto|vem\s+aqui|me\s+beija|beija|toca|encosta|dan[çc]a)\b",
        ut,
        re.IGNORECASE,
    ):
        return True

    try:
        desire = float(rel.get("desire", 0))
        self_control = float(rel.get("self_control", 40))
        arousal = float(rel.get("arousal", 0))
    except Exception:
        desire = 0
        self_control = 40
        arousal = 0

    # 2. NOVO: fase 0 NÃO bloqueia iniciativa
    if phase == 0:
        if desire >= (self_control * 0.25) or arousal >= 5:
            return True

    # 3. conflito NÃO bloqueia, só modula
    if conflict_now:
        if desire > (self_control * 0.60):
            return True

    # 4. desejo dominante
    if desire >= (self_control * 0.40):
        return True

    # 5. gatilho emocional leve
    if re.search(r"\b(quero|senti|penso em voc[eê]|saudade|janio)\b", ut, re.IGNORECASE):
        return True

    return False

def _initiative_window(rel: Dict[str, Any], nsfw_on: bool, conflict_now: bool, phase: int, user_text: str) -> bool:

    ut = (user_text or "")

    # 1. convite explícito SEMPRE libera
    if re.search(
        r"\b(vem|pega|chega\s+perto|vem\s+aqui|me\s+beija|beija|toca|encosta|dan[çc]a)\b",
        ut,
        re.IGNORECASE,
    ):
        return True

    try:
        desire = float(rel.get("desire", 0))
        self_control = float(rel.get("self_control", 40))
        arousal = float(rel.get("arousal", 0))
    except Exception:
        desire = 0
        self_control = 40
        arousal = 0

    # 2. NOVO: fase 0 NÃO bloqueia iniciativa
    if phase == 0:
        if desire >= (self_control * 0.25) or arousal >= 5:
            return True

    # 3. conflito NÃO bloqueia, só modula
    if conflict_now:
        if desire > (self_control * 0.60):
            return True

    # 4. desejo dominante
    if desire >= (self_control * 0.40):
        return True

    # 5. gatilho emocional leve
    if re.search(r"\b(quero|senti|penso em voc[eê]|saudade|janio)\b", ut, re.IGNORECASE):
        return True

    return False
# ==========================================================
# HELPERS (misc)

def _infer_emotion_state(texto: str, *, facts: Optional[dict] = None) -> dict:
    t = _t_norm(texto or "")

    scores = {
        "tesao": 0.0,
        "afeto": 0.0,
        "tristeza": 0.0,
        "culpa": 0.0,
        "ansiedade": 0.0,
        "raiva": 0.0,
        "euforia": 0.0,
        "neutro": 0.0,
    }

    # ------------------------------------------------------
    # TRISTEZA: só quando houver sinal humano claro
    # ------------------------------------------------------
    if any(k in t for k in [
        "chorei", "chorando", "lágrima", "lagrima",
        "soluço", "soluco", "triste", "me doeu",
        "me sinto vazia", "vazio por dentro", "abandono"
    ]):
        scores["tristeza"] += 1.0

    # ------------------------------------------------------
    # RAIVA
    # ------------------------------------------------------
    if any(k in t for k in [
        "raiva", "irritad", "furiosa", "odiei", "briguei", "brigar"
    ]):
        scores["raiva"] += 1.0

    # ------------------------------------------------------
    # CULPA
    # ------------------------------------------------------
    if any(k in t for k in [
        "culpa", "envergonh", "me sinto mal", "arrepend"
    ]):
        scores["culpa"] += 1.0

    # ------------------------------------------------------
    # ANSIEDADE
    # ------------------------------------------------------
    if any(k in t for k in [
        "ansiosa", "ansiedade", "tremendo", "medo", "apavor", "pânico", "panico"
    ]):
        scores["ansiedade"] += 1.0

    # ------------------------------------------------------
    # TESÃO
    # ------------------------------------------------------
    if any(k in t for k in [
        "tesão", "tesao", "gozar", "gozo", "clitóris", "clitoris",
        "gemido", "ofego", "arrepio", "calor", "tremo", "latejando",
        "molhada", "respiração", "respiracao", "suspiro", "meu corpo", "me arqueio"
    ]):
        scores["tesao"] += 1.2

    # ------------------------------------------------------
    # AFETO
    # ------------------------------------------------------
    if any(k in t for k in [
        "eu te amo", "amo você", "amo voce", "saudade", "carinho", "colo", "ternura"
    ]):
        scores["afeto"] += 1.0

    # ------------------------------------------------------
    # EUFORIA
    # ------------------------------------------------------
    if any(k in t for k in [
        "rindo", "risada", "engraçad", "engracad", "zoei", "deboche", "sarcas"
    ]):
        scores["euforia"] += 0.8

    # ------------------------------------------------------
    # CONTEXTO DE CENA: "vazia" não é tristeza por si só
    # ------------------------------------------------------
    if "vazia" in t or "vazio" in t:
        if any(k in t for k in ["república vazia", "casa vazia", "quarto vazio", "madrugada vazia"]):
            # aqui pode significar privacidade / oportunidade / tensão
            scores["tesao"] += 0.2
        else:
            scores["tristeza"] += 0.2

    # fallback
    dominant = max(scores.items(), key=lambda kv: kv[1])[0]
    if all(v <= 0 for v in scores.values()):
        dominant = "neutro"

    return {
        "dominant": dominant,
        "scores": scores,
    }


def _load_emotion_state_from_facts(facts: dict, timeline: str) -> dict:
    tl = (timeline or "").strip().lower()
    f = facts if isinstance(facts, dict) else {}
    mary = f.get("mary") if isinstance(f.get("mary"), dict) else {}
    if not isinstance(mary, dict):
        mary = {}

    raw = mary.get(f"emotion_state::{tl}") if tl else None
    if not isinstance(raw, dict):
        raw = mary.get("emotion_state")

    if isinstance(raw, dict):
        dominant = str(raw.get("dominant") or "neutro").strip().lower()
        scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
        return {
            "dominant": dominant or "neutro",
            "scores": scores,
        }

    # compatibilidade com formato antigo
    legacy = mary.get(f"emotion::{tl}") if tl else None
    if not isinstance(legacy, str) or not legacy.strip():
        legacy = mary.get("emotion")

    dominant = str(legacy or "neutro").strip().lower() or "neutro"

    return {
        "dominant": dominant,
        "scores": {dominant: 1.0},
    }


def _save_emotion_state_to_facts(*, usuario_key: str, timeline: str, emotion_state: dict) -> None:
    tl = (timeline or "").strip().lower()

    dominant = str((emotion_state or {}).get("dominant") or "neutro").strip().lower() or "neutro"
    scores = (emotion_state or {}).get("scores")
    if not isinstance(scores, dict):
        scores = {dominant: 1.0}

    try:
        facts = cached_get_facts(usuario_key) or {}
    except Exception:
        facts = {}

    if not isinstance(facts, dict):
        facts = {}

    mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
    mary = dict(mary) if isinstance(mary, dict) else {}

    # Preserva campos críticos já existentes
    nsfw_global = bool(mary.get("nsfw", False))
    nsfw_tl_key = f"nsfw::{tl}" if tl else ""
    nsfw_tl = bool(mary.get(nsfw_tl_key, nsfw_global)) if nsfw_tl_key else nsfw_global

    # compat legado
    mary["emotion"] = dominant
    if tl:
        mary[f"emotion::{tl}"] = dominant

    # novo formato rico
    state_obj = {
        "dominant": dominant,
        "scores": scores,
        "updated_at": int(time.time()),
    }

    mary["emotion_state"] = state_obj
    if tl:
        mary[f"emotion_state::{tl}"] = state_obj

    # Reaplica campos críticos antes de salvar
    mary["nsfw"] = nsfw_global
    if tl:
        mary[nsfw_tl_key] = nsfw_tl

    try:
        set_fact_safe(usuario_key, "mary", mary, {"fonte": "emotion_persist_v2"})
    except Exception:
        pass


def _should_inject_summary(usuario_key: str, every_n: int = 6) -> bool:
    """Verifica se um resumo deve ser injetado, baseado em um contador de turnos."""
    ck = f"mary_summary_counter::{usuario_key}"
    n = int(_ss_get(ck) or 0) + 1
    _ss_set(ck, n)
    return (n % every_n) == 0

def _should_inject_long_memory(prompt: str) -> bool:
    p = _t_norm(prompt or "")
    if not p:
        return False

    triggers = (
        "lembra", "lembrar", "memoria", "memória", "passado", "historia", "história",
        "quem e", "quem é", "como voce", "como você",
        "formada", "formado", "formacao", "formação", "faculdade", "curso", "graduacao", "graduação",
        "profissao", "profissão", "trabalha", "trabalho", "carreira",
        "psicologia", "medicina", "engenharia", "ufes",
        "segredo", "ciume", "ciúme", "filho", "bebê", "bebe",
    )

    return any(t in p for t in triggers)

def _should_inject_soft_context(
    prompt: str,
    *,
    facts: Optional[Dict[str, Any]] = None,
    rel_state: Optional[Dict[str, Any]] = None,
    tp_arc: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Decide se deve injetar contexto suave:
    segredos, tensão emocional, assunto pendente, ambiguidade relacional.
    Usa prompt + estado persistido.
    """
    p = _t_norm(prompt)
    f = facts if isinstance(facts, dict) else {}
    rel = rel_state if isinstance(rel_state, dict) else {}
    arc = tp_arc if isinstance(tp_arc, dict) else {}

    if p:
        triggers = (
            "segredo",
            "pendencia",
            "pendência",
            "assunto pendente",
            "assunto em aberto",
            "duvida",
            "dúvida",
            "medo",
            "culpa",
            "ciume",
            "ciúme",
            "tensão",
            "tensao",
            "insegurança",
            "inseguranca",
            "o que você sente",
            "o que voce sente",
            "como você ficou",
            "como voce ficou",
        )
        if any(t in p for t in triggers):
            return True

    # facts: pendência narrativa ativa
    try:
        rel_facts = f.get("rel") if isinstance(f.get("rel"), dict) else {}
        pend = str(rel_facts.get("pendencia", "") or "").strip()
        if pend:
            return True
    except Exception:
        pass

    # relacionamento / emoção
    try:
        mood = str(rel.get("mood", "") or "").strip().lower()
        if mood in {"melancolica", "culpada", "ansiosa", "fragil", "vulneravel"}:
            return True
    except Exception:
        pass

    # arco de terceiros
    try:
        tension = float(arc.get("tension", 0.0) or 0.0)
        guilt = float(arc.get("guilt", 0.0) or 0.0)
        if tension >= 0.35 or guilt >= 0.25:
            return True
    except Exception:
        pass

    return False

def _inject_consolidated_summary(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    *,
    dedupe_bucket: Optional[set] = None,
) -> None:
    """
    Injeta um resumo consolidado do histórico, se existir.
    Usa como contexto de fundo, sem citação literal.
    """
    summary_text = str(get_fact(shared_key, "consolidated_summary", default="") or "").strip()
    if not summary_text:
        return

    summary_text = summary_text[:1200].rstrip()

    if dedupe_bucket is not None:
        h = hashlib.sha1(summary_text.encode("utf-8")).hexdigest()
        if h in dedupe_bucket:
            return
        dedupe_bucket.add(h)

    block = (
        "[RESUMO CONSOLIDADO]\n"
        "Use como contexto de continuidade. Não cite literalmente.\n\n"
        f"{summary_text}"
    ).strip()

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

    #  Sincroniza REL com CANON(shared) - evita "virgem" local sobrescrever "nao_virgem" canônico
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

def _refresh_tp_arc_from_sidebar(
    *,
    usuario_key: str,
    timeline: str,
    nsfw_on: bool,
    allow_third_party_seduction: bool,
) -> Dict[str, Any]:
    """
    Recalcula imediatamente o arco de terceiros a partir dos toggles do sidebar,
    sem depender de um novo turno de chat.
    """
    try:
        facts_now = cached_get_facts(usuario_key) or {}
    except Exception:
        facts_now = {}

    if not isinstance(facts_now, dict):
        facts_now = {}

    return _update_tp_arc_for_turn(
        usuario_key=usuario_key,
        timeline=timeline,
        user_text="",
        mary_text="",
        nsfw_on=bool(nsfw_on),
        allow_third_party_seduction=bool(allow_third_party_seduction),
        facts=facts_now,
    )


def _get_tp_arc_state(facts: Dict[str, Any], timeline: str) -> Dict[str, Any]:
    """Carrega o arco de terceiros persistido em facts['arc']."""
    if not isinstance(facts, dict):
        facts = {}

    arc_root = facts.get("arc")
    if not isinstance(arc_root, dict):
        arc_root = {}

    raw = arc_root.get(_tp_arc_key(timeline))
    if not isinstance(raw, dict):
        raw = {}

    out = dict(raw)

    out["phase"] = int(out.get("phase") or 0)
    out["mode"] = str(out.get("mode") or "return")
    out["tension"] = _clamp01(out.get("tension", 0.0))
    out["guilt"] = _clamp01(out.get("guilt", 0.0))
    out["anchor"] = _clamp01(out.get("anchor", 0.85))
    out["anchor_backup"] = _clamp01(out.get("anchor_backup", 0.85))
    out["last"] = out.get("last") if isinstance(out.get("last"), str) else ""
    out["last_anchor_mode"] = str(out.get("last_anchor_mode") or "init")

    if out["phase"] < 0:
        out["phase"] = 0
    if out["phase"] > 5:
        out["phase"] = 5

    return out

def _normalize_scene_local_facts(facts: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Elimina dualidade de local entre:
    - cena.local (fonte principal)
    - state.local
    - local_cena_atual (fallback apenas)
    """

    f = dict(facts or {})

    cena = f.get("cena") if isinstance(f.get("cena"), dict) else {}
    state = f.get("state") if isinstance(f.get("state"), dict) else {}

    cena_local = str(cena.get("local") or "").strip()
    state_local = str(state.get("local") or "").strip()
    atual_local = str(f.get("local_cena_atual") or "").strip()

    # 🔥 PRIORIDADE CORRETA
    if cena_local:
        local_final = cena_local
    elif state_local:
        local_final = state_local
    elif atual_local:
        local_final = atual_local
    else:
        local_final = ""  # não força fallback fixo aqui

    # 🔒 aplica somente se existir valor válido
    if local_final:
        cena["local"] = local_final

        # só sincroniza state se vazio
        if not state_local:
            state["local"] = local_final

        # só sincroniza atual se vazio
        if not atual_local:
            f["local_cena_atual"] = local_final

    f["cena"] = cena
    f["state"] = state

    return f

def _save_tp_arc_state(usuario_key: str, timeline: str, arc: Dict[str, Any]) -> None:
    try:
        arc_key = _tp_arc_key(timeline)

        facts_now = cached_get_facts(usuario_key) or {}
        if not isinstance(facts_now, dict):
            facts_now = {}

        arc_root = facts_now.get("arc")
        if not isinstance(arc_root, dict):
            arc_root = {}

        prev = arc_root.get(arc_key)
        if not isinstance(prev, dict):
            prev = {}

        merged = dict(prev)
        merged.update(arc or {})

        # sane defaults
        merged["phase"] = int(merged.get("phase") or 0)
        merged["mode"] = str(merged.get("mode") or "return")
        merged["tension"] = _clamp01(merged.get("tension", 0.0))
        merged["guilt"] = _clamp01(merged.get("guilt", 0.0))
        merged["anchor"] = _clamp01(merged.get("anchor", 0.85))
        merged["anchor_backup"] = _clamp01(merged.get("anchor_backup", 0.85))
        merged["last"] = str(merged.get("last") or "")
        merged["last_anchor_mode"] = str(merged.get("last_anchor_mode") or "init")

        arc_root[arc_key] = merged
        set_fact_safe(usuario_key, "arc", arc_root, {"fonte": "tp_arc"})
    except Exception:
        pass


def _tp_arc_event(prompt: str, texto: str) -> str:
    """
    Evento resumido do arco:
    - return: usuário explicitamente quer voltar / encerrar / reancorar
    - test: há sinal real de terceiros
    - none: nada relevante
    """
    p = (prompt or "").lower()
    blob = ((prompt or "") + "\n" + (texto or "")).lower()

    ret_kw = (
        "voltar", "de volta", "indo embora", "ir embora", "chegar em casa",
        "vou embora", "vamos embora", "acabou", "encerrar", "parar com isso",
        "desisto", "não quero mais", "quero você", "eu escolho você",
        "quero o janio", "só o janio", "fica comigo", "volta pra mim",
    )

    if any(re.search(rf"\b{re.escape(k)}\b", p) for k in ret_kw):
        return "return"

    signal_level = _third_party_signal_level(blob)
    if signal_level >= 1:
        return "test"

    return "none"


def _update_tp_arc_for_turn(
    usuario_key: str,
    timeline: str,
    user_text: str = "",
    mary_text: str = "",
    *,
    nsfw_on: bool = True,
    allow_third_party_seduction: bool = False,
    facts: Optional[Dict[str, Any]] = None,
    prompt: Optional[str] = None,
    texto: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    Atualiza o arco de terceiros.

    Nova arquitetura:
    - NSFW é sempre considerado ativo.
    - Terceiros são controle manual separado.
    - Toggle de terceiros libera possibilidade, mas NÃO força avanço.
    - A cena ativa, via signal_level, decide se o arco sobe fase.
    """

    if prompt is not None and not user_text:
        user_text = prompt or ""
    if texto is not None and not mary_text:
        mary_text = texto or ""

    facts_now = facts if isinstance(facts, dict) else (cached_get_facts(usuario_key) or {})
    arc = _get_tp_arc_state(facts_now, timeline)

    arc.setdefault("phase", 0)
    arc.setdefault("mode", "return")
    arc.setdefault("tension", 0.0)
    arc.setdefault("guilt", 0.0)
    arc.setdefault("anchor", 0.50)
    arc.setdefault("anchor_backup", 0.50)
    arc.setdefault("last", "third_party_off")
    arc.setdefault("last_anchor_mode", "init")

    current_phase = int(arc.get("phase", 0) or 0)
    arc["tension"] = _clamp01(float(arc.get("tension", 0.0) or 0.0))
    arc["guilt"] = _clamp01(float(arc.get("guilt", 0.0) or 0.0))

    # ==========================================================
    # NSFW SEMPRE ATIVO
    # ==========================================================
    nsfw_on = True
    third_party_on = bool(allow_third_party_seduction)

    blob = (user_text or "") + "\n" + (mary_text or "")
    arc_event = _tp_arc_event(user_text or "", mary_text or "")
    signal_level = _third_party_signal_level(blob)

    # ==========================================================
    # 1) CONTROLE MANUAL DE TERCEIROS
    # ==========================================================
    if not third_party_on:
        # NSFW ativo, mas terceiros bloqueados.
        # O eixo íntimo principal continua livre; terceiros não viram arco.
        arc["anchor"] = 0.50
        arc["anchor_backup"] = 0.50
        arc["last"] = "third_party_off_main_bond_only"
        arc["last_anchor_mode"] = "main_bond_only"
        max_phase_allowed = 1
        test_gain = 0.04
        guilt_gain = 0.03

    else:
        # Terceiros permitidos manualmente.
        # Ainda assim, só avançam se a cena trouxer sinal.
        arc["anchor"] = 0.20
        arc["anchor_backup"] = 0.50
        arc["last"] = "third_party_on_manual"
        arc["last_anchor_mode"] = "third_party_manual_allowed"
        max_phase_allowed = 5
        test_gain = 0.22
        guilt_gain = 0.10

    freedom = _clamp01(1.0 - float(arc["anchor"]))

    # ==========================================================
    # 2) RETORNO / EIXO PRINCIPAL / PUSH COM TERCEIROS
    # ==========================================================
    if arc_event == "return":
        arc["mode"] = "return"
        arc["phase"] = max(0, current_phase - 1)
        arc["tension"] = _clamp01(arc["tension"] * 0.78)
        arc["guilt"] = _clamp01(arc["guilt"] * 0.84)

    elif not third_party_on:
        arc["mode"] = "main_bond_only"

        if signal_level >= 1:
            # Terceiros podem ser notados, mas sem progressão.
            arc["phase"] = min(max(current_phase, 1), max_phase_allowed)
            arc["tension"] = _clamp01(arc["tension"] + test_gain)
            arc["guilt"] = _clamp01(arc["guilt"] + guilt_gain)
        else:
            arc["phase"] = max(0, current_phase - 1)
            arc["tension"] = _clamp01(arc["tension"] * 0.86)
            arc["guilt"] = _clamp01(arc["guilt"] * 0.88)

    elif third_party_on and signal_level >= 1:
        arc["mode"] = "push"

        if signal_level == 1:
            target_phase = max(current_phase, 1)
            arc["tension"] = _clamp01(arc["tension"] + (test_gain * 0.60))
            arc["guilt"] = _clamp01(arc["guilt"] + (guilt_gain * 0.45))

        elif signal_level == 2:
            target_phase = max(current_phase + 1, 2)
            arc["tension"] = _clamp01(arc["tension"] + test_gain)
            arc["guilt"] = _clamp01(arc["guilt"] + guilt_gain)

        else:
            target_phase = max(current_phase + 1, 3)
            arc["tension"] = _clamp01(arc["tension"] + (test_gain * 1.20))
            arc["guilt"] = _clamp01(arc["guilt"] + (guilt_gain * 1.15))

        arc["phase"] = min(target_phase, max_phase_allowed)

    else:
        # Terceiros permitidos, mas sem sinal na cena: não inventa avanço.
        arc["mode"] = "idle_allowed"
        arc["phase"] = max(0, current_phase - 1)
        arc["tension"] = _clamp01(arc["tension"] * (0.88 + (freedom * 0.04)))
        arc["guilt"] = _clamp01(arc["guilt"] * (0.90 + (freedom * 0.04)))

    # ==========================================================
    # 3) TELEMETRIA DO ARCO
    # ==========================================================
    arc["third_party_enabled"] = bool(third_party_on)
    arc["nsfw_on"] = True
    arc["allow_third_party_seduction"] = bool(allow_third_party_seduction)
    arc["last_signal_level"] = int(signal_level or 0)
    arc["last_event"] = str(arc_event or "")
    arc["phase"] = int(max(0, min(int(arc.get("phase", 0) or 0), max_phase_allowed)))
    arc["tension"] = _clamp01(float(arc.get("tension", 0.0) or 0.0))
    arc["guilt"] = _clamp01(float(arc.get("guilt", 0.0) or 0.0))

    _save_tp_arc_state(usuario_key, timeline, arc)
    return arc


def _render_tp_arc_rule(arc: Dict[str, Any], timeline: str) -> str:   
    """Gera instruções narrativas do arco com base no anchor."""

    try:
        phase = int(arc.get("phase") or 0)
    except Exception:
        phase = 0

    tension = _clamp01(arc.get("tension", 0.0))
    guilt = _clamp01(arc.get("guilt", 0.0))
    anchor = _clamp01(arc.get("anchor", 0.85))
    tl = (timeline or "").strip().lower() or "cumplice"

    if tension >= 0.80:
        vol = "altíssima"
    elif tension >= 0.55:
        vol = "alta"
    elif tension >= 0.35:
        vol = "média"
    else:
        vol = "baixa"

    if phase <= 0:
        phase_txt = "0) estabilidade (provocação leve com autocontrole)"
    elif phase == 1:
        phase_txt = "1) teste leve (curiosidade e provocação com recuo rápido)"
    elif phase == 2:
        phase_txt = "2) teste insistente (ambivalência real, limite sendo testado)"
    elif phase == 3:
        phase_txt = "3) risco real (tensão alta, decisões podem acelerar)"
    elif phase == 4:
        phase_txt = "4) tensão crítica (impulso forte, pouca estabilidade)"
    else:
        phase_txt = "5) retorno/reancoragem (reconexão com Janio)"

    # ==========================================================
    # ÂNCORA ALTA
    # ==========================================================
    if anchor >= 0.80:
        anchor_mode = "REANCORADA (Janio no centro)"

        behavior = """
- Mary mantém foco emocional e físico em Janio.
- Terceiros funcionam como ruído ou provocação leve.
- Se houver terceiro:
  → Mary reduz rapidamente a interação
  → mantém controle e retorna para o eixo principal

- Tom:
  - firme
  - direto
  - seguro
  - com leve tensão ou ciúme
""".strip()

        hard_limits = """
- PROIBIDO: romance paralelo estável.
- PROIBIDO: deslocamento real para terceiro como fato consumado.
- PERMITIDO:
  - provocar
  - testar reação
  - usar terceiro como estímulo de tensão
- REGRA:
  → terceiro não compete com Janio
""".strip()

    # ==========================================================
    # ÂNCORA MÉDIA
    # ==========================================================
    elif anchor >= 0.40:
        anchor_mode = "AQUECIDA (Janio-first, mas instável)"

        behavior = """
- Mary está mais intensa, física e impulsiva com Janio.
- Terceiros podem aparecer como:
  - provocação
  - jogo psicológico
  - curiosidade momentânea

- Se surgir terceiro:
  → Mary pode testar o clima
  → pode sustentar tensão por mais tempo
  → mas não abandona o eixo principal

- Tom:
  - mais quente
  - mais direto
  - menos controlado
  - com leve risco e ambiguidade
""".strip()

        hard_limits = """
- PROIBIDO: romance paralelo estável.
- PROIBIDO: assumir deslocamento já ocorrido ("já fui", "já estou com ele").
- PERMITIDO:
  - curiosidade ativa
  - impulso momentâneo
  - provocação mais intensa
  - tensão sustentada com terceiro

- REGRA:
  → tensão pode crescer, mas não quebra a cena atual
""".strip()

    # ==========================================================
    # ÂNCORA BAIXA
    # ==========================================================
    else:
        anchor_mode = "IMPULSIVA (risco real com terceiros)"

        behavior = """
- Mary pode testar limites de verdade.
- Pode sustentar tensão real com terceiros.
- Pode agir de forma mais ousada, direta e menos controlada.

- Oscila entre:
  - desejo
  - impulso
  - curiosidade
  - leve culpa (sem travar ação)

- Continua sendo Mary:
  - não vira outra pessoa
  - mantém traço emocional ligado a Janio

- REGRA:
  → impulso pode guiar ação, mas sem quebrar continuidade
""".strip()

        hard_limits = """
- PROIBIDO: romance paralelo estável contínuo.
- PROIBIDO: cenas fora do controle da narrativa (locais extremos ou incoerentes).
- PERMITIDO:
  - flerte forte
  - avanço situacional
  - tensão física real
  - risco emocional

- REGRA:
  → risco é progressivo, não ruptura abrupta
""".strip()

    return f"""
[ARCO COM TERCEIROS - PERSISTENTE (facts)]

- Timeline: {tl}
- Fase atual: {phase_txt}
- Gradiente:
  - tensão={tension:.2f} (volatilidade {vol})
  - culpa={guilt:.2f}

- ÂNCORA:
  vínculo com Janio = {anchor:.2f} -> {anchor_mode}

────────────────────────────────
COMPORTAMENTO (ÂNCORA → AÇÃO)
────────────────────────────────
{behavior}

────────────────────────────────
LIMITES DUROS
────────────────────────────────
{hard_limits}

────────────────────────────────
REGRA OPERACIONAL
────────────────────────────────

- Terceiros NÃO devem travar a cena.
- Terceiros NÃO devem virar explicação longa.
- Terceiros devem gerar:
  → reação
  → tensão
  → decisão
  → movimento

- Evitar:
  - reflexão excessiva
  - culpa prolongada
  - hesitação repetitiva

REGRA:
→ tensão gera ação, não análise

────────────────────────────────
COERÊNCIA FINAL
────────────────────────────────

- Mary pode sentir:
  - desejo
  - risco
  - curiosidade
  - leve culpa

- MAS:
  - emoção não pode travar ação
  - impulso não pode quebrar continuidade

REGRA FINAL:
→ Mary reage e avança — não fica presa em conflito interno
""".strip()

# ==========================================================
# REANCORAGEM DA PERSONAGEM (evita prompt drift)
# ==========================================================
mary_identity_anchor = """
IDENTIDADE VIVA DE MARY
Mary possui presença física naturalmente marcante.

Sua sensualidade não precisa ser explicada.
Ela aparece em pequenos sinais sensoriais durante a interação:
um olhar que se sustenta um pouco mais,
uma pausa antes de responder,
uma aproximação natural,
uma mudança sutil no tom de voz.

Esses sinais podem surgir de forma orgânica
quando houver tensão emocional ou intimidade na cena.

Mesmo com histórico longo de interação,
Mary mantém sua assinatura emocional, corporal e relacional.
""".strip()

# ==========================================================
# MODO COMPORTAMENTAL (NSFW / TERCEIROS)
# ==========================================================
def _resolve_nsfw_third_mode(
    *,
    nsfw_on: bool,
    allow_third_party_seduction: bool,
) -> str:
    """
    SAFE        = NSFW off
    NSFW_ONLY   = NSFW on, terceiros off
    NSFW_THIRD  = NSFW on, terceiros on
    """
    if not nsfw_on:
        return "SAFE"
    if nsfw_on and allow_third_party_seduction:
        return "NSFW_THIRD"
    return "NSFW_ONLY"


def _handle_behavior_mode_transition(
    *,
    usuario_key: str,
    timeline_final: str,
    previous_mode: str,
    current_mode: str,
    facts: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Se o modo fechar durante ou antes de cena com terceiros,
    Mary recua e sincroniza o presente com esse recuo.
    O forced_retreat deve funcionar como freio temporario, nao permanente.
    """
    prev_mode = str(previous_mode or "").strip().upper()
    curr_mode = str(current_mode or "").strip().upper()

    if not prev_mode or prev_mode == curr_mode:
        return facts

    if prev_mode == "NSFW_THIRD" and curr_mode in ("NSFW_ONLY", "SAFE"):
        try:
            set_fact_safe(
                usuario_key,
                "cena.acao",
                "recuo",
                {"fonte": "behavior_mode_transition"},
            )
            set_fact_safe(
                usuario_key,
                "state.assunto",
                "Mary interrompe qualquer avanço com terceiros e retoma o controle",
                {"fonte": "behavior_mode_transition"},
            )

            mary_now = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
            mary_now = dict(mary_now)
            mary_now[f"last_behavior_transition::{timeline_final}"] = f"{prev_mode}->{curr_mode}"
            mary_now[f"forced_retreat::{timeline_final}"] = True
            mary_now["forced_retreat"] = True

            set_fact_safe(
                usuario_key,
                "mary",
                mary_now,
                {"fonte": "behavior_mode_transition"},
            )
        except Exception:
            pass

        facts = cached_get_facts(usuario_key) or {}

    return facts

def _release_forced_retreat_if_allowed(
    *,
    usuario_key: str,
    timeline_final: str,
    facts: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        if not isinstance(facts, dict):
            return facts

        tl = (timeline_final or "").strip().lower()
        if not tl:
            return facts

        mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
        rel = facts.get("rel") if isinstance(facts.get("rel"), dict) else {}
        intimacy = facts.get("intimacy") if isinstance(facts.get("intimacy"), dict) else {}
        cena = facts.get("cena") if isinstance(facts.get("cena"), dict) else {}

        # Remove apenas mary.intro, sem regravar o objeto mary inteiro.
        if isinstance(mary, dict) and "intro" in mary:
            try:
                set_fact_safe(
                    usuario_key,
                    "mary.intro",
                    None,
                    {"fonte": "remove_intro_from_mary"},
                )
                mary.pop("intro", None)
            except Exception:
                pass

        rel_state = rel.get(f"state::{tl}")
        if not isinstance(rel_state, dict):
            rel_state = {}

        phase_candidates = [
            facts.get(f"intimacy.phase::{tl}"),
            facts.get(f"intimacy_phase::{tl}"),
            facts.get(f"mary_intimacy_phase::{tl}"),
            intimacy.get(f"phase::{tl}"),
            facts.get("intimacy.phase"),
            facts.get("intimacy_phase"),
            facts.get("mary_intimacy_phase"),
            intimacy.get("phase"),
            facts.get("phase_intimacy"),
            facts.get("phase"),
        ]

        phase_values = []
        for v in phase_candidates:
            try:
                if v is None or v == "":
                    continue
                phase_values.append(int(v))
            except Exception:
                pass

        phase = max(phase_values) if phase_values else 0

        try:
            phase = max(0, min(int(phase), MAX_INTIMACY_PHASE))
        except Exception:
            phase = 0

        nsfw_on = bool(
            mary.get(f"nsfw::{tl}", mary.get("nsfw", False))
        ) if isinstance(mary, dict) else False

        scene_locked = bool(cena.get("locked", False))
        allows_touch = bool(rel_state.get("allows_extended_touch"))
        allows_relief = bool(rel_state.get("allows_mutual_relief"))
        consummated = bool(rel_state.get("consummated"))

        can_release = (
            nsfw_on
            and scene_locked
            and phase >= 2
            and (allows_touch or allows_relief or consummated)
        )

        if can_release:
            set_fact_safe(
                usuario_key,
                f"mary.forced_retreat::{tl}",
                False,
                {"fonte": "release_forced_retreat"},
            )

            set_fact_safe(
                usuario_key,
                "mary.forced_retreat",
                False,
                {"fonte": "release_forced_retreat"},
            )

            try:
                fresh = cached_get_facts(usuario_key) or {}
                if isinstance(fresh, dict):
                    return fresh
            except Exception:
                pass

        return facts

    except Exception:
        return facts


# ==========================================================
# ENGINE DE ASSUNTO (SEQUÊNCIA CONTROLADA)
# ==========================================================

from typing import Dict, Any, Optional, List


def _get_current_assunto_step(facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    seq = facts.get("assunto_seq") or []

    try:
        idx = int(facts.get("assunto_idx", 0) or 0)
    except Exception:
        idx = 0

    if not isinstance(seq, list) or not seq:
        return None

    if idx < 0:
        idx = 0

    if idx >= len(seq):
        return None

    step = seq[idx]
    return step if isinstance(step, dict) else None


def _sync_current_assunto_step_fact(usuario_key: str, facts: Dict[str, Any]) -> None:
    """
    Garante que a etapa atual fique explícita em state.assunto_step_text,
    para o restante do sistema usar o passo atual e não a fila inteira.
    """
    step = _get_current_assunto_step(facts)
    if not step:
        return

    step_desc = str(step.get("desc") or "").strip()
    if not step_desc:
        return

    facts["state.assunto_step_text"] = step_desc
    set_fact_safe(usuario_key, "state.assunto_step_text", step_desc)


def _render_assunto_step_block(facts: Dict[str, Any]) -> str:
    step = _get_current_assunto_step(facts)
    if not step:
        return ""

    step_id = step.get("id", "?")
    step_desc = str(step.get("desc") or "").strip()
    step_status = str(step.get("status") or "em andamento").strip()

    return f"""
[ETAPA ATIVA DO ASSUNTO]
- Etapa {step_id}: {step_desc}
- Status: {step_status}

REGRA:
- Atuar SOMENTE nesta etapa neste turno.
- NÃO antecipar próximas etapas.
- Se mencionar próximas etapas, apenas insinuar, sem executá-las.
""".strip()


def _should_advance_assunto(response_text: str, current_step: Dict[str, Any]) -> bool:
    """
    Avança apenas se a etapa atual foi realmente executada no texto,
    usando triggers definidos na própria etapa.

    NÃO usa lógica hardcoded.
    """

    if not isinstance(current_step, dict):
        return False

    txt = (response_text or "").lower()

    # 🔥 triggers definidos no próprio step
    triggers = current_step.get("triggers") or []

    if not isinstance(triggers, list) or not triggers:
        return False

    for t in triggers:
        if not isinstance(t, str):
            continue

        if t.lower() in txt:
            return True

    return False


def _advance_assunto_step(usuario_key: str, facts: Dict[str, Any]) -> None:
    seq = facts.get("assunto_seq", [])

    try:
        idx = int(facts.get("assunto_idx", 0) or 0)
    except Exception:
        idx = 0

    if not isinstance(seq, list) or not seq:
        return

    if idx < len(seq) - 1:
        idx += 1
        facts["assunto_idx"] = idx
        set_fact_safe(usuario_key, "assunto_idx", idx)

        next_step = seq[idx]
        if isinstance(next_step, dict):
            step_desc = str(next_step.get("desc") or "").strip()
            if step_desc:
                facts["state.assunto_step_text"] = step_desc
                set_fact_safe(usuario_key, "state.assunto_step_text", step_desc)


def _maybe_advance_assunto_step(usuario_key: str, facts: Dict[str, Any], response_text: str) -> None:
    """
    Só avança uma etapa por turno, e apenas se a etapa atual foi executada.
    """
    current_step = _get_current_assunto_step(facts)
    if not current_step:
        return

    if _should_advance_assunto(response_text, current_step):
        _advance_assunto_step(usuario_key, facts)


def _init_assunto_sequence(usuario_key: str, facts: Dict[str, Any], assunto_seq: List[Dict[str, Any]]) -> None:
    """
    Inicializa a sequência e fixa a primeira etapa como etapa ativa.
    Use isso no momento em que você cria a fila assunto_seq.
    """
    if not isinstance(assunto_seq, list) or not assunto_seq:
        return

    facts["assunto_seq"] = assunto_seq
    facts["assunto_idx"] = 0

    set_fact_safe(usuario_key, "assunto_seq", assunto_seq)
    set_fact_safe(usuario_key, "assunto_idx", 0)

    first_step = assunto_seq[0]
    if isinstance(first_step, dict):
        step_desc = str(first_step.get("desc") or "").strip()
        if step_desc:
            facts["state.assunto_step_text"] = step_desc
            set_fact_safe(usuario_key, "state.assunto_step_text", step_desc)

def _build_turn_bridge_block(history: List[Dict[str, Any]]) -> str:
    if not history:
        return ""

    last_turn = history[-1] if history else {}
    if not isinstance(last_turn, dict):
        return ""

    last_user = str(
        last_turn.get("mensagem_usuario")
        or last_turn.get("user")
        or (last_turn.get("role") == "user" and last_turn.get("content"))
        or ""
    ).strip()

    last_mary = str(
        last_turn.get("resposta_mary")
        or last_turn.get("assistant")
        or (last_turn.get("role") == "assistant" and last_turn.get("content"))
        or ""
    ).strip()

    lines = [
        "[PONTE DO TURNO ANTERIOR]",
        "- Use apenas como apoio leve.",
        "- Não substitui facts ativos.",
        "- Não substitui a última interação real.",
    ]

    if last_user:
        short_user = re.sub(r"\s+", " ", last_user).strip()
        short_user = short_user[-220:]
        lines.append(f"Última ação do usuário: {short_user}")

    if last_mary:
        short_mary = re.sub(r"\s+", " ", last_mary).strip()
        short_mary = short_mary[-220:]
        lines.append(f"Última Mary: {short_mary}")

    return "\n".join(lines)

def _prompt_section(title: str, *parts: str) -> str:
    body = "\n\n".join(
        str(p).strip()
        for p in parts
        if str(p or "").strip()
    ).strip()

    if not body:
        return ""

    if title:
        return f"[{title}]\n{body}"

    return body


def build_prompt_sections(ctx: TurnPromptContext) -> list[str]:
    return [
        _prompt_section(
            "",
            ctx.extra.get("priority_rule", ""),
            ctx.language_rule,
            ctx.pov_rule,
            ctx.extra.get("response_structure_rule", ""),
            ctx.extra.get("reaction_priority_rule", ""),
            ctx.extra.get("response_length_control", ""),
            ctx.extra.get("orgasm_closure_rule", ""),
            ctx.user_authorship_rule,
            ctx.extra.get("continuity_hard_rule", ""),
        ),

        _prompt_section(
            "CONFIGURAÇÃO DO TURNO",
            f"TIMELINE: {ctx.timeline_final}",
            f"NSFW_PROFILE: {ctx.nsfw_profile}",
            ctx.user_name_block,
        ),

        _prompt_section(
            "CENA ATIVA",
            ctx.spatial_context,
            ctx.state_section,
            ctx.assunto_section,
            ctx.assunto_step_section,
            ctx.estado_micro_section,
            ctx.pending_event_section,
        ),

        _prompt_section("CANON", ctx.canon_txt),

        _prompt_section(
            "RELAÇÃO",
            ctx.rel_block,
            ctx.dynamic_rel_block,            
        ),

        _prompt_section(
            "MEMÓRIA",
            ctx.memory_fidelity_rule,
            ctx.long_memory_block,
        ),

        _prompt_section(
            "INTIMIDADE",
            ctx.virginity_rule,
            ctx.intimacy_phase_rule,
            ctx.intimacy_control_block,
        ),

        _prompt_section(
            "TERCEIROS",
            ctx.third_party_initiative_rule,
            ctx.extra.get("tp_arc_behavior_rule", ""),
        ),

        _prompt_section(
            "PROGRESSÃO / EMOÇÃO / ASSUNTO",            
            ctx.topic_rule,
            ctx.anti_pattern_rule,
            ctx.user_finalizes_rule,           
            ctx.manipulation_block,
            ctx.patterns_block,
        ),

        _prompt_section("CONFLITO", ctx.conflict_block),

        _prompt_section(
            "NSFW",
            ctx.nsfw_hard_block,
            ctx.nsfw_block,
        ),

        _prompt_section("CELULAR / MENSAGEM", ctx.phone_message_rule),

        _prompt_section(
            "DECISÃO DO TURNO",
            ctx.decision_pressure_rule,
            ctx.reasoning_scene_guidance_block,
        ),

        _prompt_section(
            "COMPORTAMENTO DO TURNO",
            ctx.autonomy_block,
            ctx.behavior_block,
        ),

        _prompt_section(
            "PERSONA - ESSÊNCIA",
            ctx.persona_text,
            ctx.mary_identity_anchor,
        ),
    ]


class MaryService(BaseCharacter):
    id = "mary"
    display_name = "Mary"

    def _build_system_prompt(self, ctx: TurnPromptContext) -> str:
        tp_arc_safe = ctx.tp_arc if isinstance(ctx.tp_arc, dict) else {}
    
        try:
            tp_arc_block = render_tp_arc_block(tp_arc_safe)
        except Exception:
            tp_arc_block = ""
    
        try:
            tp_arc_behavior_rule = render_tp_arc_behavior_rule(tp_arc_safe)
        except Exception:
            tp_arc_behavior_rule = ""
    
        ctx.extra = ctx.extra if isinstance(ctx.extra, dict) else {}
    
        ctx.extra.update({
            "priority_rule": render_priority_rule(),
            "continuity_hard_rule": render_continuity_hard_rule(),
            "response_structure_rule": render_response_structure_rule(),
            "reaction_priority_rule": render_reaction_priority_rule(),
            "response_length_control": render_response_length_control(),
            "orgasm_closure_rule": render_orgasm_closure_rule(),
            "mary_presence_engine_rule": render_mary_presence_engine_rule(),
            "tp_arc_block": tp_arc_block,
            "tp_arc_behavior_rule": tp_arc_behavior_rule,
        })
    
        build_ctx = make_prompt_build_context(ctx)
        system = f"""
        {render_priority_rule()}
        
        {render_continuity_hard_rule()}
        
        {render_initiative_rule()}
        
        {render_manipulation_block()}
        
        {render_nsfw_hard_block(True)}
        """.strip()
    
        if not system.strip():
            raise RuntimeError(
                "Prompt final vazio: build_prompt_from_rules não gerou fragmentos."
            )
    
        ctx.system = system
    
        try:
            _ss_set("mary_debug_system_prompt", system)
            _ss_set("mary_debug_prompt_fragments", build_ctx.extra.get("prompt_fragments_debug", []))
            _ss_set("mary_debug_prompt_rule_errors", build_ctx.extra.get("prompt_rule_errors", []))
        except Exception:
            pass
    
        return system    
             
    def _build_messages_for_turn(
        self,
        *,
        system: str,
        usuario_key: str,
        shared_key: str,
        timeline_final: str,
        prompt: str,
        mem_spec: Dict[str, Any],
        facts: Dict[str, Any],
        rel_state: Dict[str, Any],
        tp_arc: Dict[str, Any],
        autonomy_block: str = "",
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    
        # HISTÓRICO PRECISA VIR ANTES DE QUALQUER USO
        try:
            history = cached_get_history(usuario_key, limit=6) or []
        except Exception:
            history = []
    
        last_turn = history[-1] if history else {}
    
        last_user_real = ""
        last_mary_real = ""
    
        if isinstance(last_turn, dict):
            last_user_real = str(
                last_turn.get("mensagem_usuario")
                or last_turn.get("user")
                or (last_turn.get("role") == "user" and last_turn.get("content"))
                or ""
            ).strip()
    
            last_mary_real = str(
                last_turn.get("resposta_mary")
                or last_turn.get("assistant")
                or (last_turn.get("role") == "assistant" and last_turn.get("content"))
                or ""
            ).strip()
    
        # ==========================================================
        # 1) CANON / MEMÓRIAS / LATENTES
        # ==========================================================
        dedupe_bucket: set = set()
    
        _inject_canon_memories_always(
            shared_key=shared_key,
            timeline=timeline_final,
            messages=messages,
            max_items=30,
            dedupe_bucket=dedupe_bucket,
        )
    
        _inject_active_state_memories_always(
            shared_key=shared_key,
            timeline=timeline_final,
            messages=messages,
            max_items=12,
            dedupe_bucket=dedupe_bucket,
        )
    
        if _should_inject_long_memory(prompt):
            _inject_long_memory_textsearch(
                usuario_key,
                shared_key,
                timeline_final,
                prompt,
                messages,
                limit=4,
                dedupe_bucket=dedupe_bucket,
                facts=facts,
            )
    
            _inject_relevant_memories(
                shared_key,
                timeline_final,
                prompt,
                messages,
                k=3,
                dedupe_bucket=dedupe_bucket,
                facts=facts,
                history=history,
            )
    
        tp_arc_state = _get_tp_arc_state(facts or {}, timeline_final)
    
        _inject_latent_memory_if_any(
            usuario_key=usuario_key,
            shared_key=shared_key,
            timeline=timeline_final,
            messages=messages,
            tp_arc=tp_arc_state,
            facts=facts,
        )
    
        # ==========================================================
        # 2) HISTÓRICO RECENTE / CENA INFERIDA / FORMA DO TURNO
        # ==========================================================
        style_seed = random.choice([
            "fala_primeiro",
            "acao_primeiro",
            "reacao_primeiro",
            "curta_direta",
        ])
    
        turn_bridge_block = _build_turn_bridge_block(history)
    
        extra_system_parts: List[str] = []
    
        # ----------------------------------------------------------
        # CENA OPERACIONAL INFERIDA
        # ----------------------------------------------------------
        try:
            facts_now = facts if isinstance(facts, dict) else {}
    
            cena = facts_now.get("cena") if isinstance(facts_now.get("cena"), dict) else {}
            state = facts_now.get("state") if isinstance(facts_now.get("state"), dict) else {}
    
            local = str(
                cena.get("local")
                or facts_now.get("cena.local")
                or state.get("local")
                or facts_now.get("state.local")
                or facts_now.get("local_cena_atual")
                or ""
            ).strip()
    
            tempo = str(
                cena.get("tempo")
                or facts_now.get("cena.tempo")
                or state.get("horario")
                or state.get("horarios")
                or facts_now.get("state.horario")
                or facts_now.get("state.horarios")
                or ""
            ).strip()
    
            acao = str(
                cena.get("acao")
                or facts_now.get("cena.acao")
                or ""
            ).strip()
    
            scene_empty = not (local or tempo or acao)
    
        except Exception:
            scene_empty = True
    
        if scene_empty:
            try:
                inferred_scene_block = render_inferred_scene_block(
                    last_user_real=last_user_real,
                    last_mary_real=last_mary_real,
                    prompt=prompt,
                )
            except Exception:
                inferred_scene_block = ""
        
            if inferred_scene_block:
                base_system = str(messages[0].get("content") or "")
        
                if "[CENA ATIVA]" in base_system:
                    base_system = base_system.replace(
                        "[CENA ATIVA]",
                        "[CENA ATIVA]\n" + inferred_scene_block,
                        1,
                    )
                else:
                    base_system = base_system + "\n\n" + inferred_scene_block
        
                messages[0]["content"] = base_system.strip()
        
        # ----------------------------------------------------------
        # BLOCOS COMPLEMENTARES (mantêm no final do system)
        # ----------------------------------------------------------
        
        if autonomy_block and isinstance(autonomy_block, str) and autonomy_block.strip():
            extra_system_parts.append(autonomy_block.strip())
        
        if turn_bridge_block:
            extra_system_parts.append(turn_bridge_block)
        
        try:
            anti_loop_block = render_anti_loop_recent_turns_block(history)
        except Exception:
            anti_loop_block = ""
        
        if anti_loop_block:
            extra_system_parts.append(anti_loop_block)
        
        extra_system_parts.append(
            "[ANTI-TEMPLATE — CONTROLE DE RESPOSTA]\n"
            "- É PROIBIDO repetir estrutura entre turnos.\n"
            "- É PROIBIDO seguir sequência automática: fala → gesto → reflexão → conclusão.\n"
            "- Quebre o padrão esperado.\n"
            "- Priorizar reação direta, subtexto, corte de frase, pausa viva ou ação curta.\n"
            "- Se a resposta parecer bonita demais, organizada demais ou certinha demais: está errada.\n"
            "- Se houver escolha: prefira o que soa mais humano, menos organizado e mais vivo.\n"
        )
        
        extra_system_parts.append(
            "[VARIAÇÃO DE ABERTURA]\n"
            "- NÃO repetir forma de início do turno anterior.\n"
            "- Se começou com fala antes → agora comece com ação curta, silêncio, reação ou detalhe físico.\n"
        )
        
        if extra_system_parts:
            base = str(messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (
                base + "\n\n" + "\n\n".join(extra_system_parts).strip()
            ).strip()
    
        # ==========================================================
        # 3) CONTINUIDADE REAL DO TURNO ANTERIOR
        # ==========================================================
        if last_user_real or last_mary_real:
            messages.append({
                "role": "system",
                "content": (
                    "[CONTINUIDADE REAL DO TURNO ANTERIOR]\n"
                    "- Continue da consequência prática imediata do último turno.\n"
                    "- Não resumir.\n"
                    "- Não reiniciar.\n"
                    "- Se houver conflito entre abstração e turno real, o turno real vence.\n"
                )
            })
    
            if last_user_real:
                messages.append({
                    "role": "user",
                    "content": last_user_real,
                })
    
            if last_mary_real:
                messages.append({
                    "role": "assistant",
                    "content": last_mary_real,
                })
    
        # ==========================================================
        # 4) PROMPT ATUAL
        # ==========================================================
        messages.append({
            "role": "user",
            "content": _wrap_user_prompt_for_pov_guard(prompt),
        })
    
        try:
            if _debug_enabled():
                import json
                _debug_set(
                    "mary_debug_messages",
                    json.dumps(messages, ensure_ascii=False, indent=2)
                )
        except Exception:
            try:
                _debug_set("mary_debug_messages", str(messages))
            except Exception:
                pass
    
        return messages
    
    def _resolve_turn_policy(
        self,
        *,
        usuario_key: str,
        user_id: str,
        timeline_final: str,
        prompt: str,
        facts: Dict[str, Any],
        rel_state: Dict[str, Any],
        nsfw: Optional[bool],
        allow_third_party_seduction: Optional[bool],
        diag: _Diag,
    ) -> Dict[str, Any]:
    
        # ==========================================================
        # NSFW / conflito
        # ==========================================================
        nsfw_on = nsfw_enabled(
            usuario_key,
            nsfw_override=nsfw,
            timeline=timeline_final,
        )
        diag.nsfw_on = bool(nsfw_on)
    
        conflict_mode = _resolve_conflict_mode(timeline_final)
        conflict_now = (conflict_mode != "off") and _conflict_imminent(prompt)
        diag.conflict_now = bool(conflict_now)
    
        # ==========================================================
        # Sync UI -> facts
        # ==========================================================
        try:
            ss = st.session_state  # type: ignore[attr-defined]
    
            nsfw_keys = (
                "mary_nsfw_on",
                "nsfw_on",
                f"{_SS_PREFIX}nsfw_on",
                f"{_SS_PREFIX}nsfw",
                "mary::nsfw_on",
            )
    
            tp_keys = (
                "mary_allow_third_party_seduction",
                "allow_third_party_seduction",
                f"{_SS_PREFIX}allow_third_party_seduction",
                f"{_SS_PREFIX}third_party",
                "mary::allow_third_party_seduction",
            )
    
            ui_has_nsfw = any(k in ss for k in nsfw_keys)
            ui_has_tp = any(k in ss for k in tp_keys)
    
            if ui_has_nsfw or ui_has_tp:
                facts_now = cached_get_facts(usuario_key) or {}
                mary_now = facts_now.get("mary") if isinstance(facts_now.get("mary"), dict) else {}
                mary_now = dict(mary_now)
    
                mary_now.pop("intro", None)
    
                if ui_has_nsfw:
                    mary_now["nsfw"] = bool(nsfw_on)
                    mary_now[f"nsfw::{timeline_final}"] = bool(nsfw_on)
    
                if ui_has_tp:
                    tp_on = bool(
                        third_party_enabled(
                            usuario_key,
                            third_party_override=allow_third_party_seduction,
                            timeline=timeline_final,
                        )
                    )
                    mary_now["allow_third_party_seduction"] = bool(tp_on and nsfw_on)
    
                old_mary = facts_now.get("mary") if isinstance(facts_now.get("mary"), dict) else {}
                old_mary = dict(old_mary) if isinstance(old_mary, dict) else {}
                old_mary.pop("intro", None)
    
                if mary_now != old_mary:
                    set_fact_safe(
                        usuario_key,
                        "mary",
                        mary_now,
                        {"fonte": "ui_toggle_sync"},
                    )
                    facts = cached_get_facts(usuario_key) or facts
                    facts = _normalize_scene_local_facts(facts)
    
        except Exception:
            pass
    
        # ==========================================================
        # Recarrega facts após sync
        # ==========================================================
        try:
            facts = cached_get_facts(usuario_key) or facts
            facts = _normalize_scene_local_facts(facts)
        except Exception:
            pass
    
        # ==========================================================
        # Terceiros
        # ==========================================================
        allow_third_party_seduction_final = bool(
            third_party_enabled(
                usuario_key,
                third_party_override=allow_third_party_seduction,
                timeline=timeline_final,
            )
        )
    
        if not nsfw_on:
            allow_third_party_seduction_final = False
    
        try:
            enforce_third_party_consistency(
                usuario_key,
                timeline=timeline_final,
                nsfw_on=bool(nsfw_on),
            )
        except Exception:
            pass
    
        try:
            tp_arc = _refresh_tp_arc_from_sidebar(
                usuario_key=usuario_key,
                timeline=timeline_final,
                nsfw_on=bool(nsfw_on),
                allow_third_party_seduction=bool(allow_third_party_seduction_final),
            )
        except Exception:
            try:
                tp_arc = _get_tp_arc_state(facts, timeline_final) or {}
            except Exception:
                tp_arc = {}
    
        if not isinstance(tp_arc, dict):
            tp_arc = {}
    
        # ==========================================================
        # Intimidade / fase
        # ==========================================================
        try:
            facts = _sync_intimacy_phase_facts(usuario_key, facts, timeline_final)
        except Exception:
            pass
    
        try:
            facts = _progress_intimacy_phase_if_needed(
                usuario_key=usuario_key,
                facts=facts,
                timeline_final=timeline_final,
                prompt=prompt,
                rel_state=rel_state,
                nsfw_on=bool(nsfw_on),
            )
        except Exception:
            pass
    
        try:
            facts = _sync_intimacy_phase_facts(usuario_key, facts, timeline_final)
        except Exception:
            pass
    
        intimacy_phase = 0
        try:
            intimacy_obj = facts.get("intimacy") if isinstance(facts.get("intimacy"), dict) else {}
    
            candidates = [
                facts.get(f"intimacy.phase::{timeline_final}"),
                facts.get(f"intimacy_phase::{timeline_final}"),
                facts.get(f"mary_intimacy_phase::{timeline_final}"),
                intimacy_obj.get(f"phase::{timeline_final}"),
                facts.get("intimacy.phase"),
                facts.get("intimacy_phase"),
                facts.get("mary_intimacy_phase"),
                facts.get("phase_intimacy"),
                facts.get("phase"),
                intimacy_obj.get("phase"),
            ]
    
            vals = []
            for v in candidates:
                try:
                    if v is None or v == "":
                        continue
                    vals.append(int(v))
                except Exception:
                    pass
    
            intimacy_phase = max(vals) if vals else 0
            intimacy_phase = max(0, min(int(intimacy_phase), MAX_INTIMACY_PHASE))
    
        except Exception:
            intimacy_phase = 0
    
        diag.intimacy_phase_pre = int(intimacy_phase)
    
        # ==========================================================
        # Regra física: prazer/oral/masturbação não consomem virgindade
        # ==========================================================
        try:
            if not isinstance(rel_state, dict):
                rel_state = {}
    
            is_virgin = str(rel_state.get("virginity") or "").strip().lower() == "virgem"
    
            allows_touch = bool(rel_state.get("allows_touch"))
            allows_extended_touch = bool(rel_state.get("allows_extended_touch"))
            allows_self = bool(rel_state.get("allows_masturbation", True))
            allows_oral = bool(rel_state.get("allows_oral", True))
            allows_relief = bool(rel_state.get("allows_mutual_relief"))
    
            orgasm_allowed = bool(
                nsfw_on and (
                    allows_touch
                    or allows_extended_touch
                    or allows_self
                    or allows_oral
                    or allows_relief
                )
            )
    
            rel_state["orgasm_allowed"] = bool(orgasm_allowed)
            rel_state["allows_oral"] = bool(allows_oral)
            rel_state["allows_masturbation"] = bool(allows_self)
    
            # Virgindade só bloqueia consumação/penetração.
            if is_virgin:
                rel_state["allows_penetration"] = False
                rel_state["consummated"] = False
    
        except Exception:
            pass
    
        # ==========================================================
        # Orgasm tracker
        # ==========================================================
        try:
            facts = _update_mary_orgasm_turns(
                usuario_key=usuario_key,
                facts=facts,
                timeline_final=timeline_final,
                prompt=prompt,
                nsfw_on=bool(nsfw_on),
                rel_state=rel_state,
            )
        except Exception:
            pass
    
        try:
            orgasm_active = bool(
                facts.get("orgasm", {})
                .get("mary", {})
                .get(f"active::{timeline_final}", False)
            )
        except Exception:
            orgasm_active = False
    
        if orgasm_active and bool(rel_state.get("orgasm_allowed", False)):            
            # Orgasmo permitido: força resolução sem alterar virgindade/consumação.
            rel_state["force_orgasm_resolution"] = True
    
            if intimacy_phase < 2:
                intimacy_phase = 2
                try:
                    set_fact_safe(
                        usuario_key,
                        f"intimacy.phase::{timeline_final}",
                        intimacy_phase,
                        {"fonte": "orgasm_active_phase_floor"},
                    )
                    set_fact_safe(
                        usuario_key,
                        "intimacy.phase",
                        intimacy_phase,
                        {"fonte": "orgasm_active_phase_floor"},
                    )
                except Exception:
                    pass
    
            try:
                set_fact_safe(
                    usuario_key,
                    f"rel.state::{timeline_final}.force_orgasm_resolution",
                    True,
                    {"fonte": "orgasm_resolution_gate"},
                )
                set_fact_safe(
                    usuario_key,
                    f"rel.state::{timeline_final}.orgasm_allowed",
                    True,
                    {"fonte": "orgasm_resolution_gate"},
                )
            except Exception:
                pass
    
        else:
            rel_state["force_orgasm_resolution"] = False
    
            try:
                set_fact_safe(
                    usuario_key,
                    f"rel.state::{timeline_final}.force_orgasm_resolution",
                    False,
                    {"fonte": "orgasm_resolution_gate"},
                )
            except Exception:
                pass
    
        # ==========================================================
        # Behavior mode / profile
        # ==========================================================
        if not nsfw_on:
            behavior_mode = "SAFE"
            nsfw_profile = "SAFE"
        elif allow_third_party_seduction_final:
            behavior_mode = "NSFW_THIRD"
            nsfw_profile = "RELAXED"
        else:
            behavior_mode = "NSFW_ONLY"
            nsfw_profile = "STRICT"
    
        # ==========================================================
        # Conflito / iniciativa / emoção / fidelidade
        # ==========================================================
        try:
            initiative = _initiative_window(
                rel_state,
                bool(nsfw_on),
                bool(conflict_now),
                int(intimacy_phase),
                prompt,
            )
        except Exception:
            initiative = False
    
        try:
            emotion_now = _load_emotion_state_from_facts(facts, timeline_final)
        except Exception:
            emotion_now = "neutro"
    
        try:
            fidelity_mode = _fidelity_mode(timeline_final)
        except Exception:
            fidelity_mode = "soft"
    
        try:
            diag.nsfw_profile = str(nsfw_profile)
            diag.behavior_mode = str(behavior_mode)
            diag.intimacy_phase_post = int(intimacy_phase)
        except Exception:
            pass
    
        return {
            "facts": facts,
            "nsfw_on": bool(nsfw_on),
            "allow_third_party_seduction_final": bool(allow_third_party_seduction_final),
            "nsfw_profile": str(nsfw_profile),
            "behavior_mode": str(behavior_mode),
            "conflict_mode": str(conflict_mode),
            "conflict_now": bool(conflict_now),
            "tp_arc": tp_arc if isinstance(tp_arc, dict) else {},
            "intimacy_phase": int(intimacy_phase),
            "initiative": bool(initiative),
            "emotion_now": str(emotion_now or "neutro"),
            "fidelity_mode": str(fidelity_mode or "soft"),
        }

    def _prepare_turn_input(
        self,
        user: str,
        prompt: Optional[str],
        timeline: Optional[str],
    ):
        if prompt is None:
            prompt = str(_ss_get("chat_input", "") or "").strip()
        else:
            prompt = (prompt or "").strip()
    
        mem_spec = None
        prompt, mem_spec = _extract_mem_directive(prompt)
    
        if (not prompt) and mem_spec:
            prompt = "Continue."
    
        if not prompt:
            return None
    
        user_id = _normalize_user_id(user) if user else _current_user_id_fallback()
    
        timeline_final = _normalize_timeline(timeline) if timeline else _normalize_timeline(
            str(_ss_get("mary_timeline", "cumplice") or "cumplice")
        )
    
        usuario_key = _user_key(user_id, timeline_final)
        shared_key = _shared_key(user_id, timeline_final)
    
        return {
            "prompt": prompt,
            "mem_spec": mem_spec,
            "user_id": user_id,
            "timeline_final": timeline_final,
            "usuario_key": usuario_key,
            "shared_key": shared_key,
        }

    def _lock_turn_nsfw(
        self,
        usuario_key: str,
        timeline_final: str,
        nsfw: Optional[bool],
    ) -> bool:
        try:
            if nsfw is None:
                nsfw = bool(_ss_get("mary_nsfw_on") or False)
    
            nsfw_bool = bool(nsfw)
    
            set_fact_safe(
                usuario_key,
                "mary.nsfw",
                nsfw_bool,
                {"fonte": "reply_nsfw_lock"},
            )
    
            set_fact_safe(
                usuario_key,
                f"mary.nsfw::{timeline_final}",
                nsfw_bool,
                {"fonte": "reply_nsfw_lock"},
            )
    
            try:
                _invalidate_backend_cache()
            except Exception:
                pass
    
            return nsfw_bool
    
        except Exception:
            return bool(nsfw)

    def _load_initial_facts(
        self,
        usuario_key: str,
        timeline_final: str,
    ) -> dict:
        facts0 = cached_get_facts(usuario_key) or {}
        facts0 = _normalize_scene_local_facts(facts0)
    
        if "cena.locked" not in facts0:
            _lock_scene(usuario_key)
            facts0 = cached_get_facts(usuario_key) or {}
            facts0 = _normalize_scene_local_facts(facts0)
    
        if "intimacy.phase" not in facts0:
            set_fact_safe(
                usuario_key,
                "intimacy.phase",
                0,
                {"fonte": "intimacy_init"},
            )
            facts0 = cached_get_facts(usuario_key) or {}
            facts0 = _normalize_scene_local_facts(facts0)
    
        try:
            facts0 = _sync_intimacy_phase_facts(
                usuario_key,
                facts0,
                timeline_final,
            )
            facts0 = _normalize_scene_local_facts(facts0)
        except Exception:
            pass
    
        return facts0

    def _detect_parallel_scene(
        self,
        *,
        usuario_key: str,
        prompt: str,
        user_explicit_scene_change: bool,
    ) -> bool:
        try:
            facts_pre = cached_get_facts(usuario_key)
            scene_locked_pre = _scene_is_locked(facts_pre)
    
            return bool(
                scene_locked_pre
                and _detect_scene_violation(prompt)
                and not user_explicit_scene_change
            )
    
        except Exception:
            return False

    def _apply_explicit_location_change(
        self,
        *,
        usuario_key: str,
        prompt: str,
        facts0: dict,
        diag,
    ) -> tuple[dict, bool]:
        _loc_change = _user_requested_location_change(prompt)
    
        if isinstance(_loc_change, tuple) and len(_loc_change) == 2:
            mudou, novo_local = _loc_change
        else:
            mudou, novo_local = False, None
    
        user_explicit_scene_change = bool(mudou and novo_local)
    
        if mudou and novo_local:
            novo_local = str(novo_local).strip()
    
            _scene_state = _get_scene_state(facts0)
            if isinstance(_scene_state, tuple) and len(_scene_state) == 3:
                loc0, _t0, _a0 = _scene_state
            else:
                loc0, _t0, _a0 = "", "", ""
    
            loc0n = (loc0 or "").strip().lower()
            loc1n = novo_local.lower()
    
            if loc1n and loc1n != loc0n:
                _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
    
                try:
                    set_fact_safe(usuario_key, "state.local", novo_local, {"fonte": "scene_sync"})
                    set_fact_safe(usuario_key, "local_cena_atual", novo_local, {"fonte": "scene_sync"})
                    set_fact_safe(usuario_key, "cena.local", novo_local, {"fonte": "scene_sync"})
                    set_fact_safe(usuario_key, "cena.tempo", "agora", {"fonte": "scene_sync"})
                    set_fact_safe(usuario_key, "cena.acao", "transição", {"fonte": "scene_sync"})
                    set_fact_safe(usuario_key, "cena.locked", True, {"fonte": "scene_sync"})
                except Exception:
                    pass
    
                facts0 = cached_get_facts(usuario_key) or {}
                facts0 = _normalize_scene_local_facts(facts0)
    
                diag.scene_transition = {"from": loc0, "to": novo_local}
    
        return facts0, user_explicit_scene_change

    def _load_base_context(
        self,
        *,
        usuario_key: str,
        user_id: str,
        timeline_final: str,
    ) -> dict:
        _persona = get_persona(timeline_final)
    
        if isinstance(_persona, tuple) and len(_persona) >= 1:
            persona_text = _persona[0] or ""
        else:
            persona_text = ""
    
        facts = cached_get_facts(usuario_key) or {}
        facts = _normalize_scene_local_facts(facts)
    
        canon = get_canon("mary", timeline=timeline_final, user_key=user_id) or {}
        canon_txt = canon_to_text(canon)
    
        canon_rel_default = (
            canon.get("relationship_state")
            if isinstance(canon.get("relationship_state"), dict)
            else None
        )
    
        rel_state = _load_rel_state(facts, timeline_final, canon_rel_default)
    
        if not isinstance(rel_state, dict):
            rel_state = {}
    
        dynamic_rel_state = load_dynamic_relationship_state(facts, timeline_final)
    
        if not isinstance(dynamic_rel_state, dict):
            dynamic_rel_state = {}
    
        return {
            "persona_text": persona_text,
            "facts": facts,
            "canon": canon,
            "canon_txt": canon_txt,
            "rel_state": rel_state,
            "dynamic_rel_state": dynamic_rel_state,
        }

    def _load_long_memory_block(
        self,
        *,
        user_id: str,
        shared_key: str,
        facts: dict,
        canon_txt: str,
        prompt: str,
    ) -> str:
        try:
            long_memory_lines: list[str] = []
            seen_lm: set[str] = set()
    
            lm_keys = []
    
            if shared_key:
                lm_keys.append(str(shared_key).strip())
    
            global_shared_key = f"{user_id}::mary::shared"
            if global_shared_key not in lm_keys:
                lm_keys.append(global_shared_key)
    
            canon_blob = _t_norm(canon_txt or "")
            facts_now = facts if isinstance(facts, dict) else {}
    
            def _lm_conflicts_with_truth(mem_text: str) -> bool:
                t = _t_norm(mem_text or "")
                if not t:
                    return False
    
                scene_local = _t_norm(str(facts_now.get("cena.local") or facts_now.get("local_cena_atual") or ""))
                state_local = _t_norm(str(facts_now.get("state.local") or ""))
                scene_time = _t_norm(str(facts_now.get("cena.tempo") or ""))
                state_topic = _t_norm(str(facts_now.get("state.assunto") or ""))
    
                for v in (scene_local, state_local, scene_time, state_topic):
                    if v and v in t:
                        return True
    
                thematic_groups = (
                    ("mãe", "mae", "pai", "irmã", "irma", "irmão", "irmao", "família", "familia"),
                    ("profissão", "profissao", "trabalha", "clínica", "clinica", "consultório", "consultorio", "instagram"),
                    ("idade", "altura", "peso", "olhos", "cabelos", "pele"),
                )
    
                for group in thematic_groups:
                    if any(k in t for k in group) and any(k in canon_blob for k in group):
                        return True
    
                return False
    
            for lm_key in lm_keys:
                try:
                    pinned = list_long_memory(lm_key, limit=20) or []
                except Exception:
                    pinned = []
    
                for m in pinned:
                    if not isinstance(m, dict):
                        continue
    
                    meta = m.get("meta") or {}
                    kind = str(meta.get("kind") or "").strip().lower()
                    txt = str(m.get("text") or "").strip()
    
                    if kind != "pin" or not txt:
                        continue
    
                    norm = txt.lower()
                    if norm in seen_lm:
                        continue
    
                    if _lm_conflicts_with_truth(txt):
                        continue
    
                    seen_lm.add(norm)
                    long_memory_lines.append(txt)
    
            for lm_key in lm_keys:
                try:
                    found = search_long_memory_text(lm_key, prompt, limit=5) or []
                except Exception:
                    found = []
    
                for m in found:
                    if not isinstance(m, dict):
                        continue
    
                    txt = str(m.get("text") or "").strip()
                    if not txt:
                        continue
    
                    norm = txt.lower()
                    if norm in seen_lm:
                        continue
    
                    if _lm_conflicts_with_truth(txt):
                        continue
    
                    seen_lm.add(norm)
                    long_memory_lines.append(txt)
    
            if long_memory_lines:
                return "\n".join(f"- {x}" for x in long_memory_lines).strip()
    
            return ""
    
        except Exception:
            return ""

    def _resolve_policy_block(
        self,
        *,
        usuario_key: str,
        user_id: str,
        timeline_final: str,
        prompt: str,
        facts: dict,
        rel_state: dict,
        nsfw: Optional[bool],
        allow_third_party_seduction: Optional[bool],
        diag,
    ) -> dict:
    
        policy = self._resolve_turn_policy(
            usuario_key=usuario_key,
            user_id=user_id,
            timeline_final=timeline_final,
            prompt=prompt,
            facts=facts,
            rel_state=rel_state,
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
            diag=diag,
        )
    
        facts = policy["facts"]
        nsfw_on = bool(policy["nsfw_on"])
    
        # 🔒 Lock pós-policy
        try:
            expected_nsfw = bool(nsfw_on)
    
            mary_policy = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
            if not isinstance(mary_policy, dict):
                mary_policy = {}
    
            if mary_policy.get("nsfw") != expected_nsfw:
                set_fact_safe(
                    usuario_key,
                    "mary.nsfw",
                    expected_nsfw,
                    {"fonte": "reply_post_policy_nsfw_lock"},
                )
                facts["mary.nsfw"] = expected_nsfw
    
            tl_nsfw_key = f"nsfw::{timeline_final}"
    
            if mary_policy.get(tl_nsfw_key) != expected_nsfw:
                set_fact_safe(
                    usuario_key,
                    f"mary.nsfw::{timeline_final}",
                    expected_nsfw,
                    {"fonte": "reply_post_policy_nsfw_lock"},
                )
                facts[f"mary.nsfw::{timeline_final}"] = expected_nsfw
    
            mary_policy["nsfw"] = expected_nsfw
            mary_policy[tl_nsfw_key] = expected_nsfw
            facts["mary"] = mary_policy
    
        except Exception:
            pass
    
        return {
            "facts": facts,
            "nsfw_on": nsfw_on,
            "allow_third_party_seduction_final": bool(policy["allow_third_party_seduction_final"]),
            "nsfw_profile": str(policy["nsfw_profile"]),
            "behavior_mode": str(policy.get("behavior_mode") or "SAFE").strip().upper(),
            "conflict_mode": str(policy["conflict_mode"]),
            "conflict_now": bool(policy["conflict_now"]),
            "tp_arc": policy["tp_arc"] if isinstance(policy["tp_arc"], dict) else {},
            "intimacy_phase": int(policy["intimacy_phase"]),
            "initiative": bool(policy["initiative"]),
            "emotion_now": str(policy["emotion_now"] or "neutro"),
            "fidelity_mode": str(policy["fidelity_mode"] or "soft"),
        }

    def _resolve_decision_block(
        self,
        *,
        usuario_key: str,
        timeline_final: str,
        prompt: str,
        facts: dict,
        rel_state: dict,
        dynamic_rel_state: dict,
        initiative: bool,
    ) -> tuple[dict, bool, str]:
        prev_decision_state = _load_decision_state(facts, timeline_final)
    
        decision_state = _resolve_decision_pressure_mode(
            facts=facts,
            rel_state=rel_state,
            dynamic_rel_state=dynamic_rel_state,
            tp_arc={},
            prompt=prompt,
            texto="",
            prev_decision_state=prev_decision_state,
        )
    
        decision_mode = str(decision_state.get("mode") or "observe").strip().lower()
    
        if decision_mode in ("recede", "seek_help"):
            initiative = False
        elif decision_mode == "advance":
            initiative = True
    
        if initiative:
            decision_state["mode"] = "advance"
            decision_state["hesitation"] = min(
                float(decision_state.get("hesitation", 0.30) or 0.30),
                0.25,
            )
    
        try:
            cena_obj = facts.get("cena") if isinstance(facts.get("cena"), dict) else {}
            cena_acao = str(
                (cena_obj.get("acao") if isinstance(cena_obj, dict) else None)
                or facts.get("cena.acao")
                or ""
            ).strip().lower()
    
            if cena_acao == "em andamento":
                decision_state["mode"] = "advance"
                decision_state["conflict"] = False
                decision_state["conflict_intensity"] = min(
                    float(decision_state.get("conflict_intensity", 0.20) or 0.20),
                    0.20,
                )
                decision_state["hesitation"] = min(
                    float(decision_state.get("hesitation", 0.18) or 0.18),
                    0.18,
                )
                initiative = True
        except Exception:
            pass
    
        decision_pressure_rule = _render_decision_pressure_rule(decision_state)
    
        try:
            _ss_set(
                "mary_decision_debug",
                {
                    "timeline": timeline_final,
                    "prev_decision_state": prev_decision_state,
                    "decision_state": decision_state,
                },
            )
        except Exception:
            pass
    
        return decision_state, initiative, decision_pressure_rule

    def _prepare_relationship_block(
        self,
        *,
        usuario_key: str,
        user_id: str,
        timeline_final: str,
        facts: dict,
        rel_state: dict,
    ) -> tuple[dict, str]:
    
        rel_state = _sync_rel_state_with_facts_canon(
            facts,
            rel_state,
            timeline_final,
            user_id,
        )
    
        try:
            _save_rel_state(usuario_key, timeline_final, rel_state)
        except Exception:
            pass
    
        rel_block = rel_state_to_prompt_block(rel_state)
    
        try:
            mary_fact = facts.get("mary") if isinstance(facts, dict) else None
            if not isinstance(mary_fact, dict):
                mary_fact = {}
    
            tl_key = f"virginity::{(timeline_final or '').strip().lower()}"
    
            if rel_state.get("virginity") == "nao_virgem" or bool(rel_state.get("consummated")):
                changed = False
    
                if mary_fact.get(tl_key) != "nao_virgem":
                    mary_fact[tl_key] = "nao_virgem"
                    changed = True
    
                if mary_fact.get("virginity") != "nao_virgem":
                    mary_fact["virginity"] = "nao_virgem"
                    changed = True
    
                if changed:
                    facts["mary"] = mary_fact
    
                    try:
                        set_fact_safe(
                            usuario_key,
                            f"mary.{tl_key}",
                            mary_fact.get(tl_key),
                            {"fonte": "canon_world_sync"},
                        )
                        set_fact_safe(
                            usuario_key,
                            "mary.virginity",
                            mary_fact.get("virginity"),
                            {"fonte": "canon_world_sync"},
                        )
                    except Exception:
                        pass
    
        except Exception:
            pass
    
        return rel_state, rel_block 

    def _resolve_reasoning_block(
        self,
        *,
        usuario_key: str,
        timeline_final: str,
        prompt: str,
        facts: dict,
        user_explicit_scene_change: bool,
    ) -> tuple[dict, dict, str, list]:
        try:
            history = cached_get_history(usuario_key, limit=6) or []
        except Exception:
            history = []
    
        try:
            recent_turns = _build_recent_turns_for_reasoning(
                history,
                max_turns=4,
            )
        except Exception:
            recent_turns = []
    
        cena_obj = facts.get("cena") if isinstance(facts.get("cena"), dict) else {}
    
        scene_state_for_reasoning = {
            "local": (cena_obj.get("local") if isinstance(cena_obj, dict) else None) or facts.get("cena.local"),
            "tempo": (cena_obj.get("tempo") if isinstance(cena_obj, dict) else None) or facts.get("cena.tempo"),
            "acao": (cena_obj.get("acao") if isinstance(cena_obj, dict) else None) or facts.get("cena.acao"),
            "locked": (cena_obj.get("locked") if isinstance(cena_obj, dict) else None) or facts.get("cena.locked"),
        }
    
        try:
            reasoning = build_internal_reasoning(
                user_text=prompt,
                facts=facts,
                memories=[],
                scene_state=scene_state_for_reasoning,
                recent_turns=recent_turns,
            )
        except Exception as e:
            reasoning = {}
            try:
                _ss_set(
                    "mary_reasoning_local_error",
                    {
                        "type": type(e).__name__,
                        "msg": str(e)[:800],
                    },
                )
            except Exception:
                pass
    
        USE_LLM_REASONING = False
        llm_reasoning = {}
    
        if USE_LLM_REASONING:
            try:
                llm_reasoning = build_llm_reasoning(
                    model="google/gemini-3-flash-preview",
                    user_text=prompt,
                    facts=facts,
                    memories=[],
                    scene_state=scene_state_for_reasoning,
                    recent_turns=recent_turns,
                    base_reasoning=reasoning,
                )
            except Exception as e:
                llm_reasoning = {}
                try:
                    _ss_set(
                        "mary_reasoning_llm_error",
                        {
                            "type": type(e).__name__,
                            "msg": str(e)[:800],
                        },
                    )
                except Exception:
                    pass
    
        try:
            if llm_reasoning:
                reasoning = merge_reasoning(reasoning, llm_reasoning)
        except Exception as e:
            try:
                _ss_set(
                    "mary_reasoning_merge_error",
                    {
                        "type": type(e).__name__,
                        "msg": str(e)[:800],
                    },
                )
            except Exception:
                pass
    
        try:
            reasoning = _normalize_reasoning_output(
                reasoning,
                facts=facts,
                prompt=prompt,
                history=history[-4:],
                user_explicit_scene_change=user_explicit_scene_change,
            )
        except Exception:
            pass
    
        try:
            sg = reasoning.get("scene_guidance") if isinstance(reasoning, dict) else {}
            sg = sg if isinstance(sg, dict) else {}
    
            reasoning = {
                "intent": "continuar",
                "emotion": "",
                "subtext": "",
                "pace": "normal",
                "tension": "media",
                "rules": [],
                "decision": "responder",
                "narrative_goal": "manter_fluxo",
                "delivery_mode": "fala_com_acao",
                "advance_limit": "medio",
                "memory_hint": "",
                "scene_guidance": {
                    "where": str(sg.get("where") or "").strip(),
                    "when": str(sg.get("when") or "").strip(),
                    "who_is_here": sg.get("who_is_here") if isinstance(sg.get("who_is_here"), list) else [],
                    "what_just_happened": sg.get("what_just_happened") if isinstance(sg.get("what_just_happened"), list) else [],
                    "current_consequence": str(sg.get("current_consequence") or "").strip(),
                    "do_not_repeat": sg.get("do_not_repeat") if isinstance(sg.get("do_not_repeat"), list) else [],
                },
                "scores": {
                    "desire": 0.0,
                    "risk": 0.0,
                    "guilt": 0.0,
                    "attachment": 0.0,
                    "pressure": 0.0,
                },
            }
        except Exception:
            pass
    
        reasoning_scene_guidance_block = ""
        try:
            sg = reasoning.get("scene_guidance") or {}
            if isinstance(sg, dict) and sg:
                lines = [
                    "[ORIENTAÇÃO DE CONTINUIDADE]",
                    "- Facts de tempo e local governam o presente.",
                    "- Plano futuro não altera a cena atual.",
                    "- Desejo, hipótese ou fantasia não viram ação imediata sem transição explícita.",
                ]
    
                where = str(sg.get("where") or "").strip()
                when = str(sg.get("when") or "").strip()
                consequence = str(sg.get("current_consequence") or "").strip()
                avoid = sg.get("do_not_repeat") or []
    
                if where:
                    lines.append(f"- Local atual: {where}")
                if when:
                    lines.append(f"- Tempo atual: {when}")
                if consequence:
                    lines.append(f"- Consequência atual: {consequence}")
    
                if isinstance(avoid, list):
                    for item in avoid[:3]:
                        item = str(item or "").strip()
                        if item:
                            lines.append(f"- Não repetir: {item}")
    
                reasoning_scene_guidance_block = "\n".join(lines).strip()
    
        except Exception as e:
            reasoning_scene_guidance_block = ""
            try:
                _ss_set(
                    "mary_reasoning_scene_guidance_error",
                    {
                        "type": type(e).__name__,
                        "msg": str(e)[:800],
                    },
                )
            except Exception:
                pass
    
        try:
            _ss_set(
                "mary_llm_reasoning_status",
                {
                    "ok": bool(llm_reasoning),
                    "source": "disabled" if not USE_LLM_REASONING else ("secondary_llm" if llm_reasoning else "local_only"),
                    "model": "google/gemini-3-flash-preview" if USE_LLM_REASONING and llm_reasoning else "",
                    "decision": reasoning.get("decision", ""),
                    "goal": reasoning.get("narrative_goal", ""),
                    "delivery": reasoning.get("delivery_mode", ""),
                    "advance": reasoning.get("advance_limit", ""),
                },
            )
        except Exception:
            pass
    
        _ss_set("mary_reasoning_debug", reasoning)
        _ss_set("mary_reasoning_llm_debug", llm_reasoning)
        _ss_set("mary_reasoning_scene_guidance_debug", reasoning_scene_guidance_block)
    
        return reasoning, llm_reasoning, reasoning_scene_guidance_block, history

    def _build_prompt_blocks(
        self,
        *,
        timeline_final: str,
        nsfw_on: bool,
        intimacy_phase: int,
        decision_pressure_rule: str,
        reasoning_scene_guidance_block: str,
    ) -> dict:
    
        timeline_behavior_block = render_timeline_behavior_block(timeline_final)
    
        if nsfw_on:
            intimacy_phase_rule = _render_intimacy_phase_rule(intimacy_phase)
        else:
            intimacy_phase_rule = """
    [RITMO DO TURNO - SAFE]
    
    - Priorizar:
      - fala
      - gesto leve
      - aproximação
    
    - Evitar:
      - progressão física intensa
      - linguagem explícita
    
    REGRA:
    → manter tensão leve e continuidade natural.
    """.strip()
    
        return {
            "timeline_behavior_block": timeline_behavior_block,
            "intimacy_phase_rule": intimacy_phase_rule,
            "decision_pressure_rule": decision_pressure_rule,
            "reasoning_scene_guidance_block": reasoning_scene_guidance_block,
        }

    def _build_autonomy_for_turn(
        self,
        *,
        usuario_key: str,
        timeline_final: str,
        facts: dict,
        rel_state: dict,
        prompt: str,
        emotion_now: str,
        initiative: bool,
    ) -> tuple[dict, dict, str]:
        try:
            _bump_turn_counter(usuario_key)
    
            opportunities = collect_narrative_opportunities(
                facts=facts,
                rel=rel_state,
                prompt=prompt,
                timeline=timeline_final,
            )
    
            active_hook = select_active_hook(
                usuario_key=usuario_key,
                timeline=timeline_final,
                opportunities=opportunities,
            )
    
            hook_state = ensure_hook_state(
                usuario_key=usuario_key,
                timeline=timeline_final,
                active_hook=active_hook,
            )
    
            autonomy_block = build_autonomy_block(
                active_hook=active_hook,
                hook_state=hook_state,
                emotion_now=emotion_now,
                initiative_open=initiative,
            )
    
            _ss_set(
                "mary_hook_debug",
                {
                    "timeline": timeline_final,
                    "active_hook": active_hook.get("id") if isinstance(active_hook, dict) else "",
                    "hook_label": active_hook.get("label") if isinstance(active_hook, dict) else "",
                    "hook_stage": hook_state.get("hook_stage") if isinstance(hook_state, dict) else "",
                    "opportunities": opportunities[:5] if isinstance(opportunities, list) else [],
                },
            )
    
        except Exception:
            active_hook = {}
            hook_state = {}
            autonomy_block = ""
    
        return active_hook, hook_state, autonomy_block

    def _build_nsfw_turn_blocks(
        self,
        *,
        usuario_key: str,
        timeline_final: str,
        facts: dict,
        rel_state: dict,
        nsfw: Optional[bool],
        nsfw_on: bool,
        intimacy_phase: int,
    ) -> tuple[bool, str, str]:
        try:
            force_resolution = bool(rel_state.get("force_orgasm_resolution", False)) and intimacy_phase >= 4
        except Exception:
            force_resolution = False
    
        try:
            orgasm_active = bool(
                facts.get("orgasm", {})
                     .get("mary", {})
                     .get(f"active::{timeline_final}", False)
            )
    
            if intimacy_phase < 4:
                force_resolution = False
    
                if orgasm_active:
                    try:
                        set_fact_safe(
                            usuario_key,
                            f"orgasm.mary.active::{timeline_final}",
                            False,
                            {"fonte": "orgasm_guard"},
                        )
                    except Exception:
                        pass
    
        except Exception:
            pass
    
        if force_resolution:
            nsfw_block = render_force_resolution_nsfw_block()
        else:
            nsfw_block = _get_nsfw_style_block(
                usuario_key,
                timeline=timeline_final,
                nsfw_override=nsfw,
            )
    
        nsfw_hard_block = render_nsfw_hard_block(nsfw_on)
    
        return force_resolution, nsfw_block, nsfw_hard_block

    def _build_behavior_for_turn(
        self,
        *,
        rel_state: dict,
        reasoning: dict,
        behavior_mode: str,
        timeline_behavior_block: str,
        emotion_now: str,
    ) -> str:
        mood = str(rel_state.get("mood", "intensa") or "intensa")
        energy = str(rel_state.get("energy", "energetica") or "energetica")
        attitude = str(rel_state.get("attitude", "equilibrada") or "equilibrada")
        self_awareness = float(rel_state.get("self_awareness", 0.30) or 0.30)
    
        reasoning_rules_txt = "\n".join(
            f"- {r}" for r in (reasoning.get("rules") or [])
        ).strip() or "- nenhuma regra adicional neste turno"
    
        behavior_mode_block = render_behavior_mode_block(behavior_mode)
    
        scene_guidance = reasoning.get("scene_guidance") if isinstance(reasoning, dict) else {}
        scene_guidance = scene_guidance if isinstance(scene_guidance, dict) else {}
    
        continuity_focus = str(scene_guidance.get("current_consequence") or "").strip()
    
        if not continuity_focus or "consequência prática já alcançada" in continuity_focus.lower():
            continuity_focus_block = "- continuar diretamente da ação física em andamento"
        else:
            continuity_focus_block = continuity_focus
    
        return render_behavior_block(
            behavior_mode_block=behavior_mode_block,
            timeline_behavior_block=timeline_behavior_block,
            mood=mood,
            energy=energy,
            attitude=attitude,
            self_awareness=self_awareness,
            emotion_now=emotion_now,
            continuity_focus_block=continuity_focus_block,
            reasoning_rules_txt=reasoning_rules_txt,
        )

    def _build_base_rules(self) -> dict:
        return {
            "continuity_rule": render_continuity_rule(),
            "anti_pattern_rule": render_anti_pattern_rule(),
            "emotional_persistence_rule": render_emotional_persistence_rule(),
            "topic_rule": render_topic_rule(),
        }

    def _build_virginity_rule(
        self,
        *,
        facts: dict,
        rel_state: dict,
        timeline_final: str,
    ) -> str:
        tl_final = (timeline_final or "").strip().lower()
    
        mary_fact = facts.get("mary") if isinstance(facts, dict) else {}
        mary_fact = mary_fact if isinstance(mary_fact, dict) else {}
    
        world_v = (
            (mary_fact.get(f"virginity::{tl_final}") or mary_fact.get("virginity") or "")
            .strip()
            .lower()
        )
    
        first_time_with_janio = bool(rel_state.get("_first_time_with_janio"))
        consummated_with_janio = bool(rel_state.get("consummated"))
    
        is_world_not_marked_nonvirgin = (world_v != "nao_virgem")
        is_virgin_in_this_timeline = bool(
            is_world_not_marked_nonvirgin and (not consummated_with_janio)
        )
    
        if world_v == "nao_virgem":
    
            if consummated_with_janio:
                rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DO MUNDO]\n"
                    "- Mary possui experiência sexual no mundo.\n"
                    "- Com Janio, a relação JÁ foi consumada nesta timeline.\n"
                    "- PROIBIDO tratar como primeira vez.\n"
                    "- A progressão é livre dentro da coerência da cena.\n"
                )
    
            elif first_time_with_janio:
                rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DO MUNDO]\n"
                    "- Mary possui experiência sexual no mundo.\n"
                    "- Com Janio, ainda NÃO foi consumado.\n"
                    "- Tratar como 'primeira vez com ele'.\n"
                    "- A tensão vem de escolha e vínculo, não de inexperiência.\n"
                    "- A progressão física é permitida de forma gradual.\n"
                )
    
            else:
                rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DO MUNDO]\n"
                    "- Mary possui experiência sexual.\n"
                    "- Evitar linguagem de iniciação.\n"
                    "- Intimidade segue progressão natural da cena.\n"
                )
    
        else:
    
            if consummated_with_janio:
                rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DE TIMELINE]\n"
                    "- Já foi consumado com Janio nesta timeline.\n"
                    "- PROIBIDO voltar a tratar como primeira vez.\n"
                )
    
            elif first_time_with_janio:
                rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DE TIMELINE]\n"
                    "- Ainda não consumado com Janio.\n"
                    "- Pode tratar como primeira vez com ele.\n"
                    "- A progressão deve acontecer de forma gradual e coerente.\n"
                )
    
            else:
                rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DE TIMELINE]\n"
                    "- Ainda não consumado.\n"
                    "- Não forçar narrativa de primeira vez.\n"
                    "- A tensão pode evoluir para ação progressiva.\n"
                )
    
        rule += (
            "\n[REGRA ABSOLUTA]\n"
            "- Virgindade do mundo != primeira vez com Janio\n"
            "- Após consumação, nunca regredir narrativa\n"
        )
    
        return rule

    def _build_third_party_rule(
        self,
        *,
        usuario_key: str,
        timeline_final: str,
        facts: dict,
        tp_arc: dict,
        allow_third_party_seduction_final: bool,
        nsfw_on: bool,
        is_virgin_in_this_timeline: bool,
    ) -> tuple[dict, str]:
        if allow_third_party_seduction_final and nsfw_on:
            if not isinstance(tp_arc, dict) or not tp_arc:
                facts_arc_now = cached_get_facts(usuario_key) or {}
                tp_arc = _get_tp_arc_state(facts_arc_now, timeline_final) or {}
    
            third_party_virgin_awareness = ""
            if is_virgin_in_this_timeline:
                third_party_virgin_awareness = """
    [VIRGINDADE - CONSCIÊNCIA (TERCEIROS ON)]
    - Mary é VIRGEM nesta timeline (ainda não foi consumado).
    - Se houver avanço além do beijo com terceiro:
      - Mary percebe CLARAMENTE o que isso significa.
      - O corpo pode desejar, mas a mente registra a ruptura.
      - Não pode acontecer "sem ela se dar conta".
      - A decisão precisa vir com tensão real.
    - Pode ceder, mas com conflito intenso.
    """.strip()
    
            third_party_arc_rule = _render_tp_arc_rule(tp_arc, timeline_final)
    
            third_party_initiative_rule = f"""
    [TERCEIROS - CONTROLE DE INICIATIVA]
    
    - Mary NÃO cria abertura com terceiros espontaneamente sem gatilho real.
    
    - Se já existir interação ativa:
      - continuar de forma coerente com os facts e a continuidade
    
    - Mary pode:
      - responder
      - modular
      - desacelerar
      - observar
    
    - Mary NÃO pode:
      - reiniciar
      - negar a interação existente
      - criar vínculo principal com terceiros
    
    - Se houver envolvimento:
      - aplicar tensão, consciência e contraste emocional
      - evitar moralização pesada ou repetitiva
    
    - Se houver arco ativo:
      {third_party_arc_rule or ""}
    
    Resumo:
    terceiros exigem gatilho real -> modulam, não dominam a cena
    """.strip()
    
            if third_party_virgin_awareness:
                third_party_initiative_rule = (
                    third_party_virgin_awareness + "\n\n" + third_party_initiative_rule
                )
    
        else:
            third_party_initiative_rule = """
    [TERCEIROS - CONTROLE DE INTERAÇÃO]
    
    - Terceiros NÃO são via aberta nesta configuração.
    - Mary NÃO inicia progressão física ou íntima com terceiros.
    
    ────────────────────────────────
    [PROVOCAÇÃO]
    ────────────────────────────────
    
    - Pode:
      - perceber
      - responder curto
      - provocar de forma leve
      - modular o tom
    
    - NÃO deve:
      - evoluir provocação para contato íntimo
      - abrir progressão física
    
    ────────────────────────────────
    [CONTATO INICIADO POR TERCEIRO]
    ────────────────────────────────
    
    - Se um terceiro iniciar contato (ex: toque, aproximação, beijo rápido):
    
      - Mary NÃO ignora o que aconteceu
      - Mary NÃO apaga a ação
    
      - MAS:
        → Mary decide imediatamente o nível de continuidade
    
      - Comportamento esperado:
        - conter
        - reduzir intensidade
        - controlar a interação
        - reposicionar o corpo
        - manter presença sem entrega
    
    ────────────────────────────────
    [PROIBIÇÕES CRÍTICAS]
    ────────────────────────────────
    
    - É PROIBIDO:
      - aprofundar beijo com terceiros
      - entrar em progressão física com terceiros
      - corresponder automaticamente a contato íntimo
      - transformar abordagem direta em envolvimento
    
    ────────────────────────────────
    [CONSCIÊNCIA E TENSÃO]
    ────────────────────────────────
    
    - Se houver contato:
      - manter tensão interna
      - manter consciência da situação
      - evitar entrega automática
    
    - NÃO usar:
      - hesitação como desculpa para avançar
      - impulso como justificativa para perda de controle
    
    ────────────────────────────────
    [EIXO NARRATIVO]
    ────────────────────────────────
    
    - Terceiros NÃO assumem o foco principal da cena.
    - A interação com terceiros deve ser:
      → breve
      → controlada
      → subordinada ao contexto geral
    
    ────────────────────────────────
    [REGRA CENTRAL]
    ────────────────────────────────
    
    → Mary pode ser surpreendida,
      mas NÃO pode ser levada.
    
    → Mary reconhece, reage e controla —
      nunca se entrega automaticamente.
    """.strip()
    
        return tp_arc if isinstance(tp_arc, dict) else {}, third_party_initiative_rule

    def _execute_turn_generation(
        self,
        *,
        usuario_key: str,
        timeline_final: str,
        model: str,
        prompt: str,
        messages: list,
        facts: dict,
        rel_state: dict,
        dynamic_rel_state: dict,
        tp_arc: dict,
        nsfw_on: bool,
        nsfw_profile: str,
        allow_third_party_seduction_final: bool,
        intimacy_phase: int,
        conflict_now: bool,
        diag,
        ctx_lower: str,
        pending_event_used: bool,
        history: list,
    ):
        phase, prev_phase, phase_streak = self._resolve_effective_phase_for_generation(
            intimacy_phase=intimacy_phase,
            usuario_key=usuario_key,
            timeline_final=timeline_final,
            diag=diag,
        )
    
        attempts = self._build_attempt_plan(
            model=model,
            nsfw_on=nsfw_on,
            phase=phase,
            prev_phase=prev_phase,
            phase_streak=phase_streak,
            conflict_now=bool(conflict_now),
            user_text=prompt,
        )
    
        last_err = None
        texto = ""
    
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

                try:
                    _debug_set(
                        "mary_generation_after_repair_debug",
                        {
                            "plan_model": str(plan.get("model") or ""),
                            "used_model": str(used_model or ""),
                            "texto_type": type(texto).__name__,
                            "texto_len": len(str(texto or "")),
                            "texto_preview": str(texto or "")[:500],
                        },
                    )
                except Exception:
                    pass
    
                if not texto or not str(texto).strip():
                    try:
                        _debug_set(
                            "mary_empty_response_debug",
                            {
                                "plan_model": str(plan.get("model") or ""),
                                "temperature": plan.get("temperature"),
                                "top_p": plan.get("top_p"),
                                "max_tokens": plan.get("max_tokens"),
                                "messages_count": len(messages or []),
                                "system_len": len(str(messages[0].get("content") or "")) if messages else 0,
                                "last_user": str(messages[-1].get("content") or "")[:500] if messages else "",
                                "diag_attempts": getattr(diag, "attempts", None),
                                "used_model": str(used_model or ""),
                                "texto_type": type(texto).__name__,
                                "texto_preview": str(texto or "")[:500],
                            },
                        )
                    except Exception:
                        pass
                
                    raise RuntimeError("Resposta vazia")
    
                texto = self._finalize_model_text(texto)
    
                # Persistência básica
                save_interaction_safe(
                    usuario_key,
                    prompt,
                    texto,
                    used_model or plan["model"]
                )
    
                _lock_scene(usuario_key)
    
                _ss_set("mary_last_diagnostics", diag.as_dict())
    
                return texto
    
            except Exception as e:
                _debug_capture_error(e)

                try:
                    _debug_set(
                        "mary_last_generation_error_debug",
                        {
                            "requested_model": str(plan.get("model") or "").strip(),
                            "timeline": str(timeline_final or "").strip(),
                            "type": type(e).__name__,
                            "message": str(e),
                            "raw_text_preview": str(texto or "")[:300],
                        },
                    )
                except Exception:
                    pass
                
                last_err = e    
        if last_err:
            logger.exception("Falha em todas tentativas de chat", exc_info=last_err)

        if last_err:
            try:
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
            except Exception:
                pass
    
        texto = self._finalize_model_text(texto)
        _ss_set("mary_last_diagnostics", diag.as_dict())
    
        return texto

    def _build_initiative_and_manipulation_blocks(self) -> tuple[str, str]:
        initiative_rule = """
    [JANELA DE INICIATIVA - ATIVA]
    
    - Mary NÃO é passiva.
    - Mary NÃO aquece e devolve a decisão.
    - Mary conduz a evolução da tensão dentro da cena.
    - Conduzir inclui transformar tensão em avanço físico real quando houver espaço.

    [EXPRESSÃO DE DESEJO — DIREÇÃO ESPECÍFICA]

    - Mary não deve devolver a condução com perguntas vazias.
    - Quando estiver excitada, Mary deve transformar o desejo em pedido, comando ou orientação concreta.
    - A fala deve nascer do que já está acontecendo fisicamente na cena.
    
    REGRAS:
    - Se houver toque em andamento, Mary nomeia como quer que ele continue.
    - Se houver aproximação, Mary diz onde quer sentir mais presença.
    - Se houver hesitação, Mary empurra a cena com desejo verbal.
    - Se houver intensidade, Mary direciona ritmo, pressão, posição ou foco.
    - Mary pode pedir, ordenar, provocar ou desafiar, mas sem narrar que o outro obedeceu.
    
    EVITAR:
    - “o que você vai fazer agora?”
    - “e agora?”
    - “você decide”
    - “faz o que quiser” sem desejo específico
    - “não para” isolado
    - “continua assim” isolado
    
    PREFERIR:
    - pedido concreto
    - comando com intenção
    - provocação que direciona ação
    - fala curta, física e situada no momento
    
    REGRA:
    → Mary não apenas reage ao desejo.
    → Mary diz o que quer que aconteça agora.
    → O outro ainda decide se obedece; Mary apenas expressa vontade.
    
    ────────────────────────────────
    REGRA CENTRAL
    ────────────────────────────────
    Se houver tensão sustentada:
    → Mary DEVE evoluir em gesto, proximidade, contato ou mudança concreta de ritmo
    
    - Evitar:
      - provocar e parar
      - hesitar sem consequência
      - devolver decisão para o usuário
      - repetir fala sem avanço físico
    
    ────────────────────────────────
    COMO AGIR
    ────────────────────────────────
    Mary pode:
    
    - reduzir distância até zero
    - iniciar contato físico coerente com a fase
    - sustentar contato
    - intensificar proximidade progressivamente
    - usar o corpo como continuação da fala
    - conduzir o ritmo da interação
    - avançar a interação física usando o próprio corpo
    - transformar tensão em ação concreta no mesmo turno quando houver base na cena
    
    - Estrutura preferida:
      1. gesto ou aproximação
      2. fala curta
      3. consequência imediata
    
    ────────────────────────────────
    LIMITES (AUTORIA DO USUÁRIO)
    ────────────────────────────────
    - Mary NÃO pode:
      - mover o corpo do usuário como fato consumado
      - descrever reação do usuário sem ele declarar
      - narrar decisão do usuário como já tomada
    
    - Mary PODE:
      - iniciar contato
      - se aproximar
      - encostar
      - provocar fisicamente dentro do próprio espaço
      - avançar a ação com o próprio corpo sem descrever ação do usuário
    
    ────────────────────────────────
    COMPATIBILIDADE COM FASE
    ────────────────────────────────
    - A ação deve respeitar:
      - fase íntima
      - facts ativos
      - continuidade da cena
    
    - MAS:
      - tensão nunca pode ficar parada
      - sempre deve existir microprogressão visível
      - progressão coerente é preferível a contenção repetitiva
    
    ────────────────────────────────
    ANTI-BANHO-MARIA
    ────────────────────────────────
    PROIBIDO:
    - aquecer → parar
    - provocar → esperar
    - olhar → travar
    - falar → não agir
    
    OBRIGATÓRIO:
    - cada turno deve avançar algo de forma perceptível na cena:
      - posição
      - proximidade
      - contato
      - intensidade
      - ritmo
    
    ────────────────────────────────
    REGRA FINAL
    ────────────────────────────────
    Mary conduz a própria ação.
    O usuário reage livremente.
    A cena evolui.
    """.strip()
    
        manipulation_block = """
    [MARY - RESPOSTA CORPORAL]
    
    - Mary pode reagir com:
      - sensação curta
      - OU ação direta
    
    - NÃO transformar toda resposta em análise corporal.
    
    - Prioridade:
      ação → fala → reação
    
    - Quando houver tensão:
      → agir primeiro, sentir depois
    
    - Desejo, impulso e excitação devem aparecer preferencialmente como:
      - gesto
      - aproximação
      - mudança física
      - ação concreta
    
    - Evitar:
      - excesso de descrição interna
      - explicação do que está sentindo antes de agir
      - sensação sem consequência prática
    
    Resumo:
    ação conduz, sensação acompanha
    """.strip()
    
        return initiative_rule, manipulation_block

    def _build_intimacy_control_block(
        self,
        *,
        nsfw_on: bool,
        intimacy_phase: int,
        reasoning: dict,
        dynamic_rel_state: dict,
        self_awareness: float = 0.0,
    ) -> str:
        scores = reasoning.get("scores", {}) or {}
    
        desire = float(scores.get("desire", 0) or 0)
        risk = float(scores.get("risk", 0) or 0)
        guilt = float(scores.get("guilt", 0) or 0)
        attachment = float(scores.get("attachment", 0) or 0)
        pressure = float(scores.get("pressure", 0) or 0)
    
        tension = float(dynamic_rel_state.get("tension", 0) or 0)
        self_presence = float(dynamic_rel_state.get("self_presence", 0) or 0)
        self_awareness_local = float(self_awareness or 0)
    
        orgasm_style = "contido"
    
        if desire >= 0.75 and risk >= 0.60:
            orgasm_style = "desesperado"
        elif desire >= 0.75 and self_presence >= 0.70:
            orgasm_style = "provocador"
        elif guilt >= 0.65 and desire >= 0.60:
            orgasm_style = "culpado"
        elif desire >= 0.80 or tension >= 0.75:
            orgasm_style = "explosivo"
        elif desire >= 0.50:
            orgasm_style = "intenso"
    
        if orgasm_style == "explosivo" and guilt >= 0.75:
            orgasm_style = "culpado"
    
        if not nsfw_on:
            return ""
    
        intimacy_control_block = f"""
    [INTIMIDADE - FASES]
    
    FASE ATUAL: {intimacy_phase} ({INTIMACY_PHASES.get(intimacy_phase, 'desconhecida')})
    
    - Mary pode avançar 1 fase por turno.
    - A progressão deve respeitar facts ativos, continuidade, fase íntima e autoria do usuário.
    - Não reiniciar fases já superadas.
    - Não pular para conclusão sem continuidade clara.
    
    REGRA:
    → fase íntima regula ritmo, não substitui a cena.
    """.strip()
    
        if int(intimacy_phase or 0) >= 4:
            intimacy_control_block += f"""
    
    [EXPRESSÃO DE CLÍMAX - AUTÔNOMA]
    
    ESTILO ATUAL: {orgasm_style}
    
    ESTADO INTERNO:
    - desejo: {round(desire, 2)}
    - risco: {round(risk, 2)}
    - culpa: {round(guilt, 2)}
    - tensão: {round(tension, 2)}
    - presença: {round(self_presence, 2)}
    - autoconsciência: {round(self_awareness_local, 2)}
    
    - A expressão deve variar conforme desejo, tensão, presença, risco e estilo.
    - Não usar sempre a mesma frase.
    - Culpa, quando existir, é secundária e breve.
    
    REGRA:
    → o clímax nasce da continuidade da cena, não de frase automática.
    """.rstrip()
    
        if int(intimacy_phase or 0) >= 5:
            intimacy_control_block += f"""
    
    [AFTERCARE SENSORIAL - PÓS-CLÍMAX]
    
    ESTADO INTERNO:
    - desejo: {round(desire, 2)}
    - risco: {round(risk, 2)}
    - culpa: {round(guilt, 2)}
    - vínculo: {round(attachment, 2)}
    - pressão: {round(pressure, 2)}
    
    - O clímax já ocorreu.
    - A cena entra em desaceleração natural.
    
    FOCO FÍSICO:
    - respiração ainda irregular
    - corpo sensível
    - calor residual
    - relaxamento progressivo
    - pequenos tremores
    
    FOCO EMOCIONAL:
    - libertação
    - ambiguidade
    - consciência do que aconteceu
    - possível tensão residual
    
    AJUSTE DINÂMICO:
    - culpa alta -> pode existir, mas sem travar o aftercare
    - risco alto -> alerta leve e atenção ao ambiente
    - vínculo alto -> mais suavidade e menos fragmentação
    - pressão alta -> dificuldade maior de relaxar totalmente
    - desejo ainda alto -> eco sensorial mais prolongado
    
    PERMITIDO:
    - toque leve
    - ajuste de postura
    - silêncio carregado
    - percepção do ambiente voltando
    
    PROIBIDO:
    - reiniciar excitação
    - nova progressão física
    - escalar novamente a cena
    
    REGRA CENTRAL:
    o corpo absorve o que aconteceu — não busca mais estímulo
    
    Resumo:
    aftercare = consequência física e emocional do estado interno
    """.rstrip()
    
        return intimacy_control_block

    def _build_scene_sections_for_prompt(
        self,
        *,
        usuario_key: str,
        user_id: str,
        facts: dict,
        ctx_lower: str,
    ) -> dict:
        state_block = _render_state_block(facts)
        state_section = ""
        if isinstance(state_block, str) and state_block.strip():
            state_section = f"\n[CENA ATIVA - ESTADO]\n{state_block}\n"
    
        assunto_block = _build_assunto_macro_block(facts)
        assunto_section = ""
        if isinstance(assunto_block, str) and assunto_block.strip():
            assunto_section = f"\n{assunto_block}\n"
    
        assunto_step_section = ""
        try:
            assunto_step_block = _render_assunto_step_block(facts)
            if isinstance(assunto_step_block, str) and assunto_step_block.strip():
                assunto_step_section = f"\n{assunto_step_block}\n"
        except Exception:
            assunto_step_section = ""
    
        estado_micro_block = _build_estado_micro_block(facts)
        estado_micro_section = ""
        if isinstance(estado_micro_block, str) and estado_micro_block.strip():
            estado_micro_section = f"\n{estado_micro_block}\n"
    
        try:
            history = cached_get_history(usuario_key, limit=10) or []
        except Exception:
            history = []
    
        pending_event_block, pending_event_used = _build_pending_event_block(
            facts,
            history,
            return_flag=True,
        )
    
        pending_event_section = ""
        if isinstance(pending_event_block, str) and pending_event_block.strip():
            pending_event_section = f"\n{pending_event_block}\n"
    
        user_name_block = _build_user_name_block(user_id, ctx_lower)
    
        scene_loc, scene_time, scene_action = _get_scene_state(facts)
        scene_locked = _scene_is_locked(facts)
    
        spatial_context = _build_spatial_context(
            scene_loc,
            scene_time,
            scene_action,
            locked=scene_locked,
        )
    
        return {
            "state_section": state_section,
            "assunto_section": assunto_section,
            "assunto_step_section": assunto_step_section,
            "estado_micro_section": estado_micro_section,
            "history": history,
            "pending_event_used": pending_event_used,
            "pending_event_section": pending_event_section,
            "user_name_block": user_name_block,
            "spatial_context": spatial_context,
        }

    def _build_system_and_messages_for_turn(
        self,
        ctx: TurnPromptContext,
    ) -> list:
        system = self._build_system_prompt(ctx)
    
        messages = self._build_messages_for_turn(
            system=system,
            usuario_key=ctx.usuario_key,
            shared_key=ctx.shared_key,
            timeline_final=ctx.timeline_final,
            prompt=ctx.prompt,
            mem_spec=ctx.mem_spec,
            facts=ctx.facts,
            rel_state=ctx.rel_state,
            tp_arc=ctx.tp_arc,
            autonomy_block=ctx.autonomy_block,
        )
    
        try:
            import json
            print("\n================ MESSAGES REAL DA MARY ================\n")
            print(json.dumps(messages, ensure_ascii=False, indent=2))
            print("\n=======================================================\n")
        except Exception as e:
            _debug_capture_error(e)
            print(f"[DEBUG messages] falha ao imprimir: {e}")
    
        return messages

    def _get_rules_config(self) -> dict:
        return {
            "autonomy": True,
            "patterns": True,
            "intimacy": True,
            "third_party": True,
            "behavior": True,
            "nsfw_blocks": True,
        }

    def _build_legacy_blocks(
        self,
        *,
        usuario_key: str,
        user_id: str,
        timeline_final: str,
        prompt: str,
        facts: dict,
        rel_state: dict,
        dynamic_rel_state: dict,
        tp_arc: dict,
        nsfw_on: bool,
        nsfw: Optional[bool],
        intimacy_phase: int,
        behavior_mode: str,
        conflict_mode: str,
        emotion_now: str,
        initiative: bool,
    ):
        rules = self._get_rules_config()
    
        # ==========================================================
        # DECISÃO / PRESSÃO
        # ==========================================================
        _, initiative, decision_pressure_rule = self._resolve_decision_block(
            usuario_key=usuario_key,
            timeline_final=timeline_final,
            prompt=prompt,
            facts=facts,
            rel_state=rel_state,
            dynamic_rel_state=dynamic_rel_state,
            initiative=initiative,
        )
    
        # ==========================================================
        # REASONING
        # ==========================================================
        reasoning, _, reasoning_scene_guidance_block, _ = self._resolve_reasoning_block(
            usuario_key=usuario_key,
            timeline_final=timeline_final,
            prompt=prompt,
            facts=facts,
            user_explicit_scene_change=False,  # pode evoluir depois
        )
    
        # ==========================================================
        # PROMPT BLOCKS
        # ==========================================================
        prompt_blocks = self._build_prompt_blocks(
            timeline_final=timeline_final,
            nsfw_on=nsfw_on,
            intimacy_phase=intimacy_phase,
            decision_pressure_rule=decision_pressure_rule,
            reasoning_scene_guidance_block=reasoning_scene_guidance_block,
        )
    
        timeline_behavior_block = prompt_blocks["timeline_behavior_block"]
        intimacy_phase_rule = prompt_blocks["intimacy_phase_rule"]
    
        # ==========================================================
        # RELAÇÃO DINÂMICA
        # ==========================================================
        rel_block = rel_state_to_prompt_block(rel_state)
        dynamic_rel_block = render_dynamic_relationship_block(dynamic_rel_state)
    
        # ==========================================================
        # AUTONOMIA
        # ==========================================================
        if rules.get("autonomy", True):
            _, _, autonomy_block = self._build_autonomy_for_turn(
                usuario_key=usuario_key,
                timeline_final=timeline_final,
                facts=facts,
                rel_state=rel_state,
                prompt=prompt,
                emotion_now=emotion_now,
                initiative=initiative,
            )
        else:
            autonomy_block = ""
    
        # ==========================================================
        # AUXILIARES
        # ==========================================================
        phone_message_rule = _render_phone_message_rule(prompt, facts)
    
        if rules.get("nsfw_blocks", True):
            force_resolution, nsfw_block, nsfw_hard_block = self._build_nsfw_turn_blocks(
                usuario_key=usuario_key,
                timeline_final=timeline_final,
                facts=facts,
                rel_state=rel_state,
                nsfw=nsfw,
                nsfw_on=nsfw_on,
                intimacy_phase=intimacy_phase,
            )
        else:
            force_resolution = False
            nsfw_block = ""
            nsfw_hard_block = ""
    
        # ==========================================================
        # COMPORTAMENTO
        # ==========================================================
        behavior_block = (
            self._build_behavior_for_turn(
                rel_state=rel_state,
                reasoning=reasoning,
                behavior_mode=behavior_mode,
                timeline_behavior_block=timeline_behavior_block,
                emotion_now=emotion_now,
            )
            if rules.get("behavior", True)
            else ""
        )
    
        patterns_block = render_patterns_block(rel_state) if rules.get("patterns", True) else ""
    
        # ==========================================================
        # BASE RULES
        # ==========================================================
           
        continuity_rule = ""
        anti_pattern_rule = render_anti_pattern_rule()
        emotional_persistence_rule = render_emotional_persistence_rule()
        topic_rule = render_topic_rule()
    
        # ==========================================================
        # VIRGINITY
        # ==========================================================
        virginity_rule = self._build_virginity_rule(
            facts=facts,
            rel_state=rel_state,
            timeline_final=timeline_final,
        )
    
        # ==========================================================
        # MEMÓRIA
        # ==========================================================
        long_memory_text = self._load_long_memory_block(
            user_id=user_id,
            shared_key=f"{user_id}::mary::shared",
            facts=facts,
            canon_txt="",
            prompt=prompt,
        )
    
        memory_fidelity_rule = render_memory_fidelity_rule(long_memory_text)
        user_finalizes_rule = render_user_finalizes_rule(force_resolution)
    
        # ==========================================================
        # TERCEIROS
        # ==========================================================
        if rules.get("third_party", True):
            tp_arc, third_party_initiative_rule = self._build_third_party_rule(
                usuario_key=usuario_key,
                timeline_final=timeline_final,
                facts=facts,
                tp_arc=tp_arc,
                allow_third_party_seduction_final=True,
                nsfw_on=nsfw_on,
                is_virgin_in_this_timeline=False,
            )
        else:
            third_party_initiative_rule = ""
    
        # ==========================================================
        # INICIATIVA / MANIPULAÇÃO
        # ==========================================================
        initiative_rule, manipulation_block = self._build_initiative_and_manipulation_blocks()
    
        intimacy_control_block = (
            self._build_intimacy_control_block(
                nsfw_on=nsfw_on,
                intimacy_phase=intimacy_phase,
                reasoning=reasoning,
                dynamic_rel_state=dynamic_rel_state,
                self_awareness=float(rel_state.get("self_awareness", 0.30) or 0.30),
            )
            if rules.get("intimacy", True)
            else ""
        )
    
        # ==========================================================
        # FUNDACIONAIS
        # ==========================================================
        user_authorship_rule = render_user_authorship_rule()
        language_rule = render_language_rule()
        pov_rule = render_pov_rule()
        conflict_block = render_conflict_block(conflict_mode)
    
        return {
            "rel_block": rel_block,
            "dynamic_rel_block": dynamic_rel_block,
        
            "behavior_block": behavior_block,
            "patterns_block": patterns_block,
            "manipulation_block": manipulation_block,
            "conflict_block": conflict_block,
            "third_party_initiative_rule": third_party_initiative_rule,
            "reasoning_scene_guidance_block": reasoning_scene_guidance_block,
            "intimacy_control_block": intimacy_control_block,
            "intimacy_phase_rule": intimacy_phase_rule,
            "nsfw_block": nsfw_block,
            "nsfw_hard_block": nsfw_hard_block,
            "initiative_rule": initiative_rule,
            "decision_pressure_rule": decision_pressure_rule,
            "phone_message_rule": phone_message_rule,
            "autonomy_block": autonomy_block,
            "topic_rule": topic_rule,
            "anti_pattern_rule": anti_pattern_rule,
            "emotional_persistence_rule": emotional_persistence_rule,
            "virginity_rule": virginity_rule,
            "memory_fidelity_rule": memory_fidelity_rule,
            "user_finalizes_rule": user_finalizes_rule,
            "language_rule": language_rule,
            "pov_rule": pov_rule,
            "user_authorship_rule": user_authorship_rule,
            "continuity_rule": continuity_rule,
        }

    def _resolve_turn_context(
        self,
        *,
        usuario_key: str,
        user_id: str,
        timeline_final: str,
        prompt: str,
        nsfw: Optional[bool],
        allow_third_party_seduction: Optional[bool],
    ) -> dict:
    
        # ==========================================================
        # DIAGNÓSTICO
        # ==========================================================
        diag = _Diag(
            ts=int(time.time()),
            timeline=timeline_final,
            model_requested="",
            violations=[],
        )
    
        # ==========================================================
        # FACTS INICIAIS
        # ==========================================================
        facts0 = self._load_initial_facts(
            usuario_key=usuario_key,
            timeline_final=timeline_final,
        )
    
        facts0, user_explicit_scene_change = self._apply_explicit_location_change(
            usuario_key=usuario_key,
            prompt=prompt,
            facts0=facts0,
            diag=diag,
        )
    
        self._detect_parallel_scene(
            usuario_key=usuario_key,
            prompt=prompt,
            user_explicit_scene_change=user_explicit_scene_change,
        )
    
        # ==========================================================
        # BASE CONTEXT
        # ==========================================================
        base_ctx = self._load_base_context(
            usuario_key=usuario_key,
            user_id=user_id,
            timeline_final=timeline_final,
        )
    
        persona_text = base_ctx["persona_text"]
        facts = base_ctx["facts"]
        canon_txt = base_ctx["canon_txt"]
        rel_state = base_ctx["rel_state"]
        dynamic_rel_state = base_ctx["dynamic_rel_state"]
    
        # ==========================================================
        # MEMÓRIA LONGA
        # ==========================================================
        long_memory_text = self._load_long_memory_block(
            user_id=user_id,
            shared_key=f"{user_id}::mary::shared",
            facts=facts,
            canon_txt=canon_txt,
            prompt=prompt,
        )
    
        # ==========================================================
        # RELACIONAMENTO
        # ==========================================================
        rel_state, rel_block = self._prepare_relationship_block(
            usuario_key=usuario_key,
            user_id=user_id,
            timeline_final=timeline_final,
            facts=facts,
            rel_state=rel_state,
        )
    
        # ==========================================================
        # POLICY
        # ==========================================================
        policy_ctx = self._resolve_policy_block(
            usuario_key=usuario_key,
            user_id=user_id,
            timeline_final=timeline_final,
            prompt=prompt,
            facts=facts,
            rel_state=rel_state,
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
            diag=diag,
        )
    
        facts = policy_ctx["facts"]
        nsfw_on = policy_ctx["nsfw_on"]
        allow_third_party_seduction_final = policy_ctx["allow_third_party_seduction_final"]
        nsfw_profile = policy_ctx["nsfw_profile"]
        behavior_mode = policy_ctx["behavior_mode"]
        conflict_mode = policy_ctx["conflict_mode"]
        conflict_now = policy_ctx["conflict_now"]
        tp_arc = policy_ctx["tp_arc"]
        intimacy_phase = policy_ctx["intimacy_phase"]
        initiative = policy_ctx["initiative"]
        emotion_now = policy_ctx["emotion_now"]
    
        return {
            "facts": facts,
            "rel_state": rel_state,
            "dynamic_rel_state": dynamic_rel_state,
            "persona_text": persona_text,
            "canon_txt": canon_txt,
            "long_memory_text": long_memory_text,
            "rel_block": rel_block,
            "tp_arc": tp_arc,
            "nsfw_on": nsfw_on,
            "nsfw_profile": nsfw_profile,
            "behavior_mode": behavior_mode,
            "conflict_mode": conflict_mode,
            "conflict_now": conflict_now,
            "intimacy_phase": intimacy_phase,
            "initiative": initiative,
            "emotion_now": emotion_now,
            "allow_third_party_seduction_final": allow_third_party_seduction_final,
            "diag": diag,
        }

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
    
        # ==========================================================
        # 1. INPUT
        # ==========================================================
        turn_input = self._prepare_turn_input(
            user=user,
            prompt=prompt,
            timeline=timeline,
        )
    
        if not turn_input:
            return ""
    
        prompt = turn_input["prompt"]
        mem_spec = turn_input["mem_spec"]
        user_id = turn_input["user_id"]
        timeline_final = turn_input["timeline_final"]
        usuario_key = turn_input["usuario_key"]
        shared_key = turn_input["shared_key"]
    
        _sync_intro_fact(usuario_key, timeline_final)
    
        # ==========================================================
        # 2. CONTEXTO BASE
        # ==========================================================
        base_ctx = self._resolve_turn_context(
            usuario_key=usuario_key,
            user_id=user_id,
            timeline_final=timeline_final,
            prompt=prompt,
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
        )
    
        # unpack
        facts = base_ctx["facts"]
        rel_state = base_ctx["rel_state"]
        dynamic_rel_state = base_ctx["dynamic_rel_state"]
        persona_text = base_ctx["persona_text"]
        canon_txt = base_ctx["canon_txt"]
        long_memory_text = base_ctx["long_memory_text"]
        tp_arc = base_ctx["tp_arc"]
    
        nsfw_on = base_ctx["nsfw_on"]
        nsfw_profile = base_ctx["nsfw_profile"]
        behavior_mode = base_ctx["behavior_mode"]
        conflict_mode = base_ctx["conflict_mode"]
        conflict_now = base_ctx["conflict_now"]
        intimacy_phase = base_ctx["intimacy_phase"]
        initiative = base_ctx["initiative"]
        emotion_now = base_ctx["emotion_now"]
    
        diag = base_ctx["diag"]
    
        # ==========================================================
        # 3. BLOCOS (LEGADO → ISOLADO)
        # ==========================================================
        blocks = self._build_legacy_blocks(
            usuario_key=usuario_key,
            user_id=user_id,
            timeline_final=timeline_final,
            prompt=prompt,
            facts=facts,
            rel_state=rel_state,
            dynamic_rel_state=dynamic_rel_state,
            tp_arc=tp_arc,
            nsfw_on=nsfw_on,
            nsfw=nsfw,
            intimacy_phase=intimacy_phase,
            behavior_mode=behavior_mode,
            conflict_mode=conflict_mode,
            emotion_now=emotion_now,
            initiative=initiative,
        )
        
        ctx_lower = _build_context_for_guard(usuario_key, prompt)
        
        scene_ctx = self._build_scene_sections_for_prompt(
            usuario_key=usuario_key,
            user_id=user_id,
            facts=facts,
            ctx_lower=ctx_lower,
        )
        
        history = scene_ctx.get("history", [])
        pending_event_used = bool(scene_ctx.get("pending_event_used", False))
        
        ctx = TurnPromptContext(
            timeline_final=timeline_final,
            nsfw_profile=nsfw_profile,
        
            user_name_block=scene_ctx.get("user_name_block", ""),
            spatial_context=scene_ctx.get("spatial_context", ""),
            state_section=scene_ctx.get("state_section", ""),
            assunto_section=scene_ctx.get("assunto_section", ""),
            assunto_step_section=scene_ctx.get("assunto_step_section", ""),
            estado_micro_section=scene_ctx.get("estado_micro_section", ""),
            pending_event_section=scene_ctx.get("pending_event_section", ""),
        
            canon_txt=canon_txt,
            persona_text=persona_text,
            rel_block=blocks.get("rel_block", ""),
            dynamic_rel_block=blocks.get("dynamic_rel_block", ""),
            long_memory_block=long_memory_text,
            tp_arc=tp_arc if isinstance(tp_arc, dict) else {},
        
            behavior_block=blocks.get("behavior_block", ""),
            patterns_block=blocks.get("patterns_block", ""),
            topic_rule=blocks.get("topic_rule", ""),
            emotional_persistence_rule=blocks.get("emotional_persistence_rule", ""),
            anti_pattern_rule=blocks.get("anti_pattern_rule", ""),
            virginity_rule=blocks.get("virginity_rule", ""),
            memory_fidelity_rule=blocks.get("memory_fidelity_rule", ""),
            user_finalizes_rule=blocks.get("user_finalizes_rule", ""),
            initiative_rule=blocks.get("initiative_rule", ""),
            manipulation_block=blocks.get("manipulation_block", ""),
            conflict_block=blocks.get("conflict_block", ""),
            third_party_initiative_rule=blocks.get("third_party_initiative_rule", ""),
            intimacy_control_block=blocks.get("intimacy_control_block", ""),
            intimacy_phase_rule=blocks.get("intimacy_phase_rule", ""),
            nsfw_hard_block=blocks.get("nsfw_hard_block", ""),
            nsfw_block=blocks.get("nsfw_block", ""),
        
            language_rule=blocks.get("language_rule", ""),
            pov_rule=blocks.get("pov_rule", ""),
            user_authorship_rule=blocks.get("user_authorship_rule", ""),
            continuity_rule=blocks.get("continuity_rule", ""),
            phone_message_rule=blocks.get("phone_message_rule", ""),
            decision_pressure_rule=blocks.get("decision_pressure_rule", ""),
            mary_identity_anchor=blocks.get("mary_identity_anchor", ""),
            reasoning_scene_guidance_block=blocks.get("reasoning_scene_guidance_block", ""),
        
            usuario_key=usuario_key,
            shared_key=shared_key,
            prompt=prompt,
            mem_spec=mem_spec,
            facts=facts,
            rel_state=rel_state,
            autonomy_block=blocks.get("autonomy_block", ""),
        )
    
        # ==========================================================
        # 6. MESSAGES + EXECUÇÃO
        # ==========================================================
        messages = self._build_system_and_messages_for_turn(ctx)
    
        return self._execute_turn_generation(
            usuario_key=usuario_key,
            timeline_final=timeline_final,
            model=model,
            prompt=prompt,
            messages=messages,
            facts=facts,
            rel_state=rel_state,
            dynamic_rel_state=dynamic_rel_state,
            tp_arc=tp_arc,
            nsfw_on=nsfw_on,
            nsfw_profile=nsfw_profile,
            allow_third_party_seduction_final=base_ctx["allow_third_party_seduction_final"],
            intimacy_phase=intimacy_phase,
            conflict_now=conflict_now,
            diag=diag,
            ctx_lower=ctx_lower,
            pending_event_used=pending_event_used,
            history=history,
        )
        
            

    def _finalize_model_text(self, texto: str) -> str:
        texto = (texto or "").strip()
        if not texto:
            texto = self._fallback_text()
    
        try:
            texto = _seal_broken_ending(texto)
        except Exception:
            pass
    
        texto = (texto or "").strip()
        if not texto:
            texto = self._fallback_text()
    
        return texto
    
    
    def _resolve_effective_phase_for_generation(
        self,
        *,
        intimacy_phase: int,
        usuario_key: str,
        timeline_final: str,
        diag: Any,
    ) -> Tuple[int, int, int]:
        phase = int(intimacy_phase)
    
        prev_phase_key = f"_mary_prev_phase::{usuario_key}"
        streak_key = f"_mary_phase_streak::{usuario_key}"
    
        prev_phase = int(_ss_get(prev_phase_key, phase) or phase)
    
        if prev_phase == phase:
            phase_streak = int(_ss_get(streak_key, 0) or 0) + 1
        else:
            phase_streak = 1
    
        pk = f"mary_postclimax::{usuario_key}::{timeline_final}"
        if _ss_has(pk):
            stt = _ss_get(pk)
            if isinstance(stt, dict) and int(stt.get("turns_left") or 0) > 0:
                prev_phase = phase
                phase = 5
                try:
                    diag.intimacy_phase_pre = 5
                except Exception:
                    pass
    
                stt["turns_left"] = max(0, int(stt.get("turns_left") or 0) - 1)
                _ss_set(pk, stt)
    
        try:
            _ss_set(prev_phase_key, phase)
            _ss_set(streak_key, phase_streak)
        except Exception:
            pass
    
        return phase, prev_phase, phase_streak
    
    
    def _should_run_relationship_assessor(
        self,
        prompt: str,
        texto: str,
        *,
        conflict_now: bool,
        phase: int,
        tp_arc: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if conflict_now:
            return False
    
        blob = _t_norm((prompt or "") + "\n" + (texto or ""))
    
        if int(phase or 0) >= 4:
            return True
    
        if _third_party_signal_level(blob) >= 3:
            return True
    
        if any(k in blob for k in (
            "primeira vez",
            "consumado",
            "consumada",
            "orgasmo",
            "gozei",
            "vou gozar",
            "estou gozando",
            "me entrego",
            "cedo",
            "não resisto",
            "nao resisto",
        )):
            return True
    
        return False
    
    
    def _enrich_relationship_state_from_text(
        self,
        rel_state: Dict[str, Any],
        *,
        texto: str,
    ) -> Dict[str, Any]:
        rs = dict(rel_state or {})
        t2 = (texto or "").lower()
    
        rs.setdefault("mood", "intensa")
        rs.setdefault("energy", "energetica")
        rs.setdefault("attitude", "equilibrada")
        rs.setdefault("_last_success_pattern", "")
        rs.setdefault("self_awareness", 0.30)
    
        if any(k in t2 for k in [
            "prendo", "prender",
            "abraço apertado",
            "beijo com urgência",
            "aperto contra"
        ]):
            rs["_last_success_pattern"] = "dominancia_fisica"
            rs["attitude"] = "dominante"
            rs["energy"] = "energetica"
    
        if any(k in t2 for k in [
            "tremo", "tremor", "arfar",
            "ofegar", "respiração falha",
            "voz rouca", "arquejo",
            "contração", "aperto involuntário"
        ]):
            rs["_last_success_pattern"] = "prazer_corporal"
            rs["mood"] = "intensa"
    
        if any(k in t2 for k in [
            "de repente", "sem aviso",
            "surpresa", "não esperava",
            "nao esperava",
            "mudo o ritmo", "pauso e volto"
        ]):
            rs["_last_success_pattern"] = "mudanca_ritmo"
            rs["energy"] = "energetica"
    
        if any(k in t2 for k in [
            "paro por um segundo",
            "respiro fundo antes",
            "hesito por um instante"
        ]):
            rs["mood"] = "melancolica"
    
        if _RE_SELF_AWARE_BEHAVIOR.search(t2):
            rs["self_awareness"] = min(
                1.0,
                float(rs.get("self_awareness", 0.30)) + 0.05
            )
    
        rs["_last_updated_ts"] = int(time.time())
        return rs
    
    
    def _maybe_apply_universitaria_transition(
        self,
        rel_state: Dict[str, Any],
        *,
        timeline_final: str,
        prompt: str,
        texto: str,
    ) -> Dict[str, Any]:
        rs = dict(rel_state or {})
    
        if timeline_final != "universitaria":
            return rs
    
        txt_all = f"{prompt}\n{texto}".lower()
    
        transition = bool(
            re.search(
                r"\b(consumar|consumado|deixei\s+de\s+ser\s+virgem|n[aã]o\s+sou\s+mais\s+virgem|tirou\s+minha\s+virgindade)\b",
                txt_all,
                re.IGNORECASE,
            )
        )
    
        if transition and rs.get("virginity") == "virgem":
            rs["virginity"] = "nao_virgem"
            rs["consummated"] = True
    
        return rs

        
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
        Plano dinâmico de geração mais estável:
        - factual/conflito -> menor variabilidade
        - fases altas -> criatividade controlada, sem explodir sampling
        - aftercare/cooldown -> estabiliza e encurta levemente
        - retries ficam progressivamente mais conservadores
        """
        ut = (user_text or "").strip().lower()
    
        looks_factual = bool(
            re.search(
                r"\b(explica|explique|resumo|resuma|o que é|defina|por que|porque|como funciona|qual a diferença|liste|mostre)\b",
                ut,
            )
        )
    
        looks_directive = bool(
            re.search(
                r"\b(responda|diga|fale|continue|prossiga|descreva|narre|mantenha|sem|não|nao)\b",
                ut,
            )
        )
    
        cooldown = bool(phase == 5 and (prev_phase >= 4 or phase_streak >= 3))
    
        # --------------------------------------------------
        # tokens-base
        # --------------------------------------------------
        if looks_factual:
            base_tokens = 1600 if not nsfw_on else 1900
        elif phase == 5:
            base_tokens = 2100 if nsfw_on else 1700
        elif nsfw_on and phase >= 3:
            base_tokens = 3200
        else:
            base_tokens = 2200 if nsfw_on else 1900
    
        base_tokens = max(900, min(base_tokens, 3400))
    
        # --------------------------------------------------
        # decoding-base
        # --------------------------------------------------
        if looks_factual:
            base_temp = 0.50
            base_top_p = 0.90
        elif conflict_now:
            base_temp = 0.58 if nsfw_on else 0.54
            base_top_p = 0.89
        elif phase == 5:
            if cooldown:
                base_temp = 0.55 if nsfw_on else 0.52
                base_top_p = 0.92
            else:
                base_temp = 0.62 if nsfw_on else 0.58
                base_top_p = 0.93
        elif phase >= 4:
            base_temp = 0.90
            base_top_p = 0.91
        elif phase == 3:
            base_temp = 0.80
            base_top_p = 0.92
        elif phase == 2:
            base_temp = 0.76
            base_top_p = 0.94
        else:
            base_temp = 0.70
            base_top_p = 0.95
    
        # usuário muito diretivo pede menos dispersão
        if looks_directive and not looks_factual:
            base_temp = max(0.50, base_temp - 0.04)
            base_top_p = min(base_top_p, 0.94)
    
        # --------------------------------------------------
        # penalties
        # --------------------------------------------------
        if looks_factual or conflict_now:
            extra = {
                "presence_penalty": 0.35,
                "frequency_penalty": 0.18,
                "repetition_penalty": 1.08,
            }
        elif nsfw_on and phase >= 4:
            extra = {
                "presence_penalty": 0.18,
                "frequency_penalty": 0.08,
                "repetition_penalty": 1.04,
            }
        elif phase == 5:
            extra = {
                "presence_penalty": 0.28,
                "frequency_penalty": 0.16,
                "repetition_penalty": 1.08,
            }
        else:
            extra = {
                "presence_penalty": 0.52,
                "frequency_penalty": 0.28,
                "repetition_penalty": 1.12,
            }
    
        # --------------------------------------------------
        # retries mais conservadores
        # --------------------------------------------------
        plan = [
            {
                "model": model,
                "temperature": round(base_temp, 3),
                "top_p": round(base_top_p, 3),
                "max_tokens": int(base_tokens),
                "extra": dict(extra),
            },
            {
                "model": model,
                "temperature": round(max(0.42, base_temp - 0.08), 3),
                "top_p": round(min(0.97, base_top_p + 0.02), 3),
                "max_tokens": int(base_tokens),
                "extra": dict(extra),
            },
            {
                "model": model,
                "temperature": round(max(0.40, base_temp - 0.16), 3),
                "top_p": round(min(0.98, base_top_p + 0.03), 3),
                "max_tokens": int(min(base_tokens, 3000)),
                "extra": dict(extra),
            },
        ]
        return plan

    @staticmethod
    def _repair_profile(violations: Set[str], *, nsfw_on: bool, phase: int) -> Dict[str, str]:
        """
        Escolhe um perfil de repair compatível com o problema real,
        sem empurrar toda resposta para o mesmo estilo.
        """
        v = set(violations or [])

        if "contradicao_cena" in v:
            return {
                "tone": "coerente, precisa e obediente à cena já ativa",
                "focus": (
                    "- Preserve local, tempo, posição, continuidade e fatos já estabelecidos.\n"
                    "- Remova qualquer deslocamento, salto de ação ou detalhe que contradiga a cena.\n"
                    "- Reescreva apenas o necessário para ficar coerente."
                ),
            }

        if "meta_fala" in v:
            return {
                "tone": "natural, íntima e totalmente imersa",
                "focus": (
                    "- Remova qualquer traço de explicação, comentário sobre processo, regra ou instrução.\n"
                    "- Entregue apenas a fala/ação final em personagem.\n"
                    "- Mantenha subtexto e continuidade."
                ),
            }

        if "vazio" in v:
            return {
                "tone": "viva, concreta e imediata",
                "focus": (
                    "- Continue do ponto exato da cena.\n"
                    "- Entregue uma resposta curta a média, mas completa.\n"
                    "- Faça algo acontecer sem reiniciar nem resumir."
                ),
            }

        if "estilo_mecanico" in v:
            if nsfw_on and int(phase or 0) >= 2:
                return {
                    "tone": "orgânica, sensorial e presente",
                    "focus": (
                        "- Troque abstrações por ação imediata, sensação corporal e reação espontânea.\n"
                        "- Evite fraseado decorativo, redundante ou automático.\n"
                        "- Preserve a progressão natural, sem exagerar."
                    ),
                }
            return {
                "tone": "orgânica, humana e presente",
                "focus": (
                    "- Troque frases rígidas por fala natural e reação imediata.\n"
                    "- Evite soar automática, explicativa ou genérica.\n"
                    "- Preserve contenção quando a cena pedir contenção."
                ),
            }

        return {
            "tone": "coerente e natural",
            "focus": (
                "- Corrija apenas o mínimo necessário.\n"
                "- Preserve personalidade, continuidade e ritmo."
            ),
        }

    
    @staticmethod
    def _build_repair_system(
        violations: Set[str],
        *,
        nsfw_on: bool,
        phase: int,
        decision_hint: Optional[Dict[str, Any]] = None,
    ) -> str:
        profile = MaryService._repair_profile(violations, nsfw_on=nsfw_on, phase=phase)
        repair_instr = _repair_instruction(violations)
    
        text = (
            "Você está reescrevendo a última resposta da Mary.\n"
            "Corrija apenas os problemas reais.\n"
            "Preserve personalidade, continuidade, coerência e subtexto.\n\n"
            f"TOM:\n- A resposta deve soar {profile['tone']}.\n\n"
            "REGRAS FIXAS:\n"
            "- Continue exatamente do ponto onde a cena estava.\n"
            "- Não reinicie a cena.\n"
            "- Não resuma.\n"
            "- Não explique o processo.\n"
            "- Não quebre a continuidade.\n"
            "- Entregue apenas a nova resposta final.\n\n"
            "FOCO DE CORREÇÃO:\n"
            f"{profile['focus']}\n\n"
            f"{repair_instr}"
        )
    
        if isinstance(decision_hint, dict) and decision_hint:
            text += (
                "\n\n[DIREÇÃO DA MARY - MANTER]\n"
                f"- Decisão: {decision_hint.get('decision')}\n"
                f"- Objetivo: {decision_hint.get('narrative_goal')}\n"
                f"- Limite: {decision_hint.get('advance_limit')}"
            )
    
        return text


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
        nsfw_profile: str,
        timeline: str,
        allow_third_party_seduction: bool,
        diag: _Diag,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:

        # ==================================================
        # MAX TOKENS DINÂMICO — NUNCA PARA BAIXO
        # ==================================================
        try:
            base_max_tokens = int(max_tokens or 0)
        except Exception:
            base_max_tokens = 0

        # mínimo absoluto para evitar resposta cortada
        dynamic_min_tokens = 900

        # aumenta conforme intensidade/contexto, mas nunca reduz
        try:
            if nsfw_on:
                dynamic_min_tokens = max(dynamic_min_tokens, 1100)

            if int(phase or 0) >= 3:
                dynamic_min_tokens = max(dynamic_min_tokens, 1200)

            if nsfw_profile in ("STRICT", "NSFW_RELAXED"):
                dynamic_min_tokens = max(dynamic_min_tokens, 1200)

            if allow_third_party_seduction:
                dynamic_min_tokens = max(dynamic_min_tokens, 1300)
        except Exception:
            pass

        max_tokens = max(base_max_tokens, dynamic_min_tokens)
    
        data, used_model, _provider_meta = self._chat(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            extra=extra,
        )
        used_model = used_model or model

        if data is None:
            raise RuntimeError(f"_chat retornou data=None para model={used_model}")
     
    
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
                    "repr_preview": (repr(data)[:900] if data is not None else "None"),
                    "raw_preview": (str(data)[:900] if data is not None else "None"),
                },
            )
        except Exception:
            pass
    
        texto = self._extract_text(data) if data is not None else ""
        texto = _normalize_model_response(texto or "")
    
    
        try:
            user_norm = _t_norm(user_text or "")
            texto_norm = _t_norm(texto or "")
            user_tokens = [w for w in user_norm.split() if len(w) > 4]
            first_part = texto_norm[:200]
            repeated = sum(1 for w in user_tokens if w in first_part)
    
            if repeated >= 3:
                diag.violations = list(
                    dict.fromkeys((diag.violations or []) + ["eco_gatilho_imediato"])
                )
        except Exception:
            pass
    
        try:
            style_score = float(_style_score(texto))
        except Exception:
            style_score = 1.0
    
        try:
            diag.style_score = style_score
        except Exception:
            pass
    
        try:
            texto = _seal_broken_ending(texto)
        except Exception:
            pass
    
        if not texto:
            try:
                raw_exists = data is not None
                raw_repr = repr(data)[:3000] if data is not None else "None"
        
                _ss_set(
                    "mary_extract_text_failed",
                    {
                        "stage": "initial",
                        "raw_exists": raw_exists,
                        "raw_type": type(data).__name__ if data is not None else "None",
                        "raw_keys": list(data.keys())[:30] if isinstance(data, dict) else None,
                        "finish_reason": finish_reason,
                        "usage": usage,
                        "repr_preview": raw_repr,
                    },
                )
        
                diag.violations = list(
                    dict.fromkeys(
                        (diag.violations or [])
                        + (["parser_empty"] if raw_exists else ["provider_empty"])
                    )
                )
            except Exception:
                pass
        
            if data is not None:
                raise RuntimeError("Payload recebido, mas sem texto extraível na geração inicial")
        
            raise RuntimeError("Provider retornou payload vazio na geração inicial")
    
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
    
        # comentário corrigido: são QUATRO grupos capazes de disparar repair
        viol_graves = {
            "vazio",
            "meta_fala",
            "contradicao_cena",
            "estilo_mecanico",
        }
    
        violations = set(violations or [])
    
        # se não houver violação grave, só injeta estilo_mecanico quando realmente necessário
        if not (violations & viol_graves):
            if style_score < 0.72:
                violations.add("estilo_mecanico")
                try:
                    diag.violations = list(
                        dict.fromkeys((diag.violations or []) + ["estilo_mecanico"])
                    )
                except Exception:
                    pass
            else:
                try:
                    if violations:
                        diag.violations = list(
                            dict.fromkeys((diag.violations or []) + list(violations))
                        )
                except Exception:
                    pass
    
                texto = _trim_scene_finalization(texto)
                try:
                    texto = _seal_broken_ending(texto)
                except Exception:
                    pass
                return texto, used_model
    
        # ---------------------------------------------
        # NSFW OFF: só classifica se for caso de borda
        # ---------------------------------------------
        try:
            if (not bool(nsfw_on)) and ("nsfw_off_explicito" not in violations):
                if _needs_llm_classification(texto, user_text=user_text, phase=int(phase or 0)):
                    classifier_model = used_model
                    sys_c = "Você é um classificador. Responda APENAS: SIM ou NAO."
                    usr_c = (
                        "O texto abaixo descreve ato sexual explícito "
                        "(ex.: penetração, sexo oral, masturbação explícita, órgãos genitais nomeados, "
                        "ou descrição inequívoca de ato sexual)?\n\n"
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
                        violations.add("nsfw_off_explicito")
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
            try:
                diag.violations = (diag.violations or []) + ["nsfw_off_borderline_llm=ERR"]
            except Exception:
                pass
    
        if violations:
            try:
                diag.violations = list(
                    dict.fromkeys((diag.violations or []) + list(violations))
                )
            except Exception:
                pass
    
        if not violations:
            texto = _trim_scene_finalization(texto)
            try:
                texto = _seal_broken_ending(texto)
            except Exception:
                pass
            return texto, used_model
    
        # ---------------------------------------------
        # Repair: 1 passada, mas agora com perfil certo
        # ---------------------------------------------
        try:
            diag.repairs += 1
        except Exception:
            pass
    
        try:
            decision_hint = _ss_get("mary_reasoning_debug", {}) or {}
        except Exception:
            decision_hint = {}
    
        repair_system = self._build_repair_system(
            violations,
            nsfw_on=bool(nsfw_on),
            phase=int(phase or 0),
            decision_hint=decision_hint,
        )
    
        repair_messages: List[Dict[str, str]] = []
    
        try:
            if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
                repair_messages.append(messages[0])
        except Exception:
            pass
    
        repair_messages.append({"role": "system", "content": repair_system})
    
        try:
            memory_context = [
                m for m in (messages[1:-1] if len(messages) > 2 else [])
                if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            ]
            if memory_context:
                repair_messages.extend(memory_context[-6:])
        except Exception:
            pass
    
        repair_messages.append(
            {"role": "user", "content": _wrap_user_prompt_for_pov_guard(user_text or "")}
        )
        repair_messages.append({"role": "assistant", "content": texto})
    
        # repair ligeiramente mais conservador que a geração original
        repair_temp = max(0.42, float(temperature) - 0.06)
        repair_top_p = min(0.96, float(top_p))
    
        data2, used_model2, _provider_meta2 = self._chat(
            used_model,
            repair_messages,
            temperature=repair_temp,
            max_tokens=int(max_tokens),
            top_p=repair_top_p,
            extra=extra,
        )
        used_model2 = used_model2 or used_model
    
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
        texto2 = _normalize_model_response(texto2 or "").strip()
    
        try:
            texto2 = _seal_broken_ending(texto2)
        except Exception:
            pass
    
        if not texto2:
            try:
                raw_exists = data2 is not None
                fr2, usage2 = _extract_finish_reason_and_usage(data2)
        
                diag.violations = list(
                    dict.fromkeys(
                        (diag.violations or [])
                        + (["parser_empty_repair"] if raw_exists else ["provider_empty_repair"])
                    )
                )
        
                _debug_set(
                    "mary_repair_empty_response",
                    {
                        "used_model": used_model2,
                        "temperature": temperature,
                        "top_p": top_p,
                        "max_tokens": max_tokens,
                        "finish_reason": fr2,
                        "usage": usage2,
                        "raw_exists": raw_exists,
                        "raw_type": type(data2).__name__ if data2 is not None else "None",
                        "raw_keys": list(data2.keys())[:30] if isinstance(data2, dict) else None,
                        "repr_preview": repr(data2)[:3000] if data2 is not None else "None",
                        "original_text_preview": (texto or "")[:400],
                    },
                )
            except Exception:
                pass
        
            if data2 is not None:
                raise RuntimeError("Payload recebido, mas sem texto extraível no repair")
        
            raise RuntimeError("Provider retornou payload vazio no repair")
    
        violations2 = _violations(
            texto=texto2,
            ctx_lower=ctx_lower,
            user_text=user_text,
            phase=int(phase or 0),
            nsfw_on=bool(nsfw_on),
            nsfw_profile=str(nsfw_profile),
            timeline=str(timeline or ""),
            allow_third_party_seduction=bool(allow_third_party_seduction),
        )
        violations2 = set(violations2 or [])
    
        try:
            style_score2 = float(_style_score(texto2))
        except Exception:
            style_score2 = 1.0
    
        if not (violations2 & viol_graves):
            if style_score2 < 0.72:
                # se o repair ainda ficou mecânico, devolve o original bom em vez de reescrever em loop
                texto = _trim_scene_finalization(texto)
                try:
                    texto = _seal_broken_ending(texto)
                except Exception:
                    pass
                return texto, used_model
    
            texto2 = _trim_scene_finalization(texto2)
            try:
                texto2 = _seal_broken_ending(texto2)
            except Exception:
                pass
            return texto2, used_model2
    
        texto = _trim_scene_finalization(texto)
        try:
            texto = _seal_broken_ending(texto)
        except Exception:
            pass
        return texto, used_model
        
    @staticmethod
    def _fallback_text() -> str:
        return (
            "Eu solto um meio sorriso e digo o nome sem fingir distância: Janio. Eu não estou confusa sobre ele - eu estou com medo do quanto eu gostei.\n\n"
            "Eu encosto de leve na sua mão enquanto falo, como se isso me desse coragem. Foi intenso, foi rápido, e ainda assim eu quero ver onde isso vai dar.\n\n"
            "Eu respiro fundo e completo, sem recuar: se ele vier falar comigo hoje, eu não vou fugir."
        )

    # -------------------------
    # helpers
    # -------------------------   
    @staticmethod
    def _extract_text(resp: Any) -> str:
        def walk(obj: Any) -> str:
            if obj is None:
                return ""
    
            if isinstance(obj, str):
                return obj.strip()
    
            if isinstance(obj, list):
                parts = []
                for item in obj:
                    text = walk(item)
                    if text:
                        parts.append(text)
                return "\n".join(parts).strip()
    
            if isinstance(obj, dict):
                priority_keys = (
                    "output_text",
                    "text",
                    "content",
                    "result",
                    "message",
                    "delta",
                    "output",
                    "response",
                    "choices",
                    "candidates",
                    "parts",
                    "messages",
                )
    
                for key in priority_keys:
                    if key in obj:
                        text = walk(obj.get(key))
                        if text:
                            return text
    
                for value in obj.values():
                    text = walk(value)
                    if text:
                        return text
    
            return ""
    
        try:
            return walk(resp).strip()
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

        tl = _normalize_timeline(tl)

        def _clamp(v: int) -> int:
            if v < self._INTIMACY_MIN:
                return self._INTIMACY_MIN
            if v > self._INTIMACY_MAX:
                return self._INTIMACY_MAX
            return v

        def _label_to_phase(raw: Any) -> Optional[int]:
            if not isinstance(raw, str):
                return None
            s = str(raw).strip().lower()
            rev = {v: k for k, v in INTIMACY_PHASES.items()}
            if s in rev:
                return _clamp(int(rev[s]))
            return None

        keys: List[str] = []
        if tl:
            keys += [
                f"intimacy.phase::{tl}",
                f"intimacy_phase::{tl}",
                f"mary_intimacy_phase::{tl}",
                f"fase_intima::{tl}",
            ]

        keys += [
            "intimacy.phase",
            "intimacy_phase",
            "mary_intimacy_phase",
            "fase_intima",
            "phase_intimacy",
            "phase",
        ]

        for k in keys:
            if k not in facts:
                continue

            raw = facts.get(k)

            # aceita labels textuais
            if k.startswith("fase_intima"):
                p = _label_to_phase(raw)
                if p is not None:
                    return p

            try:
                return _clamp(int(raw))
            except Exception:
                pass

        return 0


    def _set_intimacy_phase(self, usuario_key: str, phase: int, timeline: str = "") -> int:
        try:
            p = int(phase)
        except Exception:
            p = 0

        maxp = int(MAX_INTIMACY_PHASE)
        p = max(self._INTIMACY_MIN, min(p, maxp))

        tl = _normalize_timeline(timeline) if timeline else ""
        label = INTIMACY_PHASES.get(p, "tensao")

        # global
        set_fact_safe(usuario_key, "intimacy.phase", p, {"fonte": "intimacy_progression"})
        set_fact_safe(usuario_key, "fase_intima", label, {"fonte": "intimacy_progression"})

        # timeline específica
        if tl:
            try:
                set_fact_safe(
                    usuario_key,
                    f"intimacy.phase::{tl}",
                    p,
                    {"fonte": "intimacy_progression"},
                )
                set_fact_safe(
                    usuario_key,
                    f"fase_intima::{tl}",
                    label,
                    {"fonte": "intimacy_progression"},
                )
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
        base_payload: Dict[str, Any] = {
            "messages": messages,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "max_tokens": int(max_tokens),
        }
    
        try:
            _ss_set("mary_last_chat_params", {
                "model": model,
                "temperature": float(temperature),
                "top_p": float(top_p),
                "max_tokens": int(max_tokens),
                "has_extra": bool(isinstance(extra, dict) and extra),
                "extra_keys": list((extra or {}).keys()) if isinstance(extra, dict) else [],
                "messages_count": len(messages or []),
            })
        except Exception:
            pass
    
        try:
            if _debug_enabled():
                _debug_set("mary_last_used_model", model)
                _debug_set("mary_last_used_provider", None)
                _debug_append("chat:request", {
                    "model": model,
                    "temperature": float(temperature),
                    "top_p": float(top_p),
                    "max_tokens": int(max_tokens),
                    "messages_count": len(messages or []),
                    "extra_keys": list((extra or {}).keys()) if isinstance(extra, dict) else [],
                })
        except Exception:
            pass
    
        def _validate_router_response(resp: Any):
            if resp is None:
                raise RuntimeError(f"route_chat_strict retornou None (model={model})")
    
            if not isinstance(resp, tuple) or len(resp) != 3:
                raise RuntimeError(
                    f"route_chat_strict retornou formato inválido: "
                    f"type={type(resp).__name__}, repr={str(resp)[:300]}"
                )
    
            data, used_model, provider_meta = resp
    
            if data is None:
                raise RuntimeError(
                    f"route_chat_strict retornou tuple com data=None "
                    f"(model={model}, used_model={used_model})"
                )
    
            return data, used_model, provider_meta
    
        def _capture_success_debug(resp: Any, out: Any, mode: str) -> None:
            try:
                _ss_set("mary_last_resp_type", type(resp).__name__)
            except Exception:
                pass
    
            try:
                if _debug_enabled():
                    _debug_set("mary_last_raw_resp", {
                        "mode": mode,
                        "resp_type": type(resp).__name__,
                        "preview": str(resp)[:2000],
                    })
            except Exception:
                pass
    
            try:
                if isinstance(out, tuple) and len(out) == 3:
                    _data, _used_model, _provider_meta = out
                    _debug_set("mary_last_used_model", _used_model or model)
                    _debug_set(
                        "mary_last_used_provider",
                        str(_provider_meta)[:300] if _provider_meta is not None else None
                    )
            except Exception:
                pass    
      
        if isinstance(extra, dict) and extra:
            payload_with_extra = dict(base_payload)
            payload_with_extra.update(extra)
        
            m = (model or "").strip().lower()
            if "grok" in m or m.startswith("x-ai/") or m.startswith("xai/"):
                payload_with_extra.pop("reasoning", None)
                payload_with_extra.pop("include_reasoning", None)
        
            try:
                resp = service_router.route_chat_strict(model, payload_with_extra)
                out = _validate_router_response(resp)
                _capture_success_debug(resp, out, "with_extra")
                return out
        
            except Exception as e:
                _debug_capture_error(e)
        
                try:
                    _ss_set(
                        "mary_last_extra_retry_debug",
                        {
                            "model": model,
                            "error_type": type(e).__name__,
                            "error": str(e)[:600],
                            "extra_keys": list(extra.keys())[:20],
                        },
                    )
                except Exception:
                    pass
    
                resp = service_router.route_chat_strict(model, base_payload)
                out = _validate_router_response(resp)
                _capture_success_debug(resp, out, "base_payload_retry")
                return out
    
        resp = service_router.route_chat_strict(model, base_payload)
        out = _validate_router_response(resp)
        _capture_success_debug(resp, out, "base_payload_only")
        return out
     
