# core/nsfw.py
from __future__ import annotations

from typing import Optional, Any, Dict

from .repositories import get_facts, set_fact


_TRUE = {"true", "1", "on", "yes", "y", "sim"}
_FALSE = {"false", "0", "off", "no", "n", "nao", "não"}


def _to_bool(value: Any) -> Optional[bool]:
    """Converte bool/string comum em bool. Retorna None se não reconhecido."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
    return None


def _infer_timeline_from_user_key(usuario: str) -> Optional[str]:
    """
    Tentativa best-effort: se usuario for algo como 'janio::mary::universitaria',
    inferimos 'universitaria'. Se não bater, retorna None.
    """
    try:
        parts = (usuario or "").split("::")
        # padrão que você usa: user_id::mary::timeline
        if len(parts) >= 3 and parts[-2] == "mary":
            return parts[-1].strip() or None
    except Exception:
        pass
    return None


def _default_for_timeline(timeline: Optional[str]) -> bool:
    """
    Política de segurança:
    - universitária => False
    - outras => True
    - desconhecido => False
    """
    tl = (timeline or "").strip().lower()
    if not tl:
        return False
    if tl == "universitaria":
        return False
    return True


def nsfw_enabled(
    usuario: str,
    nsfw_override: Optional[bool] = None,
    timeline: Optional[str] = None,
    local_atual: Optional[str] = None,  # compat
) -> bool:
    """
    Gate NSFW UNIFICADO E ROBUSTO - única fonte de verdade.

    Precedência:
    1) nsfw_override (parâmetro explícito)
    2) streamlit session_state["mary_nsfw_on"] (se existir) -> sincroniza com facts SOMENTE se mudou
    3) facts["mary.nsfw"] (persistente)
    4) facts["nsfw_override"] (legado: "on"/"off"/true/false)
    5) default por timeline (universitaria=False; outros=True; desconhecido=False)
    """
    # 1) override explícito
    if isinstance(nsfw_override, bool):
        return nsfw_override

    # timeline inferida se não vier
    if not timeline:
        timeline = _infer_timeline_from_user_key(usuario)

    # facts (uma leitura)
    facts: Dict[str, Any] = get_facts(usuario) or {}

    # 2) session_state (se existir)
    try:
        import streamlit as st  # import local pra não quebrar fora do Streamlit

        if "mary_nsfw_on" in st.session_state:
            vss = _to_bool(st.session_state.get("mary_nsfw_on"))
            if isinstance(vss, bool):
                # sincroniza só se necessário
                current = _to_bool(facts.get("mary.nsfw"))
                if current is None or current != vss:
                    _sync_nsfw_to_facts(usuario, vss)
                return vss
    except Exception:
        # sem streamlit / sem session_state => segue
        pass

    # 3) facts modernos
    v = _to_bool(facts.get("mary.nsfw"))
    if isinstance(v, bool):
        return v

    # 4) legado: nsfw_override em facts (aceita "on/off" e variações)
    legacy = facts.get("nsfw_override")
    if isinstance(legacy, str):
        leg = legacy.strip().lower()
        if leg == "on":
            return True
        if leg == "off":
            return False
        b = _to_bool(leg)
        if isinstance(b, bool):
            return b
    else:
        b = _to_bool(legacy)
        if isinstance(b, bool):
            return b

    # 5) default seguro por timeline
    return _default_for_timeline(timeline)


def _sync_nsfw_to_facts(usuario: str, value: bool) -> None:
    """Persistência silenciosa."""
    try:
        set_fact(usuario, "mary.nsfw", bool(value), {"fonte": "nsfw_sync"})
    except Exception:
        pass
