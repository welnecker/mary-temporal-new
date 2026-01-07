#service_universitaria.py
from __future__ import annotations

from typing import Optional

from .service_core import MaryService as _MaryServiceCore


class MaryServiceUniversitaria(_MaryServiceCore):
    """
    Wrapper: força timeline = 'universitaria'
    """

    def reply(
        self,
        user: str,
        model: str,
        *,
        prompt: Optional[str] = None,
        timeline: Optional[str] = None,
        nsfw: Optional[bool] = None,
    ) -> str:
        # força timeline
        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline="universitaria",
            nsfw=nsfw,
        )

