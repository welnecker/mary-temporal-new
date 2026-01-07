from __future__ import annotations

from typing import Optional, Type

from core.common.base_service import BaseCharacter
from .persona_core import _norm_timeline
from .service_cumplice import MaryServiceCumplice
from .service_universitaria import MaryServiceUniversitaria


def get_service_class(timeline: Optional[str]) -> Type[BaseCharacter]:
    tl = _norm_timeline(timeline)
    if tl == "universitaria":
        return MaryServiceUniversitaria
    return MaryServiceCumplice


# compat (default = cúmplice)
MaryService = MaryServiceCumplice
