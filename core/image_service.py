from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

import requests
import streamlit as st

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_MODEL = "openai/gpt-5-image-mini"


def _get_openrouter_api_key() -> str:
    api_key = (
        st.secrets.get("OPENROUTER_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPENROUTER_TOKEN")
    )
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY/OPENROUTER_TOKEN não configurada.")
    return api_key


def generate_image(
    *,
    prompt: str,
    negative_prompt: str = "",
    aspect_ratio: str = "3:4",
    image_size: str = "1K",
    seed: Optional[int] = None,
    reference_images: Optional[List[str]] = None,
    timeout: int = 240,
) -> Dict[str, Any]:
    api_key = _get_openrouter_api_key()

    content: List[Dict[str, Any]] = [
        {"type": "text", "text": prompt.strip()}
    ]

    for url in (reference_images or []):
        u = str(url or "").strip()
        if not u:
            continue
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": u},
            }
        )

    messages: List[Dict[str, Any]] = [
        {
            "role": "user",
            "content": content,
        }
    ]

    if negative_prompt.strip():
        messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    "Avoid these visual elements in the final image: "
                    f"{negative_prompt.strip()}"
                ),
            },
        )

    payload: Dict[str, Any] = {
        "model": IMAGE_MODEL,
        "messages": messages,
        "modalities": ["image", "text"],
        "image_config": {
            "aspect_ratio": aspect_ratio,
            "image_size": image_size,
        },
    }

    if seed is not None:
        payload["seed"] = int(seed)

    resp = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise RuntimeError(f"Falha ao gerar imagem ({resp.status_code}): {detail}")

    data = resp.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Resposta sem choices: {data}")

    msg = choices[0].get("message") or {}
    images = msg.get("images") or []
    if not images:
        raise RuntimeError(f"Resposta sem images: {data}")

    return {
        "model": IMAGE_MODEL,
        "text": msg.get("content", ""),
        "images": images,
        "raw": data,
    }


def image_data_url_to_bytes(data_url: str) -> bytes:
    if not isinstance(data_url, str) or not data_url.startswith("data:image"):
        raise RuntimeError("Formato de imagem inválido no retorno.")
    _, b64 = data_url.split(",", 1)
    return base64.b64decode(b64)
