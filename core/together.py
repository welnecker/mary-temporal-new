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


def _debug_log_payload(model_to_send: str, body: Dict[str, Any]) -> None:
    try:
        print("\n========== TOGETHER DEBUG ==========")
        print("model_to_send:", model_to_send)
        print("endpoint:", TOGETHER_BASE_URL)
        print("body_keys:", list(body.keys()))
        print("max_tokens:", body.get("max_tokens"))
        print("temperature:", body.get("temperature"))
        print("top_p:", body.get("top_p"))

        messages = body.get("messages", [])
        print("messages_count:", len(messages) if isinstance(messages, list) else "N/A")

        if isinstance(messages, list):
            for i, m in enumerate(messages[:5]):
                if not isinstance(m, dict):
                    print(f"[msg {i}] INVALID TYPE: {type(m).__name__}")
                    continue

                role = m.get("role")
                content = m.get("content")
                print(
                    f"[msg {i}] role={role!r} "
                    f"content_type={type(content).__name__} "
                    f"content_len={len(str(content or ''))}"
                )
                print(f"[msg {i}] preview={str(content or '')[:220]!r}")

        print("====================================\n")
    except Exception as e:
        print("TOGETHER DEBUG ERROR:", e)


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
    safe_messages = _sanitize_messages(messages)

    # Payload conservador para diagnóstico:
    # - sem extra
    # - max_tokens reduzido
    body: Dict[str, Any] = {
        "model": model_to_send,
        "messages": safe_messages,
        "max_tokens": min(int(max_tokens), 800),
        "temperature": float(temperature),
        "top_p": float(top_p),
    }

    timeout = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))

    try:
        _debug_log_payload(model_to_send, body)

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

                print("\n========== TOGETHER ERROR BODY ==========")
                print("status_code:", r.status_code)
                print("error_json:", err)
                print("=========================================\n")

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
