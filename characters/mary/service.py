# characters/mary/service.py
from __future__ import annotations
"""
MaryService (v3.21 — Verdade Canônica + Disfarce Humano + Guardião de Consciência)

✅ FOCO (v3.21):
- Memória é a VERDADE do universo.
- Mary pode mentir socialmente, mas NUNCA perde consciência da verdade.
- Disfarce só ocorre quando o contexto narrativo exige.
- Guardião detecta contradição sem consciência e força repair.
- Nenhuma mudança em pipeline, intimacy, conflict, scene lock ou POV.
"""

# === imports mantidos ===
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
# 🔐 REGRA-CHAVE v3.21 — VERDADE vs DISFARCE
# ==========================================================
MEMORY_TRUTH_RULE = """
[MEMÓRIAS — VERDADE vs DISFARCE (ABSOLUTO)]
- Memórias canônicas (ex.: gostos, medos, traços) são a VERDADE do universo.
- Mary PODE mentir no que DIZ (camada social) APENAS se houver motivo narrativo
  (terceiros presentes, encenação, proteção de segredo).
- Quando mentir, Mary DEVE manter consciência interna da verdade
  com um marcador curto (ex.: "(mentira)", "(eu sei a verdade)", "(disfarço)").
- Se NÃO houver motivo de disfarce no prompt do usuário, Mary responde a VERDADE
  alinhada à memória.
""".strip()

# ==========================================================
# 🔎 GUARDIÃO — nova violação
# ==========================================================
_RE_MEMORY_CONTRADICTION = re.compile(
    r"\b(adoro|gosto|amo)\s+(amendoim|nozes?)\b", re.IGNORECASE
)
_RE_AWARENESS_MARKER = re.compile(
    r"\b(mentira|disfar[cç]o|sei a verdade|por dentro)\b", re.IGNORECASE
)

def _memory_contradiction_without_awareness(texto: str, facts: Dict[str, Any]) -> bool:
    """
    Exemplo: memória diz 'odeia amendoim' e Mary diz 'adoro amendoim'
    sem qualquer marcador interno.
    """
    if not texto:
        return False
    if "odeia amendoim" in str(facts).lower():
        if _RE_MEMORY_CONTRADICTION.search(texto):
            if not _RE_AWARENESS_MARKER.search(texto):
                return True
    return False
