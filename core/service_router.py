from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from .hf import chat as hf_chat, DEFAULT_MODELS as HF_MODELS
from .openrouter import chat as openrouter_chat, DEFAULT_MODELS as OR_MODELS
from .together import chat as together_chat, DEFAULT_MODELS as TG_MODELS

SAFE_FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324"
MODEL_ALIASES: Dict[str, str] = {}

def available_providers() -> List[Tuple[str, bool, str]]:
    have_or = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_TOKEN"))
    have_tg = bool(os.getenv("TOGETHER_API_KEY"))
    have_hf = bool(os.getenv("HUGGINGFACE_API_KEY"))
    return [
        ("OpenRouter", have_or, "OK" if have_or else "sem chave"),
        ("Together",   have_tg, "OK" if have_tg else "sem chave"),
        ("HuggingFace", have_hf, "OK" if have_hf else "sem chave"),
    ]

def list_models(provider: str | None = None) -> List[str]:
    if provider == "OpenRouter":
        return OR_MODELS[:]
    if provider == "Together":
        return TG_MODELS[:]
    if provider == "HuggingFace":
        return HF_MODELS[:]
    return (OR_MODELS[:] + TG_MODELS[:] + HF_MODELS[:]) or [SAFE_FALLBACK_MODEL]

def _provider_for(model_id: str) -> str:
    m = (model_id or "").lower().strip()

    # HuggingFace router ids geralmente têm ":" no final (namespace/provider)
    if ":" in m and m.startswith("zai-org/"):
        return "HuggingFace"

    # Together
    if m.startswith("together/") or m.startswith("deepseek-ai/") or m.startswith("moonshotai/") or m.startswith("google/"):
        return "Together"

    # OpenRouter (default)
    return "OpenRouter"

def _normalize_model_id(raw: str) -> str:
    if not raw:
        return SAFE_FALLBACK_MODEL
    low = raw.lower().strip()
    if low in MODEL_ALIASES:
        return MODEL_ALIASES[low]
    return raw

def chat(model: str, messages: List[Dict[str, str]], **kwargs: Any):
    norm_model = _normalize_model_id(model)
    provider = _provider_for(norm_model)

    if provider == "HuggingFace":
        return hf_chat(norm_model, messages, **kwargs)

    if provider == "Together":
        return together_chat(norm_model, messages, **kwargs)

    try:
        return openrouter_chat(norm_model, messages, **kwargs)
    except RuntimeError as e:
        msg = str(e).lower()
        if "not a valid model id" in msg or "model_not_found" in msg:
            return openrouter_chat(SAFE_FALLBACK_MODEL, messages, **kwargs)
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

    extra = payload.get("extra", None)
    if extra:
        kwargs["extra"] = extra

    if provider == "HuggingFace":
        return hf_chat(norm_model, msgs, **kwargs)

    if provider == "Together":
        return together_chat(norm_model, msgs, **kwargs)

    try:
        return openrouter_chat(norm_model, msgs, **kwargs)
    except RuntimeError as e:
        msg = str(e).lower()
        if "not a valid model id" in msg or "model_not_found" in msg:
            return openrouter_chat(SAFE_FALLBACK_MODEL, msgs, **kwargs)
        raise
