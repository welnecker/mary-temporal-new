from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# Base URL do router OpenAI‑compatível da Hugging Face
HF_BASE_URL = "https://router.huggingface.co/v1"

# Modelos sugeridos para o provedor Hugging Face.
# GLM‑4.7 exige o sufixo ':cerebras' para o roteador aceitar o modelo:contentReference[oaicite:1]{index=1}.
DEFAULT_MODELS: List[str] = [
    "zai-org/GLM-4.7:cerebras",
]

def _client() -> OpenAI:
    token = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HUGGINGFACE_API_KEY (ou HF_TOKEN) não configurado no Secrets do Streamlit Cloud.")
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
    """
    Envia uma requisição de chat/completion ao router da Hugging Face.

    Retorna uma tupla (data, used_model, provider), em que `data`
    imita o formato de resposta da OpenAI.
    """
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
        data = {
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
        }
        return data, model, "huggingface"
    except Exception as e:
        # Normaliza qualquer erro para o formato esperado pelo roteador
        raise RuntimeError(f"HF chat error: {e}") from e
