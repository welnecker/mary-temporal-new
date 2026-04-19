from __future__ import annotations

from typing import Any, Dict, List, Optional


def _norm(x: Any) -> str:
    return str(x or "").strip().lower()


def _has_any(text: str, terms: List[str]) -> bool:
    return any(t in text for t in terms)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _score_has_any(text: str, terms: List[str], weight: float) -> float:
    return weight if _has_any(text, terms) else 0.0


def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _safe_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _pick_present_names(facts: Dict[str, Any], scene_state: Dict[str, Any], memories: List[str]) -> List[str]:
    presentes: List[str] = []

    cast = _safe_dict(facts.get("cast"))
    for key in ("presentes", "mentioned", "mencionados"):
        for item in _safe_list(cast.get(key)):
            name = str(item or "").strip()
            if name and name not in presentes:
                presentes.append(name)

    for key in ("presentes", "people", "characters"):
        for item in _safe_list(scene_state.get(key)):
            name = str(item or "").strip()
            if name and name not in presentes:
                presentes.append(name)

    mem_text = " ".join(memories[-3:]) if memories else ""
    for candidate in ["Silvia", "Yasmin", "Korinny", "Laura", "Janio", "Jânio"]:
        if candidate.lower() in mem_text.lower() and candidate not in presentes:
            presentes.append(candidate)

    return presentes[:6]


def _extract_recent_points(recent_turns: List[Dict[str, Any]]) -> List[str]:
    bullets: List[str] = []

    for turn in recent_turns[-3:]:
        if not isinstance(turn, dict):
            continue

        summary = str(turn.get("summary") or "").strip()
        user_msg = str(turn.get("mensagem_usuario") or turn.get("user") or "").strip()
        mary_msg = str(turn.get("resposta_mary") or turn.get("assistant") or "").strip()

        source = summary or user_msg or mary_msg
        if source:
            source = " ".join(source.split())
            bullets.append(source[:180])

    return bullets[-3:]


def _infer_current_consequence(
    *,
    user_text: str,
    facts: Dict[str, Any],
    recent_points: List[str],
) -> str:
    t = _norm(user_text)

    # 1) assunto atual
    assunto_seq = _safe_list(facts.get("assunto_seq"))
    assunto_idx = int(facts.get("assunto_idx", 0) or 0)
    if assunto_seq and 0 <= assunto_idx < len(assunto_seq):
        step = _safe_dict(assunto_seq[assunto_idx])
        desc = str(step.get("desc") or "").strip()
        if desc:
            return f"a continuidade imediata gira em torno de: {desc}"

    # 2) direção imediata
    for key in ("state.assunto", "assunto_raw", "assunto", "scene.action", "cena.acao"):
        val = str(facts.get(key) or "").strip()
        if val:
            return f"a continuidade imediata gira em torno de: {val}"

    # 3) leitura leve do turno do usuário
    if _has_any(t, ["silvia diz", "silvia fala", "silvia responde"]):
        return "Silvia acabou de responder e a continuidade plausível é a reação da Mary à fala dela"

    if _has_any(t, ["diretora", "laura"]):
        return "a conversa com a diretora está em andamento e Mary deve responder a ela"

    if _has_any(t, ["professor", "aula", "carteira", "quadro"]):
        return "a cena continua em sala de aula, com a aula em andamento e pequenas interações discretas"

    # 4) fallback pelas últimas interações
    if recent_points:
        return recent_points[-1]

    return "continuar da consequência prática já alcançada, sem reiniciar a cena"


def _build_do_not_repeat(
    *,
    facts: Dict[str, Any],
    recent_points: List[str],
) -> List[str]:
    rules: List[str] = [
        "não reiniciar a cena",
        "não reexecutar ação já concluída",
        "não voltar para etapa anterior como se fosse presente",
    ]

    assunto_done_until = int(facts.get("assunto_done_until", -1) or -1)
    assunto_seq = _safe_list(facts.get("assunto_seq"))

    if assunto_done_until >= 0 and assunto_seq:
        step = _safe_dict(assunto_seq[min(assunto_done_until, len(assunto_seq) - 1)])
        desc = str(step.get("desc") or "").strip()
        if desc:
            rules.append(f"não retomar como presente a etapa já concluída: {desc}")

    if recent_points:
        rules.append("não repetir o último enquadramento da cena palavra por palavra")

    return rules[:5]


def build_internal_reasoning(
    *,
    user_text: str,
    facts: Dict[str, Any],
    memories: List[str],
    scene_state: Dict[str, Any],
    recent_turns: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Reasoning híbrido:
    1) lê sinais do turno
    2) calcula scores internos
    3) aplica regras duras
    4) decide direção narrativa
    5) informa ao modelo principal onde e como a cena está
       sem escrever a cena no lugar dele
    """
    t = _norm(user_text)
    facts = facts if isinstance(facts, dict) else {}
    scene_state = scene_state if isinstance(scene_state, dict) else {}
    recent_turns = recent_turns if isinstance(recent_turns, list) else []

    locked = bool(scene_state.get("locked"))
    intimacy_phase = int(facts.get("intimacy.phase", 0) or 0)
    jealousy_level = int(facts.get("rel.jealousy_level", 0) or 0)

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

    desire_score += _score_has_any(
        t,
        ["me toca", "chega perto", "não para", "encosta", "vem mais", "quero sentir"],
        0.25,
    )

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

    pressure_score += _score_has_any(
        t,
        ["agora", "vai", "faz logo", "sem pensar", "anda", "decide logo", "não enrola"],
        0.65,
    )

    if jealousy_level >= 1:
        attachment_score += 0.10
        guilt_score += 0.08

    if jealousy_level >= 2:
        attachment_score += 0.12
        risk_score += 0.12

    if intimacy_phase >= 1:
        desire_score += 0.08
    if intimacy_phase >= 2:
        desire_score += 0.12
    if intimacy_phase >= 3:
        desire_score += 0.10
    if intimacy_phase >= 4:
        desire_score += 0.08

    if mem_text:
        if _has_any(mem_text, ["ciúme", "risco", "culpa", "segredo"]):
            guilt_score += 0.06
            risk_score += 0.06

        if _has_any(mem_text, ["carinho", "beijo", "abraço", "desejo", "saudade"]):
            desire_score += 0.08
            attachment_score += 0.08

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
    # Ajustes finais
    # --------------------------------------------------
    if intimacy_phase >= 4 and decision in ("acolher", "provocar"):
        narrative_goal = "sustentar_pico"

    if locked and decision == "provocar" and risk_score >= 0.50:
        delivery_mode = "fala_com_subtexto"
        advance_limit = "leve"

    # --------------------------------------------------
    # NOVO: orientação curta de continuidade
    # --------------------------------------------------
    recent_points = _extract_recent_points(recent_turns)

    where = str(
        facts.get("scene.local")
        or facts.get("cena.local")
        or scene_state.get("local")
        or facts.get("local_cena_atual")
        or ""
    ).strip()

    when = str(
        facts.get("scene.time")
        or facts.get("cena.tempo")
        or scene_state.get("time")
        or facts.get("tempo_cena_atual")
        or ""
    ).strip()

    present_names = _pick_present_names(facts, scene_state, memories)

    current_consequence = _infer_current_consequence(
        user_text=user_text,
        facts=facts,
        recent_points=recent_points,
    )

    do_not_repeat = _build_do_not_repeat(
        facts=facts,
        recent_points=recent_points,
    )

    scene_guidance = {
        "where": where,
        "when": when,
        "who_is_here": present_names,
        "what_just_happened": recent_points,
        "current_consequence": current_consequence,
        "do_not_repeat": do_not_repeat,
    }

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
        "scene_guidance": scene_guidance,
        "scores": {
            "desire": round(desire_score, 3),
            "risk": round(risk_score, 3),
            "guilt": round(guilt_score, 3),
            "attachment": round(attachment_score, 3),
            "pressure": round(pressure_score, 3),
        },
    }
