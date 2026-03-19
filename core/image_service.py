# core/image_service.py
from __future__ import annotations

import base64
import requests
import streamlit as st


OPENROUTER_URL = "https://openrouter.ai/api/v1/images/generations"


def generate_image(
    *,
    prompt: str,
    negative_prompt: str = "",
    aspect_ratio: str = "3:4",
    image_size: str = "1K",
) -> dict:
    """
    Geração de imagem via OpenRouter.
    SEM fallback. Se falhar, falha.
    """

    api_key = st.secrets.get("OPENROUTER_API_KEY")

    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada no secrets")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "openai/gpt-5-image-mini",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
        "num_images": 1,
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload)

    if response.status_code != 200:
        raise RuntimeError(f"Erro OpenRouter: {response.text}")

    return response.json()


def image_data_url_to_bytes(data_url: str) -> bytes:
    """
    Converte base64 retornado em bytes pra exibir no Streamlit.
    """
    if not data_url:
        raise ValueError("Imagem vazia")

    if "," in data_url:
        data_url = data_url.split(",", 1)[1]

    return base64.b64decode(data_url)
