from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import httpx

# ============================================================
# Modelos exibidos na UI
# ============================================================
DEFAULT_MODELS = [
    "together/zai-org/GLM-5",
    "together/Qwen/Qwen3.5-397B-A17B",
    "together/Qwen/QwQ-32B",
    "together/zai-org/GLM-4.7",
]

# ============================================================
# Endpoint padrão Together
# ============================================================
TOGETHER_BASE_URL = os.getenv(
    "TOGETHER_BASE_URL",
    "https://api.together.xyz/v1/chat/completions",
)


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
    Retorna (json, used_model, "Together").
    """

    model_to_send = _strip_together_prefix(model)

    body: Dict[str, Any] = {
        "model": model_to_send,
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "top_p": float(top_p),
    }

    if isinstance(extra, dict) and extra:
        body.update(extra)

    timeout = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))

    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                TOGETHER_BASE_URL,
                json=body,
                headers=_headers(),
            )

            # erro explícito
            if r.status_code >= 400:
                try:
                    err = r.json()
                except Exception:
                    err = {"text": r.text}

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

            return data, used_ui, "Together"

    except httpx.TimeoutException as e:
        raise RuntimeError("Together: timeout") from e

    except httpx.HTTPError as e:
        raise RuntimeError(f"Together HTTPError: {e}") from e
