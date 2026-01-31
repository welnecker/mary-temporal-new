from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

HF_BASE_URL = "https://router.huggingface.co/v1"

DEFAULT_MODELS = [
    "z-ai/glm-4.7",
]

def _client() -> OpenAI:
    token = os.getenv("HUGGINGFACE_API_KEY")
    if not token:
        raise RuntimeError("HUGGINGFACE_API_KEY não configurado no Secrets do Streamlit Cloud.")
    return OpenAI(base_url=HF_BASE_URL, api_key=token)

def chat(
    model: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    top_p: float = 0.95,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str, str]:
    c = _client()

    req: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }
    if extra and isinstance(extra, dict):
        req.update(extra)

    try:
        resp = c.chat.completions.create(**req)
        text = resp.choices[0].message.content or ""

        # Normaliza para o mesmo "shape" do resto do app (choices/message/content)
        data = {
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
        }
        return data, model, "huggingface"

    except Exception as e:
        raise RuntimeError(f"HF chat error: {e}") from e
