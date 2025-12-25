# core/nsfw.py
from __future__ import annotations
from typing import Optional
import re
from .repositories import get_fact, get_facts

def nsfw_enabled(
    usuario: str,
    nsfw_override: Optional[bool] = None,
    timeline: Optional[str] = None,
    local_atual: Optional[str] = None,
) -> bool:
    """
    Gate NSFW UNIFICADO E ROBUSTO - única fonte de verdade.
    
    Ordem de precedência:
    1. nsfw_override (parâmetro explícito) - mais alta prioridade
    2. session_state["mary_nsfw_on"] (se Streamlit disponível)
    3. facts["mary.nsfw"] (persistente)
    4. facts["nsfw_override"] (legado)
    5. Default baseado em timeline (universitaria=False, outros=True)
    
    Args:
        usuario: Chave do usuário (ex: "user::mary::timeline")
        nsfw_override: Override explícito (None = não usar)
        timeline: Timeline atual para determinar default seguro
        local_atual: Local atual (não usado, mantido para compatibilidade)
    
    Returns:
        bool: True se NSFW está habilitado, False caso contrário
    """
    # 1. Override explícito tem prioridade máxima
    if isinstance(nsfw_override, bool):
        return nsfw_override
    
    # 2. Verifica session_state (Streamlit) - preferência de sessão
    try:
        import streamlit as st
        if "mary_nsfw_on" in st.session_state:
            value = st.session_state.get("mary_nsfw_on")
            if isinstance(value, bool):
                # Sincroniza com facts para persistência
                _sync_nsfw_to_facts(usuario, value)
                return value
            # Sanitiza strings
            if isinstance(value, str):
                if value.lower() in ("true", "1", "on", "yes"):
                    _sync_nsfw_to_facts(usuario, True)
                    return True
                if value.lower() in ("false", "0", "off", "no"):
                    _sync_nsfw_to_facts(usuario, False)
                    return False
    except (ImportError, AttributeError, RuntimeError):
        # Streamlit não disponível - ok, continua
        pass
    
    # 3. Verifica facts (persistente)
    facts = get_facts(usuario) or {}
    
    # 3a. Chave moderna: mary.nsfw
    v = facts.get("mary.nsfw")
    if isinstance(v, bool):
        return v
    # Sanitiza strings em facts
    if isinstance(v, str):
        if v.lower() in ("true", "1", "on", "yes"):
            return True
        if v.lower() in ("false", "0", "off", "no"):
            return False
    
    # 3b. Chave legada: nsfw_override
    override = (get_fact(usuario, "nsfw_override", "") or "").lower()
    if override == "on":
        return True
    if override == "off":
        return False
    
    # 4. Default baseado em timeline (seguro)
    if timeline:
        timeline_lower = str(timeline).strip().lower()
        # Timeline "universitaria" tem default False por segurança
        if timeline_lower == "universitaria":
            return False
        # Outras timelines: default True
        return True
    
    # 5. Fallback final: se não souber timeline, assume False (mais seguro)
    return False


def _sync_nsfw_to_facts(usuario: str, value: bool) -> None:
    """
    Sincroniza estado NSFW do session_state para facts (persistência).
    Seguro: não quebra se streamlit não estiver disponível.
    """
    try:
        from .repositories import set_fact
        set_fact(usuario, "mary.nsfw", value, {"fonte": "nsfw_sync"})
    except Exception:
        # Falha silenciosa - não crítico
        pass
