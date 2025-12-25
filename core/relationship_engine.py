from __future__ import annotations

"""
core.relationship_engine

Objetivo:
- Evoluir o "relationship_state" de forma dinâmica (com inércia e ruído leve),
  sem exigir passos manuais/predeterminados.
- Produzir um bloco curto para ser injetado no system prompt (canônico).
- Separar a lógica do service.py (que só chama evolve_relationship e persiste).

Como funciona (Degrau 1):
1) O service mantém um dict "rel_state" persistido em facts: rel.state::{timeline}
2) A cada turno, chamamos um "avaliador" LLM (saída JSON) para sugerir deltas pequenos
3) Aplicamos deltas com clamp + inércia
4) Opcionalmente promovemos/regredimos "stage" com chance (não determinístico)
5) Se timeline=universitaria e stage/condições atingirem maturidade -> sugerimos timeline "cumplice"

NOVO (virgindade dinâmica):
- Virgindade é um campo do relationship_state (virginity: "virgem"|"nao_virgem").
- O engine só muda de "virgem" para "nao_virgem" quando:
  (a) o avaliador sinaliza consummated=true (consumação clara em cena)
  (b) o stage já atingiu "intimidade" (ou acima)
  (c) confiança+apego suficientes e medo/culpa controlados
  (d) boundaries não está "alta"
- Persistência e prevalência são responsabilidade do service.py (facts).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple
import json
import random
import re


LLMAssessor = Callable[[str, str], str]


REL_STAGES = [
    "conhecendo",
    "ficando",
    "namoro",
    "intimidade",
    "noivado",
    "pre_casamento",
    "casados",
]


@dataclass(frozen=True)
class EngineConfig:
    # máximo de variação por turno, por métrica
    max_step: int = 8
    # limites do score
    lo: int = 0
    hi: int = 100
    # prob base de mudança de estágio
    base_promote: float = 0.05
    base_regress: float = 0.04
    # ruído para evitar previsibilidade (aplicado na prob)
    noise: float = 0.06


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(n: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(n)))


def default_relationship_state(timeline: str) -> Dict[str, Any]:
    tl = (timeline or "").strip() or "cumplice"

    if tl == "universitaria":
        # início: vulnerável + tensão + medo social/moral
        return {
            "stage": "conhecendo",
            "trust": 18,
            "tension": 28,
            "fear": 45,
            "guilt": 30,
            "attachment": 15,
            "boundaries": "alta",           # alta|media|baixa
            "conflict_theme": "nenhum",     # nenhum|familia|moral|rotina|ciume|risco
            "last_eval_ts": "",
            "last_stage_change_ts": "",
            "_promote_streak": 0,
            "_regress_streak": 0,

            # ✅ Virgindade dinâmica (baseline)
            "virginity": "virgem",          # virgem|nao_virgem
            "intimacy_level": 0,            # 0..3
            "consummated": False,           # True quando houver consumação clara
        }

    # cúmplice: já casados; ainda pode oscilar em confiança/tensão/medo por eventos
    return {
        "stage": "casados",
        "trust": 72,
        "tension": 55,
        "fear": 12,
        "guilt": 8,
        "attachment": 78,
        "boundaries": "baixa",
        "conflict_theme": "rotina",
        "last_eval_ts": "",
        "last_stage_change_ts": "",
        "_promote_streak": 0,
        "_regress_streak": 0,

        # ✅ Em cúmplice, normalmente já não é virgem
        "virginity": "nao_virgem",
        "intimacy_level": 3,
        "consummated": True,
    }


def rel_state_to_prompt_block(rel: Dict[str, Any]) -> str:
    if not isinstance(rel, dict):
        return ""
    return (
        "[ESTADO DE RELAÇÃO — CANÔNICO]\n"
        f"- stage: {rel.get('stage')}\n"
        f"- trust: {rel.get('trust')}\n"
        f"- tension: {rel.get('tension')}\n"
        f"- fear: {rel.get('fear')}\n"
        f"- guilt: {rel.get('guilt')}\n"
        f"- attachment: {rel.get('attachment')}\n"
        f"- boundaries: {rel.get('boundaries')}\n"
        f"- conflict_theme: {rel.get('conflict_theme')}\n"
        f"- intimacy_level: {rel.get('intimacy_level')}\n"
        f"- virginity: {rel.get('virginity')}\n"
        f"- consummated: {rel.get('consummated')}\n"
    ).strip()


def _safe_json_parse(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    if not s:
        return {}
    # tenta achar um objeto JSON no meio do texto
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def _readiness(rel: Dict[str, Any]) -> float:
    """Score de prontidão para avançar (não determinístico)."""
    trust = float(rel.get("trust", 0))
    attach = float(rel.get("attachment", 0))
    tension = float(rel.get("tension", 0))
    fear = float(rel.get("fear", 0))
    guilt = float(rel.get("guilt", 0))

    # Amor + confiança + tensão; penaliza medo/culpa.
    return (0.38 * trust) + (0.38 * attach) + (0.18 * tension) - (0.22 * fear) - (0.10 * guilt)


def _apply_deltas(rel: Dict[str, Any], upd: Dict[str, Any], cfg: EngineConfig) -> Dict[str, Any]:
    def _d(k: str) -> int:
        try:
            return int(upd.get(k, 0))
        except Exception:
            return 0

    for key in ["trust", "tension", "fear", "guilt", "attachment"]:
        delta = _d(f"{key}_delta")
        if delta > cfg.max_step:
            delta = cfg.max_step
        if delta < -cfg.max_step:
            delta = -cfg.max_step
        rel[key] = _clamp(int(rel.get(key, 0)) + delta, cfg.lo, cfg.hi)

    if isinstance(upd.get("conflict_theme"), str) and upd.get("conflict_theme"):
        rel["conflict_theme"] = str(upd["conflict_theme"]).strip()

    if isinstance(upd.get("boundaries"), str) and upd.get("boundaries"):
        rel["boundaries"] = str(upd["boundaries"]).strip()

    # intimacy_level (0..3)
    try:
        il = int(upd.get("intimacy_level", rel.get("intimacy_level", 0)))
    except Exception:
        il = int(rel.get("intimacy_level", 0) or 0)
    rel["intimacy_level"] = _clamp(il, 0, 3)

    rel["last_eval_ts"] = _now_iso()
    rel.setdefault("_promote_streak", 0)
    rel.setdefault("_regress_streak", 0)

    # mantém defaults de virgindade caso não existam
    rel.setdefault("virginity", "virgem" if rel.get("stage") != "casados" else "nao_virgem")
    rel.setdefault("consummated", False)
    return rel


def _maybe_shift_stage(rel: Dict[str, Any], upd: Dict[str, Any], timeline: str, cfg: EngineConfig) -> Tuple[Dict[str, Any], bool]:
    stage = str(rel.get("stage") or "conhecendo")
    if stage not in REL_STAGES:
        stage = "conhecendo" if (timeline or "") == "universitaria" else "casados"

    idx = REL_STAGES.index(stage)

    stage_hint = str(upd.get("stage_hint") or "stay").strip().lower()
    trust_breach = bool(upd.get("trust_breach") is True)

    readiness = _readiness(rel)

    # --- regressão (quebra de confiança + medo alto) ---
    regress_chance = cfg.base_regress
    if trust_breach:
        regress_chance += 0.18
    if rel.get("fear", 0) >= 70:
        regress_chance += 0.10
    if stage_hint == "regress":
        regress_chance += 0.12

    regress_chance += random.uniform(-cfg.noise, cfg.noise)
    regress_chance = max(0.0, min(0.65, regress_chance))

    if idx > 0 and random.random() < regress_chance:
        rel["stage"] = REL_STAGES[idx - 1]
        rel["last_stage_change_ts"] = _now_iso()
        rel["_regress_streak"] = int(rel.get("_regress_streak", 0)) + 1
        rel["_promote_streak"] = 0
        return rel, True

    # --- promoção (prontidão + sinal do avaliador) ---
    promote_chance = cfg.base_promote
    if stage_hint == "promote":
        promote_chance += 0.14

    # readiness acima de ~45 começa a permitir avanço
    promote_chance += max(0.0, min(0.45, (readiness - 45.0) / 120.0))

    # trava se culpa alta em universitária
    if (timeline or "") == "universitaria" and rel.get("guilt", 0) >= 75:
        promote_chance *= 0.35

    # trava se medo alto
    if rel.get("fear", 0) >= 75:
        promote_chance *= 0.30

    promote_chance += random.uniform(-cfg.noise, cfg.noise)
    promote_chance = max(0.0, min(0.65, promote_chance))

    if idx < len(REL_STAGES) - 1 and random.random() < promote_chance:
        rel["stage"] = REL_STAGES[idx + 1]
        rel["last_stage_change_ts"] = _now_iso()
        rel["_promote_streak"] = int(rel.get("_promote_streak", 0)) + 1
        rel["_regress_streak"] = 0
        return rel, True

    return rel, False


def _maybe_flip_virginity(rel: Dict[str, Any], upd: Dict[str, Any], timeline: str) -> Dict[str, Any]:
    """
    Virgindade dinâmica:
    - Só muda em universitária.
    - Só muda se ainda está "virgem".
    - Só muda se avaliador sinaliza consumação clara (consummated=true).
    - E se condições emocionais + stage permitem.
    """
    if (timeline or "") != "universitaria":
        return rel

    virginity = str(rel.get("virginity") or "virgem").strip().lower()
    if virginity != "virgem":
        return rel

    consummated_flag = bool(upd.get("consummated") is True)
    if not consummated_flag:
        return rel

    stage = str(rel.get("stage") or "conhecendo")
    if stage not in REL_STAGES:
        stage = "conhecendo"
    if REL_STAGES.index(stage) < REL_STAGES.index("intimidade"):
        return rel

    trust = int(rel.get("trust", 0))
    attach = int(rel.get("attachment", 0))
    fear = int(rel.get("fear", 0))
    guilt = int(rel.get("guilt", 0))
    boundaries = str(rel.get("boundaries") or "alta").strip().lower()

    # condições mínimas (ajuste fino depois)
    if trust < 65 or attach < 70:
        return rel
    if fear > 35 or guilt > 45:
        return rel
    if boundaries == "alta":
        return rel

    # ✅ muda canonicamente
    rel["virginity"] = "nao_virgem"
    rel["consummated"] = True
    rel["intimacy_level"] = max(int(rel.get("intimacy_level", 0) or 0), 3)

    return rel


def _build_assessor_prompts(timeline: str, rel: Dict[str, Any], user_msg: str, mary_msg: str) -> Tuple[str, str]:
    system = (
        "Você é um avaliador de dinâmica de relacionamento para um roleplay.\n"
        "Sua saída DEVE ser apenas um JSON válido.\n"
        "Objetivo: medir sinais emocionais e sugerir deltas pequenos (inteiros).\n"
        "Regras:\n"
        "- Não invente fatos fora do que está em USER e MARY.\n"
        "- Deltas devem estar entre -8 e +8.\n"
        "- stage_hint deve ser: stay | promote | regress.\n"
        "- conflict_theme deve ser: nenhum | familia | moral | rotina | ciume | risco.\n"
        "- boundaries deve ser: alta | media | baixa.\n"
        "- trust_breach: true apenas se houver quebra clara de confiança.\n"
        "- intimacy_level: 0..3 (0 nenhum, 1 leve, 2 médio, 3 alto)\n"
        "- consummated: true apenas se houver consumação clara em cena.\n"
    )

    payload = {
        "timeline": timeline,
        "rel_state": {
            "stage": rel.get("stage"),
            "trust": rel.get("trust"),
            "tension": rel.get("tension"),
            "fear": rel.get("fear"),
            "guilt": rel.get("guilt"),
            "attachment": rel.get("attachment"),
            "boundaries": rel.get("boundaries"),
            "conflict_theme": rel.get("conflict_theme"),
            "intimacy_level": rel.get("intimacy_level"),
            "virginity": rel.get("virginity"),
            "consummated": rel.get("consummated"),
        },
        "turn": {"user": user_msg, "mary": mary_msg},
        "return_schema": {
            "trust_delta": "int (-8..8)",
            "tension_delta": "int (-8..8)",
            "fear_delta": "int (-8..8)",
            "guilt_delta": "int (-8..8)",
            "attachment_delta": "int (-8..8)",
            "stage_hint": "stay|promote|regress",
            "conflict_theme": "nenhum|familia|moral|rotina|ciume|risco",
            "boundaries": "alta|media|baixa",
            "trust_breach": "bool",
            "intimacy_level": "int 0..3",
            "consummated": "bool",
        },
    }

    user = json.dumps(payload, ensure_ascii=False)
    return system, user


def evolve_relationship(
    rel_state: Dict[str, Any],
    user_msg: str,
    mary_msg: str,
    timeline: str,
    llm_assessor: LLMAssessor,
    cfg: EngineConfig = EngineConfig(),
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Atualiza rel_state com base no turno (user_msg + mary_msg).
    Retorna (new_rel_state, assessment_json, meta).

    meta pode conter:
    - stage_changed: bool
    - suggested_timeline: "cumplice" | None
    """
    rel = dict(rel_state or {})
    # garante base
    base = default_relationship_state(timeline)
    for k, v in base.items():
        rel.setdefault(k, v)

    sys_p, user_p = _build_assessor_prompts(timeline, rel, user_msg, mary_msg)
    raw = ""
    try:
        raw = llm_assessor(sys_p, user_p) or ""
    except Exception:
        raw = ""

    assessment = _safe_json_parse(raw) if raw else {}
    if not isinstance(assessment, dict):
        assessment = {}

    rel = _apply_deltas(rel, assessment, cfg)

    # ✅ virgindade dinâmica (antes da mudança de stage)
    rel = _maybe_flip_virginity(rel, assessment, timeline)

    rel, changed = _maybe_shift_stage(rel, assessment, timeline, cfg)

    meta: Dict[str, Any] = {"stage_changed": bool(changed)}

    # sugestão de migração universitária -> cúmplice (não automática aqui; o service decide)
    if (timeline or "") == "universitaria":
        # condição de maturidade: confiança + apego altos, medo/culpa controlados
        if (
            str(rel.get("stage")) in ("pre_casamento", "casados")
            and int(rel.get("trust", 0)) >= 68
            and int(rel.get("attachment", 0)) >= 70
            and int(rel.get("fear", 0)) <= 28
            and int(rel.get("guilt", 0)) <= 35
        ):
            meta["suggested_timeline"] = "cumplice"
        else:
            meta["suggested_timeline"] = None

    return rel, assessment, meta
