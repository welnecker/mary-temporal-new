from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from .openrouter import chat as openrouter_chat, DEFAULT_MODELS as OR_MODELS
from .together import chat as together_chat, DEFAULT_MODELS as TG_MODELS

# ✅ Hugging Face provider
from .hf import chat as hf_chat, DEFAULT_MODELS as HF_MODELS

# Modelo seguro de fallback
SAFE_FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324"

# Alias opcionais (ex: {"chimera": "tngtech/tng-r1t-chimera:free"})
MODEL_ALIASES: Dict[str, str] = {}


# -------------------------
# DETECÇÃO DE PROVIDER
# -------------------------
def available_providers() -> List[Tuple[str, bool, str]]:
    have_or = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_TOKEN"))
    have_tg = bool(os.getenv("TOGETHER_API_KEY"))
    have_hf = bool(os.getenv("HUGGINGFACE_API_KEY"))
    return [
        ("OpenRouter", have_or, "OK" if have_or else "sem chave"),
        ("Together", have_tg, "OK" if have_tg else "sem chave"),
        ("HuggingFace", have_hf, "OK" if have_hf else "sem chave"),
    ]


def list_models(provider: str | None = None) -> List[str]:
    if provider == "OpenRouter":
        return OR_MODELS[:]
    if provider == "Together":
        return TG_MODELS[:]
    if provider == "HuggingFace":
        return HF_MODELS[:]

    # Merge sem duplicar (preserva ordem)
    out: List[str] = []
    for lst in (OR_MODELS, TG_MODELS, HF_MODELS):
        for m in lst:
            if m not in out:
                out.append(m)
    return out


# -----------------------------------------
# Identificação correta do provedor
# -----------------------------------------
def _provider_for(model_id: str) -> str:
    m = (model_id or "").strip()
    low = m.lower()

    # 1) Together explícito / padrões comuns
    if low.startswith(("together/", "deepseek-ai/", "moonshotai/", "google/")):
        return "Together"

    # 2) OpenRouter explícito (IMPORTANTE: OpenRouter usa sufixos como ':free')
    if low.startswith(("x-ai/", "tngtech/", "deepseek/", "anthropic/", "qwen/", "nousresearch/")):
        return "OpenRouter"
    if low.endswith(":free"):
        return "OpenRouter"

    # 3) HuggingFace Router: só trate como HF se o sufixo após ":" for um provider HF conhecido
    #    Ex: zai-org/glm-4.7-fp8:zai-org  -> suffix 'zai-org'
    hf_suffixes = set()
    for mid in HF_MODELS:
        if ":" in (mid or ""):
            hf_suffixes.add((mid.rsplit(":", 1)[-1] or "").lower())
    if ":" in low:
        suffix = low.rsplit(":", 1)[-1]
        if suffix in hf_suffixes:
            return "HuggingFace"

    # 4) Se estiver explicitamente na lista do HF, respeite
    if m in HF_MODELS:
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
    # cobre mensagens típicas do OpenRouter e de upstreams
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
    provider = _provider_for(norm_model)

    if provider == "HuggingFace":
        return hf_chat(norm_model, messages, **kwargs)

    if provider == "Together":
        return together_chat(norm_model, messages, **kwargs)

    try:
        return openrouter_chat(norm_model, messages, **kwargs)
    except RuntimeError as e:
        if _should_fallback_openrouter(e):
            return openrouter_chat(SAFE_FALLBACK_MODEL, messages, **kwargs)
        raise


# ============================================================
# CHAMADA STRICT (onde a Mary injeta coisas especiais)
# ============================================================
def route_chat_strict(model: str, payload: Dict[str, Any]):
    """
    payload deve conter:
        messages: [...],
        max_tokens: int,
        temperature: float,
        top_p: float,
        extra: dict (opcional)
    """
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
        return hf_chat(norm_model, msgs, **kwargs)

    if provider == "Together":
        return together_chat(norm_model, msgs, **kwargs)

    try:
        return openrouter_chat(norm_model, msgs, **kwargs)
    except RuntimeError as e:
        if _should_fallback_openrouter(e):
            return openrouter_chat(SAFE_FALLBACK_MODEL, msgs, **kwargs)
        raise
