from __future__ import annotations

from typing import Optional, Any

import streamlit as st
from .service_core import MaryService


class MaryServiceUniversitaria(MaryService):
    """
    Service da timeline 'universitaria'.
    Mantém assinatura compatível com mary_app.py (_call_service_reply_safe)
    e com service.py (import MaryServiceUniversitaria).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.timeline = "universitaria"
        except Exception:
            pass

    def reply(
        self,
        *,
        user: str,
        model: str,
        prompt: Optional[str] = None,   # ✅ NÃO pode ser obrigatório
        timeline: str = "universitaria",
        nsfw: Optional[bool] = None,
        allow_third_party_seduction: Optional[bool] = None,
        **kwargs: Any,
    ):
        # força timeline correta
        timeline_final = (timeline or "universitaria").strip().lower()
        if timeline_final != "universitaria":
            timeline_final = "universitaria"

        # ✅ fallback idêntico ao comportamento do funcional:
        # quando mary_app não manda prompt, usa o chat_input.
        if prompt is None:
            try:
                prompt = (st.session_state.get("chat_input") or "").strip()
            except Exception:
                prompt = ""

        return super().reply(
            user=user,
            model=model,
            prompt=prompt,
            timeline=timeline_final,
            nsfw=nsfw,
            allow_third_party_seduction=allow_third_party_seduction,
        )
