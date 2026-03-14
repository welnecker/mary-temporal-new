from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

# core/service_router.py
_IMPORT_ERRORS: Dict[str, str] = {}

# ============================================================
# Imports SAFE (não deixar a UI cair por exceção)
# ============================================================

# OpenRouter (obrigatório no teu app)
try:
    from .openrouter import chat as openrouter_chat, DEFAULT_MODELS as OR_MODELS
except Exception as e:
    OR_MODELS = []
    _IMPORT_ERRORS["openrouter"] = f"{type(e).__name__}: {e}"

    def openrouter_chat(*args: Any, **kwargs: Any):
        raise RuntimeError(f"OpenRouter indisponível: {type(e).__name__}: {e}")


# Together (opcional)
try:
    from .together import chat as together_chat, DEFAULT_MODELS as TG_MODELS
except Exception as e:
    TG_MODELS = []
    together_chat = None  # type: ignore
    _IMPORT_ERRORS["together"] = f"{type(e).__name__}: {e}"


# HuggingFace Router (opcional)
try:
    from .hf import chat as hf_chat, DEFAULT_MODELS as HF_MODELS
except Exception as e:
    HF_MODELS = []
    hf_chat = None  # type: ignore
    _IMPORT_ERRORS["hf"] = f"{type(e).__name__}: {e}"


# ============================================================
# Config
# ============================================================

SAFE_FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324"
MODEL_ALIASES: Dict[str, str] = {}

# ============================================================
# Modelos fixos (OpenRouter) — sempre no menu
# ============================================================
PINNED_OPENROUTER_MODELS: List[str] = [
    "arcee-ai/trinity-large-preview:free",
    "minimax/minimax-m2.5",
    "tngtech/deepseek-r1t2-chimera",
]


# ============================================================
# Utils
# ============================================================

def _normalize_reasoning_into_content(resp: Any) -> Any:
    # tuple: (data, used_model, provider)
    if isinstance(resp, tuple) and len(resp) >= 1:
        data = _normalize_reasoning_into_content(resp[0])
        if len(resp) == 3:
            return (data, resp[1], resp[2])
        if len(resp) == 2:
            return (data, resp[1])
        return (data,)

    if not isinstance(resp, dict):
        return resp

    try:
        choices = resp.get("choices") or []
        if not isinstance(choices, list) or not choices:
            return resp

        c0 = choices[0] or {}
        msg = c0.get("message") or {}
        if not isinstance(msg, dict):
            return resp

        content = msg.get("content")
        reasoning = msg.get("reasoning")

        if (not isinstance(content, str) or not content.strip()) and isinstance(reasoning, str) and reasoning.strip():
            msg["content"] = reasoning
            c0["message"] = msg
            choices[0] = c0
            resp["choices"] = choices

        return resp
    except Exception:
        return resp


def _env_has_any(*keys: str) -> bool:
    return any(bool(os.getenv(k)) for k in keys)


def import_errors() -> Dict[str, str]:
    return dict(_IMPORT_ERRORS)


def _raise_if_provider_error(resp: Any, provider: str) -> None:
    # tuple: (data, used_model, provider)
    data = resp[0] if isinstance(resp, tuple) and resp else resp

    if not isinstance(data, dict):
        return

    if "error" in data and data["error"]:
        raise RuntimeError(f"{provider} error: {data['error']}")
    if "errors" in data and data["errors"]:
        raise RuntimeError(f"{provider} errors: {data['errors']}")

    # alguns providers jogam msg em "message"
    if data.get("message") and isinstance(data.get("message"), str) and ("error" in data.get("message", "").lower()):
        raise RuntimeError(f"{provider} message: {data['message']}")


def _strip_prefix(s: str, prefix: str) -> str:
    s = (s or "").strip()
    p = (prefix or "").strip()
    if s.lower().startswith(p.lower()):
        return s[len(p):].lstrip()
    return s


def _model_for_provider(model: str, provider: str) -> str:
    """
    Ajusta o ID do modelo para o provider específico.
    - Together: aceita "together/xxx" na UI, mas envia "xxx"
    - HuggingFace: se você usar "hf/" ou "huggingface/" na UI, remove.
    """
    m = (model or "").strip()
    if provider == "Together":
        return _strip_prefix(m, "together/")
    if provider == "HuggingFace":
        m = _strip_prefix(m, "hf/")
        m = _strip_prefix(m, "huggingface/")
        return m
    return m


def _sanitize_messages_for_provider(messages: Any) -> List[Dict[str, Any]]:
    """
    Normaliza mensagens para reduzir erros de validação em providers.
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
    Passa apenas campos geralmente aceitos em APIs compatíveis com chat completions.
    Evita contaminar providers com lixo de router interno.
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


# -------------------------
# Providers disponíveis
# -------------------------
def available_providers() -> List[Tuple[str, bool, str]]:
    have_or = _env_has_any("OPENROUTER_API_KEY", "OPENROUTER_TOKEN")
    have_tg = _env_has_any("TOGETHER_API_KEY")
    have_hf = _env_has_any("HUGGINGFACE_API_KEY", "HF_TOKEN")

    return [
        ("OpenRouter", have_or, "OK" if have_or else "sem chave"),
        ("Together", have_tg, "OK" if have_tg else "sem chave"),
        ("HuggingFace", have_hf, "OK" if have_hf else "sem chave"),
    ]


def list_models(provider: str | None = None) -> List[str]:
    """
    Nunca estoura exceção. Se algum provider não estiver disponível,
    simplesmente retorna lista vazia dele.

    Além disso, garante que modelos OpenRouter "pinned" apareçam sempre no menu.
    """
    prov = (provider or "").strip()

    def _dedupe_keep_order(items: List[str]) -> List[str]:
        out: List[str] = []
        seen: set[str] = set()
        for x in items:
            s = str(x or "").strip()
            if not s:
                continue
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(s)
        return out

    if prov == "OpenRouter":
        base = list(OR_MODELS or [])
        base.extend(PINNED_OPENROUTER_MODELS)
        return _dedupe_keep_order(base)

    if prov == "Together":
        return _dedupe_keep_order(list(TG_MODELS or []))

    if prov == "HuggingFace":
        return _dedupe_keep_order(list(HF_MODELS or []))

    out: List[str] = []
    for lst in (OR_MODELS or [], TG_MODELS or [], HF_MODELS or []):
        for m in lst:
            if m and m not in out:
                out.append(m)

    out.extend(PINNED_OPENROUTER_MODELS)
    out = _dedupe_keep_order(out)
    return out or [SAFE_FALLBACK_MODEL]


# -----------------------------------------
# Identificação do provedor
# -----------------------------------------
def _provider_for(model_id: str) -> str:
    m = (model_id or "").strip()
    low = m.lower()

    # HF explícito por lista
    if m in (HF_MODELS or []):
        return "HuggingFace"

    # Together explícito
    if low.startswith(("together/", "deepseek-ai/", "moonshotai/", "google/", "zai-org/")):
        return "Together"

    # OpenRouter explícito
    if low.endswith(":free"):
        return "OpenRouter"
    if low.startswith(("x-ai/", "tngtech/", "deepseek/", "anthropic/", "qwen/", "nousresearch/", "xiaomi/")):
        return "OpenRouter"

    # Heurística leve pra HF
    if (HF_MODELS or []) and _env_has_any("HUGGINGFACE_API_KEY", "HF_TOKEN"):
        for mid in HF_MODELS:
            pref = (mid.split("/", 1)[0] + "/") if "/" in mid else ""
            if pref and low.startswith(pref.lower()):
                return "HuggingFace"

    return "OpenRouter"


def _normalize_model_id(raw: str) -> str:
    if not raw:
        return SAFE_FALLBACK_MODEL
    low = raw.lower().strip()
    if low in MODEL_ALIASES:
        return MODEL_ALIASES[low]
    return raw


def _should_fallback_openrouter(err: Exception) -> bool:
    msg = str(err).lower()
    triggers = [
        "not a valid model id",
        "model_not_found",
        "model not found",
        "model_not_supported",
        "invalid_request_error",
        "param': 'model",
        'param": "model',
        "unknown model",
    ]
    return any(t in msg for t in triggers)


def _normalize_used_tuple(resp: Any, fallback_model: str, fallback_provider: str):
    """
    Garante retorno sempre em tuple: (data, used_model, provider)
    """
    if isinstance(resp, tuple):
        if len(resp) == 3:
            return resp
        if len(resp) == 2:
            return (resp[0], resp[1], fallback_provider)
        if len(resp) == 1:
            return (resp[0], fallback_model, fallback_provider)

    return (resp, fallback_model, fallback_provider)


# -----------------------------------------
# CHAMADA GERAL
# -----------------------------------------
def chat(model: str, messages: List[Dict[str, Any]], **kwargs: Any):
    norm_model = _normalize_model_id(model)
    provider = _provider_for(norm_model)
    model_to_send = _model_for_provider(norm_model, provider)

    safe_messages = _sanitize_messages_for_provider(messages)
    safe_extra = _sanitize_extra(kwargs.get("extra"))

    forwarded_kwargs: Dict[str, Any] = {
        "max_tokens": kwargs.get("max_tokens", 1024),
        "temperature": kwargs.get("temperature", 0.7),
        "top_p": kwargs.get("top_p", 0.95),
    }
    if safe_extra:
        forwarded_kwargs["extra"] = safe_extra

    if provider == "HuggingFace":
        if hf_chat is None:
            raise RuntimeError("HuggingFace provider indisponível (hf.py falhou ao importar).")
        resp = hf_chat(model_to_send, safe_messages, **forwarded_kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "HuggingFace")
        return _normalize_used_tuple(resp, norm_model, "huggingface")

    if provider == "Together":
        if together_chat is None:
            raise RuntimeError("Together provider indisponível (together.py falhou ao importar).")
        resp = together_chat(model_to_send, safe_messages, **forwarded_kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "Together")
        return _normalize_used_tuple(resp, norm_model, "together")

    try:
        resp = openrouter_chat(norm_model, safe_messages, **forwarded_kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "OpenRouter")
        return _normalize_used_tuple(resp, norm_model, "openrouter")

    except RuntimeError as e:
        if _should_fallback_openrouter(e):
            resp = openrouter_chat(SAFE_FALLBACK_MODEL, safe_messages, **forwarded_kwargs)
            resp = _normalize_reasoning_into_content(resp)
            _raise_if_provider_error(resp, "OpenRouter")
            return _normalize_used_tuple(resp, SAFE_FALLBACK_MODEL, "openrouter")
        raise


# ==========================================================
# COMPATIBILIDADE (LEGADO): call_model
# ==========================================================
def call_model(*args: Any, **kwargs: Any):
    """
    Compat wrapper para código antigo que chamava `call_model(...)`.

    Aceita assinaturas comuns:
      - call_model(model, messages, **params)
      - call_model(provider, model, messages, user)
      - call_model(provider=..., model=..., messages=..., user=...)
    e redireciona para `chat(model=..., messages=...)`.
    """
    provider = kwargs.get("provider")
    model = kwargs.get("model")
    messages = kwargs.get("messages")

    if (model is None or messages is None) and len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], list):
        model = model or args[0]
        messages = messages or args[1]
    elif (model is None or messages is None) and len(args) >= 3 and isinstance(args[1], str) and isinstance(args[2], list):
        provider = provider or args[0]
        model = model or args[1]
        messages = messages or args[2]

    if not isinstance(model, str) or not model.strip():
        raise RuntimeError("call_model: model ausente/inválido")
    if not isinstance(messages, list):
        raise RuntimeError("call_model: messages ausente/inválido")

    passthrough: Dict[str, Any] = {}
    for k in ("max_tokens", "temperature", "top_p", "extra"):
        if k in kwargs:
            passthrough[k] = kwargs[k]

    return chat(model=str(model).strip(), messages=messages, **passthrough)


# -----------------------------------------
# Strict routing (para debug)
# -----------------------------------------
def route_chat_strict(model: str, payload: Dict[str, Any]):
    norm_model = _normalize_model_id(model)
    provider = _provider_for(norm_model)
    model_to_send = _model_for_provider(norm_model, provider)

    msgs = _sanitize_messages_for_provider(payload.get("messages", []))
    safe_extra = _sanitize_extra(payload.get("extra"))

    kwargs: Dict[str, Any] = {
        "max_tokens": payload.get("max_tokens", 1024),
        "temperature": payload.get("temperature", 0.7),
        "top_p": payload.get("top_p", 0.95),
    }

    if safe_extra:
        kwargs["extra"] = safe_extra

    debug_preview = {
        "model_original": model,
        "model_normalized": norm_model,
        "provider": provider,
        "model_to_send": model_to_send,
        "kwargs": kwargs,
        "extra_keys": list(safe_extra.keys()),
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
        ],
    }

    if provider == "HuggingFace":
        if hf_chat is None:
            raise RuntimeError("HuggingFace provider indisponível (hf.py falhou ao importar).")
        try:
            resp = hf_chat(model_to_send, msgs, **kwargs)
            resp = _normalize_reasoning_into_content(resp)
            _raise_if_provider_error(resp, "HuggingFace")
            return _normalize_used_tuple(resp, norm_model, "huggingface")
        except Exception as e:
            raise RuntimeError(
                f"HuggingFace strict route failed | debug={debug_preview} | "
                f"err={type(e).__name__}: {e}"
            ) from e

    if provider == "Together":
        if together_chat is None:
            raise RuntimeError("Together provider indisponível (together.py falhou ao importar).")
        try:
            resp = together_chat(model_to_send, msgs, **kwargs)
            resp = _normalize_reasoning_into_content(resp)
            _raise_if_provider_error(resp, "Together")
            return _normalize_used_tuple(resp, norm_model, "together")
        except Exception as e:
            raise RuntimeError(
                f"Together strict route failed | debug={debug_preview} | "
                f"err={type(e).__name__}: {e}"
            ) from e

    try:
        resp = openrouter_chat(norm_model, msgs, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "OpenRouter")
        return _normalize_used_tuple(resp, norm_model, "openrouter")
    except RuntimeError as e:
        if _should_fallback_openrouter(e):
            resp = openrouter_chat(SAFE_FALLBACK_MODEL, msgs, **kwargs)
            resp = _normalize_reasoning_into_content(resp)
            _raise_if_provider_error(resp, "OpenRouter")
            return _normalize_used_tuple(resp, SAFE_FALLBACK_MODEL, "openrouter")
        raise RuntimeError(
            f"OpenRouter strict route failed | debug={debug_preview} | "
            f"err={type(e).__name__}: {e}"
        ) from e
