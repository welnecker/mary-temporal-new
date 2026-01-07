from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from .openrouter import chat as openrouter_chat, DEFAULT_MODELS as OR_MODELS
from .together import chat as together_chat, DEFAULT_MODELS as TG_MODELS

# ✅ Hugging Face provider
from .hf import chat as hf_chat, DEFAULT_MODELS as HF_MODELS

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
    # sem filtro: todos
    return OR_MODELS[:] + TG_MODELS[:] + HF_MODELS[:]

def _provider_for(model_id: str) -> str:
    """Resolve o provider pelo model_id.

    ⚠️ Bug que causava 'modelo vazio':
      OpenRouter usa sufixos como ':free' (ex: 'tngtech/...:free').
      A regra antiga 'if ":" in model -> HuggingFace' roteava ERRADO para HF,
      resultando no 400: provider 'free' inválido.
    """
    m = (model_id or "").strip()
    low = m.lower()

    # 1) Se está explicitamente na lista HF, é HF
    hf_set = {x.lower().strip() for x in (HF_MODELS or [])}
    if low in hf_set or low.startswith("hf/"):
        return "HuggingFace"

    # 2) Together por prefixos (se você usa esses ids)
    if low.startswith("together/"):
        return "Together"
    if low.startswith("deepseek-ai/"):
        return "Together"
    if low.startswith("moonshotai/"):
        return "Together"
    if low.startswith("google/"):
        return "Together"

    # 3) OpenRouter: (inclui ':free', ':beta', etc.)
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
    """Chamada strict usada pela Mary (reasoning / reparos, etc)."""
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
