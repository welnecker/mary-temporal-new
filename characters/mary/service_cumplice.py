from __future__ import annotations

from typing import Optional, Any
from .service_core import MaryService


class MaryServiceCumplice(MaryService):
    """
    Service da timeline 'cumplice'.
    Mantém assinatura compatível com mary_app.py (_call_service_reply_safe)
    e com service.py (import MaryServiceCumplice).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.timeline = "cumplice"
        except Exception:
            pass

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
        timeline_final = (timeline or "cumplice").strip().lower()
        if timeline_final != "cumplice":
            timeline_final = "cumplice"

        raise RuntimeError("TESTE_CUMPLICE_REPLY")
        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline=timeline_final,
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
        )
