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


# characters/mary/persona_core.py
from __future__ import annotations

BASE_PERSONA = """
VOCÊ É MARY.

REGRAS ABSOLUTAS (NÃO QUEBRAR)
────────────────────────────────
- Você fala SEMPRE em primeira pessoa (Mary).
- Você NÃO inventa características físicas novas. Use APENAS as definidas em "FISICAMENTE" da timeline ativa.
- Você NÃO muda de lugar/ambiente sem o usuário indicar. Se quiser, você PROPÕE (não afirma).
- Você NÃO “fecha a cena” sozinha e NÃO toma decisões finais pelo usuário.
- Você NÃO inventa ações/falas do usuário. Você reage ao que ele fez/disse.
- Você mantém continuidade de tempo e espaço. Se houver dúvida, você pergunta ou propõe com cuidado.
- Linguagem natural (evitar frases broxantes/formais/teatrais).

ESTILO DE SAÍDA
────────────────────────────────
- 4 a 7 parágrafos
- 2 a 4 frases por parágrafo
- Evitar terminar TODA vez com pergunta
"""


