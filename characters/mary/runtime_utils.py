from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List

try:
    import streamlit as st  # type: ignore
    _HAS_ST = True
except Exception:
    st = None  # type: ignore
    _HAS_ST = False

from .persona_core import _norm_timeline

_SS_PREFIX = "mary::"


def ss_get(key: str, default: Any = None) -> Any:
    if _HAS_ST and hasattr(st, "session_state"):
        return st.session_state.get(key, default)
    return default


def ss_set(key: str, value: Any) -> None:
    if _HAS_ST and hasattr(st, "session_state"):
        st.session_state[key] = value


def ss_has(key: str) -> bool:
    if _HAS_ST and hasattr(st, "session_state"):
        return key in st.session_state
    return False


def ss_del(key: str) -> None:
    if _HAS_ST and hasattr(st, "session_state"):
        st.session_state.pop(key, None)


def ss_keys() -> List[str]:
    if _HAS_ST and hasattr(st, "session_state"):
        return [k for k in st.session_state.keys() if isinstance(k, str)]
    return []


def t_norm(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_timeline(timeline: str | None) -> str:
    return _norm_timeline(timeline)


def fact_str(facts: Dict[str, Any], dotted_key: str) -> str:
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


def turn_counter_key(usuario_key: str) -> str:
    return f"mary_turn_counter::{usuario_key}"


def bump_turn_counter(usuario_key: str) -> int:
    try:
        cur = int(ss_get(turn_counter_key(usuario_key), 0) or 0)
    except Exception:
        cur = 0
    cur += 1
    ss_set(turn_counter_key(usuario_key), cur)
    return cur
