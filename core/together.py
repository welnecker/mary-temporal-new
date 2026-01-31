from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import httpx

DEFAULT_MODELS = [
    "together/meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
    "together/Qwen/Qwen2.5-72B-Instruct",
    "together/Qwen/QwQ-32B",
    "together/zai-org/GLM-4.7",
]

TOGETHER_BASE_URL = os.getenv(
    "TOGETHER_BASE_URL",
    "https://api.together.xyz/v1/chat/completions",
)


def _headers() -> Dict[str, str]:
    key = os.getenv("TOGETHER_API_KEY", "")
    if not key:
        raise RuntimeError("TOGETHER_API_KEY ausente.")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def chat(
    model: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    top_p: float = 0.95,
    extra: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], str, str]:
    """
    Wrapper para Together chat/completions.
    Retorna (json, used_model, "together").
    """
    # 👉 se vier "together/..." a gente tira o prefixo;
    # 👉 se vier "deepseek-ai/..." a gente NÃO mexe.
    if model.startswith("together/"):
        model_to_send = model.replace("together/", "", 1)
    else:
        model_to_send = model

    body: Dict[str, Any] = {
        "model": model_to_send,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }
    if extra:
        body.update(extra)

    timeout = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(TOGETHER_BASE_URL, json=body, headers=_headers())
            if r.status_code >= 400:
                try:
                    err = r.json()
                except Exception:
                    err = {"text": r.text}
                raise RuntimeError(
                    f"Together {r.status_code}: {err.get('error') or err.get('message') or err}"
                )
            data = r.json()
            used = data.get("model") or model_to_send
            # normaliza só pra exibir
            if not used.startswith("together/") and not used.startswith("deepseek-ai/"):
                used = f"together/{used}"
            return data, used, "together"
    except httpx.TimeoutException as e:
        raise RuntimeError("Together: timeout") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"Falha Together: {e}") from e
