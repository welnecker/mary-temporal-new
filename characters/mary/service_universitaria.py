# characters/mary/service_universitaria.py

from __future__ import annotations

from typing import Optional

from .service_core import MaryService


class MaryUniversitariaService(MaryService):
    """
    Wrapper da timeline 'universitaria'.
    O ERRO do 'prompt' acontece quando este service não herda de MaryService
    e acaba chamando BaseCharacter.reply via super().
    """

    id = "mary_universitaria"
    display_name = "Mary (Universitária)"

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
        # força timeline correta, mas não quebra chamadas existentes
        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline="universitaria",
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
        )
