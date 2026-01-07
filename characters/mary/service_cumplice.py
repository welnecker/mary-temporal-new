#service_cumplice.py
from __future__ import annotations

from typing import Optional

from .service_core import MaryService as _MaryServiceCore


class MaryServiceCumplice(_MaryServiceCore):
    """
    Wrapper: força timeline = 'cumplice'
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
            timeline="cumplice",
            nsfw=nsfw,
        )

