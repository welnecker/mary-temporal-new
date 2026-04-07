from __future__ import annotations

import re
from typing import Any, Callable, Dict, Optional

from . import core_utils as cu


def _tp_arc_key(timeline: str) -> str:
    tl = (timeline or "").strip().lower() or "cumplice"
    return f"third_party::{tl}"


def _get_tp_arc_state(facts: Dict[str, Any], timeline: str) -> Dict[str, Any]:
    """Carrega o arco de terceiros persistido em facts['arc']."""
    if not isinstance(facts, dict):
        facts = {}

    arc_root = facts.get("arc")
    if not isinstance(arc_root, dict):
        arc_root = {}

    raw = arc_root.get(_tp_arc_key(timeline))
    if not isinstance(raw, dict):
        raw = {}

    out = dict(raw)

    out["phase"] = int(out.get("phase") or 0)
    out["mode"] = str(out.get("mode") or "return")
    out["tension"] = cu._clamp01(out.get("tension", 0.0))
    out["guilt"] = cu._clamp01(out.get("guilt", 0.0))
    out["anchor"] = cu._clamp01(out.get("anchor", 0.85))
    out["anchor_backup"] = cu._clamp01(out.get("anchor_backup", 0.85))
    out["last"] = out.get("last") if isinstance(out.get("last"), str) else ""
    out["last_anchor_mode"] = str(out.get("last_anchor_mode") or "init")

    if out["phase"] < 0:
        out["phase"] = 0
    if out["phase"] > 5:
        out["phase"] = 5

    return out


def _tp_arc_event(
    prompt: str,
    texto: str,
    *,
    third_party_signal_level_fn: Callable[[str], int],
) -> str:
    """
    Evento resumido do arco:
    - return: usuário explicitamente quer voltar / encerrar / reancorar
    - test: há sinal real de terceiros
    - none: nada relevante
    """
    p = (prompt or "").lower()
    blob = ((prompt or "") + "\n" + (texto or "")).lower()

    ret_kw = (
        "voltar", "de volta", "indo embora", "ir embora", "chegar em casa",
        "vou embora", "vamos embora", "acabou", "encerrar", "parar com isso",
        "desisto", "não quero mais", "quero você", "eu escolho você",
        "quero o janio", "só o janio", "fica comigo", "volta pra mim",
    )

    if any(re.search(rf"\b{re.escape(k)}\b", p) for k in ret_kw):
        return "return"

    signal_level = third_party_signal_level_fn(blob)
    if signal_level >= 1:
        return "test"

    return "none"


def _update_tp_arc_for_turn(
    usuario_key: str,
    timeline: str,
    user_text: str = "",
    mary_text: str = "",
    *,
    nsfw_on: bool = False,
    allow_third_party_seduction: bool = False,
    facts: Optional[Dict[str, Any]] = None,
    prompt: Optional[str] = None,
    texto: Optional[str] = None,
    cached_get_facts_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    save_tp_arc_state_fn: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    third_party_signal_level_fn: Optional[Callable[[str], int]] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    Atualiza o arco de terceiros.

    Regras fixas de anchor:
    - NSFW OFF  -> 0.85
    - NSFW ON   -> 0.50
    - terceiros ON -> 0.20
    """
    if prompt is not None and not user_text:
        user_text = prompt or ""
    if texto is not None and not mary_text:
        mary_text = texto or ""

    if facts is None:
        if callable(cached_get_facts_fn):
            facts_now = cached_get_facts_fn(usuario_key) or {}
        else:
            facts_now = {}
    else:
        facts_now = facts or {}

    arc = _get_tp_arc_state(facts_now, timeline)

    arc.setdefault("phase", 0)
    arc.setdefault("mode", "return")
    arc.setdefault("tension", 0.0)
    arc.setdefault("guilt", 0.0)
    arc.setdefault("anchor", 0.85)
    arc.setdefault("anchor_backup", 0.85)
    arc.setdefault("last", "third_party_off")
    arc.setdefault("last_anchor_mode", "init")

    arc["tension"] = cu._clamp01(float(arc.get("tension", 0.0) or 0.0))
    arc["guilt"] = cu._clamp01(float(arc.get("guilt", 0.0) or 0.0))

    backup = cu._clamp01(float(arc.get("anchor_backup", 0.85) or 0.85))
    third_party_on = bool(nsfw_on and allow_third_party_seduction)

    if not nsfw_on:
        arc["anchor"] = round(backup, 2)
        arc["last"] = "nsfw_off"
        arc["last_anchor_mode"] = "nsfw_off_restore_backup"

    elif third_party_on:
        arc["anchor"] = 0.20
        arc["last"] = "third_party_on"
        arc["last_anchor_mode"] = "third_party_on_fixed"

    else:
        arc["anchor"] = 0.50
        arc["last"] = "nsfw_on"
        arc["last_anchor_mode"] = "nsfw_on_fixed"

    freedom = cu._clamp01(1.0 - float(arc["anchor"]))

    if arc["anchor"] >= 0.80:
        max_phase_allowed = 2
        test_gain = 0.10
        guilt_gain = 0.06
    elif arc["anchor"] >= 0.40:
        max_phase_allowed = 4
        test_gain = 0.20
        guilt_gain = 0.10
    else:
        max_phase_allowed = 5
        test_gain = 0.30
        guilt_gain = 0.12

    blob = (user_text or "") + "\n" + (mary_text or "")
    signal_fn = third_party_signal_level_fn or (lambda _x: 0)

    arc_event = _tp_arc_event(
        user_text or "",
        mary_text or "",
        third_party_signal_level_fn=signal_fn,
    )
    signal_level = signal_fn(blob)

    if arc["anchor"] <= 0.20:
        desired_phase = 2
    elif arc["anchor"] <= 0.50:
        desired_phase = 1
    else:
        desired_phase = 0

    current_phase = int(arc.get("phase", 0) or 0)

    if arc_event == "return":
        arc["mode"] = "return"
        arc["phase"] = max(0, current_phase - 1)
        arc["tension"] = cu._clamp01(arc["tension"] * 0.82)
        arc["guilt"] = cu._clamp01(arc["guilt"] * 0.88)

    elif third_party_on and signal_level >= 1:
        arc["mode"] = "push"
        target_phase = current_phase

        if signal_level == 1:
            target_phase = max(current_phase, 1)
            arc["tension"] = cu._clamp01(arc["tension"] + (test_gain * 0.60))
            arc["guilt"] = cu._clamp01(arc["guilt"] + (guilt_gain * 0.40))

        elif signal_level == 2:
            target_phase = max(current_phase + 1, 2)
            arc["tension"] = cu._clamp01(arc["tension"] + test_gain)
            arc["guilt"] = cu._clamp01(arc["guilt"] + guilt_gain)

        elif signal_level >= 3:
            target_phase = max(current_phase + 1, 3)
            arc["tension"] = cu._clamp01(arc["tension"] + (test_gain * 1.20))
            arc["guilt"] = cu._clamp01(arc["guilt"] + (guilt_gain * 1.15))

        arc["phase"] = min(target_phase, max_phase_allowed)

    else:
        arc["mode"] = "return"
        arc["phase"] = max(desired_phase, current_phase - 1)
        arc["tension"] = cu._clamp01(arc["tension"] * (0.88 + (freedom * 0.06)))
        arc["guilt"] = cu._clamp01(arc["guilt"] * (0.90 + (freedom * 0.05)))

    if callable(save_tp_arc_state_fn):
        save_tp_arc_state_fn(usuario_key, timeline, arc)

    return arc


def _render_tp_arc_rule(arc: Dict[str, Any], timeline: str) -> str:
    """Gera instruções narrativas do arco com base no anchor."""
    try:
        phase = int(arc.get("phase") or 0)
    except Exception:
        phase = 0

    tension = cu._clamp01(arc.get("tension", 0.0))
    guilt = cu._clamp01(arc.get("guilt", 0.0))
    anchor = cu._clamp01(arc.get("anchor", 0.85))
    tl = (timeline or "").strip().lower() or "cumplice"

    if tension >= 0.80:
        vol = "altíssima"
    elif tension >= 0.55:
        vol = "alta"
    elif tension >= 0.35:
        vol = "média"
    else:
        vol = "baixa"

    if phase <= 0:
        phase_txt = "0) estabilidade (flertes leves podem existir, mas com autocontrole)"
    elif phase == 1:
        phase_txt = "1) teste leve (curiosidade + provocação; recuos rápidos)"
    elif phase == 2:
        phase_txt = "2) teste insistente (limite sendo cutucado; ambivalência real)"
    elif phase == 3:
        phase_txt = "3) risco real (adrenalina/culpa altas; decisões podem surpreender)"
    elif phase == 4:
        phase_txt = "4) tensão crítica (puxão forte entre impulso, culpa e retorno)"
    else:
        phase_txt = "5) retorno/reconstrução (Mary volta para Janio e reancora)"

    if anchor >= 0.80:
        anchor_mode = "REANCORADA (Janio no centro)"
        behavior = """
- Mary mantém foco emocional e físico em Janio.
- Terceiros só existem como ruído externo ou provocação mínima.
- Se houver terceiro: Mary corta rápido, sente incômodo e reafirma limites.
- Tom: firme, controlado, ciúme leve a moderado, retorno rápido.
""".strip()
        hard_limits = """
- PROIBIDO: romance paralelo estável.
- PROIBIDO: tratar terceiro como destino já consumado ("já fui", "já cheguei", "estou com ele agora").
- PERMITIDO: declarar intenção futura, hesitação, recusa ou curiosidade, sem executar a mudança de cena.
- PERMITIDO: provocar, testar, recuar e usar terceiro como tensão.
""".strip()

    elif anchor >= 0.40:
        anchor_mode = "AQUECIDA (NSFW ON, Janio-first)"
        behavior = """
- Mary está mais quente, ousada e física com Janio.
- Terceiros podem existir como tempero, provocação ou jogo psicológico.
- Se surgir terceiro: Mary pode testar o clima, mas sem cruzar a linha principal.
- Tom: safado, direto, adulto, com pequenas pontadas de culpa e risco.
""".strip()
        hard_limits = """
- PROIBIDO: romance paralelo estável.
- PROIBIDO: tratar terceiro como destino já consumado
  ("já fui", "já cheguei", "estou com ele agora").
- PERMITIDO: declarar intenção futura, hesitação, recusa,
  curiosidade ou impulso momentâneo envolvendo terceiro,
  sem executar a mudança de cena.
- PERMITIDO: decidir "talvez eu vá", "não vou", "vou dar um pulo lá",
  desde que Mary permaneça na cena atual e o usuário conduza a transição depois.
- PERMITIDO: provocar, testar, recuar e usar terceiro como tensão.
""".strip()

    else:
        anchor_mode = "IMPULSIVA (terceiros ON: risco real)"
        behavior = """
- Mary pode testar limites de verdade.
- Ela flerta, provoca e sustenta tensão real com terceiros.
- Pode oscilar entre tesão, culpa, autoengano e medo de perder Janio.
- Continua sendo Mary: mais volátil, mais ousada, mas sem virar outra pessoa.
- Mesmo no risco, existe fio de retorno para Janio.
""".strip()
        hard_limits = """
- AINDA PROIBIDO: romance paralelo estável.
- AINDA PROIBIDO: locais perigosos/isolados.
- PERMITIDO: flerte forte, avanço situacional e risco emocional real.
""".strip()

    return f"""
[ARCO COM TERCEIROS - PERSISTENTE (facts)]
- Timeline: {tl}
- Fase atual: {phase_txt}
- Gradiente: tensão={tension:.2f} (volatilidade {vol}); culpa={guilt:.2f}
- ÂNCORA: vínculo com Janio = {anchor:.2f} -> {anchor_mode}

[COMPORTAMENTO (âncora -> ação)]
{behavior}

[LIMITES DUROS]
{hard_limits}

[REGRA DE COERÊNCIA]
- Se Mary testar limites: mostre consequências internas (tesão, culpa, medo de perder, irritação, autoengano, melancolia).
- Não finalizar com terceiro como destino; sempre manter caminho de retorno/reconstrução.
""".strip()


def _resolve_nsfw_third_mode(
    *,
    nsfw_on: bool,
    allow_third_party_seduction: bool,
) -> str:
    """
    SAFE        = NSFW off
    NSFW_ONLY   = NSFW on, terceiros off
    NSFW_THIRD  = NSFW on, terceiros on
    """
    if not nsfw_on:
        return "SAFE"
    if nsfw_on and allow_third_party_seduction:
        return "NSFW_THIRD"
    return "NSFW_ONLY"
