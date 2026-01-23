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
        return fn if callable(fn) else None
    except Exception as e:
        logging.exception("❌ Falha ao importar persona module: %s (%s)", modname, e)
        return None


def _resolver_for(tl: str) -> Callable[[str], Tuple[str, List[Dict[str, str]]]]:
    # Se já existe no cache, devolve (cache só guarda personas reais)
    if tl in _PERSONA_RESOLVER:
        return _PERSONA_RESOLVER[tl]

    # ✅ prioridade: módulos novos "personas_*"
    if tl == "universitaria":
        fn = _import_get_persona("personas_universitaria") or _import_get_persona("persona_universitaria")
    else:
        fn = _import_get_persona("personas_cumplice") or _import_get_persona("persona_cumplice")

    # Se falhar, fallback (NÃO cacheia fallback)
    if fn is None:
        def _fallback(_: str) -> Tuple[str, List[Dict[str, str]]]:
            from .persona_core import BASE_PERSONA
            return (
                BASE_PERSONA
                + "\n\n[ERRO] Não consegui importar personas_*. Verifique nome/arquivo no deploy e logs.",
                [{"role": "assistant", "timeline": tl, "content": "Eu te vejo. Diz pra mim o que você quer agora."}],
            )

        return _fallback

    # cacheia apenas quando deu certo
    _PERSONA_RESOLVER[tl] = fn
    return fn


def get_persona(timeline: Optional[str] = None) -> Tuple[str, List[Dict[str, str]]]:
    tl = _norm_timeline(timeline)
    return _resolver_for(tl)(tl)
