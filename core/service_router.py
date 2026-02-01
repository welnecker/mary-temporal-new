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
    """
    prov = (provider or "").strip()

    if prov == "OpenRouter":
        return list(OR_MODELS or [])
    if prov == "Together":
        return list(TG_MODELS or [])
    if prov == "HuggingFace":
        return list(HF_MODELS or [])

    out: List[str] = []
    for lst in (OR_MODELS or [], TG_MODELS or [], HF_MODELS or []):
        for m in lst:
            if m and m not in out:
                out.append(m)

    return out or [SAFE_FALLBACK_MODEL]


# -----------------------------------------
# Identificação do provedor
# -----------------------------------------
def _provider_for(model_id: str) -> str:
    m = (model_id or "").strip()
    low = m.lower()

    # ✅ 0) HF explícito por lista (mais forte)
    if m in (HF_MODELS or []):
        return "HuggingFace"

    # ✅ 1) Together explícito
    # NÃO inclua "zai-org/" aqui. Só prefixos que você realmente quer prender no Together.
    if low.startswith(("together/", "deepseek-ai/", "moonshotai/", "google/")):
        return "Together"

    # ✅ 2) OpenRouter explícito
    if low.endswith(":free"):
        return "OpenRouter"
    if low.startswith(("x-ai/", "tngtech/", "deepseek/", "anthropic/", "qwen/", "nousresearch/", "xiaomi/")):
        return "OpenRouter"

    # ✅ 3) Heurística leve pra HF (quando HF está configurado)
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


# -----------------------------------------
# CHAMADA GERAL
# -----------------------------------------
def chat(model: str, messages: List[Dict[str, str]], **kwargs: Any):
    norm_model = _normalize_model_id(model)
    provider = _provider_for(norm_model)              # "OpenRouter" | "Together" | "HuggingFace"
    model_to_send = _model_for_provider(norm_model, provider)

    if provider == "HuggingFace":
        if hf_chat is None:
            raise RuntimeError("HuggingFace provider indisponível (hf.py falhou ao importar).")
        resp = hf_chat(model_to_send, messages, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "HuggingFace")
        if isinstance(resp, tuple):
            return resp
        return (resp, norm_model, "huggingface")

    if provider == "Together":
        if together_chat is None:
            raise RuntimeError("Together provider indisponível (together.py falhou ao importar).")
        # together_chat já sabe remover "together/" se vier, mas ok enviar model_to_send
        resp = together_chat(model_to_send, messages, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "Together")
        if isinstance(resp, tuple):
            return resp
        return (resp, norm_model, "together")

    # OpenRouter
    try:
        resp = openrouter_chat(norm_model, messages, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "OpenRouter")
        if isinstance(resp, tuple):
            return resp
        return (resp, norm_model, "openrouter")

    except RuntimeError as e:
        if _should_fallback_openrouter(e):
            resp = openrouter_chat(SAFE_FALLBACK_MODEL, messages, **kwargs)
            resp = _normalize_reasoning_into_content(resp)
            _raise_if_provider_error(resp, "OpenRouter")
            if isinstance(resp, tuple):
                return resp
            return (resp, SAFE_FALLBACK_MODEL, "openrouter")
        raise


# ==========================================================
# ✅ COMPATIBILIDADE (LEGADO): call_model
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

    # pos args
    if (model is None or messages is None) and len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], list):
        model = model or args[0]
        messages = messages or args[1]
    elif (model is None or messages is None) and len(args) >= 3 and isinstance(args[1], str) and isinstance(args[2], list):
        provider = provider or args[0]  # não usado (roteamento é automático)
        model = model or args[1]
        messages = messages or args[2]

    if not isinstance(model, str) or not model.strip():
        raise RuntimeError("call_model: model ausente/ inválido")
    if not isinstance(messages, list):
        raise RuntimeError("call_model: messages ausente/ inválido")

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

    # ✅ define call_model aqui também (BUGFIX do NameError)
    call_model = _model_for_provider(norm_model, provider)

    msgs = payload.get("messages", [])
    kwargs = {
        "max_tokens": payload.get("max_tokens", 1024),
        "temperature": payload.get("temperature", 0.7),
        "top_p": payload.get("top_p", 0.95),
    }

    extra = payload.get("extra")
    if extra:
        kwargs["extra"] = extra

    if provider == "HuggingFace":
        if hf_chat is None:
            raise RuntimeError("HuggingFace provider indisponível (hf.py falhou ao importar).")
        resp = hf_chat(call_model, msgs, **kwargs)
        return _normalize_reasoning_into_content(resp)

    if provider == "Together":
        if together_chat is None:
            raise RuntimeError("Together provider indisponível (together.py falhou ao importar).")
        resp = together_chat(call_model, msgs, **kwargs)  # ✅ usa call_model (sem prefixo)
        return _normalize_reasoning_into_content(resp)

    try:
        resp = openrouter_chat(call_model, msgs, **kwargs)  # ✅ usa call_model por consistência
        return _normalize_reasoning_into_content(resp)
    except RuntimeError as e:
        if _should_fallback_openrouter(e):
            resp = openrouter_chat(SAFE_FALLBACK_MODEL, msgs, **kwargs)
            return _normalize_reasoning_into_content(resp)
        raise
