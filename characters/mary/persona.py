from __future__ import annotations

import importlib
import logging
from typing import List, Dict, Tuple, Optional, Callable

from .persona_core import _norm_timeline

_PERSONA_RESOLVER: dict[str, Callable[[str], Tuple[str, List[Dict[str, str]]]]] = {}

# ✅ debug para o sidebar
_LAST_PERSONA_IMPORT = {"ok": "", "err": ""}


def _import_get_persona(modname: str) -> Optional[Callable[[str], Tuple[str, List[Dict[str, str]]]]]:
    try:
        importlib.invalidate_caches()
        mod = __import__(f"{__package__}.{modname}", fromlist=["get_persona"])
        fn = getattr(mod, "get_persona", None)
        if callable(fn):
            _LAST_PERSONA_IMPORT["ok"] = modname
            _LAST_PERSONA_IMPORT["err"] = ""
            return fn
        _LAST_PERSONA_IMPORT["err"] = f"{modname}: não achei get_persona()"
        return None
    except Exception as e:
        logging.exception("❌ Falha ao importar persona module: %s", modname)
        _LAST_PERSONA_IMPORT["err"] = f"{modname}: {type(e).__name__}: {e}"
        return None


def _resolver_for(tl: str) -> Callable[[str], Tuple[str, List[Dict[str, str]]]]:
    # ✅ se cacheou fallback, não prende: tenta reimportar
    if tl in _PERSONA_RESOLVER:
        fn_cached = _PERSONA_RESOLVER[tl]
        if getattr(fn_cached, "_is_fallback", False):
            _PERSONA_RESOLVER.pop(tl, None)
        else:
            return fn_cached

    # ✅ prioridade CORRETA (seu nome real de arquivo)
    if tl == "universitaria":
        fn = _import_get_persona("persona_universitaria")
    else:
        fn = _import_get_persona("persona_cumplice")

    if fn is None:
        def _fallback(_: str) -> Tuple[str, List[Dict[str, str]]]:
            from .persona_core import BASE_PERSONA
            return (
                BASE_PERSONA + "\n\n[ERRO] Não consegui importar persona_*. Veja o Debug Persona Import no sidebar.",
                [{"role": "assistant", "timeline": tl, "content": "Eu te vejo. Diz pra mim o que você quer agora."}],
            )

        _fallback._is_fallback = True  # type: ignore[attr-defined]
        _PERSONA_RESOLVER[tl] = _fallback
        return _fallback

    _PERSONA_RESOLVER[tl] = fn
    return fn


def get_persona(timeline: Optional[str] = None) -> Tuple[str, List[Dict[str, str]]]:
    tl = _norm_timeline(timeline)
    return _resolver_for(tl)(tl)
