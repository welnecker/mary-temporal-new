# characters/mary/persona.py
from __future__ import annotations

import logging
from typing import List, Dict, Tuple, Optional, Callable

from .persona_core import _norm_timeline

_PERSONA_RESOLVER: dict[str, Callable[[str], Tuple[str, List[Dict[str, str]]]]] = {}


# --- DEBUG IMPORT PERSONA ---
_LAST_PERSONA_IMPORT: dict[str, str] = {"ok": "", "err": ""}

def _import_get_persona(modname: str) -> Optional[Callable[[str], Tuple[str, List[Dict[str, str]]]]]:
    try:
        full = f"{__package__}.{modname}"
        mod = __import__(full, fromlist=["get_persona"])
        fn = getattr(mod, "get_persona", None)
        if callable(fn):
            _LAST_PERSONA_IMPORT["ok"] = f"OK import: {full}"
            _LAST_PERSONA_IMPORT["err"] = ""
            return fn
        _LAST_PERSONA_IMPORT["ok"] = ""
        _LAST_PERSONA_IMPORT["err"] = f"Sem get_persona() em {full}"
        return None
    except Exception as e:
        logging.exception("❌ Falha ao importar persona module: %s (%s)", modname, e)
        _LAST_PERSONA_IMPORT["ok"] = ""
        _LAST_PERSONA_IMPORT["err"] = f"ERRO import {__package__}.{modname}: {type(e).__name__}: {e}"
        return None


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
        # fallback seguro: nunca quebrar o app por import
        def _fallback(_: str) -> Tuple[str, List[Dict[str, str]]]:
            from .persona_core import BASE_PERSONA
            return (
                BASE_PERSONA + "\n\n[ERRO] Não achei personas_* importáveis. Verifique nomes dos arquivos.",
                [{"role": "assistant", "timeline": tl, "content": "Eu te vejo. Diz pra mim o que você quer agora."}],
            )

        _fallback._is_fallback = True  # marca para retry
        return _fallback

    _PERSONA_RESOLVER[tl] = fn
    return fn


def get_persona(timeline: Optional[str] = None) -> Tuple[str, List[Dict[str, str]]]:
    tl = _norm_timeline(timeline)
    return _resolver_for(tl)(tl)
