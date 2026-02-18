# characters/mary/service_cumplice.py

from __future__ import annotations

from typing import Optional

from .service_core import MaryService


class MaryCumpliceService(MaryService):
    """
    Wrapper da timeline 'cumplice'.
    Mantém assinatura compatível com mary_app.py e com MaryService.reply.
    """

    id = "mary_cumplice"
    display_name = "Mary (Cúmplice)"

    def reply(
        self,
        user: str,
        model: str,
        *,
        prompt: Optional[str] = None,
        timeline: Optional[str] = None,
        nsfw: Optional[bool] = None,
        allow_third_party_seduction: Optional[bool] = None,
    ) -> str:
        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline="cumplice",
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
        )
