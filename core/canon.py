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

    Observação (Degrau 1):
    - 'relationship_state' aqui é o DEFAULT inicial.
    - O estado real deve viver nos facts (set_fact/get_facts) e evoluir por engine.
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

                # === NOVO: estado dinâmico (default inicial) ===
                "relationship_state": {
                    "stage": "conhecendo",
                    "trust": 20,        # segurança/confiança
                    "tension": 35,      # atração/tensão
                    "fear": 45,         # medo/risco
                    "guilt": 30,        # culpa/moral/família
                    "attachment": 15,   # vínculo/amor
                    "boundaries": "alta",
                    "last_signal": "primeiro_contato",
                    "notes": "Início de vínculo. Desejo existe, mas há cautela e incerteza.",
                },
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

            # === NOVO: estado dinâmico (default inicial) ===
            "relationship_state": {
                "stage": "casados",
                "trust": 75,
                "tension": 70,
                "fear": 20,
                "guilt": 10,
                "attachment": 85,
                "boundaries": "baixa",
                "last_signal": "rotina_intima",
                "notes": "Vínculo consolidado, intimidade natural e cumplicidade alta.",
            },

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
        ],
        "relationship_state": {
            "stage": "neutro",
            "trust": 50,
            "tension": 0,
            "fear": 0,
            "guilt": 0,
            "attachment": 0,
            "boundaries": "media",
            "last_signal": "none",
            "notes": "Estado padrão genérico.",
        },
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
        elif isinstance(v, dict):
            lines.append(f"- {k}:")
            for kk, vv in v.items():
                lines.append(f"  - {kk}: {vv}")
        else:
            lines.append(f"- {k}: {v}")
    return "\n".join(lines)
