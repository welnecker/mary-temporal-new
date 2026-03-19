from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from .models import (
    list_models as registry_list_models,
    normalize_model_id,
    resolve_provider,
)

_IMPORT_ERRORS: Dict[str, str] = {}

# ============================================================
# Imports SAFE (não deixar a UI cair por exceção)
# ============================================================

# OpenRouter
try:
    from .openrouter import chat as openrouter_chat
except Exception as e:
    _IMPORT_ERRORS["openrouter"] = f"{type(e).__name__}: {e}"

    def openrouter_chat(*args: Any, **kwargs: Any):
        raise RuntimeError(f"OpenRouter indisponível: {type(e).__name__}: {e}")


# Together
try:
    from .together import chat as together_chat
except Exception as e:
    together_chat = None  # type: ignore
    _IMPORT_ERRORS["together"] = f"{type(e).__name__}: {e}"


# Hugging Face
try:
    from .hf import chat as hf_chat
except Exception as e:
    hf_chat = None  # type: ignore
    _IMPORT_ERRORS["hf"] = f"{type(e).__name__}: {e}"


# ============================================================
# Utils
# ============================================================

def _normalize_reasoning_into_content(resp: Any) -> Any:
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
    data = resp[0] if isinstance(resp, tuple) and resp else resp

    if not isinstance(data, dict):
        return

    if "error" in data and data["error"]:
        raise RuntimeError(f"{provider} error: {data['error']}")
    if "errors" in data and data["errors"]:
        raise RuntimeError(f"{provider} errors: {data['errors']}")

    msg = data.get("message")
    if isinstance(msg, str) and "error" in msg.lower():
        raise RuntimeError(f"{provider} message: {msg}")


def _strip_prefix(s: str, prefix: str) -> str:
    s = (s or "").strip()
    p = (prefix or "").strip()
    if s.lower().startswith(p.lower()):
        return s[len(p):].lstrip()
    return s


def _model_for_provider(model: str, provider: str) -> str:
    m = (model or "").strip()

    if provider == "together":
        return _strip_prefix(m, "together/")

    if provider == "hf":
        m = _strip_prefix(m, "hf/")
        m = _strip_prefix(m, "huggingface/")
        return m

    return m


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


# -------------------------
# Providers disponíveis
# -------------------------
def available_providers() -> List[Tuple[str, bool, str]]:
    have_or = _env_has_any("OPENROUTER_API_KEY", "OPENROUTER_TOKEN")
    have_tg = _env_has_any("TOGETHER_API_KEY")
    have_hf = _env_has_any("HUGGINGFACE_API_KEY", "HF_TOKEN")

    return [
        ("openrouter", have_or, "OK" if have_or else "sem chave"),
        ("together", have_tg, "OK" if have_tg else "sem chave"),
        ("hf", have_hf, "OK" if have_hf else "sem chave"),
    ]


def list_models(provider: str | None = None) -> List[str]:
    """
    Lê apenas do core/models.py.
    Não injeta pinned models.
    Não cria fallback.
    """
    prov = (provider or "").strip().lower()

    if prov == "openrouter":
        return _dedupe_keep_order(list(registry_list_models("openrouter") or []))

    if prov == "together":
        return _dedupe_keep_order(list(registry_list_models("together") or []))

    if prov in ("hf", "huggingface"):
        return _dedupe_keep_order(list(registry_list_models("hf") or []))

    out: List[str] = []
    for p in ("openrouter", "together", "hf"):
        out.extend(registry_list_models(p) or [])

    return _dedupe_keep_order(out)


# -----------------------------------------
# CHAMADA GERAL
# -----------------------------------------
def chat(model: str, messages: List[Dict[str, str]], **kwargs: Any):
    norm_model = normalize_model_id(model)
    provider = resolve_provider(norm_model)
    model_to_send = _model_for_provider(norm_model, provider)

    if provider == "hf":
        if hf_chat is None:
            raise RuntimeError("HuggingFace provider indisponível (hf.py falhou ao importar).")
        resp = hf_chat(model_to_send, messages, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "HuggingFace")
        if isinstance(resp, tuple):
            return resp
        return (resp, norm_model, "hf")

    if provider == "together":
        if together_chat is None:
            raise RuntimeError("Together provider indisponível (together.py falhou ao importar).")
        resp = together_chat(model_to_send, messages, **kwargs)
        resp = _normalize_reasoning_into_content(resp)
        _raise_if_provider_error(resp, "Together")
        if isinstance(resp, tuple):
            return resp
        return (resp, norm_model, "together")

    resp = openrouter_chat(model_to_send, messages, **kwargs)
    resp = _normalize_reasoning_into_content(resp)
    _raise_if_provider_error(resp, "OpenRouter")
    if isinstance(resp, tuple):
        return resp
    return (resp, norm_model, "openrouter")


# ==========================================================
# Compatibilidade (legado): call_model
# ==========================================================
def call_model(*args: Any, **kwargs: Any):
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
    norm_model = normalize_model_id(model)
    provider = resolve_provider(norm_model)
    model_to_send = _model_for_provider(norm_model, provider)

    msgs = payload.get("messages", [])
    kwargs = {
        "max_tokens": payload.get("max_tokens", 1024),
        "temperature": payload.get("temperature", 0.7),
        "top_p": payload.get("top_p", 0.95),
    }

    extra = payload.get("extra")
    if extra:
        kwargs["extra"] = extra

    if provider == "hf":
        if hf_chat is None:
            raise RuntimeError("HuggingFace provider indisponível (hf.py falhou ao importar).")
        resp = hf_chat(model_to_send, msgs, **kwargs)
        return _normalize_reasoning_into_content(resp)

    if provider == "together":
        if together_chat is None:
            raise RuntimeError("Together provider indisponível (together.py falhou ao importar).")
        resp = together_chat(model_to_send, msgs, **kwargs)
        return _normalize_reasoning_into_content(resp)

    resp = openrouter_chat(model_to_send, msgs, **kwargs)
    return _normalize_reasoning_into_content(resp)
