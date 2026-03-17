from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# Base URL do router OpenAI-compatível da Hugging Face
HF_BASE_URL = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1")


def _get_token() -> str:
    token = (os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "HUGGINGFACE_API_KEY (ou HF_TOKEN) não configurado no Secrets do Streamlit Cloud."
        )
    return token


def _client() -> OpenAI:
    """
    Client OpenAI compatível apontando para o HF Router.
    """
    token = _get_token()
    return OpenAI(
        base_url=HF_BASE_URL,
        api_key=token,
    )


def _extract_text_from_openai_resp(resp: Any) -> str:
    """
    Extrai texto do objeto retornado por client.chat.completions.create.
    Mantém robustez para respostas com content ausente ou em formato inesperado.
    """
    try:
        choices = getattr(resp, "choices", None) or []
        if not choices:
            return ""

        c0 = choices[0]
        msg = getattr(c0, "message", None)
        if msg is None:
            return ""

        txt = getattr(msg, "content", None)
        return txt if isinstance(txt, str) else ""
    except Exception:
        return ""


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
    Envia uma requisição de chat/completions ao router da Hugging Face.

    Retorna:
        (data, used_model, "huggingface")

    Onde `data` imita uma resposta estilo OpenAI:
        {
            "model": "...",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "..."
                    }
                }
            ]
        }
    """
    if not isinstance(model, str) or not model.strip():
        raise RuntimeError("hf.chat: model inválido/vazio.")

    if not isinstance(messages, list) or not messages:
        raise RuntimeError("hf.chat: messages inválido/vazio.")

    c = _client()

    req: Dict[str, Any] = {
        "model": model.strip(),
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "top_p": float(top_p),
    }

    # Extra payload (ex.: response_format, stop, presence_penalty, frequency_penalty etc.)
    if isinstance(extra, dict) and extra:
        req.update(extra)

    try:
        resp = c.chat.completions.create(**req)

        txt = _extract_text_from_openai_resp(resp)

        try:
            used = str(getattr(resp, "model", "") or "").strip()
        except Exception:
            used = ""

        used_model = used or model.strip()

        data: Dict[str, Any] = {
            "model": used_model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": txt,
                    }
                }
            ],
        }

        return data, used_model, "huggingface"

    except Exception as e:
        raise RuntimeError(f"HF chat error: {type(e).__name__}: {e}") from e
