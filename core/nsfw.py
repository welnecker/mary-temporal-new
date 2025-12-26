from __future__ import annotations
from typing import Optional
from .repositories import get_fact, get_facts, set_fact


def nsfw_enabled(
    usuario: str,
    nsfw_override: Optional[bool] = None,
    timeline: Optional[str] = None,  # mantido só por compatibilidade
    local_atual: Optional[str] = None,
) -> bool:
    """
    NSFW UNIFICADO — TOTALMENTE LIBERADO POR PADRÃO.

    Ordem de precedência:
    1. nsfw_override explícito (parâmetro)
    2. session_state["mary_nsfw_on"] (Streamlit, se existir)
    3. facts["mary.nsfw"] (persistente)
    4. facts["nsfw_override"] (legado)
    5. DEFAULT = True (liberal)
    """

    # 1) Override explícito
    if isinstance(nsfw_override, bool):
        _sync_nsfw_to_facts(usuario, nsfw_override)
        return nsfw_override

    # 2) session_state (se Streamlit existir)
    try:
        import streamlit as st
        if "mary_nsfw_on" in st.session_state:
            v = st.session_state.get("mary_nsfw_on")
            if isinstance(v, bool):
                _sync_nsfw_to_facts(usuario, v)
                return v
            if isinstance(v, str):
                if v.lower() in ("true", "1", "on", "yes"):
                    _sync_nsfw_to_facts(usuario, True)
                    return True
                if v.lower() in ("false", "0", "off", "no"):
                    _sync_nsfw_to_facts(usuario, False)
                    return False
    except Exception:
        pass

    # 3) facts persistentes
    facts = get_facts(usuario) or {}

    v = facts.get("mary.nsfw")
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.lower() in ("true", "1", "on", "yes"):
            return True
        if v.lower() in ("false", "0", "off", "no"):
            return False

    # 4) legado
    legacy = (facts.get("nsfw_override") or "").lower()
    if legacy == "on":
        return True
    if legacy == "off":
        return False

    # 5) DEFAULT LIBERAL
    return True


def _sync_nsfw_to_facts(usuario: str, value: bool) -> None:
    try:
        set_fact(usuario, "mary.nsfw", bool(value), {"fonte": "nsfw_sync"})
    except Exception:
        pass
