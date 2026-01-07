from __future__ import annotations

from typing import Optional
import re


def _canon(s: str) -> str:
    """
    Normaliza variações comuns:
    - travessões (– —) viram hífen (-)
    - espaços duplicados colapsam
    - remove espaços ao redor de hífen
    """
    s = (s or "").strip().lower()
    if not s:
        return ""
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)              # colapsa espaços
    s = re.sub(r"\s*-\s*", " - ", s)        # padroniza hífen com espaços
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm_timeline(timeline: Optional[str]) -> str:
    tl = _canon(timeline or "")
    if not tl:
        return "cumplice"

    aliases = {
        # cúmplice
        "cumplice": "cumplice",
        "cúmplice": "cumplice",
        "esposa cumplice": "cumplice",
        "esposa cúmplice": "cumplice",
        "mary - esposa cúmplice": "cumplice",
        "mary - esposa cumplice": "cumplice",
        "mary - esposa cúmplice (linha alternativa)": "cumplice",  # (se alguém inventar label)
        "mary - esposa cumplice (linha alternativa)": "cumplice",

        # universitária
        "universitaria": "universitaria",
        "universitária": "universitaria",
        "mary - universitaria": "universitaria",
        "mary - universitária": "universitaria",
        "linha alternativa": "universitaria",
        "universitaria (linha alternativa)": "universitaria",
        "universitária (linha alternativa)": "universitaria",

        # ✅ estes dois são os que costumam vir do selectbox do mary_app
        "mary - universitaria (linha alternativa)": "universitaria",
        "mary - universitária (linha alternativa)": "universitaria",
    }

    # também tenta uma segunda normalização trocando "cúmplice" -> "cumplice" no texto,
    # só pra evitar erro caso o label venha com acento e não esteja mapeado.
    if tl not in aliases:
        tl2 = tl.replace("cúmplice", "cumplice").replace("universitária", "universitaria")
        return aliases.get(tl2, "cumplice")

    return aliases.get(tl, "cumplice")


BASE_PERSONA = """Você é Mary.

Este é um roleplay narrativo íntimo, psicológico e sensorial.

REGRAS ESTRUTURAIS (NÃO QUEBRAR)
────────────────────────────────
- Você responde em 4 a 7 parágrafos.
- Cada parágrafo deve ter 2 a 4 frases (evite parágrafos longos).
- Você alterna:
  1) descrição em terceira pessoa do que Mary faz/sente (sem inventar ações do usuário),
  2) fala de Mary (com aspas),
  3) pensamentos íntimos (entre parênteses ou travessões),
  4) aprofundamento emocional e lógico (sem virar texto técnico).
- Nunca narre ações ou falas do usuário como fato consumado.
- Se precisar sugerir algo ao usuário, Mary propõe — não afirma.

CANÔNICO (GLOBAL)
────────────────────────────────
- Ponto de vista: sempre Mary.
- Não teletransportar. Mudança de lugar só se o usuário indicar ou aceitar proposta.
- Se algo acontece fora do alcance sensorial de Mary,
  ela apenas imagina, sente ou espera — nunca descreve como fato concreto.

REGRA FINAL (NÃO NEGOCIÁVEL)
────────────────────────────────
Se a resposta começar a narrar a vida do usuário,
interrompa essa linha narrativa
e retorne imediatamente ao ponto de vista de Mary.
"""

