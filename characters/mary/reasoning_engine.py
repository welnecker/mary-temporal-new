from __future__ import annotations

from typing import Any, Dict, List, Optional


def _norm(x: Any) -> str:
    return str(x or "").strip()


def _safe_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _safe_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _clip_text(text: Any, limit: int = 180) -> str:
    t = " ".join(str(text or "").split()).strip()
    return t[:limit] if t else ""


def _extract_recent_points(recent_turns: List[Dict[str, Any]]) -> List[str]:
    """
    Ponte curta real.
    Pega só os 2 últimos pontos úteis, sem inflar o reasoning.
    """
    out: List[str] = []

    for turn in recent_turns[-2:]:
        if not isinstance(turn, dict):
            continue

        user_msg = _clip_text(
            turn.get("mensagem_usuario")
            or turn.get("user")
            or (turn.get("role") == "user" and turn.get("content"))
            or "",
            180,
        )

        mary_msg = _clip_text(
            turn.get("resposta_mary")
            or turn.get("assistant")
            or (turn.get("role") == "assistant" and turn.get("content"))
            or "",
            180,
        )

        summary = _clip_text(turn.get("summary"), 140)

        if user_msg:
            out.append(user_msg)

        if mary_msg:
            out.append(mary_msg)

        if not user_msg and not mary_msg and summary:
            out.append(summary)

    return out[-2:]


def _pick_present_names(
    facts: Dict[str, Any],
    scene_state: Dict[str, Any],
    recent_turns: List[Dict[str, Any]],
) -> List[str]:
    """
    Só considera presentes explícitos da cena atual.
    """
    presentes: List[str] = []

    cast = _safe_dict(facts.get("cast"))
    for key in ("presentes", "present", "characters", "who_is_here"):
        for item in _safe_list(cast.get(key)):
            name = _norm(item)
            if name and name not in presentes:
                presentes.append(name)

    for key in ("presentes", "present", "characters", "who_is_here"):
        for item in _safe_list(scene_state.get(key)):
            name = _norm(item)
            if name and name not in presentes:
                presentes.append(name)

    joined_recent = " ".join(
        _clip_text(
            t.get("mensagem_usuario") or t.get("user") or "",
            180,
        )
        for t in recent_turns[-2:]
        if isinstance(t, dict)
    ).lower()

    if "janio" in joined_recent and "Janio" not in presentes:
        presentes.append("Janio")

    return presentes[:4]


def _extract_current_step_text(facts: Dict[str, Any]) -> str:
    """
    Extrai SOMENTE a etapa atual do assunto.
    Não pode cair no assunto bruto inteiro.
    """

    # 1) prioridade total: etapa atual explícita
    for key in (
        "state.assunto_step_text",
        "assunto_step_text",
        "assunto_atual_texto",
    ):
        raw = facts.get(key)
        if isinstance(raw, str):
            val = _norm(raw)
            if val:
                return val

    # 2) sequência estruturada
    seq = _safe_list(facts.get("assunto_seq"))

    try:
        idx = int(facts.get("assunto_idx", facts.get("assunto.step_index", 0)) or 0)
    except Exception:
        idx = 0

    if seq and 0 <= idx < len(seq):
        step = _safe_dict(seq[idx])

        for k in ("desc", "text", "title", "label", "content"):
            raw = step.get(k)
            if isinstance(raw, str):
                val = _norm(raw)
                if val:
                    return val

    # 3) fallback mínimo: ação da cena, nunca assunto bruto completo
    for key in (
        "scene.action",
        "cena.acao",
    ):
        raw = facts.get(key)
        if isinstance(raw, str):
            val = _norm(raw)
            if val:
                return val

    return ""


def _infer_current_consequence(
    *,
    facts: Dict[str, Any],
    recent_points: List[str],
) -> str:
    """
    Consequência atual = último ponto real do turno OU etapa ativa.
    Nunca usar placeholder genérico.
    """
    if recent_points:
        val = _norm(recent_points[-1])
        if val:
            return val

    step_txt = _extract_current_step_text(facts)
    if step_txt:
        val = _norm(step_txt)
        if val:
            return val

    return ""


def _build_do_not_repeat(
    *,
    facts: Dict[str, Any],
    recent_points: List[str],
) -> List[str]:
    rules = [
        "não reiniciar a cena",
        "não reexecutar ação já concluída",
        "não voltar para etapa anterior como se fosse presente",
    ]

    done_until = facts.get("assunto_done_until")
    seq = _safe_list(facts.get("assunto_seq"))

    try:
        done_idx = int(done_until)
    except Exception:
        done_idx = -1

    if done_idx >= 0 and seq:
        try:
            step = _safe_dict(seq[min(done_idx, len(seq) - 1)])
            desc = _norm(step.get("desc") or step.get("text") or step.get("label"))
            if desc:
                rules.append(f"não retomar como presente a etapa já concluída: {desc}")
        except Exception:
            pass

    if recent_points:
        rules.append("não repetir o enquadramento do turno anterior")

    return rules[:5]


def build_internal_reasoning(
    *,
    user_text: str,
    facts: Dict[str, Any],
    memories: List[str],  # mantido por compatibilidade; não decide continuidade
    scene_state: Dict[str, Any],
    recent_turns: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Reasoning mínimo e disciplinado:
    - NÃO interpreta memória longa
    - NÃO decide emoção global
    - NÃO cria personagens presentes
    - NÃO escreve a cena
    - APENAS ancora a continuidade imediata
    """

    facts = facts if isinstance(facts, dict) else {}
    scene_state = scene_state if isinstance(scene_state, dict) else {}
    recent_turns = recent_turns if isinstance(recent_turns, list) else []

    where = _norm(
        facts.get("cena.local")
        or facts.get("scene.local")
        or facts.get("local_cena_atual")
        or scene_state.get("local")
    )

    when = _norm(
        facts.get("cena.tempo")
        or facts.get("scene.time")
        or scene_state.get("tempo")
        or scene_state.get("time")
    )

    recent_points = _extract_recent_points(recent_turns)
    who_is_here = _pick_present_names(facts, scene_state, recent_turns)
    current_consequence = _infer_current_consequence(
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
        "who_is_here": who_is_here,
        "what_just_happened": recent_points,
        "current_consequence": current_consequence,
        "do_not_repeat": do_not_repeat,
    }

    return {
        "intent": "continuar",
        "emotion": "",
        "subtext": "",
        "pace": "normal",
        "tension": "media",
        "rules": [],
        "decision": "responder",
        "narrative_goal": "manter_fluxo",
        "delivery_mode": "fala_com_acao",
        "advance_limit": "medio",
        "memory_hint": "",
        "scene_guidance": scene_guidance,
        "scores": {
            "desire": 0.0,
            "risk": 0.0,
            "guilt": 0.0,
            "attachment": 0.0,
            "pressure": 0.0,
        },
    }
