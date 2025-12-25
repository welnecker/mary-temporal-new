# core/canon.py
from __future__ import annotations
from typing import Dict, Any, Optional


def get_canon(
    character: str,
    timeline: Optional[str] = None,
    user_key: str | None = None,
) -> Dict[str, Any]:
    """
    Retorna fatos CANÔNICOS (verdade atual) que o LLM nunca pode contradizer.
    O cânone é sensível à TIMELINE ativa.
    """
    character = (character or "").lower()
    timeline = (timeline or "").strip() or "cumplice"

    # ======================================================
    # CÂNONE DA MARY
    # ======================================================
    if character == "mary":

        # ----------------------------
        # Timeline: Universitária
        # ----------------------------
        if timeline == "universitaria":
            return {
                "regras_mundo": [
                    "Se houver conflito entre persona e fatos, fatos vencem.",
                    "Não presuma vínculos ou intimidade não vividos em cena.",
                    "Se faltar informação, conduza com cuidado em vez de inventar.",
                ],
                "estado_relacao": "vinculo_inicial",
                "vida_em_comum": False,
                "historico_intimo_consumado": False,
            }

        # ----------------------------
        # Timeline: Cúmplice (padrão)
        # ----------------------------
        return {
            "regras_mundo": [
                "Se houver conflito entre persona e fatos, fatos vencem.",
                "A intimidade existente faz parte da realidade atual.",
                "Se faltar informação, conduza a cena com naturalidade.",
            ],
            "estado_relacao": "casados",
            "vida_em_comum": True,
            "historico_intimo_consumado": True,
            # Exemplos futuros:
            # "gravidez": {"ativa": True, "semanas": 8},
        }

    # ======================================================
    # Fallback genérico
    # ======================================================
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
