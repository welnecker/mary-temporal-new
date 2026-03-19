from __future__ import annotations

import os
from typing import Optional

import streamlit as st
from openai import OpenAI


REFINER_MODEL = "gpt-4.1-mini"


def _get_openai_api_key() -> str:
    api_key = (
        st.secrets.get("OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    api_key = str(api_key).strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada.")
    return api_key


def refine_visual_prompt(
    *,
    base_prompt: str,
    scene_summary: str = "",
    emotion: str = "",
    extra: str = "",
    style_hint: str = "adult comic book style, expressive American graphic novel style",
    model: Optional[str] = None,
) -> str:
    """
    Refina um prompt visual já existente, preservando a identidade da Mary
    e o estilo HQ adulto americano.
    Retorna APENAS o prompt final refinado.
    """
    prompt_in = str(base_prompt or "").strip()
    if not prompt_in:
        raise RuntimeError("base_prompt vazio para refinamento.")

    api_key = _get_openai_api_key()
    client = OpenAI(api_key=api_key)

    system_msg = (
        "You are a specialist in rewriting image generation prompts.\n"
        "Your job is to transform rough prompts into strong cinematic prompts.\n"
        "Return ONLY the final refined prompt.\n"
        "Do not explain.\n"
        "Do not use markdown.\n"
        "Do not add labels like 'Prompt:' or bullet points.\n"
        "Preserve the character identity, visual consistency, and art style.\n"
        "Target style: adult comic book, expressive American graphic novel, cinematic, detailed.\n"
    )

    user_msg = f"""
Refine this image prompt for a visual generation model.

Requirements:
- Keep the same character identity.
- Strengthen cinematic composition, lighting, framing, pose, and atmosphere.
- Keep it visually clear and direct.
- Maintain grounded realism within stylized American adult comic aesthetics.
- Preserve the emotional tone.
- Avoid repetition and weak generic phrasing.
- Keep the output as one polished prompt block.

Style hint:
{style_hint}

Scene summary:
{scene_summary}

Emotion:
{emotion}

Extra notes:
{extra}

Base prompt:
{prompt_in}
""".strip()

    response = client.chat.completions.create(
        model=model or REFINER_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=700,
    )

    txt = response.choices[0].message.content or ""
    txt = str(txt).strip()

    if not txt:
        raise RuntimeError("A IA não retornou prompt refinado.")

    return txt
