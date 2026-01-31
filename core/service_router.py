# core/service_router.py
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from .openrouter import chat as openrouter_chat, DEFAULT_MODELS as OR_MODELS
from .together import chat as together_chat, DEFAULT_MODELS as TG_MODELS

# ✅ Hugging Face provider (Router HF via OpenAI SDK)
from .hf import chat as hf_chat, DEFAULT_MODELS as HF_MODELS

# Modelo seguro de fallback (OpenRouter)
SAFE_FALLBACK_MODEL = "deepseek/deepseek-chat-v3-0324"

# Alias opcionais (ex: {"chimera": "tngtech/tng-r1t-chimera:free"})
MODEL_ALIASES: Dict[str, str] = {}


# ============================================================
# NORMALIZAÇÃO: reasoning -> content (quando content vem vazio)
# ============================================================
def _normalize_reasoning_into_content(resp: Any) -> Any:
    """
    Alguns providers retornam a resposta em message.reasoning e deixam message.content vazio.
    Este normalizador copia reasoning -> content quando content está vazio,
    para evitar 'modelo retornou vazio' no service.

    Suporta:
      - dict OpenAI-like
      - tuple(data, used_model, provider) (normaliza o data)
    """
    # tuple: (data, used_model, provider)
    if isinstance(resp, tuple) and len(resp) >= 1:
        data = _normalize_reasoning_into_content(resp[0])
        # mantém metadados do tuple intactos
        if len(resp) >= 3:
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


# ============================================================
# PROVIDERS DISPONÍVEIS
# ============================================================
def available_providers() -> List[Tuple[str, bool, str]]:
    have_or = bool(os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_TOKEN"))
    have_tg = bool(os.getenv("TOGETHER_API_KEY"))
    # ✅ aceita os dois nomes (você disse que já tem a chave no Secrets)
    have_hf = bool(os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN"))
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


# ============================================================
# NORMALIZAÇÃO DE MODEL ID (corrige prefixos ruins vindos da UI)
# ============================================================
def _strip_provider_prefix(raw: str) -> tuple[str, str | None]:
    """
    Aceita modelos vindos como:
      - "together/<id>"
      - "hf/<id>" ou "huggingface/<id>"
      - "openrouter/<id>"

    Retorna (model_sem_prefixo, provider_hint_ou_None)

    Observação:
      - "openrouter/auto" é um model id real; mantemos como OpenRouter.
      - Para "together/<id>", removemos o prefixo e deixamos provider_hint="Together".
        Porém: se o <id> estiver em HF_MODELS, vamos tratar como HuggingFace (salvamento).
    """
    m = (raw or "").strip()
    low = m.lower()

    if low.startswith("huggingface/"):
        return (m.split("/", 1)[1].strip(), "HuggingFace")
    if low.startswith("hf/"):
        return (m.split("/", 1)[1].strip(), "HuggingFace")

    if low.startswith("together/"):
        return (m.split("/", 1)[1].strip(), "Together")

    if low.startswith("openrouter/"):
        # openrouter/auto é válido; mantém o prefixo e sinaliza OpenRouter
        return (m.strip(), "OpenRouter")

    return (m, None)


def _normalize_model_id(raw: str) -> str:
    if not raw:
        return SAFE_FALLBACK_MODEL

    model, _hint = _strip_provider_prefix(raw)

    low = model.lower().strip()
    if low in MODEL_ALIASES:
        return MODEL_ALIASES[low]

    return model


# ============================================================
# IDENTIFICAÇÃO DO PROVEDOR
# ============================================================
def _provider_for(model_id: str) -> str:
    m = (model_id or "").strip()
    low = m.lower()

    # 0) Prefixos explícitos vencem sempre
    if low.startswith("together/"):
        return "Together"
    if low.startswith(("hf/", "huggingface/")):
        return "HuggingFace"
    if low.startswith(("openrouter/", "or/")):
        return "OpenRouter"

    # 1) Membership é a regra mais confiável
    if m in HF_MODELS:
        return "HuggingFace"
    if m in TG_MODELS:
        return "Together"
    if m in OR_MODELS:
        return "OpenRouter"

    # 2) Heurísticas OpenRouter
    if low.endswith(":free"):
        return "OpenRouter"
    if low.startswith(("x-ai/", "tngtech/", "deepseek/", "anthropic/", "qwen/", "nousresearch/", "xiaomi/")):
        return "OpenRouter"

    # 3) HF Router com sufixo ":provider" (se você usar algum dia)
    hf_suffixes = set()
    for mid in HF_MODELS:
        if ":" in (mid or ""):
            hf_suffixes.add((mid.rsplit(":", 1)[-1] or "").lower())
    if ":" in low:
        suffix = low.rsplit(":", 1)[-1]
        if suffix in hf_suffixes:
            return "HuggingFace"

    return "OpenRouter"


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


# ============================================================
# CHAMADA GERAL
# ============================================================
def chat(model: str, messages: List[Dict[str, str]], **kwargs: Any):
    # pega hint + strip prefix
    raw = model or ""
    stripped, hint = _strip_provider_prefix(raw)

    norm_model = _normalize_model_id(stripped)
    provider = _provider_for(norm_model, provider_hint=hint)

    if provider == "HuggingFace":
        resp = hf_chat(norm_model, messages, **kwargs)
        return _normalize_reasoning_into_content(resp)

    if provider == "Together":
        resp = together_chat(norm_model, messages, **kwargs)
        return _normalize_reasoning_into_content(resp)

    # OpenRouter
    try:
        resp = openrouter_chat(norm_model, messages, **kwargs)
        return _normalize_reasoning_into_content(resp)
    except RuntimeError as e:
        if _should_fallback_openrouter(e):
            resp = openrouter_chat(SAFE_FALLBACK_MODEL, messages, **kwargs)
            return _normalize_reasoning_into_content(resp)
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
    raw = model or ""
    stripped, hint = _strip_provider_prefix(raw)

    norm_model = _normalize_model_id(stripped)
    provider = _provider_for(norm_model, provider_hint=hint)

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
        resp = hf_chat(norm_model, msgs, **kwargs)
        return _normalize_reasoning_into_content(resp)

    if provider == "Together":
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
