# characters/mary/persona.py
from __future__ import annotations

import logging
from typing import List, Dict, Tuple, Optional, Callable

from .persona_core import _norm_timeline

_PERSONA_RESOLVER: dict[str, Callable[[str], Tuple[str, List[Dict[str, str]]]]] = {}


def _import_get_persona(modname: str) -> Optional[Callable[[str], Tuple[str, List[Dict[str, str]]]]]:
    try:
        mod = __import__(f"{__package__}.{modname}", fromlist=["get_persona"])
        fn = getattr(mod, "get_persona", None)
        if callable(fn):
            return fn
        logging.error("❌ Módulo %s importou, mas não tem get_persona() chamável.", modname)
        return None
    except Exception as e:
        logging.exception("❌ Falha ao importar persona module: %s (%s)", modname, e)
        return None


def _fallback_factory(tl: str) -> Callable[[str], Tuple[str, List[Dict[str, str]]]]:
    def _fallback(_: str) -> Tuple[str, List[Dict[str, str]]]:
        from .persona_core import BASE_PERSONA
        return (
            BASE_PERSONA + "\n\n[ERRO] Não achei personas_* importáveis. Verifique nomes dos arquivos.",
            [{"role": "assistant", "timeline": tl, "content": "Eu te vejo. Diz pra mim o que você quer agora."}],
        )

    _fallback._is_fallback = True  # marca para permitir retry depois
    return _fallback


def _resolver_for(tl: str) -> Callable[[str], Tuple[str, List[Dict[str, str]]]]:
    # Se já existe no cache, mas era fallback, tenta reimportar
    if tl in _PERSONA_RESOLVER:
        fn_cached = _PERSONA_RESOLVER[tl]
        if getattr(fn_cached, "_is_fallback", False):
            _PERSONA_RESOLVER.pop(tl, None)
        else:
            return fn_cached

    # ✅ prioridade: módulos novos "personas_*"
    if tl == "universitaria":
        fn = _import_get_persona("personas_universitaria") or _import_get_persona("persona_universitaria")
    else:
        fn = _import_get_persona("personas_cumplice") or _import_get_persona("persona_cumplice")

    if fn is None:
        fn = _fallback_factory(tl)

    _PERSONA_RESOLVER[tl] = fn
    return fn


def get_persona(timeline: Optional[str] = None) -> Tuple[str, List[Dict[str, str]]]:
    tl = _norm_timeline(timeline)
    return _resolver_for(tl)(tl)
