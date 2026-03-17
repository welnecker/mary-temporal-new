from typing import Dict, Any, List


def _norm(x: Any) -> str:
    return str(x or "").strip().lower()


def _has_any(text: str, terms: List[str]) -> bool:
    return any(t in text for t in terms)


def build_internal_reasoning(
    *,
    user_text: str,
    facts: Dict[str, Any],
    memories: List[str],
    scene_state: Dict[str, Any],
) -> Dict[str, Any]:
    t = _norm(user_text)
    facts = facts if isinstance(facts, dict) else {}
    scene_state = scene_state if isinstance(scene_state, dict) else {}

    locked = bool(scene_state.get("locked"))
    intimacy_phase = int(facts.get("intimacy.phase", 0) or 0)
    jealousy_level = int(facts.get("rel.jealousy_level", 0) or 0)
    nsfw_on = bool(facts.get("nsfw.on", False))

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

    if locked:
        rules.append("nao_mudar_cena")
        rules.append("nao_avancar_tempo")

    # --------------------------------------------------
    # Romance / carinho / proximidade
    # --------------------------------------------------
    if _has_any(t, ["amor", "beijo", "me beija", "fica comigo", "vem cá", "abraço", "carinho"]):
        intent = "aproximar"
        emotion = "envolvida"
        subtext = "desejo_com_vinculo"
        pace = "lento"
        tension = "media"
        decision = "acolher"
        narrative_goal = "aprofundar_conexao"
        delivery_mode = "fala_direta"
        advance_limit = "medio"

    # --------------------------------------------------
    # Convite arriscado / terceiro / traição
    # --------------------------------------------------
    if _has_any(t, ["enzo", "outro homem", "encontro", "trair", "quiosque", "sozinho comigo"]):
        intent = "conflito"
        emotion = "dividida"
        subtext = "curiosidade_reprimida"
        pace = "lento"
        tension = "alta"
        decision = "hesitar"
        narrative_goal = "prolongar_tensao"
        delivery_mode = "fala_com_subtexto"
        advance_limit = "minimo"
        rules.append("nao_concluir_ato")
        rules.append("manter_ambiguidade")

        if jealousy_level >= 2:
            decision = "resistir"
            emotion = "alerta"
            narrative_goal = "proteger_vinculo"

    # --------------------------------------------------
    # Pressão direta / ordem / tentativa de acelerar
    # --------------------------------------------------
    if _has_any(t, ["agora", "vai", "faz logo", "sem pensar", "anda", "decide logo"]):
        intent = "resistir"
        emotion = "tensa"
        subtext = "nao_quero_ser_empurrada"
        pace = "curto"
        tension = "alta"
        decision = "recuar_com_presenca"
        narrative_goal = "retomar_controle"
        delivery_mode = "fala_direta"
        advance_limit = "minimo"

    # --------------------------------------------------
    # Intimidade mais alta
    # --------------------------------------------------
    if intimacy_phase >= 2 and _has_any(t, ["quero você", "me toca", "chega perto", "não para", "te desejo"]):
        intent = "ceder_com_controle"
        emotion = "acesa"
        subtext = "entrega_progressiva"
        pace = "normal"
        tension = "alta"
        decision = "provocar"
        narrative_goal = "escalar_sem_finalizar"
        delivery_mode = "micro_acao"
        advance_limit = "medio"

    if intimacy_phase >= 4:
        rules.append("permitir_climax_se_usuario_sinalizar")
        narrative_goal = "sustentar_pico"

    # --------------------------------------------------
    # Memória pode influenciar levemente
    # --------------------------------------------------
    memory_hint = memories[-1] if memories else ""
    if memory_hint and decision == "responder":
        subtext = "eco_de_memoria"

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
    }
