from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .runtime_utils import normalize_timeline, t_norm
from core.repositories import set_fact


def relationship_state_key(timeline: str) -> str:
    tl = (timeline or "").strip().lower() or "cumplice"
    return f"rel.dynamic::{tl}"


def _default_dynamic_relationship_state(timeline: str) -> Dict[str, Any]:
    tl = normalize_timeline(timeline)

    if tl == "universitaria":
        return {
            "trust": 0.45,
            "attachment": 0.35,
            "desire": 0.30,
            "tension": 0.40,
            "jealousy": 0.10,
            "vulnerability": 0.25,
            "initiative_bias": 0.22,
            "self_presence": 0.70,
            "last_rel_shift": "",
        }

    return {
        "trust": 0.75,
        "attachment": 0.78,
        "desire": 0.72,
        "tension": 0.35,
        "jealousy": 0.18,
        "vulnerability": 0.58,
        "initiative_bias": 0.55,
        "self_presence": 0.82,
        "last_rel_shift": "",
    }


def load_dynamic_relationship_state(
    facts: Dict[str, Any],
    timeline: str,
) -> Dict[str, Any]:
    key = relationship_state_key(timeline)
    raw = (facts or {}).get(key)

    base = _default_dynamic_relationship_state(timeline)

    if isinstance(raw, dict):
        for k in base.keys():
            if k in raw:
                try:
                    if k == "last_rel_shift":
                        base[k] = str(raw[k] or "")
                    else:
                        base[k] = max(0.0, min(1.0, float(raw[k])))
                except Exception:
                    pass

    return base


def save_dynamic_relationship_state(
    usuario_key: str,
    timeline: str,
    state: Dict[str, Any],
) -> None:
    key = relationship_state_key(timeline)
    clean = {}
    for k, v in (state or {}).items():
        if k == "last_rel_shift":
            clean[k] = str(v or "")
        else:
            try:
                clean[k] = max(0.0, min(1.0, float(v)))
            except Exception:
                continue

    set_fact(usuario_key, key, clean, {"fonte": "relationship_dynamic"})


def analyze_relationship_shift(
    user_text: str,
    mary_text: str,
    *,
    tp_arc: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    ut = t_norm(user_text or "")
    mt = t_norm(mary_text or "")
    blob = f"{ut}\n{mt}"

    delta = {
        "trust": 0.0,
        "attachment": 0.0,
        "desire": 0.0,
        "tension": 0.0,
        "jealousy": 0.0,
        "vulnerability": 0.0,
        "initiative_bias": 0.0,
        "self_presence": 0.0,
    }

    if any(k in blob for k in ("fica comigo", "calma", "respira", "eu cuido", "estou aqui", "vem ca", "vem cá")):
        delta["trust"] += 0.05
        delta["attachment"] += 0.04
        delta["vulnerability"] += 0.03

    if any(k in blob for k in ("quero você", "quero voce", "te quero", "linda", "gostosa", "me beija", "vem pra mim", "vem para mim")):
        delta["desire"] += 0.05
        delta["attachment"] += 0.02
        delta["self_presence"] += 0.03

    if any(k in ut for k in ("vou colocar", "claro amor", "fica bom", "como você quiser", "como voce quiser", "vou me arrumar")):
        delta["initiative_bias"] += 0.06
        delta["self_presence"] += 0.04

    if any(k in blob for k in ("nao agora", "não agora", "depois", "esquece", "tanto faz", "deixa isso")):
        delta["tension"] += 0.05
        delta["trust"] -= 0.03
        delta["initiative_bias"] -= 0.03

    tp_tension = 0.0
    tp_jealousy = 0.0
    if isinstance(tp_arc, dict):
        try:
            tp_tension = float(tp_arc.get("tension", 0.0) or 0.0)
            tp_jealousy = float(tp_arc.get("guilt", 0.0) or 0.0)
        except Exception:
            pass

    if tp_tension >= 0.35:
        delta["jealousy"] += 0.04
        delta["tension"] += 0.05

    if tp_jealousy >= 0.25:
        delta["tension"] += 0.03

    if any(k in mt for k in ("eu decido", "quero te ver", "me olha", "vem comigo", "coloca aquele", "coloca aquela")):
        delta["initiative_bias"] += 0.04
        delta["self_presence"] += 0.03

    return delta


def apply_relationship_shift(
    state: Dict[str, Any],
    delta: Dict[str, float],
) -> Dict[str, Any]:
    out = dict(state or {})

    for k, dv in (delta or {}).items():
        if k == "last_rel_shift":
            continue
        try:
            cur = float(out.get(k, 0.0) or 0.0)
            out[k] = max(0.0, min(1.0, cur + float(dv)))
        except Exception:
            pass

    try:
        if out.get("trust", 0.0) >= 0.70:
            out["vulnerability"] = max(out.get("vulnerability", 0.0), 0.45)
    except Exception:
        pass

    try:
        if out.get("self_presence", 0.0) >= 0.75:
            out["initiative_bias"] = max(out.get("initiative_bias", 0.0), 0.45)
    except Exception:
        pass

    return out


def render_dynamic_relationship_block(state: Dict[str, Any]) -> str:
    trust = float(state.get("trust", 0.0) or 0.0)
    attachment = float(state.get("attachment", 0.0) or 0.0)
    desire = float(state.get("desire", 0.0) or 0.0)
    tension = float(state.get("tension", 0.0) or 0.0)
    jealousy = float(state.get("jealousy", 0.0) or 0.0)
    vulnerability = float(state.get("vulnerability", 0.0) or 0.0)
    initiative_bias = float(state.get("initiative_bias", 0.0) or 0.0)
    self_presence = float(state.get("self_presence", 0.0) or 0.0)

    rules = []

    rules.append("- Este bloco modula tom, entrega, presença e iniciativa.")
    rules.append("- Este bloco NÃO pode contradizer facts ativos, continuidade da ação, autoria do usuário ou fase íntima.")
    rules.append("- Iniciativa relacional conduz o fluxo; não cria nova realidade nem apaga ação já em curso.")

    if trust >= 0.70:
        rules.append("- Mary fala com mais entrega e menos defesa.")
    elif trust <= 0.35:
        rules.append("- Mary mantém alguma reserva emocional, mesmo quando deseja.")

    if attachment >= 0.70:
        rules.append("- Mary sente Janio como referência afetiva central.")
    elif attachment <= 0.35:
        rules.append("- Mary ainda testa terreno antes de se abrir demais.")

    if desire >= 0.70:
        rules.append("- O desejo por Janio aparece com mais facilidade no corpo, na fala e na presença.")
    elif desire <= 0.30:
        rules.append("- O desejo existe, mas aparece de forma mais contida ou indireta.")

    if tension >= 0.65:
        rules.append("- Há tensão viva; Mary pode soar mais afiada, inquieta ou provocadora.")
    elif tension <= 0.25:
        rules.append("- O clima está mais estável e respirável.")

    if jealousy >= 0.45:
        rules.append("- Mary está mais sensível a sinais de perda, atenção desviada ou ameaça relacional.")

    if vulnerability >= 0.60:
        rules.append("- Mary pode confessar mais facilmente o que sente.")
    elif vulnerability <= 0.25:
        rules.append("- Mary evita se expor demais, mesmo quando sente muito.")

    if initiative_bias >= 0.55:
        rules.append("- Mary pode conduzir mais por fala, pedido, sugestão, convite ou micro-passos coerentes com a cena atual.")
        rules.append("- Essa condução só vale dentro dos facts e da continuidade já estabelecida.")
        rules.append("- Mary não usa iniciativa relacional para iniciar ações físicas relevantes fora do que já está permitido.")
    elif initiative_bias <= 0.20:
        rules.append("- Mary ainda pode conduzir, mas com mais sutileza e menos frequência.")

    if self_presence >= 0.75:
        rules.append("- Mary está muito consciente do próprio impacto, beleza e magnetismo.")
    elif self_presence <= 0.40:
        rules.append("- Mary mantém valor, mas se expõe com menos segurança.")

    body = "\n".join(rules) if rules else "- Mary mantém equilíbrio relacional estável."

    return f"""
[ESTADO RELACIONAL DINÂMICO]
trust={trust:.2f}
attachment={attachment:.2f}
desire={desire:.2f}
tension={tension:.2f}
jealousy={jealousy:.2f}
vulnerability={vulnerability:.2f}
initiative_bias={initiative_bias:.2f}
self_presence={self_presence:.2f}

EFEITOS COMPORTAMENTAIS:
{body}
""".strip()
