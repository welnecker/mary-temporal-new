from __future__ import annotations

from typing import Optional

from .service_core import MaryService as _MaryServiceCore


class MaryServiceCumplice(_MaryServiceCore):
    """
    Wrapper: timeline fixa = 'cumplice'
    - Ignora qualquer timeline passada pelo caller.
    - Se nsfw vier None, aplica default (True), mas o mary_app pode sobrescrever.
    """

    def reply(
        self,
        user: str,
        model: str,
        *,
        prompt: Optional[str] = None,
        timeline: Optional[str] = None,  # ignorado
        nsfw: Optional[bool] = None,
    ) -> str:
        if nsfw is None:
            nsfw = True

        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline="cumplice",
            nsfw=nsfw,
        )
