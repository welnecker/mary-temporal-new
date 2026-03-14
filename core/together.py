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
# Endpoint
# ============================================================
TOGETHER_BASE_URL = os.getenv(
    "TOGETHER_BASE_URL",
    "https://api.together.xyz/v1/chat/completions",
)


# ============================================================
# Helpers
# ============================================================
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


def _sanitize_messages(messages: Any) -> List[Dict[str, Any]]:
    """
    Aceita:
    - content string
    - content list[blocks] com type=text / image_url
    - content None -> ""
    - outros tipos -> str(content)
    """
    out: List[Dict[str, Any]] = []

    if not isinstance(messages, list):
        return out

    for m in messages:
        if not isinstance(m, dict):
            continue

        role = str(m.get("role") or "").strip()
        content = m.get("content")

        if not role:
            continue

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            safe_blocks: List[Dict[str, Any]] = []

            for block in content:
                if not isinstance(block, dict):
                    continue

                btype = str(block.get("type") or "").strip()

                if btype == "text" and isinstance(block.get("text"), str):
                    safe_blocks.append({"type": "text", "text": block["text"]})
                    continue

                if btype == "image_url" and isinstance(block.get("image_url"), dict):
                    url = block["image_url"].get("url")
                    if isinstance(url, str) and url.strip():
                        safe_blocks.append(
                            {"type": "image_url", "image_url": {"url": url.strip()}}
                        )
                    continue

            out.append({"role": role, "content": safe_blocks})
            continue

        if content is None:
            out.append({"role": role, "content": ""})
            continue

        out.append({"role": role, "content": str(content)})

    return out


def _sanitize_extra(extra: Any) -> Dict[str, Any]:
    """
    Só deixa passar campos geralmente aceitos pela Together em chat/completions.
    """
    if not isinstance(extra, dict):
        return {}

    allowed = {
        "stop",
        "stream",
        "presence_penalty",
        "frequency_penalty",
        "response_format",
        "tools",
        "tool_choice",
        "logprobs",
        "top_logprobs",
        "n",
        "seed",
        "safe_model",
    }

    clean: Dict[str, Any] = {}
    for k, v in extra.items():
        if k in allowed and v is not None:
            clean[k] = v

    return clean


def _debug_payload_preview(body: Dict[str, Any]) -> Dict[str, Any]:
    msgs = body.get("messages", [])
    return {
        "model": body.get("model"),
        "max_tokens": body.get("max_tokens"),
        "temperature": body.get("temperature"),
        "top_p": body.get("top_p"),
        "extra_keys": sorted(
            [
                k for k in body.keys()
                if k not in {"model", "messages", "max_tokens", "temperature", "top_p"}
            ]
        ),
        "messages_preview": [
            {
                "role": m.get("role"),
                "content_type": type(m.get("content")).__name__,
                "content_preview": (
                    m.get("content")[:300]
                    if isinstance(m.get("content"), str)
                    else str(m.get("content"))[:300]
                ),
            }
            for m in msgs[:3]
            if isinstance(m, dict)
        ],
    }


# ============================================================
# Main
# ============================================================
def chat(
    model: str,
    messages: List[Dict[str, Any]],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    top_p: float = 0.95,
    extra: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], str, str]:
    """
    Wrapper para Together chat/completions.
    Retorna:
        (json, used_model_ui, "Together")
    """

    model_to_send = _strip_together_prefix(model)
    safe_messages = _sanitize_messages(messages)
    safe_extra = _sanitize_extra(extra)

    body: Dict[str, Any] = {
        "model": model_to_send,
        "messages": safe_messages,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "top_p": float(top_p),
    }

    if safe_extra:
        body.update(safe_extra)

    timeout = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))

    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                TOGETHER_BASE_URL,
                json=body,
                headers=_headers(),
            )

            if r.status_code >= 400:
                try:
                    err = r.json()
                except Exception:
                    err = {"text": r.text}

                preview = _debug_payload_preview(body)
                raise RuntimeError(
                    f"Together HTTP {r.status_code}: {err} | payload={preview}"
                )

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
