from __future__ import annotations

from typing import List, Dict, Tuple, Optional, Callable

from .persona_core import _norm_timeline

# cache simples de resolvers (evita import repetido em reruns)
_PERSONA_RESOLVER: dict[str, Callable[[str], Tuple[str, List[Dict[str, str]]]]] = {}


def _resolver_for(tl: str) -> Callable[[str], Tuple[str, List[Dict[str, str]]]]:
    if tl in _PERSONA_RESOLVER:
        return _PERSONA_RESOLVER[tl]

    if tl == "universitaria":
        from .persona_universitaria import get_persona as _get
    else:
        from .persona_cumplice import get_persona as _get

    _PERSONA_RESOLVER[tl] = _get
    return _get


# Mantém compatibilidade com imports antigos:
# - import characters.mary.persona as mary_persona
# - mary_persona.get_persona(timeline)
def get_persona(timeline: Optional[str] = None) -> Tuple[str, List[Dict[str, str]]]:
    tl = _norm_timeline(timeline)
    return _resolver_for(tl)(tl)
