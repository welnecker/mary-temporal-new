from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple, Optional

import httpx

# Lista de modelos “sugeridos” para a UI (pode ampliar à vontade)
DEFAULT_MODELS = [
    "x-ai/grok-4.1-fast",              # Grok como sugestão principal
    "tngtech/tng-r1t-chimera:free",     # Chimera de apoio
    "xiaomi/mimo-v2-flash:free",        # Xiaomi MiMo
    "deepseek/deepseek-chat-v3-0324",
    "anthropic/claude-3.5-haiku",
    "qwen/qwen3-max",
    "nousresearch/hermes-3-llama-3.1-405b",
]

OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)

def _headers() -> Dict[str, str]:
    token = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_TOKEN") or ""
    if not token:
        raise RuntimeError(
            "OPENROUTER_API_KEY/OPENROUTER_TOKEN ausente. "
            "Defina nas secrets/env para usar OpenRouter."
        )

    # Referer e X-Title ajudam em rate-limit / identificação no OpenRouter
    referer = os.getenv("APP_PUBLIC_URL", "") or "https://streamlit.app"
    x_title = os.getenv("APP_NAME", "") or "PERSONAGENS2025"

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "HTTP-Referer": referer,
        "X-Title": x_title,
    }

def _extract_content(data: Dict[str, Any]) -> str:
    """
    Tenta extrair o texto do assistant de forma robusta.
    Cobre content como string e content como lista de partes.
    """
    try:
        choices = data.get("choices") or []
        if not choices:
            return ""
        c0 = choices[0] or {}
        msg = c0.get("message") or {}
        content = msg.get("content")

        # Caso padrão (string)
        if isinstance(content, str):
            return content

        # Alguns providers podem devolver lista de partes
        if isinstance(content, list):
            parts: List[str] = []
            for p in content:
                if isinstance(p, str):
                    parts.append(p)
                elif isinstance(p, dict):
                    # padrões comuns: {"type":"text","text":"..."} ou {"text":"..."}
                    t = p.get("text")
                    if isinstance(t, str):
                        parts.append(t)
            return "".join(parts)

        # fallback (providers antigos / compat)
        txt2 = c0.get("text")
        return txt2 if isinstance(txt2, str) else ""
    except Exception:
        return ""

def chat(
    model: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    top_p: float = 0.95,
    stop: Optional[List[str] | str] = None,
    extra: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], str, str, Dict[str, Any]]:
    """
    Chamador simples ao endpoint de chat do OpenRouter.

    Retorna:
      (data_json, used_model, "openrouter", meta)

    meta inclui:
      - finish_reason
      - usage
      - content_len
      - content_preview (primeiros 200 chars)
    """
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }

    # stop opcional (cuidado com </think>!)
    if stop is not None:
        body["stop"] = stop

    # extra pode incluir: reasoning, response_format, etc.
    if extra:
        # OBS: aqui você pode passar {"reasoning": {...}} direto
        body.update(extra)

    timeout = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))

    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(OPENROUTER_BASE_URL, headers=_headers(), json=body)

            if r.status_code >= 400:
                try:
                    err = r.json()
                except Exception:
                    err = {"text": r.text}

                # O OpenRouter costuma retornar {"error": {...}} ou {"message": "..."}
                raise RuntimeError(
                    f"OpenRouter {r.status_code}: {err.get('error') or err.get('message') or err}"
                )

            data = r.json()
            used = data.get("model") or model

            # meta p/ debug de truncamento
            finish_reason = ""
            try:
                finish_reason = (data.get("choices") or [])[0].get("finish_reason") or ""
            except Exception:
                finish_reason = ""

            usage = data.get("usage") or {}
            content = _extract_content(data)
            meta = {
                "finish_reason": finish_reason,
                "usage": usage,
                "content_len": len(content or ""),
                "content_preview": (content or "")[:200],
            }

            return data, used, "openrouter", meta

    except httpx.TimeoutException as e:
        raise RuntimeError("OpenRouter: timeout") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"OpenRouter falhou: {e}") from e
