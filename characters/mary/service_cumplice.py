# characters/mary/service_cumplice.py

from __future__ import annotations

from typing import Optional

from .service_core import MaryService


class MaryServiceCumplice(_MaryServiceCore):
    """
    Service da timeline 'cumplice'.
    Mantém assinatura compatível com mary_app.py (_call_service_reply_safe)
    e com service.py (import MaryServiceCumplice).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # garante timeline padrão
        self.timeline = "cumplice"

    def reply(
        self,
        *,
        user: str,
        model: str,
        prompt: str,
        timeline: str = "cumplice",
        nsfw=None,
        allow_third_party_seduction=None,
        **kwargs,
    ):
        # força timeline correta se vier vazia
        timeline = (timeline or "cumplice").strip().lower()
        if timeline != "cumplice":
            timeline = "cumplice"

        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline=timeline,
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
        )
