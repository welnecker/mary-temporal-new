from __future__ import annotations

from typing import Optional, Any
from .service_core import MaryService


class MaryServiceCumplice(MaryService):

def reply(
    self,
    *,
    user: str,
    model: str,
    prompt: Optional[str] = None,
    timeline: str = "cumplice",
    nsfw: Optional[bool] = None,
    allow_third_party_seduction: Optional[bool] = None,
    **kwargs: Any,
):
    # força timeline correta
    timeline_final = (timeline or "cumplice").strip().lower()
    if timeline_final != "cumplice":
        timeline_final = "cumplice"

    return super().reply(
        user=user,
        model=model,
        prompt=prompt,
        timeline=timeline_final,
        nsfw=nsfw,
        allow_third_party_seduction=allow_third_party_seduction,
    )
