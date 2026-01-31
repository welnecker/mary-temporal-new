from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

# ============================================================
# Imports SAFE (não deixar a UI cair pro fallback por exceção)
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

# core/service_router.py
_IMPORT_ERRORS: Dict[str, str] = {}


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

    # padrões comuns
    if "error" in data and data["error"]:
        raise RuntimeError(f"{provider} error: {data['error']}")
    if "errors" in data and data["errors"]:
        raise RuntimeError(f"{provider} errors: {data['errors']}")

    # alguns providers jogam msg em "message"
    if data.get("message") and isinstance(data.get("message"), str) and ("error" in data.get("message","").lower()):
        raise RuntimeError(f"{provider} message: {data['message']}")


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

    # fallback visual só se realmente ficou vazio
    return out or [SAFE_FALLBACK_MODEL]


# -----------------------------------------
# Identificação correta do provedor
# -----------------------------------------
def _provider_for(model_id: str) -> str:
    m = (model_id or "").strip()
    low = m.lower()

    # ✅ 0) HF explícito por lista (mais forte)
    if m in (HF_MODELS or []):
        return "HuggingFace"

    # ✅ 1) Together explícito (apenas prefixos que realmente são Together)
    # NÃO incluir "zai-org/" aqui.
    if low.startswith(("together/", "deepseek-ai/", "moonshotai/", "google/")):
        return "Together"

    # ✅ 2) OpenRouter explícito
    if low.endswith(":free"):
        return "OpenRouter"
    if low.startswith(("x-ai/", "tngtech/", "deepseek/", "anthropic/", "qwen/", "nousresearch/", "xiaomi/")):
        return "OpenRouter"

    # ✅ 3) Se o HF estiver configurado e o modelo parece HF (ex: "org/model" sem together/)
    # Heurística segura: se está na lista HF_DEFAULT, já caiu no item 0.
    # Então aqui só tenta HF se tiver chave e HF_MODELS não vazio e o modelo começar com prefixo de algum HF model.
    if (HF_MODELS or []) and _env_has_any("HUGGINGFACE_API_KEY", "HF_TOKEN"):
        # se existir algum HF model com mesmo prefixo org/
        for mid in HF_MODELS:
            pref = (mid.split("/", 1)[0] + "/") if "/" in mid else ""
            if pref and low.startswith(pref.lower()):
                return "HuggingFace"

    # Default
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
    provider = _provider_for(norm_model)  # "OpenRouter" | "Together" | "HuggingFace"

    if provider == "HuggingFace":
        if hf_chat is None:
            raise RuntimeError("HuggingFace provider indisponível (hf.py falhou ao importar).")
        resp = hf_chat(norm_model, messages, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "HuggingFace")

        # ✅ garante tuple (data, used_model, used_provider)
        if isinstance(resp, tuple):
            return resp
        return (resp, norm_model, "huggingface")

    if provider == "Together":
        if together_chat is None:
            raise RuntimeError("Together provider indisponível (together.py falhou ao importar).")
        resp = together_chat(norm_model, messages, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "Together")

        # ✅ garante tuple (data, used_model, used_provider)
        if isinstance(resp, tuple):
            return resp
        return (resp, norm_model, "together")

    # OpenRouter
    try:
        resp = openrouter_chat(norm_model, messages, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "OpenRouter")

        # ✅ se OpenRouter não devolver tuple, padroniza também
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



def route_chat_strict(model: str, payload: Dict[str, Any]):
    norm_model = _normalize_model_id(model)
    provider = _provider_for(norm_model)

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
        resp = hf_chat(norm_model, msgs, **kwargs)
        return _normalize_reasoning_into_content(resp)

    if provider == "Together":
        if together_chat is None:
            raise RuntimeError("Together provider indisponível (together.py falhou ao importar).")
        resp = together_chat(norm_model, msgs, **kwargs)
        return _normalize_reasoning_into_content(resp)

    try:
        resp = openrouter_chat(norm_model, msgs, **kwargs)
        return _normalize_reasoning_into_content(resp)
    except RuntimeError as e:
        if _should_fallback_openrouter(e):
            resp = openrouter_chat(SAFE_FALLBACK_MODEL, msgs, **kwargs)
            return _normalize_reasoning_into_content(resp)
        raise
