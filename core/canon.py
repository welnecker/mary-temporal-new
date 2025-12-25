# core/canon.py
from __future__ import annotations

from typing import Dict, Any


def get_canon(character: str, user_key: str | None = None) -> Dict[str, Any]:
    """
    Retorna fatos CANÔNICOS (verdade atual) que o LLM nunca pode contradizer.
    Neste Degrau 1 vamos começar simples e estável.
    Depois (Degrau 2/3) isso pode vir de DB/Sheets.
    """
    character = (character or "").lower()

    # Cânone base por personagem
    if character == "mary":
        return {
            # Coloque aqui apenas fatos que você quer que sejam sempre respeitados
            # (o que "é verdade AGORA", não a persona de origem).
            "regras_mundo": [
                "Se houver conflito entre persona e fatos, fatos vencem.",
                "Se faltar informação, pergunte em vez de inventar.",
            ],
            # Exemplo de fatos que você pode ligar/desligar
            # (ajuste para o seu caso real quando quiser)
            "estado_relacao": "casados",
            # "virgindade": False,
            # "gravidez": {"ativa": True, "semanas": 8, "confirmado_em": "2025-11-26"},
        }

    return {
        "regras_mundo": [
            "Se houver conflito entre persona e fatos, fatos vencem.",
            "Se faltar informação, pergunte em vez de inventar.",
        ]
    }


def canon_to_text(canon: Dict[str, Any]) -> str:
    """
    Converte o dicionário de cânone em texto curto, claro e 'model-friendly'.
    """
    lines: list[str] = []
    for k, v in canon.items():
        if isinstance(v, list):
            lines.append(f"- {k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)
