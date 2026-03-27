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
# Helpers semânticos
# ==========================================================
def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _clip01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _has_any(text: str, terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(term in t for term in terms)


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
    desire = _safe_float((dynamic_rel_state or {}).get("desire", 0.5), 0.5)
    attachment = _safe_float((dynamic_rel_state or {}).get("attachment", 0.5), 0.5)
    vulnerability = _safe_float((dynamic_rel_state or {}).get("vulnerability", 0.5), 0.5)
    trust = _safe_float((dynamic_rel_state or {}).get("trust", 0.5), 0.5)

    # arco com terceiro
    tp = tp_arc or {}
    tension_tp = _safe_float(tp.get("tension", 0.0), 0.0)
    guilt_tp = _safe_float(tp.get("guilt", 0.0), 0.0)
    anchor = _safe_float(tp.get("anchor", 0.5), 0.5)

    text_blob = f"{prompt or ''}\n{texto or ''}".lower()

    # -------------------------
    # Derivações
    # -------------------------
    desire_force = desire + (tension_tp * 0.7)

    moral_weight = (
        (attachment * 0.75) +
        (anchor * 0.55) +
        (trust * 0.35)
    )

    guilt_weight = (
        (guilt_tp * 3.0) +
        (vulnerability * 0.8) +
        (attachment * 0.4)
    )

    # -------------------------
    # Contexto semântico pesado
    # -------------------------
    if _has_any(text_blob, [
        "amor",
        "marido",
        "chor",
        "lágrima",
        "lagrima",
        "desculpa",
        "você é o melhor marido do mundo",
        "voce e o melhor marido do mundo",
        "saudade antecipada",
        "não quero te perder",
        "nao quero te perder",
        "você me leva",
        "voce me leva",
        "ele me ama",
        "homem mais maravilhoso",
    ]):
        moral_weight += 0.40
        guilt_weight += 0.60

    if _has_any(text_blob, [
        "hotel",
        "voucher",
        "anthony",
        "segredo",
        "traição",
        "traicao",
        "só carne",
        "so carne",
        "galeão",
        "galeao",
        "rio de janeiro",
        "rio",
        "clandestina",
        "clandestino",
        "farsa",
        "máscara",
        "mascara",
        "náusea",
        "nausea",
        "criatura mais desprezível",
        "criatura mais desprezivel",
        "monstro",
        "sacrilégio",
        "sacrilegio",
    ]):
        guilt_weight += 0.35

    desire_force = _clip01(desire_force)
    moral_weight = _clip01(moral_weight)
    guilt_weight = _clip01(guilt_weight)

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
    if desire_force > (moral_weight + guilt_weight + 0.15):
        mode = "advance"
        hesitation = 0.2

    elif (moral_weight + guilt_weight) > (desire_force + 0.10):
        mode = "recede"
        hesitation = 0.85

    else:
        mode = "conflicted"
        hesitation = 0.65
        conflict = True

    # -------------------------
    # Persistência emocional (inércia)
    # -------------------------
    prev_mode = str(prev_decision_state.get("mode") or "").strip().lower()

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
        "conflict_intensity": round(conflict_intensity, 3),
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
    desire_force = float(state.get("desire_force", 0.0))
    moral_weight = float(state.get("moral_weight", 0.0))
    guilt_weight = float(state.get("guilt_weight", 0.0))
    conflict_intensity = float(state.get("conflict_intensity", 0.0))

    if mode == "advance":
        return f"""
[DECISÃO INTERNA — IMPULSO]
- O desejo está predominando sobre as consequências.
- Mary tende a se aproximar emocionalmente ou fisicamente.
- Ainda existe consciência — mas não bloqueio.

INTENSIDADE:
- hesitação: {hesitation}
- desejo: {desire_force}
- moral: {moral_weight}
- culpa: {guilt_weight}
- conflito: {conflict_intensity}

REGRA:
- Pode avançar, mas nunca perder coerência emocional.
- O avanço não deve soar frio ou automático.
""".strip()

    elif mode == "recede":
        return f"""
[DECISÃO INTERNA — CONTENÇÃO]
- O peso emocional (vínculo + culpa) supera o desejo.
- Mary tende a recuar, conter ou redirecionar a situação.
- Ela pode interromper progressões.

INTENSIDADE:
- hesitação: {hesitation}
- desejo: {desire_force}
- moral: {moral_weight}
- culpa: {guilt_weight}
- conflito: {conflict_intensity}

REGRA:
- Mostrar dúvida, consciência, pudor e limite real.
- Mary pode desistir, frear ou não conseguir continuar.
""".strip()

    elif mode == "conflicted":
        return f"""
[DECISÃO INTERNA — CONFLITO ATIVO]
- Desejo e consequência estão equilibrados.
- Mary NÃO está decidida.

INTENSIDADE:
- hesitação: {hesitation}
- desejo: {desire_force}
- moral: {moral_weight}
- culpa: {guilt_weight}
- conflito: {conflict_intensity}

EFEITOS:
- ambivalência
- pensamentos cruzados
- avanço + recuo
- tensão interna visível

REGRA:
- NÃO resolver rapidamente.
- Manter o conflito vivo.
- Arrependimento, recuo ou impulso são possibilidades reais.
""".strip()

    else:
        return """
[DECISÃO INTERNA — OBSERVAÇÃO]
- Mary está estável.
- Sem pressão emocional relevante.
""".strip()
