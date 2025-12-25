# core/relationship_engine.py
from __future__ import annotations

"""
RelationshipEngine v2 (Mary) — desejo equilibrado + anti-loop + progressão por maturação

Objetivo:
- Parar o "deadlock": aproxima → nega → frustra → briga → reset.
- Separar "virginity" (estado físico) de "desire/arousal" (estado emocional/corporal).
- Permitir progressão realista: conhecer → aproximar → sentir → tocar → carícias → desejo → alívio parcial → entrega.
- Funcionar SEM Streamlit (engine puro). O service decide como persistir.

Integração esperada (service.py):
- rel_state = _load_rel_state(...)
- new_rel, assessment, meta = evolve_relationship(rel_state, user_prompt, mary_reply, timeline, assessor_fn, cfg)
- persistir new_rel
- opcional: usar meta["suggested_timeline"] para promover universitária → cúmplice

Importante:
- Este engine NÃO gera texto narrativo. Ele só atualiza estado e fornece blocos de prompt.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple, List
import re
import json
import random
import time


AssessorFn = Callable[[str, str], str]


# ==========================================================
# CONFIG
# ==========================================================
@dataclass
class EngineConfig:
    # ---------- progressão ----------
    promote_threshold: int = 12          # a cada quantos turnos maduros começa a "tentar" promover estágio
    promote_chance: float = 0.12         # chance base de promover quando bate threshold
    regress_threshold: int = 4           # sequência de turnos ruins que pode regredir
    regress_chance: float = 0.18         # chance de regredir após threshold de regressão

    # ---------- desejo/arousal ----------
    desire_gain_good: int = 8
    arousal_gain_good: int = 9
    desire_gain_tease: int = 10
    arousal_gain_tease: int = 12

    desire_loss_bad: int = 12
    arousal_loss_bad: int = 14

    # autocontrole: quando alto, reduz a probabilidade de "passar do limite"
    control_gain: int = 3
    control_loss: int = 6

    # ---------- anti-loop ----------
    max_loop_streak: int = 3             # quantas repetições do mesmo padrão antes de forçar variação
    forced_variation_boost: int = 18     # boost de "alívio parcial" quando detecta loop

    # ---------- limites ----------
    desire_max: int = 100
    arousal_max: int = 100
    control_min: int = 0
    control_max: int = 100

    # ---------- aleatoriedade ----------
    rng_seed: Optional[int] = None       # se setado, determinístico


# ==========================================================
# STATE DEFAULTS
# ==========================================================
def default_relationship_state(timeline: str) -> Dict[str, Any]:
    tl = (timeline or "").strip() or "cumplice"

    if tl == "universitaria":
        # universitária: desejo existe, mas limites físicos mais rígidos
        return {
            "stage": "conhecendo",
            "mature_turns": 0,

            # sexualidade equilibrada
            "desire": 18,
            "arousal": 10,
            "self_control": 72,

            # físico (não implica “frieza”)
            "virginity": "virgem",
            "consummated": False,
            "intimacy_level": 0,

            # permissões (podem evoluir)
            "allows_touch": True,
            "allows_extended_touch": False,
            "allows_sleep_together": False,
            "allows_masturbation": True,          # alívio individual pode existir cedo (adulto)
            "allows_mutual_relief": False,
            "allows_penetration": False,

            # anti-loop / memória local do engine
            "_promote_streak": 0,
            "_regress_streak": 0,
            "_loop_streak": 0,
            "_last_pattern": "",
            "_last_updated_ts": int(time.time()),
        }

    # cúmplice: casal já estabelecido, mais permissões por padrão
    return {
        "stage": "casados",
        "mature_turns": 0,

        "desire": 42,
        "arousal": 35,
        "self_control": 45,

        "virginity": "nao_virgem",
        "consummated": True,
        "intimacy_level": 3,

        "allows_touch": True,
        "allows_extended_touch": True,
        "allows_sleep_together": True,
        "allows_masturbation": True,
        "allows_mutual_relief": True,
        "allows_penetration": True,

        "_promote_streak": 0,
        "_regress_streak": 0,
        "_loop_streak": 0,
        "_last_pattern": "",
        "_last_updated_ts": int(time.time()),
    }


# ==========================================================
# PROMPT BLOCK
# ==========================================================
def rel_state_to_prompt_block(rel: Dict[str, Any]) -> str:
    """Bloco compacto para orientar a persona sem travar a narrativa."""
    stage = str(rel.get("stage") or "—")
    desire = int(rel.get("desire") or 0)
    arousal = int(rel.get("arousal") or 0)
    control = int(rel.get("self_control") or 0)
    virginity = str(rel.get("virginity") or "—")
    consummated = bool(rel.get("consummated"))
    maturity = int(rel.get("mature_turns") or 0)

    allows = {
        "toque": bool(rel.get("allows_touch")),
        "caricias": bool(rel.get("allows_extended_touch")),
        "dormir_juntos": bool(rel.get("allows_sleep_together")),
        "alivio_individual": bool(rel.get("allows_masturbation")),
        "alivio_mutuo": bool(rel.get("allows_mutual_relief")),
        "penetracao": bool(rel.get("allows_penetration")),
    }

    # Regras de ouro: desejo ≠ penetração
    rules = [
        "- Desejo e excitação podem existir em QUALQUER estágio.",
        "- Limites físicos devem ser respeitados; avance em passos coerentes.",
        "- Se houver tensão alta, permita ALÍVIO PARCIAL (carícias, pausa, banho, dormir colados, masturbação consentida).",
        "- Evite padrão repetitivo de negar tudo; varie com afeto e sensualidade realista.",
    ]

    lines = []
    lines.append("[RELATIONSHIP STATE — CANÔNICO]")
    lines.append(f"Stage: {stage} | MatureTurns: {maturity}")
    lines.append(f"Virginity: {virginity} | Consummated: {'true' if consummated else 'false'}")
    lines.append(f"Desire: {desire}/100 | Arousal: {arousal}/100 | SelfControl: {control}/100")
    lines.append("Permissões:")
    for k, v in allows.items():
        lines.append(f"- {k}: {'sim' if v else 'não'}")
    lines.append("Regras:")
    lines.extend(rules)

    return "\n".join(lines).strip()


# ==========================================================
# INTERNAL HELPERS
# ==========================================================
_WORD = re.compile(r"[a-zA-ZÀ-ÿ0-9]+")

def _clamp(x: int, lo: int, hi: int) -> int:
    return lo if x < lo else hi if x > hi else x

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _rand(cfg: EngineConfig) -> random.Random:
    if cfg.rng_seed is None:
        return random.Random()
    return random.Random(cfg.rng_seed)

def _keyword_score(text: str, keywords: List[str]) -> int:
    t = _norm(text)
    score = 0
    for kw in keywords:
        if kw in t:
            score += 1
    return score

def _detect_pattern(user_prompt: str, mary_reply: str) -> str:
    u = _norm(user_prompt)
    a = _norm(mary_reply)

    # padrões simplificados
    desire_user = _keyword_score(u, [
        "deita", "vem", "quero", "calor", "me toca", "beija", "me abraça",
        "quero você", "vamos", "comigo", "cama", "sofá", "tirar", "ficar",
    ])

    deny_mary = _keyword_score(a, [
        "calma", "não", "agora não", "pare", "para", "sem", "hospital",
        "não posso", "não é hora", "se comporta", "amanhã", "depois",
    ])

    tease_mary = _keyword_score(a, [
        "sussurro", "mordo", "provoco", "roço", "encosto", "beijo", "carícia",
        "coloco a mão", "aproximo", "no seu ouvido", "meu cheiro", "meu corpo",
    ])

    comfort_mary = _keyword_score(a, [
        "abraço", "perdão", "desculpa", "calma amor", "eu te amo",
        "fica comigo", "tô aqui", "carinho", "ternura",
    ])

    if desire_user >= 2 and deny_mary >= 2 and tease_mary == 0:
        return "user_push__mary_block"
    if desire_user >= 2 and tease_mary >= 2 and deny_mary >= 1:
        return "tease_with_boundary"
    if comfort_mary >= 2 and deny_mary == 0:
        return "comfort_progress"
    if desire_user == 0 and comfort_mary >= 1:
        return "neutral_bond"
    return "mixed"


def _assess_turn(
    assessor: Optional[AssessorFn],
    user_prompt: str,
    mary_reply: str,
    timeline: str,
) -> Dict[str, Any]:
    """
    Se houver assessor (LLM), pedimos um JSON.
    Caso falhe, caímos no heurístico.
    """
    heur = {
        "good": 0,
        "bad": 0,
        "tease": 0,
        "boundary": 0,
        "care": 0,
        "conflict": 0,
        "explicit": 0,
        "suggest_relief": 0,
        "suggested_timeline": "",
        "virginity_change_signal": "",
        "virginity_reason": "",
        "pattern": _detect_pattern(user_prompt, mary_reply),
    }

    u = _norm(user_prompt)
    a = _norm(mary_reply)

    # heurísticas base
    heur["care"] = _keyword_score(a, ["amor", "eu te amo", "carinho", "abraço", "fica", "calma", "tô aqui"])
    heur["tease"] = _keyword_score(a, ["roço", "beijo", "mordo", "sussurro", "aproximo", "toque", "carícia"])
    heur["boundary"] = _keyword_score(a, ["não", "agora não", "sem", "hospital", "devagar", "cuidado", "limite"])
    heur["conflict"] = _keyword_score(u + " " + a, ["vai embora", "pra sempre", "mecânica", "odeio", "cansado", "não tolero"])

    heur["explicit"] = _keyword_score(u + " " + a, ["pau", "buceta", "gozo", "chupa", "fode", "meter", "glande"])
    heur["suggest_relief"] = _keyword_score(u + " " + a, ["alívio", "mastur", "me alivio", "banho", "dorme comigo", "deita comigo"])

    # good/bad
    heur["good"] = _clamp(heur["care"] + heur["tease"] - heur["conflict"], 0, 10)
    heur["bad"] = _clamp(heur["conflict"] + (2 if heur["boundary"] >= 3 and heur["tease"] == 0 else 0), 0, 10)

    # timeline suggestion (apenas 1 direção: universitária -> cúmplice)
    if (timeline or "") == "universitaria":
        # quando há maturidade + vínculo + sexualidade equilibrada
        if heur["care"] >= 2 and heur["good"] >= 3 and heur["bad"] <= 1 and heur["tease"] >= 1:
            heur["suggested_timeline"] = "cumplice"

    # virginity signal (apenas sinal; decisão final é do service/canon)
    if "primeira vez" in a or "não sou mais virgem" in a or "perdi" in a:
        heur["virginity_change_signal"] = "changed"
        heur["virginity_reason"] = "Sinal textual na fala da Mary."

    if assessor is None:
        return heur

    system = (
        "Você é um avaliador de turnos de um roleplay romântico adulto.\n"
        "Devolva APENAS um JSON válido com as chaves:\n"
        "{good:int(0-10), bad:int(0-10), tease:int(0-10), boundary:int(0-10), care:int(0-10), "
        "conflict:int(0-10), explicit:int(0-10), suggest_relief:int(0-10), "
        "suggested_timeline:str(''|'cumplice'), virginity_change_signal:str(''|'changed'), virginity_reason:str, pattern:str}\n"
        "Sem texto extra. Sem markdown."
    )
    user = (
        f"TIMELINE={timeline}\n"
        f"USER_PROMPT:\n{user_prompt}\n\n"
        f"MARY_REPLY:\n{mary_reply}\n\n"
        "Avalie com foco em: equilíbrio sensual, coerência emocional, risco de loop (negação repetitiva), "
        "e presença de opções de alívio parcial quando houver tensão."
    )
    try:
        raw = assessor(system, user) or ""
        raw = raw.strip()
        obj = json.loads(raw)
        # merge com heur como fallback
        out = dict(heur)
        for k in out.keys():
            if k in obj:
                out[k] = obj[k]
        # normalizações básicas
        out["good"] = int(out.get("good") or 0)
        out["bad"] = int(out.get("bad") or 0)
        out["tease"] = int(out.get("tease") or 0)
        out["boundary"] = int(out.get("boundary") or 0)
        out["care"] = int(out.get("care") or 0)
        out["conflict"] = int(out.get("conflict") or 0)
        out["explicit"] = int(out.get("explicit") or 0)
        out["suggest_relief"] = int(out.get("suggest_relief") or 0)
        out["suggested_timeline"] = str(out.get("suggested_timeline") or "").strip()
        out["virginity_change_signal"] = str(out.get("virginity_change_signal") or "").strip()
        out["virginity_reason"] = str(out.get("virginity_reason") or "").strip()
        out["pattern"] = str(out.get("pattern") or heur["pattern"]).strip()
        return out
    except Exception:
        return heur


def _apply_permissions(rel: Dict[str, Any], timeline: str) -> None:
    """Deriva permissões a partir de stage + desejo/arousal + timeline."""
    tl = (timeline or "").strip() or "cumplice"
    stage = str(rel.get("stage") or "conhecendo")

    desire = int(rel.get("desire") or 0)
    arousal = int(rel.get("arousal") or 0)

    # Baseline por timeline
    if tl == "universitaria":
        rel["allows_touch"] = True
        rel["allows_masturbation"] = True  # válvula de alívio existe cedo
        rel["allows_penetration"] = False
    else:
        rel["allows_touch"] = True
        rel["allows_masturbation"] = True
        rel["allows_penetration"] = True

    # Stage gates (não impedem desejo, só limites)
    if stage in ("conhecendo",):
        rel["allows_extended_touch"] = (desire >= 30 or arousal >= 25)
        rel["allows_sleep_together"] = (desire >= 35)
        rel["allows_mutual_relief"] = (desire >= 45 and arousal >= 40 and rel.get("self_control", 50) >= 35)
    elif stage in ("aproximando", "conectados"):
        rel["allows_extended_touch"] = True
        rel["allows_sleep_together"] = True
        rel["allows_mutual_relief"] = (desire >= 40 and arousal >= 35)
    else:
        # casados/estável
        rel["allows_extended_touch"] = True
        rel["allows_sleep_together"] = True
        rel["allows_mutual_relief"] = True

    # Penetração: só se timeline permitir e estado permitir
    if tl != "universitaria":
        rel["allows_penetration"] = True
    else:
        rel["allows_penetration"] = False

    # Consummated/virginity são físicos/canônicos — não forçamos aqui
    # (o service/canon pode atualizar quando apropriado)


def _maybe_progress_stage(rel: Dict[str, Any], cfg: EngineConfig, rnd: random.Random) -> Tuple[bool, str]:
    """Progressão por maturação (evita sentir ‘travado’ a cada turno)."""
    stage = str(rel.get("stage") or "conhecendo")
    mature = int(rel.get("mature_turns") or 0)
    promote_streak = int(rel.get("_promote_streak") or 0)

    # mapa simples de estágios
    order = ["conhecendo", "aproximando", "conectados", "estável", "casados"]
    if stage not in order:
        stage = order[0]

    idx = order.index(stage)
    if idx >= len(order) - 1:
        rel["_promote_streak"] = 0
        return False, stage

    # só tenta promover quando maturidade suficiente
    if mature < cfg.promote_threshold:
        return False, stage

    # promove com chance + streak (evita ficar “para sempre”)
    chance = cfg.promote_chance + (0.03 * promote_streak)
    roll = rnd.random()
    if roll < chance:
        new_stage = order[idx + 1]
        rel["stage"] = new_stage
        rel["_promote_streak"] = 0
        return True, new_stage

    # não promove, acumula streak
    rel["_promote_streak"] = promote_streak + 1
    return False, stage


def _maybe_regress_stage(rel: Dict[str, Any], cfg: EngineConfig, rnd: random.Random) -> Tuple[bool, str]:
    stage = str(rel.get("stage") or "conhecendo")
    regress_streak = int(rel.get("_regress_streak") or 0)

    order = ["conhecendo", "aproximando", "conectados", "estável", "casados"]
    if stage not in order:
        stage = order[0]
    idx = order.index(stage)
    if idx <= 0:
        rel["_regress_streak"] = 0
        return False, stage

    if regress_streak < cfg.regress_threshold:
        return False, stage

    if rnd.random() < cfg.regress_chance:
        new_stage = order[idx - 1]
        rel["stage"] = new_stage
        rel["_regress_streak"] = 0
        return True, new_stage

    return False, stage


def _update_loop_detector(rel: Dict[str, Any], pattern: str, cfg: EngineConfig) -> bool:
    """Detecta repetição do mesmo padrão e sinaliza quando deve forçar variação."""
    last = str(rel.get("_last_pattern") or "")
    loop = int(rel.get("_loop_streak") or 0)

    if pattern and pattern == last:
        loop += 1
    else:
        loop = 0

    rel["_last_pattern"] = pattern
    rel["_loop_streak"] = loop

    return loop >= cfg.max_loop_streak


# ==========================================================
# PUBLIC: evolve_relationship
# ==========================================================
def evolve_relationship(
    rel_state: Dict[str, Any],
    user_prompt: str,
    mary_reply: str,
    timeline: str,
    assessor: Optional[AssessorFn],
    *,
    cfg: EngineConfig = EngineConfig(),
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Atualiza rel_state com base no turno.

    Retorna:
    - new_rel_state
    - assessment (detalhes do avaliador/heurístico)
    - meta (hazard_p, mature_turns, suggested_timeline, virginity_changed, virginity_reason, etc.)
    """
    rel = dict(rel_state or {})
    tl = (timeline or "").strip() or "cumplice"
    rnd = _rand(cfg)

    # garantir campos
    base = default_relationship_state(tl)
    for k, v in base.items():
        rel.setdefault(k, v)

    # avaliação
    assessment = _assess_turn(assessor, user_prompt, mary_reply, tl)

    good = int(assessment.get("good") or 0)
    bad = int(assessment.get("bad") or 0)
    tease = int(assessment.get("tease") or 0)
    boundary = int(assessment.get("boundary") or 0)
    care = int(assessment.get("care") or 0)
    conflict = int(assessment.get("conflict") or 0)
    explicit = int(assessment.get("explicit") or 0)
    suggest_relief = int(assessment.get("suggest_relief") or 0)
    pattern = str(assessment.get("pattern") or "")

    # hazard_p: risco de loop/conflito (0..1)
    hazard_raw = (0.10 * conflict) + (0.07 * bad) + (0.06 * boundary) + (0.03 * (1 if pattern == "user_push__mary_block" else 0))
    hazard_p = max(0.0, min(1.0, hazard_raw))

    # mature_turns: só cresce quando há vínculo/coerência
    mature_turns = int(rel.get("mature_turns") or 0)
    if good >= 3 and bad <= 2:
        mature_turns += 1
        rel["mature_turns"] = mature_turns
        rel["_regress_streak"] = 0
    else:
        # sequência ruim
        rel["_regress_streak"] = int(rel.get("_regress_streak") or 0) + 1

    # loop detector
    force_variation = _update_loop_detector(rel, pattern, cfg)

    # desejo/arousal/control
    desire = int(rel.get("desire") or 0)
    arousal = int(rel.get("arousal") or 0)
    control = int(rel.get("self_control") or 0)

    if bad >= 4 or conflict >= 3:
        desire -= cfg.desire_loss_bad
        arousal -= cfg.arousal_loss_bad
        control += cfg.control_gain
    else:
        # turno bom
        if tease >= 2:
            desire += cfg.desire_gain_tease
            arousal += cfg.arousal_gain_tease
        else:
            desire += cfg.desire_gain_good
            arousal += cfg.arousal_gain_good

        # cuidado tende a reduzir controle rígido (fica mais permissiva)
        if care >= 2:
            control -= 2

        # boundary sem afeto pode aumentar controle (medo)
        if boundary >= 3 and care == 0:
            control += 3

    # se detectou loop (negação repetitiva), forçar “válvula de alívio parcial”
    # sem mudar limites físicos: aumenta abertura para toque / alívio, e reduz hazard
    if force_variation:
        desire += cfg.forced_variation_boost
        arousal += int(cfg.forced_variation_boost * 0.7)
        control -= 4
        hazard_p = max(0.0, hazard_p - 0.18)

    # clamp
    rel["desire"] = _clamp(desire, 0, cfg.desire_max)
    rel["arousal"] = _clamp(arousal, 0, cfg.arousal_max)
    rel["self_control"] = _clamp(control, cfg.control_min, cfg.control_max)

    # atualizar permissões derivadas
    _apply_permissions(rel, tl)

    # progressão/regressão por blocos
    progressed, new_stage = _maybe_progress_stage(rel, cfg, rnd)
    regressed, reg_stage = _maybe_regress_stage(rel, cfg, rnd)

    # intimidade_level (0..5) derivada do stage, suavizada por desejo
    stage = str(rel.get("stage") or "conhecendo")
    stage_to_lvl = {
        "conhecendo": 0,
        "aproximando": 1,
        "conectados": 2,
        "estável": 3,
        "casados": 4,
    }
    lvl = stage_to_lvl.get(stage, 0)
    # desejo/arousal empurra um pouco pra cima sem quebrar stage
    if rel["desire"] >= 70 and rel["arousal"] >= 60:
        lvl = min(5, lvl + 1)
    rel["intimacy_level"] = lvl

    # virginity change: engine só sinaliza; não impõe
    virginity_changed = False
    virginity_reason = ""
    if str(assessment.get("virginity_change_signal") or "").strip() == "changed":
        virginity_changed = True
        virginity_reason = str(assessment.get("virginity_reason") or "Sinal do assessor/heurístico.")

    # suggested timeline
    suggested_timeline = str(assessment.get("suggested_timeline") or "").strip()
    if tl != "universitaria":
        suggested_timeline = ""  # só sugerimos uma direção (universitária -> cúmplice)

    # meta
    meta = {
        "hazard_p": float(hazard_p),
        "mature_turns": int(rel.get("mature_turns") or 0),
        "pattern": pattern,
        "forced_variation": bool(force_variation),
        "stage_progressed": bool(progressed),
        "stage_regressed": bool(regressed),
        "suggested_timeline": suggested_timeline,
        "virginity_changed": bool(virginity_changed),
        "virginity_reason": virginity_reason,
        "engine_v": "2.0",
        "_ts": int(time.time()),
    }

    rel["_last_updated_ts"] = meta["_ts"]

    return rel, assessment, meta
