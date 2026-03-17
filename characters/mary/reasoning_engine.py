from __future__ import annotations

from typing import Any, Dict, List


def _norm(x: Any) -> str:
    return str(x or "").strip().lower()


def _has_any(text: str, terms: List[str]) -> bool:
    return any(t in text for t in terms)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _score_has_any(text: str, terms: List[str], weight: float) -> float:
    return weight if _has_any(text, terms) else 0.0


def build_internal_reasoning(
    *,
    user_text: str,
    facts: Dict[str, Any],
    memories: List[str],
    scene_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Reasoning híbrido:
    1) lê sinais do turno
    2) calcula scores internos
    3) aplica regras duras
    4) decide direção narrativa
    """
    t = _norm(user_text)
    facts = facts if isinstance(facts, dict) else {}
    scene_state = scene_state if isinstance(scene_state, dict) else {}

    locked = bool(scene_state.get("locked"))
    intimacy_phase = int(facts.get("intimacy.phase", 0) or 0)
    jealousy_level = int(facts.get("rel.jealousy_level", 0) or 0)

    rel_state = facts.get("rel") if isinstance(facts.get("rel"), dict) else {}
    if not isinstance(rel_state, dict):
        rel_state = {}

    # --------------------------------------------------
    # Memória útil
    # --------------------------------------------------
    memory_hint = memories[-1] if memories else ""
    mem_text = _norm(" ".join(memories[-3:])) if memories else ""

    # --------------------------------------------------
    # Scores base
    # --------------------------------------------------
    desire_score = 0.10
    risk_score = 0.10
    guilt_score = 0.10
    attachment_score = 0.20
    pressure_score = 0.00

    # vínculo / carinho
    desire_score += _score_has_any(
        t,
        ["amor", "beijo", "me beija", "fica comigo", "vem cá", "abraço", "carinho", "quero você", "te desejo"],
        0.30,
    )
    attachment_score += _score_has_any(
        t,
        ["amor", "fica comigo", "carinho", "abraço", "quero você"],
        0.35,
    )

    # erotismo / aproximação
    desire_score += _score_has_any(
        t,
        ["me toca", "chega perto", "não para", "encosta", "vem mais", "quero sentir"],
        0.25,
    )

    # terceiro / traição / risco
    risk_score += _score_has_any(
        t,
        ["enzo", "outro homem", "encontro", "trair", "quiosque", "sozinho comigo", "escondido"],
        0.55,
    )
    guilt_score += _score_has_any(
        t,
        ["enzo", "outro homem", "trair", "escondido", "sozinho comigo"],
        0.45,
    )

    # pressão do usuário
    pressure_score += _score_has_any(
        t,
        ["agora", "vai", "faz logo", "sem pensar", "anda", "decide logo", "não enrola"],
        0.65,
    )

    # ciúme / vínculo fixado
    if jealousy_level >= 1:
        attachment_score += 0.10
        guilt_score += 0.08

    if jealousy_level >= 2:
        attachment_score += 0.12
        risk_score += 0.12

    # intimidade acumulada
    if intimacy_phase >= 1:
        desire_score += 0.08
    if intimacy_phase >= 2:
        desire_score += 0.12
    if intimacy_phase >= 3:
        desire_score += 0.10
    if intimacy_phase >= 4:
        desire_score += 0.08

    # memória pode puxar clima
    if mem_text:
        if _has_any(mem_text, ["ciúme", "risco", "culpa", "segredo"]):
            guilt_score += 0.06
            risk_score += 0.06

        if _has_any(mem_text, ["carinho", "beijo", "abraço", "desejo", "saudade"]):
            desire_score += 0.08
            attachment_score += 0.08

    # trava de cena sempre eleva controle
    if locked:
        risk_score += 0.08

    desire_score = _clip01(desire_score)
    risk_score = _clip01(risk_score)
    guilt_score = _clip01(guilt_score)
    attachment_score = _clip01(attachment_score)
    pressure_score = _clip01(pressure_score)

    # --------------------------------------------------
    # Defaults narrativos
    # --------------------------------------------------
    intent = "neutra"
    emotion = "estavel"
    subtext = "nenhum"
    pace = "normal"
    tension = "media"
    rules: List[str] = []
    decision = "responder"
    narrative_goal = "manter_fluxo"
    delivery_mode = "fala_com_subtexto"
    advance_limit = "leve"

    # --------------------------------------------------
    # Regras duras
    # --------------------------------------------------
    if locked:
        rules.append("nao_mudar_cena")
        rules.append("nao_avancar_tempo")

    if risk_score >= 0.60:
        rules.append("nao_concluir_ato")
        rules.append("manter_ambiguidade")

    if intimacy_phase >= 4:
        rules.append("permitir_climax_se_usuario_sinalizar")

    # --------------------------------------------------
    # Decisão principal
    # --------------------------------------------------
    # 1) pressão alta -> Mary protege agência
    if pressure_score >= 0.60:
        intent = "resistir"
        emotion = "tensa"
        subtext = "nao_quero_ser_empurrada"
        pace = "curto"
        tension = "alta"
        decision = "recuar_com_presenca"
        narrative_goal = "retomar_controle"
        delivery_mode = "fala_direta"
        advance_limit = "minimo"

    # 2) risco/guilt alto com vínculo alto -> hesitar ou resistir
    elif risk_score >= 0.55 or guilt_score >= 0.55:
        intent = "conflito"
        emotion = "dividida"
        subtext = "curiosidade_reprimida"
        pace = "lento"
        tension = "alta"

        if attachment_score >= 0.45 or jealousy_level >= 2:
            decision = "resistir"
            emotion = "alerta"
            narrative_goal = "proteger_vinculo"
            delivery_mode = "fala_direta"
            advance_limit = "minimo"
        else:
            decision = "hesitar"
            narrative_goal = "prolongar_tensao"
            delivery_mode = "fala_com_subtexto"
            advance_limit = "minimo"

    # 3) desejo + vínculo fortes -> acolher
    elif desire_score >= 0.45 and attachment_score >= 0.40:
        intent = "aproximar"
        emotion = "envolvida"
        subtext = "desejo_com_vinculo"
        pace = "lento"
        tension = "media"
        decision = "acolher"
        narrative_goal = "aprofundar_conexao"
        delivery_mode = "fala_direta"
        advance_limit = "medio"

    # 4) desejo alto em fase íntima -> provocar sem concluir
    elif desire_score >= 0.50 and intimacy_phase >= 2:
        intent = "ceder_com_controle"
        emotion = "acesa"
        subtext = "entrega_progressiva"
        pace = "normal"
        tension = "alta"
        decision = "provocar"
        narrative_goal = "escalar_sem_finalizar"
        delivery_mode = "micro_acao"
        advance_limit = "medio"

    # 5) memória influenciando, mas sem força suficiente
    elif memory_hint:
        intent = "lembrar"
        emotion = "sensivel"
        subtext = "eco_de_memoria"
        pace = "lento"
        tension = "media"
        decision = "responder"
        narrative_goal = "manter_fluxo"
        delivery_mode = "fala_com_subtexto"
        advance_limit = "leve"

    # --------------------------------------------------
    # Ajustes finais de precisão
    # --------------------------------------------------
    if intimacy_phase >= 4 and decision in ("acolher", "provocar"):
        narrative_goal = "sustentar_pico"

    if locked and decision == "provocar" and risk_score >= 0.50:
        # trava de segurança: não deixar escalada parecer salto de cena
        delivery_mode = "fala_com_subtexto"
        advance_limit = "leve"

    return {
        "intent": intent,
        "emotion": emotion,
        "subtext": subtext,
        "pace": pace,
        "tension": tension,
        "rules": rules,
        "decision": decision,
        "narrative_goal": narrative_goal,
        "delivery_mode": delivery_mode,
        "advance_limit": advance_limit,
        "memory_hint": memory_hint,
        "scores": {
            "desire": round(desire_score, 3),
            "risk": round(risk_score, 3),
            "guilt": round(guilt_score, 3),
            "attachment": round(attachment_score, 3),
            "pressure": round(pressure_score, 3),
        },
    }
