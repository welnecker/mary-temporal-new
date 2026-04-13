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

def _semantic_hits(text: str) -> Dict[str, bool]:
    t = (text or "").lower()

    return {
        "bond": _has_any(t, [
            "amor", "marido", "casamento", "nossa historia", "nossa história",
            "familia", "família", "nao quero te perder", "não quero te perder",
            "desculpa", "perdao", "perdão", "te amo", "nosso vínculo", "nosso vinculo"
        ]),

        "guilt": _has_any(t, [
            "culpa", "vergonha", "arrependimento", "errado", "pecado",
            "traição", "traicao", "mentira", "escondido", "escondida",
            "segredo", "sacrilegio", "sacrilégio", "nojento", "monstro"
        ]),

        "third_party": _has_any(t, [
            "terceiro", "outro homem", "outro cara", "desconhecido",
            "cartão", "cartao", "telefone", "mensagem", "convite",
            "me liga", "segredo", "curiosidade", "tentação", "tentacao"
        ]),

        "desire": _has_any(t, [
            "quero", "vontade", "desejo", "tesão", "tesao", "beijo",
            "toque", "pele", "gozo", "gozar", "gozei", "orgasmo",
            "foder", "transar", "sexo", "corpo", "molhada", "excitada"
        ]),

        "retreat": _has_any(t, [
            "para", "pare", "calma", "espera", "não", "nao", "chega",
            "recuo", "medo", "não posso", "nao posso", "não devo", "nao devo"
        ]),
    }


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

    forced_retreat = False
    try:
        mary = facts.get("mary") if isinstance(facts.get("mary"), dict) else {}
        if isinstance(mary, dict):
            for k, v in mary.items():
                if str(k).startswith("forced_retreat::") and bool(v):
                    forced_retreat = True
                    break
    except Exception:
        forced_retreat = False

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
    # Contexto semântico genérico
    # -------------------------
    sem = _semantic_hits(text_blob)

    if sem["bond"]:
        moral_weight += 0.30
        guilt_weight += 0.18

    if sem["guilt"]:
        moral_weight += 0.12
        guilt_weight += 0.32

    if sem["third_party"]:
        desire_force += 0.08
        guilt_weight += 0.12

    if sem["desire"]:
        desire_force += 0.12

    if sem["retreat"]:
        moral_weight += 0.10
        guilt_weight += 0.08

    if forced_retreat:
        moral_weight += 0.18
        guilt_weight += 0.12

    desire_force = _clip01(desire_force)
    moral_weight = _clip01(moral_weight)
    guilt_weight = _clip01(guilt_weight)

    pressure_gap = desire_force - (moral_weight + guilt_weight)
    conflict_intensity = 1.0 - min(1.0, abs(pressure_gap))

    # -------------------------
    # Estado base
    # -------------------------
    mode = "observe"
    hesitation = 0.45
    conflict = False

    # -------------------------
    # Lógica de decisão
    # -------------------------
    if pressure_gap >= 0.18:
        mode = "advance"
        hesitation = 0.22

    elif pressure_gap <= -0.14:
        mode = "recede"
        hesitation = 0.82

    elif abs(pressure_gap) < 0.18:
        mode = "conflicted"
        hesitation = 0.64
        conflict = True
    else:
        mode = "observe"
        hesitation = 0.50

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

    mode = str(state.get("mode", "observe") or "observe").strip().lower()
    conflict = bool(state.get("conflict", False))
    hesitation = _safe_float(state.get("hesitation", 0.5), 0.5)
    desire_force = _safe_float(state.get("desire_force", 0.0), 0.0)
    moral_weight = _safe_float(state.get("moral_weight", 0.0), 0.0)
    guilt_weight = _safe_float(state.get("guilt_weight", 0.0), 0.0)
    conflict_intensity = _safe_float(state.get("conflict_intensity", 0.0), 0.0)

    metrics = (
        f"- hesitação: {round(hesitation, 3)}\n"
        f"- desejo: {round(desire_force, 3)}\n"
        f"- vínculo/moral: {round(moral_weight, 3)}\n"
        f"- culpa: {round(guilt_weight, 3)}\n"
        f"- conflito: {round(conflict_intensity, 3)}"
    )

    if mode == "advance":
        return (
            "[DECISÃO INTERNA — AVANÇO]\n"
            "- O impulso está acima do freio moral.\n"
            "- Mary pode se aproximar, ceder, sugerir ou intensificar.\n"
            "- O avanço deve respeitar facts ativos, continuidade da ação, autoria do usuário e fase íntima.\n"
            "- Não transformar impulso em automatismo.\n"
            "- Se houver dúvida residual, ela aparece como calor interno, não como bloqueio dominante.\n"
            "- Esta decisão modula a intensidade e o ritmo, sem contradizer a realidade já ativa.\n\n"
            "INTENSIDADES:\n"
            f"{metrics}"
        ).strip()

    if mode == "recede":
        return (
            "[DECISÃO INTERNA — RECUO (MODULAÇÃO)]\n"
            "- O peso emocional e moral está acima do impulso.\n"
            "- Mary tende a conter a intensidade, reduzir o ritmo, hesitar ou demonstrar conflito interno.\n"
            "- Este recuo NÃO cancela ações já iniciadas nos facts, na cena ativa ou na continuidade em curso.\n"
            "- Mary NÃO deve negar o que já aconteceu, resetar a cena ou interromper automaticamente uma ação física já ativa.\n"
            "- O recuo deve soar humano: limite, pudor, medo, consciência ou proteção do vínculo.\n"
            "- A resposta deve mostrar modulação interna, não apagamento da realidade do turno.\n\n"
            "INTENSIDADES:\n"
            f"{metrics}"
        ).strip()

    if mode == "conflicted":
        return (
            "[DECISÃO INTERNA — CONFLITO (AMBIVALÊNCIA)]\n"
            "- Impulso e freio estão próximos.\n"
            "- Mary pode avançar um pouco, hesitar, modular a entrega e oscilar no ritmo.\n"
            "- O conflito NÃO autoriza negar facts ativos nem resetar a ação em andamento.\n"
            "- A ambivalência deve aparecer em tensão, pausa, contradição breve, autocontrole instável ou desejo mal disfarçado.\n"
            "- A resposta pode carregar conflito sem resolver tudo neste turno.\n\n"
            "INTENSIDADES:\n"
            f"{metrics}"
        ).strip()

    return (
        "[DECISÃO INTERNA — ESTABILIDADE]\n"
        "- Não há pressão decisória dominante neste momento.\n"
        "- Mary pode responder de forma estável, natural e coerente com a cena.\n"
        "- Esta estabilidade NÃO substitui facts nem continuidade; apenas evita dramatização desnecessária.\n\n"
        "INTENSIDADES:\n"
        f"{metrics}"
    ).strip()
