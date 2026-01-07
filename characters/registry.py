# characters/registry.py
from __future__ import annotations
from characters.mary.persona_core import _norm_timeline

from importlib import import_module
from typing import Dict, Tuple, List, Type
import inspect
import secrets

from core.common.base_service import BaseCharacter


# ==========================
# Catálogo (sempre minúsculo)
# ==========================
_CATALOG: Dict[str, Tuple[str, str]] = {
    # Default (compat): MaryService (em characters.mary.service)
    "mary": ("characters.mary.service", "MaryService"),

    # ✅ Variantes opcionais (separação por timeline)
    # Você pode usar get_service("mary:universitaria") ou get_service("mary:cumplice")
    "mary:universitaria": ("characters.mary.service_universitaria", "MaryServiceUniversitaria"),
    "mary:cumplice": ("characters.mary.service_cumplice", "MaryServiceCumplice"),

    # Outros personagens
    "laura": ("characters.laura.service", "LauraService"),
    "adelle": ("characters.adelle.service", "AdelleService"),
    "nerith": ("characters.nerith.service", "NerithService"),
}

# Cache por personagem (chave interna varia conforme ambiente)
_SERVICE_CACHE: Dict[str, BaseCharacter] = {}


# ==========================
# Helpers: Streamlit session
# ==========================
def _streamlit_session_prefix() -> str:
    """
    Se rodando em Streamlit, retorna um prefixo único por sessão
    para impedir vazamento de instância entre usuários/sessões.
    Fora do Streamlit retorna "" (cache global como antes).
    """
    try:
        import streamlit as st  # type: ignore
    except Exception:
        return ""

    # Garante um id por sessão
    sid = st.session_state.get("_registry_session_id")
    if not sid:
        sid = secrets.token_hex(8)
        st.session_state["_registry_session_id"] = sid

    return f"st::{sid}::"


def _cache_key(name: str) -> str:
    """
    Normaliza e aplica namespace por sessão Streamlit (se houver).
    """
    key = (name or "").strip().lower() or "mary"
    return _streamlit_session_prefix() + key


def clear_service_cache(name: str | None = None) -> None:
    """
    Limpa o cache de um personagem específico ou todo cache.

    - Em Streamlit: se name=None, limpa apenas a sessão atual.
    - Fora do Streamlit: se name=None, limpa tudo.
    """
    prefix = _streamlit_session_prefix()

    if name is None:
        if prefix:
            # limpa só a sessão atual
            for k in list(_SERVICE_CACHE.keys()):
                if k.startswith(prefix):
                    _SERVICE_CACHE.pop(k, None)
        else:
            _SERVICE_CACHE.clear()
        return

    k = _cache_key(name)
    _SERVICE_CACHE.pop(k, None)


def list_characters() -> List[str]:
    # Mostra apenas personagens "principais" (sem variantes)
    base = [k for k in _CATALOG.keys() if ":" not in k]
    return [k.capitalize() for k in base]


def _load_class(module_name: str, class_name: str) -> Type[BaseCharacter]:
    mod = import_module(module_name)
    cls = getattr(mod, class_name)
    if not inspect.isclass(cls) or not issubclass(cls, BaseCharacter):
        raise TypeError(f"{class_name} não é subclass de BaseCharacter")
    return cls


def _resolve_by_catalog(key: str) -> BaseCharacter:
    module_name, class_name = _CATALOG[key]
    cls = _load_class(module_name, class_name)
    return cls()


def _resolve_by_convention(name_lc: str) -> BaseCharacter:
    """
    Convenção padrão:
      characters.<name>.service / <Name>Service
    Também aceita name no formato "mary:universitaria"
      -> characters.mary.service_universitaria / MaryServiceUniversitaria
    """
    if ":" in name_lc:
        base, variant = name_lc.split(":", 1)
        base = (base or "").strip().lower()
        variant = (variant or "").strip().lower()

        if base == "mary":
            variant = _norm_timeline(variant)
            if variant in ("universitaria", "cumplice"):

            module_name = f"characters.mary.service_{variant}"
            class_name = f"MaryService{variant.capitalize()}"
            cls = _load_class(module_name, class_name)
            return cls()

    module_name = f"characters.{name_lc}.service"
    class_name = f"{name_lc.capitalize()}Service"
    cls = _load_class(module_name, class_name)
    return cls()


def get_service(name: str) -> BaseCharacter:
    """
    Resolve serviço por:
    1) Catálogo (case-insensitive)
    2) Convenção (módulo + classe)
    Cacheia por nome (isolado por sessão Streamlit se aplicável).

    ✅ Aceita variantes:
      - get_service("mary:universitaria")
      - get_service("mary:cumplice")
    """
    raw = (name or "").strip().lower()
    key = raw or "mary"

    ck = _cache_key(key)
    if ck in _SERVICE_CACHE:
        return _SERVICE_CACHE[ck]

    inst: BaseCharacter | None = None

    # 1) Catálogo
    if key in _CATALOG:
        try:
            inst = _resolve_by_catalog(key)
        except Exception:
            inst = None

    # 2) Convenção
    if inst is None:
        try:
            inst = _resolve_by_convention(key)
        except Exception:
            inst = None

    # 3) Fallback final seguro: Mary default
    if inst is None:
        inst = _resolve_by_catalog("mary")

    _SERVICE_CACHE[ck] = inst
    return inst


def list_models_for_character(name: str) -> List[str]:
    """
    (Opcional) Se cada service expõe 'supported_models()', devolve;
    caso contrário retorna lista vazia para a UI não quebrar.
    """
    try:
        svc = get_service(name)
        if hasattr(svc, "supported_models") and callable(getattr(svc, "supported_models")):
            return list(getattr(svc, "supported_models")() or [])
    except Exception:
        pass
    return []
