# core/prompt_injectors.py
from __future__ import annotations

from typing import Dict, Any


def inject_canon(base_prompt: str, canon_text: str) -> str:
    """
    Injeta os fatos canônicos NO TOPO do prompt.
    O LLM deve tratar isso como verdade superior.
    """
    return f"""\
FATOS CANÔNICOS (VERDADE ATUAL — NÃO CONTRADIZER):
{canon_text}

REGRAS OBRIGATÓRIAS:
- Nunca contradiga os FATOS CANÔNICOS.
- Se a persona disser algo diferente, adapte a narrativa para encaixar nos fatos.
- Se estiver ambíguo, pergunte ao usuário ao invés de inventar.

{base_prompt}
"""
