from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ============================================================
# Endpoint padrão Together
# ============================================================
TOGETHER_BASE_URL = os.getenv(
    "TOGETHER_BASE_URL",
    "https://api.together.xyz/v1/chat/completions",
)

DEFAULT_TIMEOUT = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))


def _headers() -> Dict[str, str]:
    key = (os.getenv("TOGETHER_API_KEY", "") or "").strip()
    if not key:
        raise RuntimeError("TOGETHER_API_KEY ausente.")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _strip_together_prefix(model: str) -> str:
    m = (model or "").strip()
    if m.lower().startswith("together/"):
        return m.split("/", 1)[1].strip()
    return m


def _normalize_used_model_for_ui(used: str) -> str:
    u = (used or "").strip()
    if not u:
        return ""
    if u.lower().startswith("together/"):
        return u
    return f"together/{u}"


def _sanitize_messages(messages: Any) -> List[Dict[str, str]]:
    safe: List[Dict[str, str]] = []
    allowed_roles = {"system", "user", "assistant"}

    if not isinstance(messages, list):
        return safe

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        role = str(msg.get("role") or "").strip().lower()
        content = msg.get("content")

        if role not in allowed_roles:
            continue

        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = str(content)

        safe.append(
            {
                "role": role,
                "content": content,
            }
        )

    return safe


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
    Wrapper para Together chat/completions.
    Retorna (json, used_model, "together").
    """
    model = (model or "").strip()
    if not model:
        raise RuntimeError("Together: model vazio")

    safe_messages = _sanitize_messages(messages)
    if not safe_messages:
        raise RuntimeError("Together: messages inválido/vazio")

    model_to_send = _strip_together_prefix(model)

    body: Dict[str, Any] = {
        "model": model_to_send,
        "messages": safe_messages,
        "max_tokens": min(int(max_tokens), 2600),
        "temperature": float(temperature),
        "top_p": float(top_p),
        "presence_penalty": 0.3,
        "frequency_penalty": 0.2,
        "repetition_penalty": 1.08,
        "stop": ["</s>"],
    }

    if isinstance(extra, dict) and extra:
        body.update(extra)

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            r = client.post(
                TOGETHER_BASE_URL,
                json=body,
                headers=_headers(),
            )

            if r.status_code >= 400:
                try:
                    err = r.json()
                except Exception:
                    err = {"text": r.text[:2000]}

                raise RuntimeError(f"Together HTTP {r.status_code}: {err}")

            data = r.json()

            if not isinstance(data, dict):
                raise RuntimeError(
                    f"Together retornou tipo inesperado: {type(data).__name__}"
                )

            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise RuntimeError(f"Together sem choices: {data}")

            used_raw = data.get("model") or model_to_send
            used_ui = _normalize_used_model_for_ui(str(used_raw))

            return data, used_ui, "together"

    except httpx.TimeoutException as e:
        raise RuntimeError("Together: timeout") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"Together HTTPError: {e}") from e
