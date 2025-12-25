# core/canon.py
from __future__ import annotations
from typing import Dict, Any, Optional


def get_canon(
    character: str,
    timeline: Optional[str] = None,
    user_key: str | None = None,
) -> Dict[str, Any]:
    character = (character or "").lower()
    timeline = (timeline or "").strip() or "cumplice"

    if character == "mary":

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

                # baseline completo para o engine
                "relationship_state": {
                    "stage": "conhecendo",
                    "trust": 20,
                    "tension": 35,
                    "fear": 45,
                    "guilt": 30,
                    "attachment": 15,
                    "boundaries": "alta",
                    "conflict_theme": "moral",
                    "last_signal": "primeiro_contato",
                    "notes": "Início de vínculo: desejo e curiosidade existem, mas há cautela e conflito interno.",
                    "_promote_streak": 0,
                    "_regress_streak": 0,
                },
            }

        return {
            "regras_mundo": [
                "Se houver conflito entre persona e fatos, fatos vencem.",
                "A intimidade existente faz parte da realidade atual.",
                "Se faltar informação, conduza a cena com naturalidade.",
            ],
            "estado_relacao": "casados",
            "vida_em_comum": True,
            "historico_intimo_consumado": True,

            "relationship_state": {
                "stage": "casados",
                "trust": 75,
                "tension": 70,
                "fear": 20,
                "guilt": 10,
                "attachment": 85,
                "boundaries": "baixa",
                "conflict_theme": "rotina",
                "last_signal": "rotina_intima",
                "notes": "Vínculo consolidado: cumplicidade alta e intimidade natural, com espaço para tensão e afeto.",
                "_promote_streak": 0,
                "_regress_streak": 0,
            },
        }

    return {
        "regras_mundo": [
            "Se houver conflito entre persona e fatos, fatos vencem.",
            "Se faltar informação, pergunte em vez de inventar.",
        ]
    }


def canon_to_text(canon: Dict[str, Any]) -> str:
    lines: list[str] = []
    for k, v in (canon or {}).items():
        if isinstance(v, list):
            lines.append(f"- {k}:")
            for item in v:
                lines.append(f"  - {item}")
        elif isinstance(v, dict):
            lines.append(f"- {k}:")
            for kk, vv in v.items():
                lines.append(f"  - {kk}: {vv}")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)
