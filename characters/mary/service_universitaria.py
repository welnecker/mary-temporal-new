from __future__ import annotations

from typing import Optional, Any
from .service_core import MaryService


class MaryServiceUniversitaria(MaryService):
    """
    Service da timeline 'universitaria'.
    Mantém assinatura compatível com mary_app.py (_call_service_reply_safe)
    e com service.py (import MaryServiceUniversitaria).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # timeline default
        try:
            self.timeline = "universitaria"
        except Exception:
            pass

    def reply(
        self,
        *,
        user: str,
        model: str,
        prompt: str,
        timeline: str = "universitaria",
        nsfw: Optional[bool] = None,
        allow_third_party_seduction: Optional[bool] = None,
        **kwargs: Any,
    ):
        # força timeline correta
        timeline_final = (timeline or "universitaria").strip().lower()
        if timeline_final != "universitaria":
            timeline_final = "universitaria"

        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline=timeline_final,
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
        )
