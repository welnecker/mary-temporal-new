from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple, Optional

import httpx

# ============================================================
# Config
# ============================================================
LMSTUDIO_BASE_URL = os.getenv(
    "LMSTUDIO_BASE_URL",
    "http://127.0.0.1:1234/v1/chat/completions",
)

DEFAULT_TIMEOUT = float(os.getenv("LLM_HTTP_TIMEOUT", "180"))

# Modelos exibidos na UI
# Você pode sobrescrever isso no futuro via env ou models.py
DEFAULT_MODELS: List[str] = [
    "lmstudio/local-model",
]


def _headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
    }


def _strip_lmstudio_prefix(model: str) -> str:
    m = (model or "").strip()
    if m.lower().startswith("lmstudio/"):
        return m.split("/", 1)[1].strip()
    return m


def _normalize_used_model_for_ui(used: str) -> str:
    u = (used or "").strip()
    if not u:
        return ""
    if u.lower().startswith("lmstudio/"):
        return u
    return f"lmstudio/{u}"


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


def _extract_error_payload(r: httpx.Response) -> str:
    try:
        j = r.json()
    except Exception:
        return r.text[:2000]

    err = j.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("error") or err.get("type") or str(err)
        return str(msg)
    if isinstance(err, str):
        return err
    if isinstance(j.get("message"), str):
        return j["message"]
    return str(j)[:2000]


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
    Wrapper para LM Studio OpenAI-compatible API.
    Retorna (json, used_model, "lmstudio").
    """

    model_to_send = _strip_lmstudio_prefix(model)
    safe_messages = _sanitize_messages(messages)

    if not model_to_send:
        raise RuntimeError("LM Studio: model vazio")

    if not safe_messages:
        raise RuntimeError("LM Studio: messages vazio")

    body: Dict[str, Any] = {
        "model": model_to_send,
        "messages": safe_messages,
        "max_tokens": max(32, int(max_tokens)),
        "temperature": float(temperature),
        "top_p": float(top_p),
        "stream": False,
    }

    if extra and isinstance(extra, dict):
        body.update(extra)

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            r = client.post(
                LMSTUDIO_BASE_URL,
                json=body,
                headers=_headers(),
            )

            if r.status_code >= 400:
                msg = _extract_error_payload(r)
                raise RuntimeError(f"LM Studio {r.status_code}: {msg}")

            data = r.json()

            if not isinstance(data, dict):
                raise RuntimeError(
                    f"LM Studio retornou tipo inesperado: {type(data).__name__}"
                )

            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise RuntimeError(f"LM Studio sem choices: {data}")

            used_raw = data.get("model") or model_to_send
            used_ui = _normalize_used_model_for_ui(str(used_raw))

            try:
                c0 = choices[0] or {}
                finish_reason = c0.get("finish_reason")
                usage = data.get("usage") or {}
                data["_lm_meta"] = {
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "requested_model": model,
                    "used_model": used_ui,
                    "base_url": LMSTUDIO_BASE_URL,
                }
            except Exception:
                pass

            return data, used_ui, "lmstudio"

    except httpx.TimeoutException as e:
        raise RuntimeError("LM Studio: timeout") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"LM Studio HTTPError: {e}") from e
