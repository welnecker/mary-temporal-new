from __future__ import annotations

import os
import re
from typing import Dict, List, Optional

MODEL_REGISTRY: Dict[str, List[str]] = {
    "openrouter": [
        "google/gemini-3-flash-preview",  
        "deepseek/deepseek-v3.2",
        "x-ai/grok-4.1-fast",        
        "xiaomi/mimo-v2-flash",
        "deepseek/deepseek-chat-v3-0324",                        
        "openai/gpt-5.4",
    ],
    "together": [
        "google/gemma-3n-E4B-it",
        "together/zai-org/GLM-5",
        "together/moonshotai/Kimi-K2.5",
        "together/meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        "together/zai-org/GLM-4.7",
        "ServiceNow-AI/Apriel-1.5-15b-Thinker",
    ],
    "hf": [
        "moonshotai/Kimi-K2-Instruct-0905:fireworks-ai",
    ],
    "lmstudio": [
        "lmstudio/deepseek/deepseek-r1-0528-qwen3-8b",
        "lmstudio/llama-3-8b-lexi-uncensored",
    ],
}

ENV_MODEL_VARS: Dict[str, str] = {
    "openrouter": "OPENROUTER_MODELS",
    "together": "TOGETHER_MODELS",
    "hf": "HF_MODELS",
    "lmstudio": "LMSTUDIO_MODELS",
}

PROVIDER_ALIASES: Dict[str, str] = {
    "huggingface": "hf",
    "hf": "hf",
    "openrouter": "openrouter",
    "together": "together",
    "lmstudio": "lmstudio",
    "lm studio": "lmstudio",
    "local": "lmstudio",
}

# ============================================================
# Aliases opcionais de modelo
# ============================================================
MODEL_ALIASES: Dict[str, str] = {
    # "chimera": "tngtech/deepseek-r1t2-chimera",
}

# ============================================================
# Helpers
# ============================================================
def _normalize_provider(provider: Optional[str]) -> str:
    p = (provider or "").strip().lower()
    return PROVIDER_ALIASES.get(p, p)


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        v = (item or "").strip()
        if not v:
            continue
        k = v.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(v)
    return out


def _env_list(var_name: str, defaults: List[str]) -> List[str]:
    raw = os.getenv(var_name, "") or ""
    if not raw.strip():
        return defaults

    parts = [p.strip() for p in re.split(r"[,\n;]+", raw) if p.strip()]
    return _dedupe_keep_order(parts) or defaults


# ============================================================
# API pública
# ============================================================
def normalize_model_id(raw: str) -> str:
    if not raw:
        return ""
    low = raw.strip().lower()
    return MODEL_ALIASES.get(low, raw.strip())


def list_models(provider: Optional[str]) -> List[str]:
    p = _normalize_provider(provider)
    defaults = MODEL_REGISTRY.get(p, [])
    env_var = ENV_MODEL_VARS.get(p)

    if not defaults:
        return []

    if env_var:
        return _env_list(env_var, defaults)

    return _dedupe_keep_order(defaults)


def available_providers() -> List[str]:
    out: List[str] = []

    if os.getenv("OPENROUTER_API_KEY"):
        out.append("openrouter")

    if os.getenv("TOGETHER_API_KEY"):
        out.append("together")

    if os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN"):
        out.append("hf")

    # provider local
    out.append("lmstudio")

    return out or ["openrouter", "together", "hf", "lmstudio"]


def default_model(provider: Optional[str]) -> str:
    models = list_models(provider)
    return models[0] if models else ""


def provider_has_model(provider: Optional[str], model: str) -> bool:
    p = _normalize_provider(provider)
    m = normalize_model_id(model)
    return m in list_models(p)


def resolve_provider(model: str) -> str:
    m = normalize_model_id(model)
    if not m:
        raise RuntimeError("Modelo vazio.")

    # 1) match exato no registry
    for provider in ("openrouter", "together", "hf", "lmstudio"):
        if m in list_models(provider):
            return provider

    # 2) heurísticas leves
    low = m.lower()

    if low.startswith("lmstudio/"):
        return "lmstudio"

    if low.startswith("together/"):
        return "together"

    if m in list_models("openrouter"):
        return "openrouter"

    raise RuntimeError(f"Modelo não cadastrado em core/models.py: {m}")


def all_models() -> Dict[str, List[str]]:
    return {provider: list_models(provider) for provider in MODEL_REGISTRY.keys()}


def flattened_models() -> List[str]:
    out: List[str] = []
    for provider in MODEL_REGISTRY.keys():
        out.extend(list_models(provider))
    return _dedupe_keep_order(out)
