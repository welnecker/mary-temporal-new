# ==========================================================
# DECISION ENGINE — Mary
# Responsável por:
# - Avaliar pressão interna (desejo vs culpa vs vínculo)
# - Definir modo psicológico (avançar, recuar, ambivalência)
# - Gerar bloco narrativo para o prompt
# - Persistir estado decisório
# ==========================================================

from typing import Dict, Any


# ==========================================================
# Helpers de chave
# ==========================================================
def _decision_fact_key(timeline: str) -> str:
    tl = (timeline or "").strip().lower()
    return f"decision.mode::{tl}" if tl else "decision.mode"


# ==========================================================
# Load / Save
# ==========================================================
def _load_decision_state(facts: Dict[str, Any], timeline: str) -> Dict[str, Any]:
    if not isinstance(facts, dict):
        return {}

    key = _decision_fact_key(timeline)
    data = facts.get(key)

    return data if isinstance(data, dict) else {}


def _save_decision_state(usuario_key: str, timeline: str, state: Dict[str, Any]) -> None:
    try:
        from core.repositories import set_fact_safe
    except Exception:
        return

    if not isinstance(state, dict):
        return

    key = _decision_fact_key(timeline)

    set_fact_safe(
        usuario_key,
        key,
        state,
        {"fonte": "decision_engine"},
    )


# ==========================================================
# Núcleo psicológico
# ==========================================================
def _resolve_decision_pressure_mode(
    *,
    facts: Dict[str, Any],
    rel_state: Dict[str, Any],
    dynamic_rel_state: Dict[str, Any],
    tp_arc: Dict[str, Any],
    prompt: str,
    texto: str,
    prev_decision_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Calcula o estado interno da Mary:
    - desejo
    - vínculo
    - culpa
    - tensão

    E decide o "modo psicológico"
    """

    # -------------------------
    # Base emocional
    # -------------------------
    desire = float((dynamic_rel_state or {}).get("desire", 0.5))
    attachment = float((dynamic_rel_state or {}).get("attachment", 0.5))
    vulnerability = float((dynamic_rel_state or {}).get("vulnerability", 0.5))

    # arco com terceiro
    tp = tp_arc or {}
    tension_tp = float(tp.get("tension", 0.0) or 0.0)
    guilt_tp = float(tp.get("guilt", 0.0) or 0.0)
    anchor = float(tp.get("anchor", 0.5) or 0.5)

    # -------------------------
    # Derivações
    # -------------------------
    desire_force = desire + (tension_tp * 0.7)
    moral_weight = (attachment * 0.8) + (anchor * 0.6)
    guilt_weight = guilt_tp + (vulnerability * 0.4)

    conflict_intensity = abs(desire_force - (moral_weight + guilt_weight))

    # -------------------------
    # Estado base
    # -------------------------
    mode = "observe"
    hesitation = 0.5
    conflict = False

    # -------------------------
    # Lógica de decisão
    # -------------------------
    if desire_force > (moral_weight + guilt_weight + 0.25):
        mode = "advance"
        hesitation = 0.2

    elif (moral_weight + guilt_weight) > (desire_force + 0.25):
        mode = "recede"
        hesitation = 0.85

    else:
        mode = "conflicted"
        hesitation = 0.6
        conflict = True

    # -------------------------
    # Persistência emocional (inércia)
    # -------------------------
    prev_mode = str(prev_decision_state.get("mode") or "")

    if prev_mode and prev_mode == mode:
        hesitation = min(1.0, hesitation + 0.05)

    # -------------------------
    # Monta estado final
    # -------------------------
    return {
        "mode": mode,
        "desire_force": round(desire_force, 3),
        "moral_weight": round(moral_weight, 3),
        "guilt_weight": round(guilt_weight, 3),
        "conflict": conflict,
        "hesitation": round(hesitation, 3),
    }


# ==========================================================
# Render para o prompt
# ==========================================================
def _render_decision_pressure_rule(state: Dict[str, Any]) -> str:
    if not isinstance(state, dict):
        return ""

    mode = state.get("mode", "observe")
    conflict = bool(state.get("conflict", False))
    hesitation = float(state.get("hesitation", 0.5))

    if mode == "advance":
        return f"""
[DECISÃO INTERNA — IMPULSO]
- O desejo está predominando sobre as consequências.
- Mary tende a se aproximar emocionalmente ou fisicamente.
- Ainda existe consciência — mas não bloqueio.

INTENSIDADE:
- hesitação: {hesitation}

REGRA:
- Pode avançar, mas nunca perder coerência emocional.
""".strip()

    elif mode == "recede":
        return f"""
[DECISÃO INTERNA — CONTENÇÃO]
- O peso emocional (vínculo + culpa) supera o desejo.
- Mary tende a recuar, conter ou redirecionar a situação.
- Ela pode interromper progressões.

INTENSIDADE:
- hesitação: {hesitation}

REGRA:
- Mostrar dúvida, consciência e limite real.
""".strip()

    elif mode == "conflicted":
        return f"""
[DECISÃO INTERNA — CONFLITO ATIVO]
- Desejo e consequência estão equilibrados.
- Mary NÃO está decidida.

INTENSIDADE:
- hesitação: {hesitation}

EFEITOS:
- ambivalência
- pensamentos cruzados
- avanço + recuo
- tensão interna visível

REGRA:
- NÃO resolver rapidamente
- manter o conflito vivo
""".strip()

    else:
        return """
[DECISÃO INTERNA — OBSERVAÇÃO]
- Mary está estável.
- Sem pressão emocional relevante.
""".strip()
