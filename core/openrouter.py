from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import httpx

# Lista de modelos “sugeridos” para a UI (pode ampliar à vontade)
DEFAULT_MODELS = [
    "x-ai/grok-4.1-fast",               # Grok como sugestão principal
    "tngtech/tng-r1t-chimera:free",      # Chimera de apoio
    "xiaomi/mimo-v2-flash:free",
    "deepseek/deepseek-chat-v3-0324",
    "anthropic/claude-3.5-haiku",
    "qwen/qwen3-max",
    "nousresearch/hermes-3-llama-3.1-405b",
]

OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)

# Não permitimos sobrescrever isso via "extra" por segurança/consistência
_RESERVED_BODY_KEYS = {"model", "messages"}


def _headers() -> Dict[str, str]:
    token = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_TOKEN") or ""
    if not token:
        raise RuntimeError(
            "OPENROUTER_API_KEY/OPENROUTER_TOKEN ausente. "
            "Defina nas secrets/env para usar OpenRouter."
        )

    # Referer e X-Title ajudam no rate-limit do OpenRouter
    referer = os.getenv("APP_PUBLIC_URL", "") or "https://streamlit.app"
    x_title = os.getenv("APP_NAME", "") or "PERSONAGENS2025"
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "HTTP-Referer": referer,
        "X-Title": x_title,
    }


def _is_xiaomi_mimo(model_id: str) -> bool:
    """
    MiMo (Xiaomi) costuma performar melhor e mais rápido sem reasoning.
    Ex: "xiaomi/mimo-v2-flash:free"
    """
    low = (model_id or "").strip().lower()
    return low.startswith("xiaomi/mimo-v2-flash")


def _merge_extra(body: Dict[str, Any], extra: Dict[str, Any] | None, *, model: str) -> None:
    """
    - Suporta extra direto: {"reasoning": {...}, "stop": [...], ...}
    - Suporta extra_body: {"extra_body": {...}} (estilo OpenAI SDK)
    - Evita sobrescrever keys críticas (model/messages)
    - Aplica default para MiMo: reasoning desativado (effort=none), se o chamador não setar.
    """
    # Default “rápido/fluido” para MiMo: desliga reasoning, a menos que o chamador mande.
    if _is_xiaomi_mimo(model) and "reasoning" not in body:
        body["reasoning"] = {"effort": "none"}

    if not extra:
        return

    # Aceita os dois formatos (muitos callers usam extra={"extra_body": {...}})
    extra_body = extra.get("extra_body")
    payload = extra_body if isinstance(extra_body, dict) else extra

    for k, v in payload.items():
        if k in _RESERVED_BODY_KEYS:
            continue
        body[k] = v


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
    Chamador simples ao endpoint de chat do OpenRouter.
    Retorna (json, used_model, "openrouter").
    Lança RuntimeError com a mensagem detalhada em caso de falha HTTP.
    """
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
    }

    _merge_extra(body, extra, model=model)

    timeout = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(OPENROUTER_BASE_URL, headers=_headers(), json=body)

            # Se a API retornar erro, exponha o corpo para debug
            if r.status_code >= 400:
                try:
                    err = r.json()
                except Exception:
                    err = {"text": r.text}

                # normaliza mensagens típicas do OpenRouter
                msg: Any = None
                if isinstance(err, dict) and isinstance(err.get("error"), dict):
                    msg = err["error"].get("message") or err["error"]
                elif isinstance(err, dict):
                    msg = err.get("message") or err.get("error")
                if not msg:
                    msg = err

                raise RuntimeError(f"OpenRouter {r.status_code}: {msg}")

            data = r.json()
            used = data.get("model") or model
            return data, used, "openrouter"

    except httpx.TimeoutException as e:
        raise RuntimeError("OpenRouter: timeout") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"OpenRouter falhou: {e}") from e
