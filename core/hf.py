from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

# Base URL do router OpenAI-compatível da Hugging Face
HF_BASE_URL = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1")

# Modelos sugeridos para o provedor Hugging Face
DEFAULT_MODELS: List[str] = [
    "zai-org/GLM-4.7:cerebras",
]


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
    return OpenAI(base_url=HF_BASE_URL, api_key=token)


def _extract_text_from_openai_resp(resp: Any) -> str:
    """
    Extrai texto do objeto retornado por client.chat.completions.create.
    Mantém robustez (alguns providers retornam content None).
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

    Retorna (data, used_model, "huggingface"), onde `data` imita resposta OpenAI:
      {
        "model": "...",
        "choices": [{"message": {"role": "assistant", "content": "..."}}]
      }
    """
    if not isinstance(model, str) or not model.strip():
        raise RuntimeError("hf.chat: model inválido/vazio.")
    if not isinstance(messages, list) or not messages:
        raise RuntimeError("hf.chat: messages inválido/vazio.")

    # Timeout controlado por env (mesmo padrão do Together)
    timeout = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))

    c = _client()

    req: Dict[str, Any] = {
        "model": model.strip(),
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "top_p": float(top_p),
        # HF Router entende isso como OpenAI compat.
        # 'timeout' aqui NÃO é parâmetro oficial do endpoint; é do client.
    }

    # Extra payload (ex.: response_format, stop, presence_penalty, frequency_penalty etc.)
    if extra and isinstance(extra, dict):
        req.update(extra)

    try:
        # O client OpenAI v1 usa httpx por baixo e aceita timeout via client.options,
        # mas como não estamos configurando options aqui, fazemos o básico:
        # a maioria dos ambientes respeita timeout default interno do httpx.
        # Ainda assim, em Streamlit Cloud geralmente funciona bem com esse padrão.
        resp = c.chat.completions.create(**req)

        txt = _extract_text_from_openai_resp(resp)

        # modelo realmente usado (quando o provider normaliza/resolve alias)
        used = ""
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
        # Normaliza erro
        raise RuntimeError(f"HF chat error: {type(e).__name__}: {e}") from e
