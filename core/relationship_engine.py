from __future__ import annotations

"""
RelationshipEngine v2.2 (Mary) — desejo equilibrado + anti-loop + progressão por maturação (robusto)

Melhorias principais vs v2.0:
- RNG estável por turno (evita “loucura” ou “reset” de aleatoriedade a cada chamada).
- Loop detector mais responsivo (streak não zera pra 0; começa em 1 no novo padrão).
- Ordem de decisões: regressão primeiro (se necessário), senão progressão.
- Heurísticas menos sensíveis a "não"/"calma" (reduz falso "bloqueio").
- Meta "must_offer_relief" quando detecta loop/deadlock (service injeta direção narrativa).
- Permissões consideram mature_turns como gatilho de evolução (especialmente em universitária).
"""

from dataclasses import dataclass
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
    promote_threshold: int = 10          # um pouco mais rápido
    promote_chance: float = 0.14
    regress_threshold: int = 4
    regress_chance: float = 0.16

    # ---------- desejo/arousal ----------
    desire_gain_good: int = 7
    arousal_gain_good: int = 8
    desire_gain_tease: int = 10
    arousal_gain_tease: int = 12

    desire_loss_bad: int = 12
    arousal_loss_bad: int = 14

    # autocontrole
    control_gain: int = 3
    control_loss: int = 6

    # ---------- anti-loop ----------
    max_loop_streak: int = 3
    forced_variation_boost: int = 18
    forced_variation_relief_flag: bool = True  # meta: must_offer_relief

    # ---------- limites ----------
    desire_max: int = 100
    arousal_max: int = 100
    control_min: int = 0
    control_max: int = 100

    # ---------- aleatoriedade ----------
    rng_seed: Optional[int] = None  # se setado, determinístico


# ==========================================================
# STATE DEFAULTS
# ==========================================================
def default_relationship_state(timeline: str) -> Dict[str, Any]:
    tl = (timeline or "").strip() or "cumplice"

    if tl == "universitaria":
        return {
            "stage": "conhecendo",
            "mature_turns": 0,

            "desire": 18,
            "arousal": 10,
            "self_control": 40,  # ↓ reduzido para destravar emocionalmente

            "virginity": "virgem",
            "consummated": False,
            "intimacy_level": 0,

            "allows_touch": True,
            "allows_extended_touch": False,
            "allows_sleep_together": False,
            "allows_masturbation": True,
            "allows_mutual_relief": False,
            "allows_penetration": False,

            # 🔵 NOVO — DINÂMICA INTERNA
            "humor": "equilibrada",      # alegre | melancolica | intensa | provocadora
            "energia": "estavel",        # cansada | energetica | letargica
            "attitude": "equilibrada",   # submissa | dominante | equilibrada

            # 🔵 MEMÓRIA DE PADRÕES
            "pattern_memory": [],

            "_promote_streak": 0,
            "_regress_streak": 0,
            "_loop_streak": 0,
            "_last_pattern": "",
            "_last_updated_ts": int(time.time()),
        }

    return {
        "stage": "casados",
        "mature_turns": 0,

        "desire": 42,
        "arousal": 35,
        "self_control": 35,  # ↓ também reduzido aqui

        "virginity": "nao_virgem",
        "consummated": True,
        "intimacy_level": 3,

        "allows_touch": True,
        "allows_extended_touch": True,
        "allows_sleep_together": True,
        "allows_masturbation": True,
        "allows_mutual_relief": True,
        "allows_penetration": True,

        # 🔵 NOVO — DINÂMICA INTERNA
        "humor": "intensa",
        "energia": "energetica",
        "attitude": "equilibrada",

        # 🔵 MEMÓRIA DE PADRÕES
        "pattern_memory": [],

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

    rules = [
        "- Desejo e excitação podem existir em QUALQUER estágio.",
        "- Limites físicos devem ser respeitados; avance em passos coerentes.",
        "- Se tensão estiver alta, ofereça ALÍVIO PARCIAL coerente com permissões.",
        "- Evite negar tudo repetidamente; varie com afeto, provocação e alternativas realistas.",
    ]

    # Direção adicional quando tensão está alta
    if desire >= 70 or arousal >= 65:
        rules.append("- Tensão alta: seja mais física e direta (sem quebrar os limites canônicos).")

    lines: List[str] = []
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
def _clamp(x: int, lo: int, hi: int) -> int:
    return lo if x < lo else hi if x > hi else x

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _stable_seed(rel: Dict[str, Any], cfg: EngineConfig) -> int:
    """
    Seed estável por turno:
    - Se cfg.rng_seed existe: determinístico total.
    - Senão: mistura _last_updated_ts + mature_turns + desire/arousal.
    """
    if cfg.rng_seed is not None:
        return int(cfg.rng_seed)

    ts = int(rel.get("_last_updated_ts") or 0)
    m = int(rel.get("mature_turns") or 0)
    d = int(rel.get("desire") or 0)
    a = int(rel.get("arousal") or 0)
    # hash simples e estável
    return (ts * 1315423911 + m * 2654435761 + d * 97531 + a * 433) & 0x7FFFFFFF

def _rand(rel: Dict[str, Any], cfg: EngineConfig) -> random.Random:
    return random.Random(_stable_seed(rel, cfg))


def _keyword_score(text: str, keywords: List[str]) -> int:
    t = _norm(text)
    score = 0
    for kw in keywords:
        if kw in t:
            score += 1
    return score


# Padrões mais específicos (reduz falso positivo)
_RE_USER_PUSH = re.compile(r"\b(quero\s+você|vem\s+c[áa]|vamos\s+pro|vamos\s+pra|deita|cama|me\s+toca|me\s+beija)\b", re.I)
_RE_MARY_HARD_BLOCK = re.compile(r"\b(agora\s+n[aã]o|para\s+com\s+isso|n[aã]o\s+posso|sem\s+isso|n[aã]o\s+é\s+hora)\b", re.I)
_RE_MARY_TEASE = re.compile(r"\b(ro[cç]o|mordo|provoco|car[ií]cia|beijo|encosto|sussurro)\b", re.I)
_RE_MARY_CARE = re.compile(r"\b(eu\s+te\s+amo|fica\s+comigo|t[oô]\s+aqui|me\s+desculpa|perd[aã]o|abra[cç]o)\b", re.I)


def _detect_pattern(user_prompt: str, mary_reply: str) -> str:
    u = user_prompt or ""
    a = mary_reply or ""

    user_push = 1 if _RE_USER_PUSH.search(u) else 0
    mary_block = 1 if _RE_MARY_HARD_BLOCK.search(a) else 0
    mary_tease = 1 if _RE_MARY_TEASE.search(a) else 0
    mary_care = 1 if _RE_MARY_CARE.search(a) else 0

    if user_push and mary_block and not mary_tease and not mary_care:
        return "user_push__mary_block"

    if user_push and mary_tease and mary_block:
        return "tease_with_boundary"
    if mary_care and not mary_block:
        return "comfort_progress"
    if not user_push and mary_care:
        return "neutral_bond"
    return "mixed"


def _assess_turn(
    assessor: Optional[AssessorFn],
    user_prompt: str,
    mary_reply: str,
    timeline: str,
) -> Dict[str, Any]:
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

    # “boundary” mais restrito: não conta “não” genérico
    heur["care"] = 3 * (1 if _RE_MARY_CARE.search(mary_reply or "") else 0) + _keyword_score(a, ["carinho", "ternura"])
    heur["tease"] = 3 * (1 if _RE_MARY_TEASE.search(mary_reply or "") else 0) + _keyword_score(a, ["provoca", "roça", "beija"])
    heur["boundary"] = 4 * (1 if _RE_MARY_HARD_BLOCK.search(mary_reply or "") else 0) + _keyword_score(a, ["devagar", "cuidado", "limite"])
    heur["conflict"] = _keyword_score(u + " " + a, ["vai embora", "odeio", "cansado", "frio", "mecânica", "sempre assim"])

    # explicit/suggest_relief ficam só como sinal (não “travam” engine)
    heur["explicit"] = _keyword_score(u + " " + a, ["pau", "buceta", "gozo", "chupa", "fode", "meter"])
    heur["suggest_relief"] = _keyword_score(u + " " + a, ["alívio", "banho", "deita comigo", "dorme comigo", "me alivio", "masturb"])

    heur["good"] = _clamp((heur["care"] // 2) + (heur["tease"] // 2) - heur["conflict"], 0, 10)
    heur["bad"] = _clamp(heur["conflict"] + (2 if heur["boundary"] >= 4 and heur["tease"] == 0 else 0), 0, 10)

    if (timeline or "") == "universitaria":
        if heur["care"] >= 2 and heur["good"] >= 3 and heur["bad"] <= 1 and heur["tease"] >= 1:
            heur["suggested_timeline"] = "cumplice"

    if "primeira vez" in a or "não sou mais virgem" in a or "perdi" in a:
        heur["virginity_change_signal"] = "changed"
        heur["virginity_reason"] = "Sinal textual na fala da Mary."

    if assessor is None:
        return heur

        system = (
        "Você é um avaliador de turnos de um roleplay romântico adulto.\n"
        "Seu objetivo é AJUDAR a progressão natural sem forçar atos além das permissões.\n"
        "\n"
        "RETORNE APENAS um JSON válido (sem markdown, sem texto extra) com as chaves:\n"
        "{good:int(0-10), bad:int(0-10), tease:int(0-10), boundary:int(0-10), care:int(0-10), "
        "conflict:int(0-10), explicit:int(0-10), suggest_relief:int(0-10), "
        "suggested_timeline:str(''|'cumplice'), virginity_change_signal:str(''|'changed'), virginity_reason:str, pattern:str}\n"
        "\n"
        "RUBRICA (muito importante):\n"
        "1) 'boundary' só é ALTO quando há BLOQUEIO DURO/recusa clara e repetida do avanço físico.\n"
        "   - Não marque boundary alto por frases suaves como 'devagar', 'calma', 'espera' se houver afeto e continuidade.\n"
        "2) 'tease' e 'good' devem subir quando há avanço físico coerente com o clima (beijos, carícias, aproximação, tensão, provocação) "
        "   MESMO que ainda haja limites.\n"
        "3) 'suggest_relief' mede se, quando há tensão alta, a resposta oferece UMA ALTERNATIVA REALISTA e consentida "
        "   (ex.: beijar mais, acariciar, ficar no colo, banho juntos, mãos por cima da roupa, dormir abraçados, aliviar sem ultrapassar limites).\n"
        "4) 'bad' sobe quando há stonewalling/negação repetitiva SEM alternativa (loop de 'não pode' / 'agora não' / 'sem isso') "
        "   ou quebra emocional.\n"
        "5) 'conflict' é só briga/hostilidade/desconexão, não confunda com tensão erótica.\n"
        "6) 'explicit' é apenas sinal de vocabulário direto; NÃO deve aumentar 'bad' por si só.\n"
        "7) Se TIMELINE=universitaria e houver evolução afetiva + tensão + alternativas consistentes, pode sugerir 'cumplice'.\n"
    )

    user = (
        f"TIMELINE={timeline}\n"
        "Avalie com foco em:\n"
        "- Progressão sensual/afetiva com coerência\n"
        "- Evitar loop (negação repetitiva sem alternativa)\n"
        "- Presença de alternativas de alívio parcial quando a tensão está alta\n"
        "- Respeito aos limites canônicos (não penalize limites, penalize ausência de alternativas)\n"
        "\n"
        f"USER_PROMPT:\n{user_prompt}\n\n"
        f"MARY_REPLY:\n{mary_reply}\n"
    )
    try:
        raw = (assessor(system, user) or "").strip()
        obj = json.loads(raw)

        out = dict(heur)
        for k in out.keys():
            if k in obj:
                out[k] = obj[k]

        # normalizações
        for k in ("good", "bad", "tease", "boundary", "care", "conflict", "explicit", "suggest_relief"):
            out[k] = int(out.get(k) or 0)

        out["suggested_timeline"] = str(out.get("suggested_timeline") or "").strip()
        out["virginity_change_signal"] = str(out.get("virginity_change_signal") or "").strip()
        out["virginity_reason"] = str(out.get("virginity_reason") or "").strip()
        out["pattern"] = str(out.get("pattern") or heur["pattern"]).strip()
        return out
    except Exception:
        return heur


def _apply_permissions(rel: Dict[str, Any], timeline: str) -> None:
    tl = (timeline or "").strip() or "cumplice"
    stage = str(rel.get("stage") or "conhecendo")

    desire = int(rel.get("desire") or 0)
    arousal = int(rel.get("arousal") or 0)
    mature = int(rel.get("mature_turns") or 0)
    control = int(rel.get("self_control") or 0)

    # Baseline por timeline
    if tl == "universitaria":
        rel["allows_touch"] = True
        rel["allows_masturbation"] = True
        rel["allows_penetration"] = False
    else:
        rel["allows_touch"] = True
        rel["allows_masturbation"] = True
        rel["allows_penetration"] = True

    # Stage gates (limites físicos, não afetam desejo)
    if stage == "conhecendo":
        rel["allows_extended_touch"] = (desire >= 30 or arousal >= 25)
        rel["allows_sleep_together"] = (mature >= 4 and desire >= 32)
        # mutual relief: exige maturação OU tensão alta com controle baixo/moderado
        rel["allows_mutual_relief"] = (
            (mature >= 6 and desire >= 40 and arousal >= 35) or
            (desire >= 55 and arousal >= 50 and control <= 55)
        )
    elif stage in ("aproximando", "conectados"):
        rel["allows_extended_touch"] = True
        rel["allows_sleep_together"] = True
        rel["allows_mutual_relief"] = (mature >= 5 or (desire >= 42 and arousal >= 38))
    else:
        rel["allows_extended_touch"] = True
        rel["allows_sleep_together"] = True
        rel["allows_mutual_relief"] = True

    # Penetração: só se timeline permitir
    rel["allows_penetration"] = (tl != "universitaria")


def _maybe_progress_stage(rel: Dict[str, Any], cfg: EngineConfig, rnd: random.Random) -> Tuple[bool, str]:
    stage = str(rel.get("stage") or "conhecendo")
    mature = int(rel.get("mature_turns") or 0)
    streak = int(rel.get("_promote_streak") or 0)

    order = ["conhecendo", "aproximando", "conectados", "estável", "casados"]
    if stage not in order:
        stage = order[0]
    idx = order.index(stage)
    if idx >= len(order) - 1:
        rel["_promote_streak"] = 0
        return False, stage

    if mature < cfg.promote_threshold:
        return False, stage

    chance = cfg.promote_chance + (0.03 * streak)
    if rnd.random() < chance:
        new_stage = order[idx + 1]
        rel["stage"] = new_stage
        rel["_promote_streak"] = 0
        return True, new_stage

    rel["_promote_streak"] = streak + 1
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

    # se não regrediu, mantém streak (não zera)
    return False, stage


def _update_loop_detector(rel: Dict[str, Any], pattern: str, cfg: EngineConfig) -> bool:
    last = str(rel.get("_last_pattern") or "")
    loop = int(rel.get("_loop_streak") or 0)

    if pattern and pattern == last:
        loop += 1
    else:
        # novo padrão inicia em 1 (não 0) pra resposta mais rápida
        loop = 1 if pattern else 0

    rel["_last_pattern"] = pattern
    rel["_loop_streak"] = loop
    return loop >= cfg.max_loop_streak


# ==========================================================
# PUBLIC
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
    rel = dict(rel_state or {})
    tl = (timeline or "").strip() or "cumplice"

    # garantir campos
    base = default_relationship_state(tl)
    for k, v in base.items():
        rel.setdefault(k, v)

    rnd = _rand(rel, cfg)

    assessment = _assess_turn(assessor, user_prompt, mary_reply, tl)

    good = int(assessment.get("good") or 0)
    bad = int(assessment.get("bad") or 0)
    tease = int(assessment.get("tease") or 0)
    boundary = int(assessment.get("boundary") or 0)
    care = int(assessment.get("care") or 0)
    conflict = int(assessment.get("conflict") or 0)
    pattern = str(assessment.get("pattern") or "")

    # hazard_p (0..1)
    hazard_raw = (0.10 * conflict) + (0.07 * bad) + (0.06 * (1 if boundary >= 4 else 0)) + (0.04 * (1 if pattern == "user_push__mary_block" else 0))
    hazard_p = max(0.0, min(1.0, hazard_raw))

    # mature_turns cresce em turnos bons/coerentes
    mature_turns = int(rel.get("mature_turns") or 0)
    if good >= 3 and bad <= 2:
        mature_turns += 1
        rel["mature_turns"] = mature_turns
        rel["_regress_streak"] = 0
    else:
        rel["_regress_streak"] = int(rel.get("_regress_streak") or 0) + 1

    # loop detector
    force_variation = _update_loop_detector(rel, pattern, cfg)

    desire = int(rel.get("desire") or 0)
    arousal = int(rel.get("arousal") or 0)
    control = int(rel.get("self_control") or 0)

    if bad >= 4 or conflict >= 3:
        desire -= cfg.desire_loss_bad
        arousal -= cfg.arousal_loss_bad
        control += cfg.control_gain
    else:
        if tease >= 2:
            desire += cfg.desire_gain_tease
            arousal += cfg.arousal_gain_tease
        else:
            desire += cfg.desire_gain_good
            arousal += cfg.arousal_gain_good

        if care >= 2:
            control -= 2

        if boundary >= 4 and care == 0 and tease == 0:
            control += 3

    must_offer_relief = False
    if force_variation:
        desire += cfg.forced_variation_boost
        arousal += int(cfg.forced_variation_boost * 0.7)
        control -= 4
        hazard_p = max(0.0, hazard_p - 0.18)
        must_offer_relief = bool(cfg.forced_variation_relief_flag)

    rel["desire"] = _clamp(desire, 0, cfg.desire_max)
    rel["arousal"] = _clamp(arousal, 0, cfg.arousal_max)
    rel["self_control"] = _clamp(control, cfg.control_min, cfg.control_max)

    _apply_permissions(rel, tl)

    # Decisão de estágio: regressão primeiro, senão progressão
    regressed, _ = _maybe_regress_stage(rel, cfg, rnd)
    progressed = False
    if not regressed:
        progressed, _ = _maybe_progress_stage(rel, cfg, rnd)

    # intimacy_level (0..5)
    stage = str(rel.get("stage") or "conhecendo")
    stage_to_lvl = {
        "conhecendo": 0,
        "aproximando": 1,
        "conectados": 2,
        "estável": 3,
        "casados": 4,
    }
    lvl = stage_to_lvl.get(stage, 0)
    if rel["desire"] >= 70 and rel["arousal"] >= 60:
        lvl = min(5, lvl + 1)
    rel["intimacy_level"] = lvl

    virginity_changed = False
    virginity_reason = ""
    if str(assessment.get("virginity_change_signal") or "").strip() == "changed":
        virginity_changed = True
        virginity_reason = str(assessment.get("virginity_reason") or "Sinal do assessor/heurístico.")

    suggested_timeline = str(assessment.get("suggested_timeline") or "").strip()
    if tl != "universitaria":
        suggested_timeline = ""

    meta = {
        "hazard_p": float(hazard_p),
        "mature_turns": int(rel.get("mature_turns") or 0),
        "pattern": pattern,
        "forced_variation": bool(force_variation),
        "must_offer_relief": bool(must_offer_relief),
        "stage_progressed": bool(progressed),
        "stage_regressed": bool(regressed),
        "suggested_timeline": suggested_timeline,
        "virginity_changed": bool(virginity_changed),
        "virginity_reason": virginity_reason,
        "engine_v": "2.2",
        "_ts": int(time.time()),
    }

    rel["_last_updated_ts"] = meta["_ts"]
    return rel, assessment, meta
