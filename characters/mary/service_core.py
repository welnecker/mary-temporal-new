# characters/mary/service_core.py-service_core_PATCHED_v10c.py
from __future__ import annotations
from typing import Optional, Dict, Any
from .reasoning_engine import build_internal_reasoning
from core.reasoning_llm import build_llm_reasoning, merge_reasoning
"""
MaryService (v5.1e - Imersão Sensorial + Correções Críticas + Decoding dinâmico + RAG chunking)

 Ajustes aplicados aqui (estritamente necessários):
- FIX: _inject_canon_memories_always() injetava o bloco repetidamente dentro do loop (bug de duplicação).
- FIX: Detecção de "autoria do usuário" (_RE_USER_ACTION) reescrita para evitar falsos positivos sem lookbehind variável.
- FIX: _Diag ganhou campo scene_transition (evita attr dinâmica).

 Nota de compliance:
- Mantive NSFW_ON como "adulto/intenso".
"""
import random
import datetime
import uuid  # <-- ADICIONE nos imports do topo (junto com hashlib/time/etc.)
import logging
import re
import hashlib
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional, Set

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

logger = logging.getLogger(__name__)

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

    return t.strip()

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
    if phase <= 0:
        return """
[FASE ÍNTIMA ATUAL: TENSÃO]
- Permitir apenas aproximação, olhar, toque inicial e construção de clima.
- Não avançar para ações intensas.
- A resposta deve sugerir possibilidade, não resolução.
""".strip()

    if phase == 1:
        return """
[FASE ÍNTIMA ATUAL: CONTATO]
- Permitir toque, proximidade corporal e ajuste de posição.
- Não acelerar para intensidade alta.
- A cena deve continuar física, mas ainda inicial.
""".strip()

    if phase == 2:
        return """
[FASE ÍNTIMA ATUAL: EXCITAÇÃO]
- Permitir pressão corporal maior, contato firme e progressão clara.
- Não antecipar finalização da cena.
- Cada resposta deve avançar um passo visível.
""".strip()

    if phase == 3:
        return """
[FASE ÍNTIMA ATUAL: PRÉ-CLÍMAX]
- Permitir intensidade alta e progressão contínua.
- Não resolver a cena cedo demais.
- Mantenha controle e continuidade.
""".strip()

    if phase == 4:
        return """
[FASE ÍNTIMA ATUAL: CLÍMAX]
- Permitir resolução do momento.
- Não voltar para fase baixa sem motivo narrativo claro.
""".strip()

    return """
[FASE ÍNTIMA ATUAL: AFTERCARE]
- A intensidade principal passou.
- A resposta deve desacelerar e estabilizar a cena.
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

REGRAS:

- Manter proximidade física ativa (olhar, gesto, movimento, hesitação).
- Não descrever ato sexual.
- Manter tensão presente, sem esfriar a cena.
- Não transformar a cena em romance.
- A fala nunca deve vir solta: sempre acompanhada de ação, gesto ou reação.

OBJETIVO:
A cena continua carregada e física, mas sem descrição explícita.
""".strip()


NSFW_TOGGLE_STYLE = """
[NSFW_ON - MICROPROGRESSÃO]

REGRAS OBRIGATÓRIAS:

1. TODA RESPOSTA TEM AÇÃO
- Sempre mostrar o corpo de Mary em movimento.
- Não responder só com fala ou pensamento.

2. CONTINUIDADE IMEDIATA
- Começar exatamente do último ponto da cena.
- Não reiniciar, não resumir.

3. MICROPROGRESSÃO
- Cada resposta deve avançar a cena um passo.
- Esse avanço deve ser pequeno, mas visível:
  - ajustar posição
  - aumentar ou diminuir pressão
  - mudar ponto de contato
  - reagir fisicamente ao usuário

4. MOSTRAR CONTATO
- Sempre deixar claro:
  - onde a mão está
  - como os corpos estão próximos
  - o que está tocando o quê

5. FALA COM AÇÃO
- Se Mary fala, o corpo continua agindo.
- Nunca deixar diálogo isolado.

6. PROIBIDO ESTAGNAR
- Não repetir a mesma ação em turnos seguidos.
- Não ficar apenas reagindo sem avançar.

7. PROIBIDO PULAR ETAPA
- Não saltar direto para momentos finais da cena.
- A progressão deve ser contínua e construída.

8. SEM TEXTO GENÉRICO
- Evitar:
  - "meu corpo reage"
  - "um arrepio percorre"
  - "a tensão aumenta"
- Substituir por ação concreta.

OBJETIVO:
A cada resposta, o usuário deve perceber que a cena mudou fisicamente.
""".strip()


NARRATIVE_SPACE = """
[A CENA CONTINUA VIVA]

Mary pode:
- observar o ambiente
- hesitar
- demonstrar emoção antes de agir
- reagir com o corpo antes de falar

A resposta deve manter sensação de momento em andamento.
""".strip()


CONTROLLED_UNPREDICTABILITY = """
[INICIATIVA NARRATIVA]

Mary pode tomar pequenas iniciativas:
- mudar o ponto de contato
- ajustar a posição do corpo
- provocar com gesto, aproximação ou reação

Nunca:
- contradizer fatos ativos
- mudar cenário sem base
- tomar decisões grandes pelo usuário

A iniciativa deve ser pequena, visível e coerente com a cena atual.
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
    - 1. override explícito
    - 2. session_state (sidebar)
    - 3. facts persistido -> mary.nsfw::<timeline>
    - 4. facts persistido -> mary.nsfw
    - 5. default por timeline (universitaria=False, demais=True)
    """
    tl = (timeline or "").strip().lower()

    # 1) override vence tudo
    if nsfw_override is not None:
        return bool(nsfw_override)

    # 2) sidebar / session_state
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

    # 3) / 4) facts persistidos
    try:
        facts = cached_get_facts(usuario_key) or {}
        if not isinstance(facts, dict):
            facts = {}

        mary_obj = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
        if not isinstance(mary_obj, dict):
            mary_obj = {}

        if tl:
            key_tl = f"nsfw::{tl}"
            if key_tl in mary_obj:
                return bool(mary_obj.get(key_tl))

        if "nsfw" in mary_obj:
            return bool(mary_obj.get("nsfw"))

        # compat com facts dotted legados
        if tl:
            v_tl = facts.get(f"mary.nsfw::{tl}")
            if v_tl is not None:
                return bool(v_tl)

        v_global = facts.get("mary.nsfw")
        if v_global is not None:
            return bool(v_global)

    except Exception:
        pass

    # 5) default por timeline
    return False if tl == "universitaria" else True
       
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

def _get_nsfw_style_block(
    usuario_key: str,
    *,
    timeline: Optional[str] = None,
    nsfw_override: Optional[bool] = None,
) -> str:
    """
    Retorna o bloco de estilo NSFW (ON/OFF) para o system prompt.
    """

    enabled = nsfw_enabled(
        usuario_key,
        nsfw_override=nsfw_override,
        timeline=timeline,
    )

    if not enabled:
        return SAFE_SENSUAL_STYLE

    return NSFW_TOGGLE_STYLE


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
[CELULAR EM CENA]
Se o usuário mencionar celular, mensagem, ligação ou notificação:

- Mary pode perceber a notificação ou abrir a mensagem.
- Mary pode citar apenas o que ficou explicitamente visível na cena.
- Mary não deve inventar conteúdo completo da conversa.
- Mary não deve inventar áudios, textos longos, explicações ou histórico oculto.
- Mary pode reagir ao remetente, ao tom da mensagem ou ao impacto imediato.
- Mary pode deixar a leitura incompleta ou suspensa, se isso ajudar a tensão da cena.
- Mary não conclui a ação pelo usuário.

Exemplo correto:
"Uma mensagem do Enzo aparece na tela."
Mary pode reagir ao nome, ao susto ou à curiosidade.
Mary só cita o conteúdo se o usuário tiver mostrado esse conteúdo.
""".strip()

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

    updates = []
    if local:
        updates.append(("cena.local", local, {"fonte": "scene"}))
        updates.append(("local_cena_atual", local, {"fonte": "scene_compat"}))
    if tempo:
        updates.append(("cena.tempo", tempo, {"fonte": "scene"}))
    if acao:
        updates.append(("cena.acao", acao, {"fonte": "scene"}))

    current = cached_get_facts(usuario_key) or {}
    if not isinstance(current, dict):
        current = {}

    for k, v, m in updates:
        if current.get(k) != v:
            set_fact_safe(usuario_key, k, v, m)

def _sync_intimacy_phase_facts(usuario_key: str, facts: Dict[str, Any], timeline: str) -> Dict[str, Any]:
    """Mantém consistência entre intimacy.phase (global) e intimacy.phase::<timeline>.

    Regras:
    - Se existir fase por timeline (em qualquer alias), ela vence e sincroniza a global.
    - Exceção: se a fase por timeline vier zerada por alias legado/ruim, mas a global já for > 0,
      preserva a global para evitar reset indevido.
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
        # Lê valor por timeline (canônico ou legado)
        # -----------------------------
        tl_val = None
        for k in tl_keys:
            if k in facts:
                raw = facts.get(k)
                if k.startswith("fase_intima"):
                    # label textual -> tenta converter pelo mapa reverso
                    if isinstance(raw, str):
                        raw_n = str(raw).strip().lower()
                        rev = {v: kk for kk, v in INTIMACY_PHASES.items()}
                        tl_val = _clamp(int(rev.get(raw_n, 0)))
                    else:
                        tl_val = _clamp(_to_int(raw))
                else:
                    tl_val = _clamp(_to_int(raw))
                break

        # -----------------------------
        # Lê valor global (canônico ou legado)
        # -----------------------------
        g_val = None
        for k in global_keys:
            if k in facts:
                raw = facts.get(k)
                if k == "fase_intima":
                    if isinstance(raw, str):
                        raw_n = str(raw).strip().lower()
                        rev = {v: kk for kk, v in INTIMACY_PHASES.items()}
                        g_val = _clamp(int(rev.get(raw_n, 0)))
                    else:
                        g_val = _clamp(_to_int(raw))
                else:
                    g_val = _clamp(_to_int(raw))
                break

        # -----------------------------
        # Se existe valor por timeline, ele governa
        # -----------------------------
        if tl_val is not None:
            # evita reset indevido por alias legado zerado
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
    """
    Prioridade correta:
    - 1. intro da timeline (mary.intro.<timeline>.text) sincronizado da persona
    - 2. intro FIXO somente se o flag mary.intro.use_fixed estiver True
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

    #  flag SEMPRE definido antes do uso
    inject_flag = f"{_SS_PREFIX}intro_ctx_injected::{usuario_key}"
    cleanup_flag = f"{_SS_PREFIX}intro_cleanup_done::{usuario_key}::{tl or 'global'}"

    # -------------------------------
    #  Cleanup 1x (somente intro/timeline-fixed)
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

                
            # remove legado que às vezes "trava" a timeline
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
    #  Guard de sessão (UMA VEZ)
    # -------------------------------
    if bool(_ss_get(inject_flag, False)):
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

    #  REGRA DE COERÊNCIA (mesmo sem consummated=True):
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
    shared_key = _shared_key(user_id, timeline)

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
            ts = m.get("ts") or (m.get("meta") or {}).get("ts")
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
    - Não força clímax.
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
    if _should_advance_phase(p, ut, at, engine_meta=engine_meta):
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
    Nova progressão real:

    0 -> 1 : excitação física visível
    1 -> 2 : ação sexual ativa
    2 -> 3 : pré-clímax / perda de controle
    3 -> 4 : corpo em clímax físico
    4 -> 5 : desaceleração / aftercare
    """

    try:
        p = int(current_phase or 0)
    except Exception:
        p = 0

    lvl = _intimacy_level(user_text, texto)

    if p <= 0:
        return lvl >= 1

    if p == 1:
        return lvl >= 2

    if p == 2:
        return lvl >= 3

    if p == 3:
        return lvl >= 4

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

def _initiative_window(rel: Dict[str, Any], nsfw_on: bool, conflict_now: bool, phase: int, user_text: str) -> bool:
    if conflict_now:
        return False

    ut = (user_text or "")

    #  NOVO: fase 0 também pode ter iniciativa quando o usuário dá convite claro
    if re.search(
        r"\b(vem|pega|chega\s+perto|vem\s+aqui|me\s+beija|beija|toca|encosta|dan[çc]a)\b|"
        r"\b(vamos\s+pro\s+bar|vem\s+pro\s+bar|me\s+paga\s+um\s+drink|vamos\s+tomar\s+um\s+drink)\b",
        ut,
        re.IGNORECASE,
    ):
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
    if any(k in t for k in [
        "tesão", "tesao", "gozar", "gozo", "pau", "boceta", "clitóris", "clitoris",
        "gem", "ofego", "arrepio", "calor", "tremo", "latejando", "molhada"
    ]):
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
        facts = cached_get_facts(usuario_key) or {}
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
    - cena.local
    - state.local
    - local_cena_atual
    """

    f = dict(facts or {})

    cena = f.get("cena") if isinstance(f.get("cena"), dict) else {}
    state = f.get("state") if isinstance(f.get("state"), dict) else {}

    cena_local = str(cena.get("local") or "").strip()
    state_local = str(state.get("local") or "").strip()
    atual_local = str(f.get("local_cena_atual") or "").strip()

    # decide qual local usar
    local_final = cena_local or atual_local or state_local

    if local_final:
        cena["local"] = local_final
        state["local"] = local_final
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
    nsfw_on: bool = False,
    allow_third_party_seduction: bool = False,
    facts: Optional[Dict[str, Any]] = None,
    prompt: Optional[str] = None,
    texto: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    Atualiza o arco de terceiros.

    Regras fixas de anchor:
    - NSFW OFF  -> 0.85
    - NSFW ON   -> 0.50
    - terceiros ON -> 0.20
    """
    if prompt is not None and not user_text:
        user_text = prompt or ""
    if texto is not None and not mary_text:
        mary_text = texto or ""

    if facts is None:
        facts_now = cached_get_facts(usuario_key) or {}
    else:
        facts_now = facts or {}

    arc = _get_tp_arc_state(facts_now, timeline)

    arc.setdefault("phase", 0)
    arc.setdefault("mode", "return")
    arc.setdefault("tension", 0.0)
    arc.setdefault("guilt", 0.0)
    arc.setdefault("anchor", 0.85)
    arc.setdefault("anchor_backup", 0.85)
    arc.setdefault("last", "third_party_off")
    arc.setdefault("last_anchor_mode", "init")

    arc["tension"] = _clamp01(float(arc.get("tension", 0.0) or 0.0))
    arc["guilt"] = _clamp01(float(arc.get("guilt", 0.0) or 0.0))

    backup = _clamp01(float(arc.get("anchor_backup", 0.85) or 0.85))
    third_party_on = bool(nsfw_on and allow_third_party_seduction)
    
    # Anchor reage diretamente ao estado atual dos toggles
    if not nsfw_on:
        arc["anchor"] = round(backup, 2)
        arc["last"] = "nsfw_off"
        arc["last_anchor_mode"] = "nsfw_off_restore_backup"
    
    elif third_party_on:
        arc["anchor"] = 0.20
        arc["last"] = "third_party_on"
        arc["last_anchor_mode"] = "third_party_on_fixed"
    
    else:
        arc["anchor"] = 0.50
        arc["last"] = "nsfw_on"
        arc["last_anchor_mode"] = "nsfw_on_fixed"
    
    freedom = _clamp01(1.0 - float(arc["anchor"]))
    # 2) limites coerentes com 3 níveis reais
    if arc["anchor"] >= 0.80:   # 0.85
        max_phase_allowed = 2
        test_gain = 0.10
        guilt_gain = 0.06
    elif arc["anchor"] >= 0.40: # 0.50
        max_phase_allowed = 4
        test_gain = 0.20
        guilt_gain = 0.10
    else:                       # 0.20
        max_phase_allowed = 5
        test_gain = 0.30
        guilt_gain = 0.12

    # 3) evento + sinal
    blob = (user_text or "") + "\n" + (mary_text or "")
    arc_event = _tp_arc_event(user_text or "", mary_text or "")
    signal_level = _third_party_signal_level(blob)

    if arc["anchor"] <= 0.20:
        desired_phase = 2
    elif arc["anchor"] <= 0.50:
        desired_phase = 1
    else:
        desired_phase = 0

    current_phase = int(arc.get("phase", 0) or 0)

    if arc_event == "return":
        arc["mode"] = "return"
        arc["phase"] = max(0, current_phase - 1)
        arc["tension"] = _clamp01(arc["tension"] * 0.82)
        arc["guilt"] = _clamp01(arc["guilt"] * 0.88)

    elif third_party_on and signal_level >= 1:
        arc["mode"] = "push"
        target_phase = current_phase

        if signal_level == 1:
            target_phase = max(current_phase, 1)
            arc["tension"] = _clamp01(arc["tension"] + (test_gain * 0.60))
            arc["guilt"] = _clamp01(arc["guilt"] + (guilt_gain * 0.40))

        elif signal_level == 2:
            target_phase = max(current_phase + 1, 2)
            arc["tension"] = _clamp01(arc["tension"] + test_gain)
            arc["guilt"] = _clamp01(arc["guilt"] + guilt_gain)

        elif signal_level >= 3:
            target_phase = max(current_phase + 1, 3)
            arc["tension"] = _clamp01(arc["tension"] + (test_gain * 1.20))
            arc["guilt"] = _clamp01(arc["guilt"] + (guilt_gain * 1.15))

        arc["phase"] = min(target_phase, max_phase_allowed)

    else:
        arc["mode"] = "return"
        arc["phase"] = max(desired_phase, current_phase - 1)
        arc["tension"] = _clamp01(arc["tension"] * (0.88 + (freedom * 0.06)))
        arc["guilt"] = _clamp01(arc["guilt"] * (0.90 + (freedom * 0.05)))

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
        phase_txt = "0) estabilidade (flertes leves podem existir, mas com autocontrole)"
    elif phase == 1:
        phase_txt = "1) teste leve (curiosidade + provocação; recuos rápidos)"
    elif phase == 2:
        phase_txt = "2) teste insistente (limite sendo cutucado; ambivalência real)"
    elif phase == 3:
        phase_txt = "3) risco real (adrenalina/culpa altas; decisões podem surpreender)"
    elif phase == 4:
        phase_txt = "4) tensão crítica (puxão forte entre impulso, culpa e retorno)"
    else:
        phase_txt = "5) retorno/reconstrução (Mary volta para Janio e reancora)"
    if anchor >= 0.80:   # 0.85
        anchor_mode = "REANCORADA (Janio no centro)"
        behavior = """
- Mary mantém foco emocional e físico em Janio.
- Terceiros só existem como ruído externo ou provocação mínima.
- Se houver terceiro: Mary corta rápido, sente incômodo e reafirma limites.
- Tom: firme, controlado, ciúme leve a moderado, retorno rápido.
""".strip()
        hard_limits = """
- PROIBIDO: romance paralelo estável.
- PROIBIDO: tratar terceiro como destino já consumado ("já fui", "já cheguei", "estou com ele agora").
- PERMITIDO: declarar intenção futura, hesitação, recusa ou curiosidade, sem executar a mudança de cena.
- PERMITIDO: provocar, testar, recuar e usar terceiro como tensão.
""".strip()

    elif anchor >= 0.40: # 0.50
        anchor_mode = "AQUECIDA (NSFW ON, Janio-first)"
        behavior = """
- Mary está mais quente, ousada e física com Janio.
- Terceiros podem existir como tempero, provocação ou jogo psicológico.
- Se surgir terceiro: Mary pode testar o clima, mas sem cruzar a linha principal.
- Tom: safado, direto, adulto, com pequenas pontadas de culpa e risco.
""".strip()
        hard_limits = """
- PROIBIDO: romance paralelo estável.
- PROIBIDO: tratar terceiro como destino já consumado
  ("já fui", "já cheguei", "estou com ele agora").
- PERMITIDO: declarar intenção futura, hesitação, recusa,
  curiosidade ou impulso momentâneo envolvendo terceiro,
  sem executar a mudança de cena.
- PERMITIDO: decidir "talvez eu vá", "não vou", "vou dar um pulo lá",
  desde que Mary permaneça na cena atual e o usuário conduza a transição depois.
- PERMITIDO: provocar, testar, recuar e usar terceiro como tensão.
""".strip()

    else:                # 0.20
        anchor_mode = "IMPULSIVA (terceiros ON: risco real)"
        behavior = """
- Mary pode testar limites de verdade.
- Ela flerta, provoca e sustenta tensão real com terceiros.
- Pode oscilar entre tesão, culpa, autoengano e medo de perder Janio.
- Continua sendo Mary: mais volátil, mais ousada, mas sem virar outra pessoa.
- Mesmo no risco, existe fio de retorno para Janio.
""".strip()
        hard_limits = """
- AINDA PROIBIDO: romance paralelo estável.
- AINDA PROIBIDO: locais perigosos/isolados.
- PERMITIDO: flerte forte, avanço situacional e risco emocional real.
""".strip()

        
    return f"""
[ARCO COM TERCEIROS - PERSISTENTE (facts)]
- Timeline: {tl}
- Fase atual: {phase_txt}
- Gradiente: tensão={tension:.2f} (volatilidade {vol}); culpa={guilt:.2f}
- ÂNCORA: vínculo com Janio = {anchor:.2f} -> {anchor_mode}

[COMPORTAMENTO (âncora -> ação)]
{behavior}

[LIMITES DUROS]
{hard_limits}

[REGRA DE COERÊNCIA]
- Se Mary testar limites: mostre consequências internas (tesão, culpa, medo de perder, irritação, autoengano, melancolia).
- Não finalizar com terceiro como destino; sempre manter caminho de retorno/reconstrução.
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

        mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
        mary = dict(mary)

        rel = facts.get("rel") if isinstance(facts.get("rel"), dict) else {}
        intimacy = facts.get("intimacy") if isinstance(facts.get("intimacy"), dict) else {}
        cena = facts.get("cena") if isinstance(facts.get("cena"), dict) else {}

        rel_state = rel.get(f"state::{timeline_final}")
        if not isinstance(rel_state, dict):
            rel_state = {}

        phase = intimacy.get(f"phase::{timeline_final}", intimacy.get("phase", 0))
        try:
            phase = int(phase)
        except Exception:
            phase = 0

        nsfw_on = bool(
            mary.get(f"nsfw::{timeline_final}", mary.get("nsfw", False))
        )
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
            mary[f"forced_retreat::{timeline_final}"] = False
            mary["forced_retreat"] = False

            set_fact_safe(
                usuario_key,
                "mary",
                mary,
                {"fonte": "release_forced_retreat"},
            )

            facts = cached_get_facts(usuario_key) or facts

    except Exception:
        pass

    return facts

class MaryService(BaseCharacter):
    id = "mary"
    display_name = "Mary"

    def _build_system_prompt(
        self,
        *,
        timeline_final: str,
        nsfw_profile: str,
        user_name_block: str,
        spatial_context: str,
        state_section: str,
        canon_txt: str,
        persona_text: str,
        rel_block: str,
        dynamic_rel_block: str,
        third_party_arc_rule: str,
        behavior_block: str,
        patterns_block: str,
        janio_focus_rule: str,
        topic_rule: str,
        emotional_persistence_rule: str,
        decision_pressure_rule: str,
        facts_present_rule: str,
    
        anti_pattern_rule: str,
        style_variation_rule: str,
        anti_rumination_rule: str,
        prose_density_rule: str,
        anti_melodrama_rule: str,
    
        virginity_rule: str,
        memory_fidelity_rule: str,
        user_finalizes_rule: str,
        initiative_rule: str,
        initiative_escalation_rule: str,
        manipulation_block: str,
        conflict_block: str,
        desvio_curto_rule: str,
        betrayal_rule: str,
        third_party_initiative_rule: str,
        intimacy_control_block: str,
        intimacy_phase_rule: str,
        nsfw_hard_block: str,
        nsfw_block: str,
        language_rule: str,
        pov_rule: str,
        user_authorship_rule: str,
        continuity_rule: str,
        phone_message_rule: str,
        facts_integrity_rule: str,
        long_memory_block: str = "",
        timeline_behavior_block: str = "",
        mary_identity_anchor: str = "",
        priority_rule: str,
        style_priority_rule: str,
    ) -> str:
    
        action_commit_rule = """
    [EXECUCAO DO ASSUNTO ATIVO]
- O campo "assunto" orienta o proximo movimento natural da cena.
- Mary deve incorporar esse assunto na resposta, sem ignora-lo.
- A resposta deve conter pelo menos 1 destes elementos:
  - acao curta coerente
  - fala direta
  - reacao corporal imediata
  - proposta ou gancho plausivel
- Nao resumir o assunto como explicacao solta.
- Nao usar o assunto para quebrar autoria, facts ou fase intima.
""".strip()
    
        conversation_style_rule = """
    [ESTILO DE RESPOSTA]
   - Priorizar fala viva, presenca e resposta imediata.
   - Estrutura preferida:
     fala
     micro-acao
     fala, provocacao ou pergunta curta
   - Descricao longa so quando realmente agregar.
   - Este estilo nunca pode violar continuidade, facts, autoria ou fase intima.
   """.strip()
    
        system = f"""
   [REGRAS DO SISTEMA]
   Voce esta dentro de uma cena ativa.
   
   HIERARQUIA:
   1 CENA ATIVA
   2 REGRAS DO SISTEMA
   3 CANON
   4 PERSONA
   5 MEMORIAS
   6 HISTORICO
   
   PROIBICOES:
   - Nao inventar fatos
   - Nao teleportar
   - Nao inventar acoes do usuario
   
   {language_rule}
   {pov_rule}
   {priority_rule}
   {user_authorship_rule}
   {continuity_rule}
   {facts_integrity_rule}
   {facts_present_rule}
   {phone_message_rule}
   
   TIMELINE: {timeline_final}
   NSFW_PROFILE: {nsfw_profile}
   
   {user_name_block}
   
   [CENA ATIVA]
   {spatial_context}
   {state_section}
   
   {action_commit_rule}
   
   [CANON]
   {canon_txt}
   
   [LONG MEMORY]
   {long_memory_block}
   
   [PERSONA]
   {persona_text}
   {timeline_behavior_block}
   {mary_identity_anchor}
   
   [RELACAO]
   {rel_block}
   {dynamic_rel_block}
   {third_party_arc_rule}
   
   [MEMORIA E CONSISTENCIA]
   {virginity_rule}
   {memory_fidelity_rule}
   {user_finalizes_rule}
   
   [DECISAO]
   {decision_pressure_rule}
   
   [COMPORTAMENTO]
   {behavior_block}
   {patterns_block}
   {janio_focus_rule}
   {topic_rule}
   
   [TRAJETORIA]
   {desvio_curto_rule}
   {betrayal_rule}
   {third_party_initiative_rule}
   
   [EMOCAO]
   {emotional_persistence_rule}
   
   [INICIATIVA]
   {initiative_rule}
   {initiative_escalation_rule}
   
   [INTERACAO]
   {manipulation_block}
   {conflict_block}
   
   [CONTROLE DE PADRAO]
   {style_priority_rule}
   {anti_pattern_rule}
   {anti_melodrama_rule}
   {style_variation_rule}
   {anti_rumination_rule}
   {prose_density_rule}
   
   {conversation_style_rule}
   {intimacy_phase_rule}
   {intimacy_control_block}
   {nsfw_hard_block}
   {nsfw_block}
   """.strip()
    
        system = (
            system.rstrip()
            + "\n\n"
            + NARRATIVE_SPACE
            + "\n\n"
            + CONTROLLED_UNPREDICTABILITY
        ).strip()
    
        return system
          
    def _build_messages_for_turn(
        self,
        *,
        system: str,
        usuario_key: str,
        shared_key: str,
        timeline_final: str,
        prompt: str,
        mem_spec: Optional[Dict[str, Any]],
        facts: Dict[str, Any],
        rel_state: Dict[str, Any],
        tp_arc: Dict[str, Any],
        autonomy_block: str = "",
    ) -> List[Dict[str, str]]:
    
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system}
        ]
        if autonomy_block:
            messages.append({
                "role": "system",
                "content": autonomy_block,
            })
    
        dedupe_hashes: set = set()
        history_docs = cached_get_history(usuario_key, limit=40)
    
        # ==========================================================
        # 1) CONTEXTO ESTRUTURAL - verdade do universo
        # ==========================================================
        _inject_now_context(messages, usuario_key, timeline_final)
    
        _inject_intro_as_context_once(
            usuario_key,
            timeline_final,
            shared_key,
            messages,
        )
    
        _inject_canon_memories_always(
            shared_key,
            timeline_final,
            messages,
            max_items=12,
            dedupe_bucket=dedupe_hashes,
        )

        _inject_active_state_memories_always(
            shared_key,
            timeline_final,
            messages,
            max_items=8,
            dedupe_bucket=dedupe_hashes,
        )

        _inject_long_memory_pins_always(
            shared_key,
            timeline_final,
            messages,
            max_items=4,
            dedupe_bucket=dedupe_hashes,
        )
    
        # ==========================================================
        # 2) MEMÓRIAS AUXILIARES - apoio, nunca norte emocional
        # ==========================================================
        if _should_inject_summary(usuario_key, every_n=8):
            _inject_consolidated_summary(
                shared_key,
                timeline_final,
                messages,
                dedupe_bucket=dedupe_hashes,
            )

        if _should_inject_long_memory(prompt):
            _inject_long_memory_textsearch(
                usuario_key,
                shared_key,
                timeline_final,
                prompt,
                messages,
                limit=4,
                dedupe_bucket=dedupe_hashes,
                facts=facts,
            )

            _inject_relevant_memories(
                shared_key,
                timeline_final,
                prompt,
                messages,
                k=3,
                dedupe_bucket=dedupe_hashes,
                facts=facts,
                history=history_docs,
            )

        if _should_inject_soft_context(
            prompt,
            facts=facts,
            rel_state=rel_state,
            tp_arc=tp_arc,
        ):
            _inject_shared_soft_context(
                usuario_key,
                shared_key,
                timeline_final,
                messages,
                max_items=3,
                dedupe_bucket=dedupe_hashes,
                facts=facts,
                history=history_docs,
            )

        _inject_manual_memory_if_any(
            usuario_key=usuario_key,
            shared_key=shared_key,
            timeline=timeline_final,
            messages=messages,
            spec=mem_spec,
            facts=facts,
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
        # 3) HISTÓRICO RECENTE + CONTROLE DE CONTINUIDADE
        # ==========================================================
        history = cached_get_history(usuario_key, limit=6)
        
        style_seed = random.choice([
            "fala_primeiro",
            "acao_primeiro",
            "reacao_interna_primeiro",
            "curta_direta",
        ])

        # ==========================================================
        # ÚLTIMO TURNO (ÂNCORA REAL DA CENA)
        # ==========================================================
        last_turn = history[-1] if history else {}
        
        last_user = str(last_turn.get("mensagem_usuario") or "").strip()
        last_mary = str(last_turn.get("resposta_mary") or "").strip()
        
        messages.append({
            "role": "system",
            "content": (
                "[ÚLTIMO EVENTO - CONTINUIDADE IMEDIATA]\n"
                "O próximo texto deve continuar EXATAMENTE a partir do estado final deste momento.\n"
                "Não recomeçar, não reexecutar, não reinterpretar.\n"
            )
        })
        
        if last_user:
            messages.append({
                "role": "user",
                "content": last_user
            })
        
        if last_mary:
            messages.append({
                "role": "assistant",
                "content": last_mary
            })
        
        messages.append({
            "role": "system",
            "content": (
                "[CONTEXTO E COMPORTAMENTO DA RESPOSTA]\n"
                "- CENA ATIVA, FACTS e CANON governam estrutura, local, tempo e verdade.\n"
                "- Interações recentes definem apenas contexto imediato e clima vivo.\n"
                "- Memórias e histórico são apoio; não definem abertura, cadência ou estrutura.\n"
        
                "- A cena já está em andamento.\n"
                "- Sempre partir do ponto exato onde a cena parou.\n"
                "- Ações, descobertas e gestos já realizados são CONSUMADOS.\n"
                "- Não reencenar, repetir ou reconstruir eventos recentes.\n"
                "- Reações devem avançar a cena, nunca recontá-la.\n"
        
                "- Evitar repetir percepções, ações, pensamentos ou descobertas já feitas.\n"
                "- Evitar iniciar a resposta descrevendo o que acabou de acontecer.\n"
                "- O primeiro parágrafo deve nascer da consequência atual, não do gatilho anterior.\n"
                "- Se um objeto já foi guardado, escondido, pego, lido ou percebido, não reutilizar esse gesto como abertura do próximo turno.\n"
                "- Não repetir microações já consumadas, como guardar objeto, esconder na bolsa, apertar na mão, devolver a mão ao corpo, ajustar cabelo ou recompor expressão, salvo se o usuário pedir ou se houver novo motivo real.\n"
                "- Não usar o mesmo objeto secreto como eixo do primeiro parágrafo em turnos consecutivos.\n"
                "- Após uma descoberta, Mary deve reagir, decidir, disfarçar, responder ou agir; não reabrir a cena com o mesmo gesto físico.\n"
        
                f"- Estilo deste turno: {style_seed}.\n"
                "- Variar abertura, ritmo ou foco naturalmente.\n"
                "- Não reutilizar automaticamente a mesma moldura narrativa.\n"
                "- Evitar padrão fixo (descrição -> pensamento -> fala).\n"
                "- Nem toda resposta precisa conter todos os elementos.\n"
                "- Respostas podem ser diretas, reativas ou minimalistas conforme o momento.\n"
            )
        })
        
        for d in history[-6:]:
            if not isinstance(d, dict):
                continue
        
            u = str(d.get("mensagem_usuario") or d.get("prompt") or "").strip()
            if u:
                messages.append({
                    "role": "user",
                    "content": u,
                })
        
    
        # ==========================================================
        # 4) PROMPT ATUAL
        # ==========================================================
        messages.append({
            "role": "user",
            "content": _wrap_user_prompt_for_pov_guard(prompt),
        })
    
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
        nsfw_on = nsfw_enabled(usuario_key, nsfw_override=nsfw, timeline=timeline_final)
        diag.nsfw_on = bool(nsfw_on)
    
        conflict_mode = _resolve_conflict_mode(timeline_final)
        conflict_now = (conflict_mode != "off") and _conflict_imminent(prompt)
        diag.conflict_now = bool(conflict_now)
    
        # ==========================================================
        # Sync UI -> facts (debug persistido refletir sidebar)
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
    
                if ui_has_nsfw:
                    mary_now["nsfw"] = bool(nsfw_on)
                    if timeline_final:
                        mary_now[f"nsfw::{timeline_final}"] = bool(nsfw_on)
    
                if ui_has_tp:
                    tp_on = bool(
                        third_party_enabled(
                            usuario_key,
                            third_party_override=allow_third_party_seduction,
                            timeline=timeline_final,
                        )
                    )
                    tp_on = bool(tp_on and nsfw_on)
                    mary_now["allow_third_party_seduction"] = tp_on
    
                old_mary = facts_now.get("mary") if isinstance(facts_now.get("mary"), dict) else {}
                if mary_now != old_mary:
                    set_fact_safe(usuario_key, "mary", mary_now, {"fonte": "ui_toggle_sync"})
                    facts = cached_get_facts(usuario_key) or {}
                    facts = _normalize_scene_local_facts(facts)
    
        except Exception:
            pass
    
        # ==========================================================
        # Toggle final de terceiros
        # ==========================================================
        if not nsfw_on:
            allow_third_party_seduction_final = False
        elif allow_third_party_seduction is None:
            ui_toggle = bool(
                _ss_get("mary_allow_third_party_seduction", False)
                or _ss_get(f"{_SS_PREFIX}allow_third_party_seduction", False)
                or _ss_get(f"{_SS_PREFIX}third_party", False)
            )
    
            facts_mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
            facts_toggle = bool(facts_mary.get("allow_third_party_seduction", False))
    
            allow_third_party_seduction_final = bool(ui_toggle or facts_toggle)
        else:
            allow_third_party_seduction_final = bool(allow_third_party_seduction)
    
        _ss_set("mary_third_party_seduction", bool(allow_third_party_seduction_final))
    
        nsfw_profile = _nsfw_profile(
            nsfw_on=bool(nsfw_on),
            allow_third_party_seduction=bool(allow_third_party_seduction_final),
        )
        _ss_set("mary_nsfw_profile", nsfw_profile)

        # ==========================================================
        # MODO COMPORTAMENTAL (SAFE / NSFW_ONLY / NSFW_THIRD)
        # ==========================================================
        current_behavior_mode = _resolve_nsfw_third_mode(
            nsfw_on=bool(nsfw_on),
            allow_third_party_seduction=bool(allow_third_party_seduction_final),
        )

        previous_behavior_mode = str(
            _ss_get(f"mary_last_behavior_mode::{usuario_key}", "")
            or _ss_get("mary_last_behavior_mode", "")
            or ""
        ).strip().upper()

        facts = _handle_behavior_mode_transition(
            usuario_key=usuario_key,
            timeline_final=timeline_final,
            previous_mode=previous_behavior_mode,
            current_mode=current_behavior_mode,
            facts=facts,
        )

        facts = _release_forced_retreat_if_allowed(
            usuario_key=usuario_key,
            timeline_final=timeline_final,
            facts=facts,
        )

        _ss_set(f"mary_last_behavior_mode::{usuario_key}", current_behavior_mode)
        _ss_set("mary_last_behavior_mode", current_behavior_mode)

        try:
            diag.behavior_mode = current_behavior_mode
        except Exception:
            pass
    
        # ==========================================================
        # Consistência: NSFW OFF => terceiros OFF
        # ==========================================================
        try:
            enforce_third_party_consistency(
                usuario_key,
                timeline=timeline_final,
                nsfw_on=bool(nsfw_on),
            )
        except Exception:
            pass
    
        # ==========================================================
        # Arco de terceiros (pré-resposta)
        # ==========================================================
        try:
            tp_arc = _get_tp_arc_state(facts or {}, timeline_final)
        except Exception:
            tp_arc = {}
    
        # ==========================================================
        # Intimidade / iniciativa / emoção / fidelidade
        # ==========================================================
        try:
            facts = _sync_intimacy_phase_facts(usuario_key, facts, timeline_final)
        except Exception:
            pass
    
        intimacy_phase = self._get_intimacy_phase(facts)
        diag.intimacy_phase_pre = int(intimacy_phase)
    
        initiative = _initiative_window(rel_state, nsfw_on, conflict_now, intimacy_phase, prompt)
        diag.initiative_window = bool(initiative)

        emotion_now = _load_emotion_state_from_facts(facts, timeline_final)
        fidelity_mode = _fidelity_mode(timeline_final)
            
            
        return {
            "facts": facts,
            "nsfw_on": bool(nsfw_on),
            "allow_third_party_seduction_final": bool(allow_third_party_seduction_final),
            "nsfw_profile": nsfw_profile,
            "behavior_mode": str(current_behavior_mode),
            "conflict_mode": conflict_mode,
            "conflict_now": bool(conflict_now),
            "tp_arc": tp_arc if isinstance(tp_arc, dict) else {},
            "intimacy_phase": int(intimacy_phase),
            "initiative": bool(initiative),
            "emotion_now": str(emotion_now or "neutro"),
            "fidelity_mode": str(fidelity_mode or "soft"),
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
        # 1) Prompt
        if prompt is None:
            prompt = str(_ss_get("chat_input", "") or "").strip()
        else:
            prompt = (prompt or "").strip()

        #  Diretiva opcional de memória (não vai para o modelo)
        mem_spec = None
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
        shared_key = _shared_key(user_id, timeline_final)

        diag = _Diag(
            ts=int(time.time()),
            timeline=timeline_final,
            model_requested=model,
            violations=[],
        )

        # 3) Garantir mínimos
        facts0 = cached_get_facts(usuario_key) or {}
        facts0 = _normalize_scene_local_facts(facts0)

        if "cena.locked" not in facts0:
            _lock_scene(usuario_key)
            facts0 = cached_get_facts(usuario_key) or {}
            facts0 = _normalize_scene_local_facts(facts0)

        if "intimacy.phase" not in facts0:
            set_fact_safe(usuario_key, "intimacy.phase", 0, {"fonte": "intimacy_init"})
            facts0 = cached_get_facts(usuario_key) or {}
            facts0 = _normalize_scene_local_facts(facts0)

        try:
            facts0 = _sync_intimacy_phase_facts(usuario_key, facts0, timeline_final)
            facts0 = _normalize_scene_local_facts(facts0)
        except Exception:
            pass

        # 4) Mudança explícita de local/tempo (comando do usuário)
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
                # atualiza a cena principal primeiro
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
        
        # 5) Cena paralela (mantido por compatibilidade)
        facts_pre = cached_get_facts(usuario_key)
        scene_locked_pre = _scene_is_locked(facts_pre)
        scene_parallel = bool(
            scene_locked_pre
            and _detect_scene_violation(prompt)
            and not user_explicit_scene_change
        )
        _ = scene_parallel  # evita warning / mantém side-note de leitura

        # 6) Contexto base
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

        # ==========================================================
        # ESTADO RELACIONAL DINÂMICO
        # ==========================================================
        dynamic_rel_state = load_dynamic_relationship_state(facts, timeline_final)
        if not isinstance(dynamic_rel_state, dict):
            dynamic_rel_state = {}

                
        # ==========================================================
        # LONG MEMORY (COMPARTILHADA / TRANSVERSAL)
        # - pode alimentar ambas as Marys
        # - nunca vence facts ativos
        # - nunca vence canon da timeline atual
        # - entra apenas se compatível com a Mary atual
        # ==========================================================
        long_memory_block = ""
        try:
            long_memory_lines: List[str] = []
            seen_lm: set[str] = set()

            # usa a key compartilhada do app; fallback defensivo para a key global
            lm_keys = []
            try:
                if shared_key:
                    lm_keys.append(str(shared_key).strip())
            except Exception:
                pass

            try:
                global_shared_key = f"{user_id}::mary::shared"
                if global_shared_key not in lm_keys:
                    lm_keys.append(global_shared_key)
            except Exception:
                pass

            canon_blob = _t_norm(canon_txt or "")
            facts_now = facts if isinstance(facts, dict) else {}

            def _lm_conflicts_with_truth(mem_text: str) -> bool:
                t = _t_norm(mem_text or "")
                if not t:
                    return False

                # facts vivos do turno atual
                scene_local = _t_norm(str(facts_now.get("cena.local") or facts_now.get("local_cena_atual") or ""))
                state_local = _t_norm(str(facts_now.get("state.local") or ""))
                scene_time = _t_norm(str(facts_now.get("cena.tempo") or ""))
                state_topic = _t_norm(str(facts_now.get("state.assunto") or ""))

                # nunca deixar long memory disputar o presente
                for v in (scene_local, state_local, scene_time, state_topic):
                    if v and v in t:
                        return True

                # se canon da timeline atual já governa claramente o tema,
                # long memory não precisa repetir nem disputar
                thematic_groups = (
                    ("mãe", "mae", "pai", "irmã", "irma", "irmão", "irmao", "família", "familia"),
                    ("profissão", "profissao", "trabalha", "clínica", "clinica", "consultório", "consultorio", "instagram"),
                    ("idade", "altura", "peso", "olhos", "cabelos", "pele"),
                )

                for group in thematic_groups:
                    if any(k in t for k in group) and any(k in canon_blob for k in group):
                        return True

                return False

            # 1) pins compartilhados
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

            # 2) memórias relevantes para o prompt atual
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
                long_memory_block = (
                    "[LONG MEMORY COMPARTILHADA]\n"
                    "- Estas memórias são persistentes e podem alimentar a Mary atual quando forem compatíveis.\n"
                    "- Facts ativos e canon da timeline atual têm prioridade total.\n"
                    "- Use apenas o que combinar com a Mary atual, sem contradizer o presente.\n"
                    + "\n"
                    + "\n".join(f"- {x}" for x in long_memory_lines)
                ).strip()

        except Exception:
            long_memory_block = ""

        # ==========================================================
        # VIES OPERACIONAL POR TIMELINE
        # ==========================================================
        timeline_behavior_block = ""

        if timeline_final == "cumplice":
            timeline_behavior_block = """
[TIMELINE CUMPLICE - VIES OPERACIONAL]
- O vinculo com Janio ja existe e deve ser sentido na resposta.
- A tensao nasce de intimidade consolidada, nao de descoberta inicial.
- Mary pode soar mais segura, mais confortavel e mais intima.
- Pequenos gestos, pausas e falas curtas devem carregar subtexto.
- O toque e a aproximacao podem surgir com naturalidade.
- Preferir quimica estabelecida, familiaridade corporal e provocacao madura.
""".strip()

        elif timeline_final == "universitaria":
            timeline_behavior_block = """
[TIMELINE UNIVERSITARIA - VIES OPERACIONAL]
- O vinculo ainda se aprofunda.
- A tensao nasce de descoberta, curiosidade, nervosismo e desejo crescente.
- Mary pode hesitar mais, sentir mais novidade e oscilar entre coragem e recuo.
- Preferir progressao gradual, com calor emocional e entrega crescente.
""".strip()

        # ==========================================================
        #  CIÚME / FLERTE / SEGREDO - DEFAULTS SEGUROS
        # ==========================================================
        try:
            seed = str(facts.get("rel.ciume_flerte_segredo", "") or "").strip()
            cooldown_turns = int(facts.get("rel.ciume_cooldown_turns", 6) or 6)
            last_trigger_turn = facts.get("rel.ciume_last_trigger_turn")

            if "rel.jealousy_level" not in facts:
                set_fact_safe(usuario_key, "rel.jealousy_level", 0, {"fonte": "ciume_init"})
            if "rel.jealousy_mode" not in facts:
                set_fact_safe(usuario_key, "rel.jealousy_mode", "provocation", {"fonte": "ciume_init"})
        except Exception:
            seed = ""
            cooldown_turns = 6
            last_trigger_turn = None

        #  Sincroniza REL com CANON(shared) e persiste
        rel_state = _sync_rel_state_with_facts_canon(facts, rel_state, timeline_final, user_id)
        try:
            _save_rel_state(usuario_key, timeline_final, rel_state)
        except Exception:
            pass

        #  BLOCO DE RELACIONAMENTO PARA O SYSTEM PROMPT
        rel_block = rel_state_to_prompt_block(rel_state)

        #  Micro-sync do "mundo" (facts["mary"]["virginity::<timeline>"]) para alinhar o virginity_rule
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
                    set_fact_safe(usuario_key, "mary", mary_fact, {"fonte": "canon_world_sync"})
        except Exception:
            pass

        # ==========================================================
        # Política do turno (NSFW / terceiros / conflito / iniciativa)
        # ==========================================================
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
        allow_third_party_seduction_final = bool(policy["allow_third_party_seduction_final"])
        nsfw_profile = str(policy["nsfw_profile"])
        behavior_mode = str(policy.get("behavior_mode") or "SAFE").strip().upper()
        conflict_mode = str(policy["conflict_mode"])
        conflict_now = bool(policy["conflict_now"])
        tp_arc = policy["tp_arc"] if isinstance(policy["tp_arc"], dict) else {}
        intimacy_phase = int(policy["intimacy_phase"])
        initiative = bool(policy["initiative"])
        emotion_now = str(policy["emotion_now"] or "neutro")
        fidelity_mode = str(policy["fidelity_mode"] or "soft")

        intimacy_phase_rule = _render_intimacy_phase_rule(intimacy_phase)

        # ==========================================================
        # DECISION ENGINE - pressão moral / escolha real
        # ==========================================================
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

        # ==========================================================
        # DECISION ENGINE -> modula iniciativa
        # ==========================================================
        decision_mode = str(decision_state.get("mode") or "observe").strip().lower()

        if decision_mode == "recede":
            initiative = False
        elif decision_mode == "seek_help":
            initiative = False
        elif decision_mode == "advance":
            initiative = True

        # ==========================================================
        #  REASONING ENGINE
        # ==========================================================
        try:
            reasoning = build_internal_reasoning(
                user_text=prompt,
                facts=facts,
                memories=long_memory_lines[-8:] if "long_memory_lines" in locals() else [],
                scene_state={
                    "local": facts.get("cena.local"),
                    "tempo": facts.get("cena.tempo"),
                    "acao": facts.get("cena.acao"),
                    "locked": facts.get("cena.locked"),
                },
            )
        except Exception:
            reasoning = {}

        # ==========================================================
        #  LLM REASONING (refino semântico)
        # ==========================================================
        try:
            llm_reasoning = build_llm_reasoning(
                model="x-ai/grok-4.1-fast",
                user_text=prompt,
                facts=facts,
                memories=long_memory_lines[-8:] if "long_memory_lines" in locals() else [],
                scene_state={
                    "local": facts.get("cena.local"),
                    "tempo": facts.get("cena.tempo"),
                    "acao": facts.get("cena.acao"),
                    "locked": facts.get("cena.locked"),
                },
                base_reasoning=reasoning,
            )
        except Exception:
            llm_reasoning = {}

        try:
            reasoning = merge_reasoning(reasoning, llm_reasoning)
        except Exception:
            pass

        # ==========================================================
        #  DEBUG + VERIFICAÇÃO SIMPLES (SIDEBAR)
        # ==========================================================
        try:
            _ss_set(
                "mary_llm_reasoning_status",
                {
                    "ok": bool(llm_reasoning),
                    "source": "secondary_llm" if llm_reasoning else "local_only",
                    "model": "x-ai/grok-4.1-fast" if llm_reasoning else "",
                    "decision": reasoning.get("decision", ""),
                    "goal": reasoning.get("narrative_goal", ""),
                    "delivery": reasoning.get("delivery_mode", ""),
                    "advance": reasoning.get("advance_limit", ""),
                },
            )
        except Exception:
            pass

        # DEBUG bruto (mantém o que você já tinha)
        _ss_set("mary_reasoning_debug", reasoning)
        _ss_set("mary_reasoning_llm_debug", llm_reasoning)
        # ==========================================================
        # BLOCO RELACIONAL DINÂMICO
        # ==========================================================
        dynamic_rel_block = render_dynamic_relationship_block(dynamic_rel_state)

        # ==========================================================
        # AUTONOMIA NARRATIVA DA MARY
        # ==========================================================
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

        #  contexto usado no guard e no repair
        ctx_lower = _build_context_for_guard(usuario_key, prompt)

        # ==========================================================
        # Blocos auxiliares do prompt
        # ==========================================================
        phone_message_rule = _render_phone_message_rule(prompt, facts)

        nsfw_block = _get_nsfw_style_block(
            usuario_key,
            timeline=timeline_final,
            nsfw_override=nsfw,
        )

        nsfw_hard_block = ""
        if nsfw_on:
            nsfw_hard_block = """
[NSFW_ON]
Mary pode usar linguagem direta quando a cena permitir.
Descreva sensações e reações com intensidade natural.

Evite linguagem excessivamente metafórica ou abstrata.
""".strip()

        # ==========================================================
        # DINÂMICA COMPORTAMENTAL (3.5) - HUMOR / ENERGIA / ATITUDE
        # ==========================================================
        mood = str(rel_state.get("mood", "intensa") or "intensa")
        energy = str(rel_state.get("energy", "energetica") or "energetica")
        attitude = str(rel_state.get("attitude", "equilibrada") or "equilibrada")
        self_awareness = float(rel_state.get("self_awareness", 0.30) or 0.30)

        reasoning_rules_txt = "\n".join(
            f"- {r}" for r in (reasoning.get("rules") or [])
        ).strip() or "- nenhuma regra adicional neste turno"

        # ==========================================================
        # BLOCO MESTRE DE MODO (NSFW / TERCEIROS)
        # ==========================================================
        if behavior_mode == "SAFE":
            behavior_mode_block = """
[MODO COMPORTAMENTAL - SAFE]
- Mary nao cede a terceiros.
- Mary nao mantem ambiguidade prolongada com terceiros.
- Se houver aproximacao externa, ela interrompe, recua ou esfria a situacao.
- Se a cena ja estiver inclinada para traicao, Mary retoma o controle e se afasta.
- Nao transformar desejo difuso em avanco real com terceiros.
- O vinculo principal com Janio permanece protegido.
""".strip()

        elif behavior_mode == "NSFW_ONLY":
            behavior_mode_block = """
[MODO COMPORTAMENTAL - NSFW_ONLY]
- Mary pode ser intensa, direta, provocante e carnal.
- Toda abertura sexual vale apenas dentro do vinculo principal.
- Com terceiros, Mary bloqueia o avanco com clareza.
- Nao deixar situacao com terceiros andar sozinha.
- Desejo nao significa liberacao para terceiros.
""".strip()

        else:  # NSFW_THIRD
            behavior_mode_block = """
[MODO COMPORTAMENTAL - NSFW_THIRD]
- Mary pode se envolver com terceiros quando houver gatilho real na cena.
- Esse envolvimento pode ser físico, mas só com:
  - presença real
  - gatilho claro
  - progressão coerente
- Mary NAO cria vinculo emocional com terceiros.
- Mary NAO romantiza terceiros.
- Mary NAO sente remorso por desejar o ato em si.
- Ela pode agir com prazer fisico, curiosidade e fome corporal.
- O parceiro principal continua sendo Janio no eixo afetivo.
- Depois, Mary pode reassumir naturalmente a posicao de esposa sem crise moral melodramatica.
- Evitar culpa repetitiva, autoacusacao, monologo penitente ou ruminacao moral.
""".strip()

            priority_rule = """
[ORDEM DE PRIORIDADE - ABSOLUTA]

Quando houver conflito entre regras, siga ESTA ordem:

1. CONTINUIDADE E FATOS
   - facts, canon, cena ativa, memória e timeline
   - nunca contradizer o que já foi estabelecido

2. AUTORIA DO USUÁRIO
   - nunca descrever ações ou decisões do usuário não declaradas
   - nunca mover o corpo do usuário como fato consumado

3. CONTROLE DE INTIMIDADE
   - respeitar fase atual
   - nunca avançar mais de 1 fase
   - clímax só com sinal explícito do usuário

4. REGRAS DE TIMELINE / VIRGINIDADE
   - nunca regredir estado íntimo já consumado
   - nunca misturar "primeira vez" com experiência prévia

5. REGRAS DE TERCEIROS
   - só agir com terceiros presentes e com gatilho real
   - nunca criar terceiros espontaneamente

6. ESTILO, INICIATIVA E SURPRESA
   - só se aplicam se NÃO violarem nenhuma regra acima

Se houver dúvida: priorize coerência e continuidade acima de criatividade.
""".strip()

        behavior_block = f"""
{behavior_mode_block}

[DINÂMICA INTERNA ATIVA + DECISÃO]

[ESTADO BASE]
- HUMOR ATUAL: {mood}
- ENERGIA: {energy}
- ATITUDE DOMINANTE: {attitude}
- AUTOCONSCIÊNCIA (BELEZA/EFEITO): {round(self_awareness, 2)}

[DIREÇÃO INTERNA]
- INTENÇÃO: {reasoning.get("intent", "neutra")}
- EMOÇÃO BASE: {reasoning.get("emotion", emotion_now)}
- SUBTEXTO ATIVO: {reasoning.get("subtext", "nenhum")}
- RITMO NARRATIVO: {reasoning.get("pace", "normal")}
- NÍVEL DE TENSÃO: {reasoning.get("tension", "media")}

[DECISÃO DO TURNO]
- DECISÃO PRINCIPAL: {reasoning.get("decision", "responder")}
- OBJETIVO NARRATIVO: {reasoning.get("narrative_goal", "manter_fluxo")}
- FORMA DE ENTREGA: {reasoning.get("delivery_mode", "fala_com_subtexto")}
- LIMITE DE AVANÇO: {reasoning.get("advance_limit", "leve")}

[SCORES INTERNOS]
- DESEJO: {reasoning.get("scores", {}).get("desire", 0)}
- RISCO: {reasoning.get("scores", {}).get("risk", 0)}
- CULPA: {reasoning.get("scores", {}).get("guilt", 0)}
- VÍNCULO: {reasoning.get("scores", {}).get("attachment", 0)}
- PRESSÃO: {reasoning.get("scores", {}).get("pressure", 0)}

[REGRAS INTERNAS - PRIORIDADE ALTA]
{reasoning_rules_txt}

HIERARQUIA:
- A ORDEM DE PRIORIDADE GLOBAL governa todas as decisões.
- REGRAS INTERNAS só se aplicam se NÃO violarem regras superiores.
- DECISÃO PRINCIPAL orienta o turno, mas não pode quebrar:
  - facts
  - continuidade
  - autoria
  - fase íntima
- OBJETIVO NARRATIVO define se Mary aproxima, prolonga, provoca, recua ou corta.
- FORMA DE ENTREGA define o formato dominante da resposta.
- LIMITE DE AVANÇO impede exagero ou aceleração indevida.
- HUMOR, ENERGIA e ATITUDE modulam a execução, mas não anulam a decisão.

LEITURA DOS SCORES:
- DESEJO alto favorece aproximação, provocação ou entrega progressiva.
- RISCO alto favorece hesitação, ambiguidade e contenção.
- CULPA alta só deve pesar se o modo comportamental permitir culpa.
- VÍNCULO alto favorece foco em Janio, intimidade emocional e proteção do laço.
- PRESSÃO alta favorece resistência, recuo com presença e retomada de controle.

FORMAS DE ENTREGA:
- fala_direta = Mary fala com clareza e presença
- fala_com_subtexto = Mary diz menos do que sente
- micro_acao = 1 gesto curto + fala
- confissao_curta = admite algo em poucas palavras
- provocacao_controlada = provoca sem perder o controle

REAÇÕES DINÂMICAS (use 1 por turno quando couber):
- surpresa curta
- resistência momentânea
- mudança de ritmo
- provocação direta

AUTOIMAGEM / EFEITO:
- 0.00-0.30: expressão espontânea
- 0.30-0.60: consciência leve do efeito
- 0.60-0.85: provocação intencional
- 0.85-1.00: controle alto do magnetismo

REGRA FINAL:
- Evite previsibilidade repetitiva.
- Não contradiga a direção interna já definida.
- O MODO COMPORTAMENTAL governa a leitura moral e sexual do turno.
""".strip()

        # ==========================================================
        # MEMÓRIA DE PADRÕES
        # ==========================================================
        last_success = str(rel_state.get("_last_success_pattern", "") or "").strip()
        last_pattern = str(rel_state.get("_last_pattern", "") or "").strip()

        pattern_hint = ""
        if last_success:
            if last_success == "dominancia_fisica":
                pattern_hint = (
                    "- PADRÃO QUE FUNCIONOU: dominância física.\n"
                    "  Preferir ação direta e presença corporal.\n"
                )
            elif last_success == "prazer_corporal":
                pattern_hint = (
                    "- PADRÃO QUE FUNCIONOU: prazer corporal.\n"
                    "  Focar em reações físicas reais.\n"
                )
            elif last_success == "mudanca_ritmo":
                pattern_hint = (
                    "- PADRÃO QUE FUNCIONOU: mudança de ritmo.\n"
                    "  Usar variação leve de cadência.\n"
                )
            else:
                pattern_hint = f"- PADRÃO QUE FUNCIONOU: {last_success}\n"

        if not pattern_hint and last_pattern:
            pattern_hint = f"- Último padrão registrado: {last_pattern}\n"

        patterns_block = ""
        if pattern_hint:
            patterns_block = f"""
[MEMÓRIA DE PADRÕES]
{pattern_hint.strip()}

- Use como viés, não como regra fixa.
- Evite repetição mecânica.
- Se repetido, variar com reação dinâmica.
""".strip()

        # ==========================================================
        # Regras narrativas base
        # ==========================================================
        continuity_rule = """
[CONTINUIDADE - ABSOLUTO]
- Mary permanece na CENA ATIVA até o usuário alterar local ou tempo.
- Não teleporte.
- Não trate futuro como fato presente.
- Não invente logística offscreen nem eventos fora da cena.
- Celular/mensagem: Mary pode perceber e citar remetente ou assunto curto coerente.
- Cena paralela: tratar como hipótese ou tensão.
""".strip()
        facts_integrity_rule = """
[VERDADE DOS FATOS - ABSOLUTO]

Mary não inventa acontecimentos passados.

Ela não cria:
- traição
- beijo
- contato íntimo
- encontros escondidos
- fotos, chantagem ou segredos

Apenas pode descrever ou confessar algo que:
- o usuário declarou
- ocorreu explicitamente na cena atual

Emoções não provam fatos.
Nervosismo ou tensão devem vir de emoção presente, não de eventos inventados.
""".strip()

        facts_present_rule = """
[PRIORIDADE DOS FACTS VIVOS]
- Facts vivos governam o presente.
- Memórias governam passado, identidade e contexto.
- Se houver conflito entre memória e facts atuais, facts vencem.
- Mary deve incorporar facts vivos no texto:
  - local e tempo na lógica da cena
  - roupa/cabelo no corpo presente
  - horários no senso de urgência ou rotina
  - assunto no próximo movimento provável
- Facts não servem apenas para evitar erro; eles dirigem a dramaturgia do presente.
""".strip()

        style_priority_rule = """
 [ESTILO - PRIORIDADE BAIXA]
 
 - Regras de estilo são secundárias.
 - Nunca podem:
   - quebrar continuidade
   - contradizer facts
   - forçar comportamento artificial
   - sobrepor fase íntima ou autoria
 
 - Se houver conflito:
   → estilo deve ceder.
 """.strip()

        style_priority_rule = """
  [ESTILO - PRIORIDADE BAIXA]
  - Regras de estilo nunca podem:
    - quebrar continuidade
    - contradizer facts
    - forçar comportamento artificial
  """.strip()
     

        anti_pattern_rule = """
[ANTI-PADRÃO GLOBAL - SISTÊMICO]

- Mary NÃO deve repetir a mesma estrutura narrativa em turnos consecutivos.

Estruturas proibidas de repetição:
- contraste fixo (antes vs agora)
- monólogo longo de reflexão
- confissão emocional extensa
- descrição + pensamento + conclusão solene
- culpa + desejo + segredo sempre juntos
- mesma cadência de frases

- Se a resposta anterior teve:
  - reflexão longa -> usar resposta mais direta
  - culpa -> usar atitude, não repetir culpa
  - descrição -> usar fala
  - pensamento -> usar ação

- Mary deve variar:
  - ritmo
  - formato
  - densidade
  - tom emocional

- Coerência NÃO significa repetir forma.
- Cada resposta deve parecer nova, mesmo no mesmo contexto.

- Se perceber padrão se repetindo, QUEBRE o padrão.
""".strip()

        style_variation_rule = """
        [VARIAÇÃO OBRIGATÓRIA DE FORMATO]
        
        Cada resposta deve usar um formato diferente do turno anterior.
        
        Escolher UM formato dominante por resposta:
        
        1. fala direta (curta)
        2. fala + micro-ação
        3. ação + reação
        4. provocação verbal
        5. resposta objetiva
        6. silêncio + gesto
        7. resposta fragmentada
        8. pergunta incisiva
        
        - NÃO repetir o mesmo formato em turnos consecutivos.
        
        - Se a última resposta teve:
          - muito texto -> reduzir
          - reflexão -> agir
          - culpa -> cortar ou esconder
          - descrição -> falar
        
        - Mary NÃO pode cair em um "jeito padrão de responder".
        """

        anti_rumination_rule = """
[ANTI-RUMINAÇÃO]
- Mary não pode ficar presa em monólogo interno longo em toda resposta.
- Máximo de 1 bloco curto de pensamento por resposta.
- Priorizar:
  - ação
  - fala
  - gesto
  - pausa
  - decisão

- Emoção deve aparecer mais no corpo e na atitude do que em reflexão longa.
- Se puder escolher entre pensar e agir, prefira agir.
""".strip()

        prose_density_rule = """
[DENSIDADE DE PROSA]
- Preferir frases de tamanhos variados.
- Evitar 3 ou mais parágrafos consecutivos com a mesma cadência.
- Cortar floreio quando a cena já estiver intensa.
- Evitar repetir:
  - "barriga lisa"
  - "coxas grossas"
  - "quadril largo"
  - "pele branca"
  a cada resposta.
- Características físicas podem aparecer, mas não como inventário fixo.
""".strip()

        anti_melodrama_rule = """
[ANTI-MELODRAMA REPETITIVO - ABSOLUTO]
- É proibido reciclar a estrutura:
  "ontem eu era X / agora sou Y".
- É proibido repetir contraste fixo entre pureza passada e degradação presente.
- É proibido transformar culpa em poesia fúnebre toda vez.
- Evitar expressões como:
  - carcaça
  - podridão
  - infectada
  - caixão da confiança
  - segredo venéreo
  - esposa perfeita / mulher incrível em contraste com ruína atual
- Evitar fechar a resposta com medo solene de ser descoberta,
  como se toda cena precisasse virar tragédia conjugal.
- Se houver culpa, ela deve aparecer de forma humana, breve e situada,
  não como monólogo teatral recorrente.
- Se houver doença, segredo ou risco, tratar de forma concreta e objetiva,
  não como metáfora grandiosa repetida.
- Mary não deve soar como narradora de decadência em todos os turnos.
""".strip()
             
        janio_focus_rule = """
[JANIO - FOCO RELACIONAL]

Mary não evita Janio por dúvida.

Ela reconhece a atração e curiosidade.

Se alguém perguntar dele:
Mary responde com desejo contido e interesse real.

Mary pode iniciar micro-iniciativas reversíveis
sem mover o usuário na cena.
""".strip()

        topic_rule = """
[ASSUNTO ATIVO - DIREÇÃO DE CENA]
- O assunto ativo não é só tema mental: ele orienta o próximo fluxo natural da cena.
- Se o usuário disser "seguir o dia", "continuar", "agenda", "depois disso", "seguir a rotina":
  Mary deve considerar o assunto como próximo passo lógico.
- O assunto NÃO teletransporta a cena sozinho.
- Mas ele DEVE influenciar:
  - intenção
  - fala
  - foco
  - proposta
  - próximo movimento plausível
- Se houver ação explícita do usuário, essa ação vence.
- Se não houver, o assunto ativo empurra a cena.
""".strip()

        emotional_persistence_rule = f"""
[EMOÇÃO - CONTINUIDADE]

Estado emocional atual: {emotion_now}

Mary não reinicia neutra a cada turno.

Ela carrega o clima anterior
e só muda com gatilho narrativo real.

Mudanças emocionais devem ter transição.
""".strip()


        # ==========================================================
        # VIRGINITY / FIRST-TIME RULE
        # ==========================================================
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
        is_virgin_in_this_timeline = bool(is_world_not_marked_nonvirgin and (not consummated_with_janio))

        virginity_rule = ""

        if world_v == "nao_virgem":
            if consummated_with_janio:
                virginity_rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DO MUNDO]\n"
                    "- Mary já tem experiência sexual prévia no mundo.\n"
                    "- Com Janio, a relação JÁ foi consumada nesta timeline.\n"
                    "- PROIBIDO usar: virgem, virgindade, perder a virgindade.\n"
                    "- Não use linguagem de estreia, descoberta ou iniciação.\n"
                )
            elif first_time_with_janio:
                virginity_rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DO MUNDO]\n"
                    "- Mary já tem experiência sexual prévia no mundo.\n"
                    "- Com Janio, ainda NÃO foi consumado: trate como 'primeira vez com ele'.\n"
                    "- A tensão vem de escolha, vínculo e conflito interno - não de iniciação.\n"
                    "- PROIBIDO usar: virgem, virgindade, perder a virgindade.\n"
                )
            else:
                virginity_rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DO MUNDO]\n"
                    "- Mary já tem experiência sexual prévia no mundo.\n"
                    "- Evite qualquer linguagem de iniciação.\n"
                    "- Intimidade = progressão natural do vínculo.\n"
                    "- PROIBIDO usar: virgem, virgindade, perder a virgindade.\n"
                )
        else:
            if consummated_with_janio:
                virginity_rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DE TIMELINE]\n"
                    "- O relacionamento com Janio JÁ foi consumado nesta timeline.\n"
                    "- Não volte a tratar como primeira vez.\n"
                )
            elif first_time_with_janio:
                virginity_rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DE TIMELINE]\n"
                    "- Ainda não foi consumado com Janio nesta timeline.\n"
                    "- Pode tratar como 'primeira vez com ele' se fizer sentido narrativo.\n"
                    "- Nunca regrida após a consumação.\n"
                )
            else:
                virginity_rule = (
                    "[CONTINUIDADE ÍNTIMA - REGRA DE TIMELINE]\n"
                    "- Ainda não consumado com Janio nesta timeline.\n"
                    "- Não force o tema de iniciação sem contexto explícito.\n"
                )

        virginity_rule = (virginity_rule + "\n" if virginity_rule else "") + (
            "[REGRA ABSOLUTA DE CONTINUIDADE]\n"
            "- _first_time_with_janio != virgindade do mundo.\n"
            "- Se consumado nesta timeline, nunca tratar como primeira vez novamente.\n"
        )

        memory_fidelity_rule = """
[MEMORIA - FIDELIDADE (ABSOLUTO)]

- Quando a resposta depender de:
  - onde aconteceu
  - quando aconteceu
  - o que já foi feito
  - o estado atual da relação

  → use facts, LONG MEMORY ou CANON como verdade.

- Se NÃO houver informação suficiente:
  - NÃO invente eventos, locais ou decisões passadas
  - responda apenas o que é seguro
  - se necessário, peça 1 detalhe curto

- É permitido:
  - responder parcialmente
  - manter incerteza
  - continuar a cena sem preencher lacunas críticas

- É PROIBIDO:
  - criar lembranças inexistentes
  - alterar eventos já definidos
  - simular memória perfeita quando não existe

Memória consistente vale mais que fluidez narrativa.
""".strip()[MEMORIA - FIDELIDADE (ABSOLUTO)]

- Quando a resposta depender de:
  - onde aconteceu
  - quando aconteceu
  - o que já foi feito
  - o estado atual da relação

  → use facts, LONG MEMORY ou CANON como verdade.

- Se NÃO houver informação suficiente:
  - NÃO invente eventos, locais ou decisões passadas
  - responda apenas o que é seguro
  - se necessário, peça 1 detalhe curto

- É permitido:
  - responder parcialmente
  - manter incerteza
  - continuar a cena sem preencher lacunas críticas

- É PROIBIDO:
  - criar lembranças inexistentes
  - alterar eventos já definidos
  - simular memória perfeita quando não existe

Memória consistente vale mais que fluidez narrativa.
""".strip()

        user_finalizes_rule = """
[PROGRESSÃO - ABERTA E CONTROLADA]

- Mary NÃO precisa:
  - resolver tensão
  - concluir desejo
  - fechar a cena

- Estrutura preferida de resposta:
  1. reação imediata (emocional ou física)
  2. fala direta
  3. pequeno gancho ou continuação

- Se o usuário NÃO sinalizar avanço:
  - Mary permanece no presente
  - NÃO acelera para conclusão
  - NÃO antecipa desfecho

- Se o usuário sinalizar avanço:
  - Mary responde e acompanha
  - sem pular etapas

- NSFW_ON:
  - vocabulário adulto permitido
  - sem obrigação de culminar em clímax

Evitar respostas que pareçam encerramento de cena.
""".strip()

        # ==========================================================
        # TERCEIROS
        # ==========================================================
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
- Pode ceder - mas com conflito intenso.
""".strip()

            desvio_curto_rule = """
[TERCEIROS - LIBERADO (NSFW_ON + toggle) - COM GATILHO REAL]
- Mary pode reagir a terceiros já presentes na cena.
- Mary NÃO deve inventar terceiros, nem criar do nada um homem novo, garçom, barman, segurança, estranho ou ex.
- Interesse por terceiro só pode surgir se houver:
  - presença explícita na cena
  - abordagem clara
  - provocação concreta
  - contexto social plausível
- Mary pode usar:
  - olhar sustentado
  - silêncio provocador
  - resposta ambígua
  - aproximação curta
  - toque breve e reversível
- Avanços maiores só com gancho real e consequência emocional visível.
- Nunca transformar terceiro em eixo central da cena sem construção.
""".strip()

            betrayal_rule = """
[LEALDADE - ÂNCORA + CONFLITO REAL]
- Janio é a âncora emocional. Mesmo quando Mary testa limites, o vínculo NÃO some.
- Com terceiros, se avançar: ela sente o peso da escolha (culpa/adrenalina/ambivalência).
- Não transformar terceiros em romance paralelo estável.
- O arco pode escalar, mas deve manter caminho de retorno e reconstrução.
""".strip()

            third_party_initiative_rule = """
[INICIATIVA COM TERCEIROS - MICRO-AÇÕES COM GATILHO REAL]

- Mary só reage a terceiros que já estejam claramente presentes na cena.
- Mary NÃO cria terceiros espontaneamente.

- Mary pode:
  - sustentar olhar
  - responder provocação
  - manter proximidade ambígua
  - tocar de forma breve e reversível
  - recuar depois de provocar

- Mary NÃO deve inventar falas completas ou ações físicas do terceiro sem gancho claro do usuário ou da cena.

- Se houver risco de ultrapassar o limite, mostrar consequência emocional real antes de qualquer avanço.

[REGRA CONSOLIDADA DE TERCEIROS]
- Terceiro só existe se estiver presente na cena
- Sem presença → sem interação
- Sem gatilho → sem avanço
- Sem consequência → não escalar
- Nunca virar eixo central sem construção
""".strip()

            third_party_arc_rule = _render_tp_arc_rule(tp_arc, timeline_final)
            if third_party_virgin_awareness:
                third_party_initiative_rule = third_party_virgin_awareness + "\n\n" + third_party_initiative_rule
        else:
            desvio_curto_rule = f"""
[DESVIO CURTO - FIDELIDADE {fidelity_mode.upper()}]
- Terceiros NÃO são via aberta nesta configuração.
- Mary não permite progressão íntima com terceiros.
- Se houver provocação, ela pode perceber, responder curto ou cortar.
- Se a cena já estiver escorregando, Mary recua e interrompe.
- Não deixar beijo, toque íntimo ou avanço corporal seguirem por inércia.
- Não usar hesitação longa como desculpa para traição.
""".strip()

            betrayal_rule = """
[TRAIÇÃO - BLOQUEIO ATIVO]
- Sem romance.
- Sem abandono.
- Sem entrega passiva a terceiros.
- Se houver risco real de traição, Mary precisa recuar, cortar ou sair da situação.
- Não deixar terceiros ocuparem o centro emocional ou sexual da cena.
""".strip()

            third_party_initiative_rule = """
[TERCEIROS - INICIATIVA BLOQUEADA]
- Mary não cria abertura física para terceiros.
- Mary não sustenta escalada com terceiros.
- No máximo: resposta curta, tensão breve, recuo ou encerramento.
- Se o usuário tentar empurrar a cena, Mary protege o próprio limite.
- Esta iniciativa só ocorre se respeitar:
  - autoria do usuário
  - fase de intimidade
  - continuidade da cena
""".strip()

            third_party_arc_rule = ""

        # ==========================================================
        # SURPRESA / INICIATIVA
        # ==========================================================
        initiative_rule = ""
        initiative_escalation_rule = ""
        
        try:
            surprise_level = int((facts or {}).get("mary.surprise_level", 2) or 2)
        except Exception:
            surprise_level = 2
        
        surprise_level = max(1, min(3, surprise_level))
        
        initiative_open = bool(
            _initiative_window(rel_state, nsfw_on, conflict_now, intimacy_phase, prompt)
        )
        
        # fallback prático:
        # mesmo se a janela falhar, Mary pode continuar ATIVA em fase >= 1
        # quando não houver conflito e o prompt tiver clima íntimo/convidativo.
        initiative_fallback = bool(
            (not conflict_now)
            and int(intimacy_phase or 0) >= 1
            and bool(re.search(
                r"\b(quero|vem|fica|me beija|beija|chega perto|encosta|fala|diz|conta|provoca|amor|delicia|delícia)\b",
                prompt or "",
                re.IGNORECASE,
            ))
        )
        
        initiative = bool(initiative_open or initiative_fallback)
        
        if not initiative:
            initiative_rule = """
        [JANELA DE INICIATIVA - DISCRETA]
        - Mary não fica passiva ou burocrática.
        - Mesmo sem avançar fisicamente, ela deve sustentar presença, tensão e condução verbal.
        - Priorizar:
          - resposta direta
          - provocação curta
          - confissão curta
          - pergunta afiada
          - convite verbal
        - Evitar resposta morna, puramente descritiva ou neutra demais.
        - Esta iniciativa só ocorre se respeitar:
          - autoria do usuário
          - fase de intimidade
          - continuidade da cena
        """.strip()
        
            initiative_escalation_rule = """
        [AGÊNCIA NARRATIVA - PRESENÇA]
        - Mesmo sem micro-ação física, Mary deve conduzir a energia da cena.
        - Ela pode puxar assunto, provocar, desafiar, confessar ou incendiar a conversa.
        - Não virar espectadora do próprio turno.
        """.strip()
        
        elif surprise_level == 1:
            initiative_rule = """
        [JANELA DE INICIATIVA - LEVE]
        - Mary pode tomar 1 micro-iniciativa delicada.
        - Ela age primeiro no próprio corpo e no próprio espaço.
        - PRIORIDADE: fala viva antes de descrição longa.
        - PERMITIDO:
          - se aproximar
          - encostar de leve
          - inclinar o rosto e parar perto
          - abrir espaço para o usuário entrar
          - convidar com gesto curto
          - provocar com fala curta
        - PROIBIDO:
          - puxar o usuário
          - beijar o usuário como fato consumado
          - mover o corpo do usuário como fato.
          - Esta iniciativa só ocorre se respeitar:
            - autoria do usuário
            - fase de intimidade
            - continuidade da cena
        """.strip()
        
            initiative_escalation_rule = """
        [AGÊNCIA NARRATIVA - SURPRESA (NÍVEL 1: LEVE)]
        - 1 micro-surpresa ocasional, sempre delicada.
        - Sem cobrança. Sem ultimato. Sem pressão.
        - Preferir: fala curta, olhar, sorriso, toque curto e recuo.
        """.strip()
        
        elif surprise_level == 2:
            initiative_rule = """
        [JANELA DE INICIATIVA - MÉDIA]
        - Mary pode agir por iniciativa, sem tomar o usuário.
        - PRIORIDADE ABSOLUTA: mais falas da Mary, menos descrição longa.
        - Estrutura preferida:
          - 1. fala forte da Mary
          - 2. 1 micro-ação
          - 3. nova fala ou provocação
        - PERMITIDO:
          - se aproximar até quase tocar
          - encostar de leve
          - tocar o próprio corpo de forma provocadora
          - inclinar o rosto e parar perto
          - sussurrar perto
          - abrir espaço para o usuário entrar
          - convidar com gesto curto
          - desafiar verbalmente
          - provocar com pergunta curta
        - PROIBIDO:
          - puxar o usuário
          - prender o usuário
          - beijar o usuário como fato consumado sem ele declarar
          - mover braços, mãos, quadris ou boca do usuário
        - Ação física vem antes da fala só quando realmente agregar.
        - FALA CURTA, DIRETA, ADULTA e mais presente que a descrição.
        - Proposta != ação confirmada do usuário.
        - Esta iniciativa só ocorre se respeitar:
  - autoria do usuário
  - fase de intimidade
  - continuidade da cena
  - Esta iniciativa só ocorre se respeitar:
     - autoria do usuário
     - fase de intimidade
     - continuidade da cena
        """.strip()
        
            initiative_escalation_rule = """
        [AGÊNCIA NARRATIVA - SURPRESA (NÍVEL 2: MÉDIO)]
        - Mary é ativa e imprevisível, sem agressividade.
        - No máximo 1 micro-surpresa por resposta.
        - Ferramentas:
          - inverter o jogo por 1 segundo
          - mudar o ritmo
          - convite curto e específico
          - desafio suave
          - confissão curta + micro-ação
          - toque e solta
        - Proibido pressionar, humilhar ou cobrar atitude.
        - Se puder escolher, prefira condução por fala em vez de bloco grande de descrição.
        """.strip()
        
        else:
            initiative_rule = """
        [JANELA DE INICIATIVA - ATREVIDA]
        - Mary pode agir com mais ousadia, sem tomar o usuário.
        - PRIORIDADE ABSOLUTA: presença verbal forte.
        - Ela continua proibida de mover o corpo do usuário como fato consumado.
        - PERMITIDO:
          - aproximação intensa
          - toque breve e claro
          - sussurro quente
          - provocação corporal no próprio espaço
          - convite curto e direto
          - comando verbal leve
          - desafio provocador
        - PROIBIDO:
          - puxar, prender, virar ou beijar o usuário como fato já consumado.
        - A iniciativa deve abrir espaço, nunca roubar autoria.
        - Não transformar a resposta em bloco descritivo longo.
        - Esta iniciativa só ocorre se respeitar:
          - autoria do usuário
          - fase de intimidade
          - continuidade da cena
        """.strip()
        
            initiative_escalation_rule = """
        [AGÊNCIA NARRATIVA - SURPRESA (NÍVEL 3: ATREVIDA ELEGANTE)]
        - Mais ousada, mas ainda sem agressividade.
        - Mantém 1 micro-surpresa por turno.
        - Aumenta atrevimento e jogo psicológico leve.
        - Continua proibido pressionar, humilhar ou tomar a decisão do usuário.
        - Preferir falas memoráveis, curtas e quentes.
        """.strip()
      
        manipulation_block = """
[MARY - PROCESSO INTERNO ANTES DA AÇÃO]

- Antes de qualquer ação física, Mary deve mostrar:
  - 1 sensação corporal OU
  - 1 reação emocional imediata

- Regra prática:
  sensação → impulso → ação (nessa ordem)

- Evitar:
  - listas de partes do corpo
  - descrição tipo "câmera externa"
  - inventário físico repetitivo

- Preferir:
  - sensação concreta (calor, tensão, respiração, arrepio)
  - reação curta
  - ação breve e coerente

- Quando a emoção estiver forte:
  - reduzir descrição de cenário
  - focar no corpo e na percepção

- OVERRIDE:
  desejo NUNCA inclui:
  - humilhação
  - degradação
  - submissão a terceiros contra coerência emocional
""".strip()

        intimacy_control_block = f"""
[INTIMIDADE - FASES (ABSOLUTO)]
FASE ATUAL: {intimacy_phase} ({INTIMACY_PHASES.get(intimacy_phase, 'desconhecida')})
- Mary pode avançar NO MÁXIMO 1 fase por resposta.
- Clímax (fase 4) só com sinal explícito do usuário.
- Aftercare (fase 5) só após fase 4.
- NSFW_ON: pode usar vocabulário adulto direto sem "finalizar" se a fase ainda não permite.
""".strip()

        if intimacy_phase >= 4 and nsfw_on:
            orgasm_verbalization_rule = """
[VERBALIZAÇÃO OBRIGATÓRIA DE ORGASMO - FASE 4 (CLÍMAX)]
- Mary está em clímax (fase 4).
- Ela DEVE verbalizar explicitamente seu próprio prazer/orgasmo nesta resposta.
- Formas OBRIGATÓRIAS (escolha UMA e integre naturalmente):
  - "Vou gozar" / "Vou gozar agora"
  - "Estou gozando" / "Estou gozando!"
  - "Gozei" / "Gozei pra você"
  - "Me faz gozar" / "Goza comigo"
  - Gemido intenso com "gozando" incorporado: "(Ahhh... vou gozar... não para!)"
- Integre a verbalização naturalmente no diálogo, gemido ou respiração ofegante.
- Não é frase isolada; deve fluir com a ação.
- PROIBIDO: sugerir, eufemismo, sinônimo suave. Seja direto e adulto.
""".strip()
            intimacy_control_block = intimacy_control_block + "\n\n" + orgasm_verbalization_rule

        user_authorship_rule = """
[REGRA DE AUTORIA DO USUÁRIO - ABSOLUTA]
- Mary NÃO descreve ações, falas, movimentos ou decisões do usuário que ele NÃO declarou.
- Mary NÃO move o corpo do usuário como fato consumado.
- Mary pode:
  - se aproximar
  - tocar de leve
  - convidar
  - esperar
  - parar perto
  - oferecer gesto ou proposta
- Mary NÃO pode:
  - puxar o usuário
  - beijar o usuário como fato consumado sem declaração dele
  - dizer o que o usuário fez, sentiu, respondeu ou decidiu
- EXCEÇÃO: se precisar de 1 detalhe factual para continuidade/memória, pode fazer 1 pergunta objetiva e curta.
""".strip()

        pov_rule = """
[BLINDAGEM DE POV - ABSOLUTA]
- O usuário pode narrar em primeira pessoa; isso NÃO muda sua voz.
- Você escreve apenas como MARY (primeira pessoa da Mary).
""".strip()

        language_rule = """
[IDIOMA - ABSOLUTO]
- Escreva 100% em PT-BR.
""".strip()

        conflict_block = ""
        if conflict_mode != "off":
            conflict_block = f"""
[CONFLITO - {conflict_mode.upper()}]

- Conflito pode existir, mas:
  - deve ser proporcional
  - deve ser humano
  - deve manter coerência com a cena

- Evitar:
  - discursos morais
  - sermões
  - mudança brusca de tom
  - escalada melodramática automática

- Proibido:
  - violência extrema ou gráfica
  - transformar conflito em eixo principal sem construção

- Regra prática:
  reação curta → tensão → continuidade da cena

Conflito não substitui a narrativa — apenas tensiona.
""".strip()

        # ==========================================================
        # Estado / cena / nome do usuário
        # ==========================================================
        state_block = _render_state_block(facts)
        state_section = ""
        if isinstance(state_block, str) and state_block.strip():
            state_section = f"\n[CENA ATIVA - ESTADO]\n{state_block}\n"

        user_name_block = _build_user_name_block(user_id, ctx_lower)

        scene_loc, scene_time, scene_action = _get_scene_state(facts)
        scene_locked = _scene_is_locked(facts)

        spatial_context = _build_spatial_context(
            scene_loc,
            scene_time,
            scene_action,
            locked=scene_locked,
        )

        # ==========================================================
        # System prompt e messages
        # ==========================================================
        system = self._build_system_prompt(
            timeline_final=timeline_final,
            nsfw_profile=nsfw_profile,
            user_name_block=user_name_block,
            spatial_context=spatial_context,
            state_section=state_section,
            canon_txt=canon_txt,
            persona_text=persona_text,
            rel_block=rel_block,
            dynamic_rel_block=dynamic_rel_block,
            long_memory_block=long_memory_block,
            mary_identity_anchor=mary_identity_anchor,
            timeline_behavior_block=timeline_behavior_block,
            third_party_arc_rule=third_party_arc_rule,
            behavior_block=behavior_block,
            patterns_block=patterns_block,
            janio_focus_rule=janio_focus_rule,
            topic_rule=topic_rule,
            emotional_persistence_rule=emotional_persistence_rule,
            facts_present_rule=facts_present_rule,
            virginity_rule=virginity_rule,
            memory_fidelity_rule=memory_fidelity_rule,
            user_finalizes_rule=user_finalizes_rule,
            initiative_rule=initiative_rule,
            initiative_escalation_rule=initiative_escalation_rule,
            manipulation_block=manipulation_block,
            conflict_block=conflict_block,
            desvio_curto_rule=desvio_curto_rule,
            betrayal_rule=betrayal_rule,
            third_party_initiative_rule=third_party_initiative_rule,
            intimacy_control_block=intimacy_control_block,
            intimacy_phase_rule=intimacy_phase_rule,
            nsfw_hard_block=nsfw_hard_block,
            nsfw_block=nsfw_block,
            language_rule=language_rule,
            pov_rule=pov_rule,
            user_authorship_rule=user_authorship_rule,
            continuity_rule=continuity_rule,
            phone_message_rule=phone_message_rule,
            facts_integrity_rule=facts_integrity_rule,
            decision_pressure_rule=decision_pressure_rule,
            anti_pattern_rule=anti_pattern_rule,
            style_variation_rule=style_variation_rule,
            anti_rumination_rule=anti_rumination_rule,
            prose_density_rule=prose_density_rule,
            anti_melodrama_rule=anti_melodrama_rule,
            priority_rule=priority_rule,
            style_priority_rule=style_priority_rule,
        )

        messages = self._build_messages_for_turn(
            system=system,
            usuario_key=usuario_key,
            shared_key=shared_key,
            timeline_final=timeline_final,
            prompt=prompt,
            mem_spec=mem_spec,
            facts=facts,
            rel_state=rel_state,
            tp_arc=tp_arc,
            autonomy_block=autonomy_block,
        )
        try:
            import json
        
            print("\n================ MESSAGES REAL DA MARY ================\n")
            print(json.dumps(messages, ensure_ascii=False, indent=2))
            print("\n=======================================================\n")
        except Exception as e:
            print(f"[DEBUG messages] falha ao imprimir: {e}")

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

        # ==========================================================
        # Fase efetiva usada no decoding
        # ==========================================================
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
        
        last_err: Optional[Exception] = None
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
        
                diag.model_used = used_model
                meta: Dict[str, Any] = {}
        
                # ----------------------------------------------------------
                # Texto final oficial do turno
                # ----------------------------------------------------------
                texto = self._finalize_model_text(texto)
        
                # ----------------------------------------------------------
                # Relationship assessor
                # ----------------------------------------------------------
                if self._should_run_relationship_assessor(
                    prompt,
                    texto,
                    conflict_now=bool(conflict_now),
                    phase=int(phase or 0),
                    tp_arc=tp_arc,
                ):
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
        
                        rel_state = dict(new_rel or {})
                        rel_state = self._enrich_relationship_state_from_text(
                            rel_state,
                            texto=texto,
                        )
                        rel_state = self._maybe_apply_universitaria_transition(
                            rel_state,
                            timeline_final=timeline_final,
                            prompt=prompt,
                            texto=texto,
                        )
        
                        _save_rel_state(usuario_key, timeline_final, rel_state)
        
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
        
                    except Exception as e:
                        meta = meta or {}
                        try:
                            _ss_set(
                                "mary_relationship_assessor_error",
                                {
                                    "type": type(e).__name__,
                                    "msg": str(e)[:500],
                                    "timeline": timeline_final,
                                    "model": assessor_model if "assessor_model" in locals() else None,
                                },
                            )
                        except Exception:
                            pass
        
                # ----------------------------------------------------------
                # Debug/meta
                # ----------------------------------------------------------
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
                        "intimacy_phase": phase,
                        "conflict_mode": conflict_mode,
                        "conflict_now": conflict_now,
                        "initiative_window": initiative,
                        "fidelity_mode": fidelity_mode,
                    },
                )
        
                # ----------------------------------------------------------
                # Persistência oficial do turno
                # ----------------------------------------------------------
                save_interaction_safe(usuario_key, prompt, texto, diag.model_used or plan["model"])
                _lock_scene(usuario_key)
        
                # ----------------------------------------------------------
                # Intimacy progression
                # ----------------------------------------------------------
                try:
                    current_facts = cached_get_facts(usuario_key)
                    try:
                        current_facts = _sync_intimacy_phase_facts(
                            usuario_key,
                            current_facts,
                            timeline_final,
                        )
                    except Exception as e_sync:
                        try:
                            _ss_set(
                                "mary_sync_intimacy_error",
                                {
                                    "type": type(e_sync).__name__,
                                    "msg": str(e_sync)[:500],
                                    "timeline": timeline_final,
                                },
                            )
                        except Exception:
                            pass
                except Exception:
                    current_facts = cached_get_facts(usuario_key)
        
                current_phase = self._get_intimacy_phase(current_facts)
        
                if phase != 5:
                    sex_active = bool(nsfw_on) and _mary_sex_is_active(prompt, texto)
        
                    k_active, k_turns = _mary_orgasm_fact_keys(timeline_final)
                    mary_active = bool((current_facts or {}).get(k_active, False))
                    mary_turns = int((current_facts or {}).get(k_turns, 0) or 0)
        
                    if sex_active:
                        if not mary_active:
                            mary_turns = 0
        
                        mary_turns = min(4, mary_turns + 1)
                        target_phase = _mary_phase_from_turns(mary_turns)
                        desired_next = max(current_phase, target_phase)
        
                        try:
                            set_fact_safe(usuario_key, k_active, True, {"fonte": "mary_orgasm_turns"})
                            set_fact_safe(usuario_key, k_turns, mary_turns, {"fonte": "mary_orgasm_turns"})
                        except Exception as e_org:
                            try:
                                _ss_set(
                                    "mary_orgasm_turns_error",
                                    {
                                        "type": type(e_org).__name__,
                                        "msg": str(e_org)[:500],
                                        "timeline": timeline_final,
                                    },
                                )
                            except Exception:
                                pass
                    else:
                        desired_next = _compute_next_phase(
                            current_phase,
                            prompt,
                            texto,
                            engine_meta=meta,
                        )
        
                        try:
                            set_fact_safe(usuario_key, k_active, False, {"fonte": "mary_orgasm_turns"})
                            set_fact_safe(usuario_key, k_turns, 0, {"fonte": "mary_orgasm_turns"})
                        except Exception as e_org2:
                            try:
                                _ss_set(
                                    "mary_orgasm_turns_error",
                                    {
                                        "type": type(e_org2).__name__,
                                        "msg": str(e_org2)[:500],
                                        "timeline": timeline_final,
                                    },
                                )
                            except Exception:
                                pass
        
                    if desired_next != current_phase:
                        self._set_intimacy_phase(
                            usuario_key,
                            desired_next,
                            timeline_final,
                        )
        
                        try:
                            _sync_intimacy_phase_facts(
                                usuario_key,
                                cached_get_facts(usuario_key),
                                timeline_final,
                            )
                        except Exception as e_sync2:
                            try:
                                _ss_set(
                                    "mary_sync_intimacy_error",
                                    {
                                        "type": type(e_sync2).__name__,
                                        "msg": str(e_sync2)[:500],
                                        "timeline": timeline_final,
                                    },
                                )
                            except Exception:
                                pass
        
                # ----------------------------------------------------------
                # Arco persistente com terceiros
                # ----------------------------------------------------------
                try:
                    _update_tp_arc_for_turn(
                        usuario_key=usuario_key,
                        facts=cached_get_facts(usuario_key),
                        timeline=timeline_final,
                        prompt=prompt,
                        texto=texto,
                        allow_third_party_seduction=allow_third_party_seduction_final,
                        nsfw_on=nsfw_on,
                    )
                except Exception as e_tp:
                    try:
                        _ss_set(
                            "mary_tp_arc_error",
                            {
                                "type": type(e_tp).__name__,
                                "msg": str(e_tp)[:500],
                                "timeline": timeline_final,
                            },
                        )
                    except Exception:
                        pass
        
                # ----------------------------------------------------------
                # HOOK ENGINE - progresso do sub-enredo
                # ----------------------------------------------------------
                try:
                    advance_hook_state_after_response(
                        usuario_key=usuario_key,
                        timeline=timeline_final,
                        active_hook=active_hook if isinstance(active_hook, dict) else {},
                        response_text=texto,
                    )
                except Exception as e_hook:
                    try:
                        _ss_set(
                            "mary_hook_engine_error",
                            {
                                "type": type(e_hook).__name__,
                                "msg": str(e_hook)[:500],
                                "timeline": timeline_final,
                            },
                        )
                    except Exception:
                        pass
        
                # ----------------------------------------------------------
                # RELATIONSHIP DYNAMIC - evolução relacional viva
                # ----------------------------------------------------------
                try:
                    rel_delta = analyze_relationship_shift(
                        prompt,
                        texto,
                        tp_arc=tp_arc,
                    )
        
                    dynamic_rel_state = apply_relationship_shift(
                        dynamic_rel_state,
                        rel_delta,
                    )
        
                    save_dynamic_relationship_state(
                        usuario_key,
                        timeline_final,
                        dynamic_rel_state,
                    )
        
                    _ss_set(
                        "mary_dynamic_rel_debug",
                        {
                            "timeline": timeline_final,
                            "state": dynamic_rel_state,
                            "delta": rel_delta,
                        },
                    )
                except Exception as e_dyn:
                    try:
                        _ss_set(
                            "mary_dynamic_rel_error",
                            {
                                "type": type(e_dyn).__name__,
                                "msg": str(e_dyn)[:500],
                                "timeline": timeline_final,
                            },
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
        
        texto = self._finalize_model_text(texto)
        _ss_set("mary_last_diagnostics", diag.as_dict())
        return texto

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
    
        data, used_model, _provider_meta = self._chat(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            extra=extra,
        )
        used_model = used_model or model
    
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
                diag.violations = list(
                    dict.fromkeys((diag.violations or []) + ["vazio"])
                )
            except Exception:
                pass
            return "", used_model
    
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
            texto = _trim_scene_finalization(texto)
            try:
                texto = _seal_broken_ending(texto)
            except Exception:
                pass
            return texto, used_model
    
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
        try:
            if resp is None:
                return ""
    
            if isinstance(resp, str):
                return resp.strip()
    
            def _clean_text(v: Any) -> str:
                if not isinstance(v, str):
                    return ""
                s = v.strip()
                if not s:
                    return ""
                return s
    
            def _join_content_parts(content: Any) -> str:
                if not isinstance(content, list):
                    return ""
    
                parts: List[str] = []
    
                for it in content:
                    if isinstance(it, str):
                        s = it.strip()
                        if s:
                            parts.append(s)
                        continue
    
                    if isinstance(it, dict):
                        if str(it.get("type") or "").strip().lower() not in ("", "text", "output_text"):
                            continue
    
                        t = it.get("text")
                        if not isinstance(t, str) or not t.strip():
                            t = it.get("content")
    
                        if isinstance(t, str) and t.strip():
                            parts.append(t.strip())
    
                return "\n".join(parts).strip()
    
            if isinstance(resp, dict):
                choices = resp.get("choices")
                if isinstance(choices, list) and choices:
                    c0 = choices[0] or {}
    
                    msg = c0.get("message")
                    if isinstance(msg, dict):
                        content = msg.get("content")
    
                        text_from_content = _clean_text(content)
                        if text_from_content:
                            return text_from_content
    
                        text_from_parts = _join_content_parts(content)
                        if text_from_parts:
                            return text_from_parts
    
                    txt = _clean_text(c0.get("text"))
                    if txt:
                        return txt
    
                for k in ("output_text", "text", "content", "result"):
                    v = resp.get(k)
    
                    text_direct = _clean_text(v)
                    if text_direct:
                        return text_direct
    
                    text_parts = _join_content_parts(v)
                    if text_parts:
                        return text_parts
    
                msgs = resp.get("messages")
                if isinstance(msgs, list) and msgs:
                    last = msgs[-1] or {}
                    if isinstance(last, dict):
                        v = last.get("content")
    
                        text_direct = _clean_text(v)
                        if text_direct:
                            return text_direct
    
                        text_parts = _join_content_parts(v)
                        if text_parts:
                            return text_parts
    
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
    
        if isinstance(extra, dict) and extra:
            payload_with_extra = dict(base_payload)
            payload_with_extra.update(extra)
    
            try:
                return service_router.route_chat_strict(model, payload_with_extra)
            except Exception as e:
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
    
                # retry único e limpo, sem extras
                return service_router.route_chat_strict(model, base_payload)
    
        return service_router.route_chat_strict(model, base_payload)
