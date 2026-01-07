from __future__ import annotations

from typing import Optional

from .service_core import MaryService as _MaryServiceCore


class MaryServiceUniversitaria(_MaryServiceCore):
    """
    Wrapper: timeline fixa = 'universitaria'
    - Ignora qualquer timeline passada pelo caller.
    - Se nsfw vier None, aplica default seguro (False).
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
            nsfw = False

        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline="universitaria",
            nsfw=nsfw,
        )
