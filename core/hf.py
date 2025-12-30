from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

HF_BASE_URL = "https://router.huggingface.co/v1"

DEFAULT_MODELS = [
    "zai-org/GLM-4.7-FP8:zai-org",
]

def _client() -> OpenAI:
    token = os.getenv("HUGGINGFACE_API_KEY")
    if not token:
        raise RuntimeError("HUGGINGFACE_API_KEY não configurado no Secrets do Streamlit Cloud.")
    return OpenAI(base_url=HF_BASE_URL, api_key=token)

def chat(model: str, messages: List[Dict[str, str]], **kwargs: Any) -> str:
    c = _client()

    req: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": kwargs.get("max_tokens", 1024),
        "temperature": kwargs.get("temperature", 0.7),
        "top_p": kwargs.get("top_p", 0.95),
    }

    extra: Optional[Dict[str, Any]] = kwargs.get("extra")
    if extra and isinstance(extra, dict):
        req.update(extra)

    try:
        resp = c.chat.completions.create(**req)
        return resp.choices[0].message.content or ""
    except Exception as e:
        raise RuntimeError(f"HF chat error: {e}") from e
