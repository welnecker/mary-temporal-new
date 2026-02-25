from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple, Optional

import httpx

# Lista de modelos “sugeridos” para a UI (pode ampliar à vontade)
DEFAULT_MODELS = [
    "x-ai/grok-4.1-fast",               # Grok como sugestão principal
    "tngtech/deepseek-r1t2-chimera",      # Chimera de apoio
    "xiaomi/mimo-v2-flash",
    "deepseek/deepseek-chat-v3-0324",
    "anthropic/claude-3.5-haiku",
    "qwen/qwen3-max",
    "nousresearch/hermes-3-llama-3.1-405b",
]

OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL",
    "https://openrouter.ai/api/v1/chat/completions",
)

# Timeout HTTP padrão (segundos)
DEFAULT_TIMEOUT = float(os.getenv("LLM_HTTP_TIMEOUT", "60"))

# =========================================
# HEADERS
# =========================================
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

# =========================================
# UTIL: parse de erro do OpenRouter
# =========================================
def _extract_error_payload(r: httpx.Response) -> str:
    try:
        j = r.json()
    except Exception:
        return r.text[:2000]

    # Formatos comuns:
    # {"error": {"message": "...", ...}}
    # {"error": "..."}
    # {"message": "..."}
    err = j.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("error") or err.get("type") or str(err)
        return str(msg)
    if isinstance(err, str):
        return err
    if isinstance(j.get("message"), str):
        return j["message"]
    return str(j)[:2000]

# =========================================
# ✅ NORMALIZAÇÃO: providers que devolvem texto em "reasoning"
# =========================================
def _normalize_reasoning_into_content(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Alguns providers retornam:
      choices[0].message.content = "" (vazio)
      choices[0].message.reasoning = "texto final"
    Isso quebra pipelines que extraem apenas "content".
    Então: se content estiver vazio e reasoning for str não-vazio,
    copiamos reasoning -> content.
    """
    try:
        choices = data.get("choices") or []
        if not isinstance(choices, list) or not choices:
            return data

        c0 = choices[0] or {}
        msg = c0.get("message") or {}
        if not isinstance(msg, dict):
            return data

        content = msg.get("content")
        reasoning = msg.get("reasoning")

        content_is_empty = (not isinstance(content, str)) or (not content.strip())
        if content_is_empty and isinstance(reasoning, str) and reasoning.strip():
            msg["content"] = reasoning
            c0["message"] = msg
            choices[0] = c0
            data["choices"] = choices
    except Exception:
        pass

    return data

# =========================================
# DEFAULTS: Reasoning para modelos específicos
# =========================================
def _default_reasoning_for_model(model: str) -> Optional[Dict[str, Any]]:
    """
    Para o roleplay, é comum querer o texto final "fluido".
    Alguns modelos podem gastar muito em reasoning.
    Aqui aplicamos um default: desligar reasoning para xiaomi/*,
    a não ser que o chamador já tenha passado 'reasoning' manualmente.

    OBS: Mesmo com effort="none", alguns providers ainda preenchem "reasoning".
    Por isso existe _normalize_reasoning_into_content() acima.
    """
    m = (model or "").strip().lower()
    if m.startswith("xiaomi/"):
        # effort none: tenta reduzir custo/latência; mas não depende disso para funcionar
        return {"reasoning": {"effort": "none"}}
    return None

def _merge_body_defaults(model: str, body: Dict[str, Any]) -> Dict[str, Any]:
    # Se o chamador já passou reasoning, respeite.
    if "reasoning" in body or "include_reasoning" in body:
        return body

    defaults = _default_reasoning_for_model(model)
    if defaults:
        for k, v in defaults.items():
            if k not in body:
                body[k] = v
    return body

# =========================================
# SERVICE
# =========================================
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

    - Mantém compatibilidade com seu service_router/MaryService (3-tuple).
    - Injeta data["_or_meta"] com finish_reason/usage para debug (opcional).
    """
    if not model or not str(model).strip():
        raise RuntimeError("OpenRouter: model vazio")

    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "top_p": float(top_p),
    }

    # extra: campos adicionais no ROOT (ex: reasoning, tools, response_format, etc.)
    if extra:
        body.update(extra)

    # aplica defaults por modelo (ex: xiaomi -> reasoning off)
    body = _merge_body_defaults(model, body)

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            r = client.post(OPENROUTER_BASE_URL, headers=_headers(), json=body)

            if r.status_code >= 400:
                msg = _extract_error_payload(r)
                raise RuntimeError(f"OpenRouter {r.status_code}: {msg}")

            data = r.json()

            # ✅ CORREÇÃO PRINCIPAL: se veio texto em reasoning, move pra content
            data = _normalize_reasoning_into_content(data)

            used = data.get("model") or model

            # meta para debug (não quebra seu fluxo atual)
            try:
                c0 = (data.get("choices") or [])[0] or {}
                finish_reason = c0.get("finish_reason")
                usage = data.get("usage") or {}
                data["_or_meta"] = {
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "requested_model": model,
                    "used_model": used,
                }
            except Exception:
                pass

            return data, used, "openrouter"

    except httpx.TimeoutException as e:
        raise RuntimeError("OpenRouter: timeout") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"OpenRouter falhou: {e}") from e
