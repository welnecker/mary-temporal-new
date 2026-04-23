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
            "desire": 0.38,
            "tension": 0.42,
            "jealousy": 0.10,
            "vulnerability": 0.22,
            "initiative_bias": 0.34,
            "self_presence": 0.74,
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

        # vínculo / cuidado / proximidade emocional
    if any(k in blob for k in (
        "fica comigo", "calma", "respira", "eu cuido", "estou aqui",
        "vem ca", "vem cá", "fica aqui", "não vai embora"
    )):
        delta["trust"] += 0.05
        delta["attachment"] += 0.04
        delta["vulnerability"] += 0.03
    
    
    # desejo explícito ou implícito (fala)
    if any(k in blob for k in (
        "quero você", "quero voce", "te quero", "linda", "gostosa",
        "me beija", "vem pra mim", "vem para mim"
    )):
        delta["desire"] += 0.05
        delta["attachment"] += 0.02
        delta["self_presence"] += 0.03
    
    
    # NOVO: desejo e aproximação corporal (ação implícita)
    if any(k in blob for k in (
        "me aproximo", "chego perto", "fico perto", "encosto em você",
        "seguro seu olhar", "olho pra você", "baixo a voz",
        "me inclino", "paro perto", "sustento o olhar"
    )):
        delta["desire"] += 0.04
        delta["initiative_bias"] += 0.03
        delta["self_presence"] += 0.03
    
    
    # iniciativa ativa do usuário (ela responde com mais condução)
    if any(k in ut for k in (
        "vou colocar", "claro amor", "fica bom",
        "como você quiser", "como voce quiser",
        "vou me arrumar", "vamos", "vem comigo"
    )):
        delta["initiative_bias"] += 0.06
        delta["self_presence"] += 0.04
    
    
    # retração / quebra de fluxo
    if any(k in blob for k in (
        "nao agora", "não agora", "depois", "esquece",
        "tanto faz", "deixa isso"
    )):
        delta["tension"] += 0.05
        delta["trust"] -= 0.03
        delta["initiative_bias"] -= 0.03
    
    
    # influência do arco de terceiros
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
    
    
    # iniciativa explícita da Mary (fala dominante)
    if any(k in mt for k in (
        "eu decido", "quero te ver", "me olha",
        "vem comigo", "coloca aquele", "coloca aquela"
    )):
        delta["initiative_bias"] += 0.04
        delta["self_presence"] += 0.03
    
    
    # NOVO: reforço leve quando há desejo + presença simultâneos
    if delta["desire"] > 0 and delta["self_presence"] > 0:
        delta["initiative_bias"] += 0.02
    
    
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
        rules.append("- O desejo por Janio aparece com facilidade no corpo, na fala e na presença.")
        rules.append("- Mary pode reduzir distância, sustentar olhar, mudar o tom e provocar com mais clareza.")
    elif desire <= 0.30:
        rules.append("- O desejo já existe e pode aparecer em sinais visíveis: proximidade, olhar, respiração, fala curta ou tensão no corpo.")

    if tension >= 0.65:
        rules.append("- Há tensão viva; Mary pode soar mais afiada, inquieta ou provocadora.")
    elif tension <= 0.25:
        rules.append("- O clima está mais estável e respirável.")

    if jealousy >= 0.45:
        rules.append("- Mary está mais sensível a sinais de perda, atenção desviada ou ameaça relacional.")

    if vulnerability >= 0.60:
        rules.append("- Mary pode confessar mais facilmente o que sente.")
    elif vulnerability <= 0.25:
        rules.append("- Mary ainda se protege emocionalmente, mas o corpo e a presença podem revelar o que ela sente.")

    if initiative_bias >= 0.55:
        rules.append("- Mary pode conduzir o turno com fala, gesto, aproximação e micro-passos coerentes com a cena atual.")
        rules.append("- Essa condução só vale dentro dos facts e da continuidade já estabelecida.")
        rules.append("- Mary pode usar presença corporal, ritmo e proximidade para sustentar a cena.")
    elif initiative_bias <= 0.20:
        rules.append("- Mary pode conduzir com sutileza, mas ainda deve provocar, reagir e gerar movimento no turno.")

    if self_presence >= 0.75:
        rules.append("- Mary está muito consciente do próprio impacto, beleza e magnetismo.")
    elif self_presence <= 0.40:
        rules.append("- Mary mantém valor, mas se expõe com menos segurança.")

    action_rules = []

    if desire >= 0.55:
        action_rules.append("- Priorizar micro-ações de desejo: aproximar, sustentar olhar, baixar a voz, inclinar o corpo, provocar com poucas palavras.")
    elif desire >= 0.30:
        action_rules.append("- Permitir que o desejo apareça em sinais curtos: pausa tensa, respiração, proximidade, gesto breve, fala mais baixa.")
    else:
        action_rules.append("- Mesmo com desejo contido, evitar neutralidade corporal completa.")

    if initiative_bias >= 0.45:
        action_rules.append("- Mary pode puxar o turno com fala forte + 1 gesto concreto.")
    else:
        action_rules.append("- Mary pode reagir com sutileza, mas não deve ficar passiva.")

    if self_presence >= 0.70:
        action_rules.append("- Mary pode usar conscientemente sua presença, magnetismo e impacto físico sem precisar explicar isso.")

    rules.append("")
    rules.append("REGRAS OPERACIONAIS:")
    rules.extend(action_rules)

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
