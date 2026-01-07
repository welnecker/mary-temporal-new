from __future__ import annotations

from typing import List, Dict, Tuple, Optional

from .persona_core import _norm_timeline


# Mantém compatibilidade com imports antigos:
# - import characters.mary.persona as mary_persona
# - mary_persona.get_persona(timeline)
def get_persona(timeline: Optional[str] = None) -> Tuple[str, List[Dict[str, str]]]:
    tl = _norm_timeline(timeline)

    if tl == "universitaria":
        from .persona_universitaria import get_persona as _get
        return _get(tl)

    from .persona_cumplice import get_persona as _get
    return _get(tl)
