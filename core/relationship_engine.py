# core/relationship_engine.py
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Callable


# ==========================
# Types / Config
# ==========================

RelState = Dict[str, Any]
Assessment = Dict[str, Any]


@dataclass(frozen=True)
class EngineConfig:
    # Limites por turno (evita “pulo” emocional)
    max_delta: int = 8
    # Ruído controlado para evitar previsibilidade (pequeno!)
    noise: int = 1
    # Inércia: quanto do delta realmente entra (0..1)
    inertia: float = 0.85
    # Quantos turnos “estáveis” para promover estágio
    promote_streak_needed: int = 3
    # Quantos turnos “ruins” para regredir estágio
    regress_streak_needed: int = 2


# Ordem de evolução (microfases)
STAGE_ORDER = [
    "conhecendo",
    "ficando",
    "namoro",
    "intimidade",
    "noivado",
    "pre_casamento",
    "casados",
]

# Se quiser permitir regressão até certo ponto, mantenha esta lista.
# (Ex.: não voltar de “noivado” para “conhecendo” facilmente)
MIN_STAGE_INDEX_UNIVERSITARIA = 0


# ==========================
# Defaults
# ==========================

def default_relationship_state(timeline: str) -> RelState:
    """
    Estado inicial (default) caso ainda não exista fact persistido.
    Idealmente você usa o do canon.py, mas isso aqui é fallback seguro.
    """
    timeline = (timeline or "").strip() or "cumplice"

    if timeline == "universitaria":
        return {
            "stage": "conhecendo",
            "trust": 20,
            "tension": 35,
            "fear": 45,
            "guilt": 30,
            "attachment": 15,
            "boundaries": "alta",
            "last_signal": "primeiro_contato",
            "notes": "Início de vínculo. Desejo existe, mas há cautela.",
            # Contadores internos (não precisam ir para prompt)
            "_promote_streak": 0,
            "_regress_streak": 0,
        }

    # cúmplice
    return {
        "stage": "casados",
        "trust": 75,
        "tension": 70,
        "fear": 20,
        "guilt": 10,
        "attachment": 85,
        "boundaries": "baixa",
        "last_signal": "rotina_intima",
        "notes": "Vínculo consolidado e íntimo.",
        "_promote_streak": 0,
        "_regress_streak": 0,
    }


# ==========================
# Prompt helpers
# ==========================

def rel_state_to_prompt_block(rel: RelState) -> str:
    """
    Bloco curto e 'model-friendly' para injetar no prompt.
    Não inclua chaves internas (_promote_streak etc).
    """
    keys = ["stage", "trust", "tension", "fear", "guilt", "attachment", "boundaries", "last_signal", "notes"]
    lines = ["[ESTADO DE RELAÇÃO — CANÔNICO]"]
    for k in keys:
        if k in rel:
            lines.append(f"- {k}: {rel[k]}")
    return "\n".join(lines)


# ==========================
# Assessment (LLM JSON)
# ==========================

ASSESSMENT_SYSTEM = """Você é um avaliador psicológico/narrativo.
Sua tarefa NÃO é escrever história. Você apenas avalia sinais do turno e retorna JSON.
Siga estritamente o schema e responda SOMENTE com JSON válido.
"""

ASSESSMENT_INSTRUCTIONS = """Analise:
(1) a mensagem do usuário
(2) a resposta da personagem

Retorne deltas pequenos (-8..+8) para:
trust, tension, fear, guilt, attachment

Também retorne:
- signal: uma palavra curta descrevendo o evento (ex: "flirt", "confession", "kiss", "touch", "retreat", "argument", "reassure", "care", "jealousy", "family", "moral")
- intimacy_level: 0..3 (0 nenhum, 1 leve, 2 médio, 3 alto)
- stage_hint: "promote" | "regress" | "stay"
- confidence: 0..1

Schema:
{
  "deltas": {"trust": int, "tension": int, "fear": int, "guilt": int, "attachment": int},
  "signal": str,
  "intimacy_level": int,
  "stage_hint": str,
  "confidence": float
}
"""

def build_assessment_prompt(user_msg: str, mary_reply: str) -> str:
    return f"""{ASSESSMENT_INSTRUCTIONS}

USUÁRIO:
{user_msg}

PERSONAGEM:
{mary_reply}
"""


def parse_assessment_json(text: str) -> Assessment:
    """
    Extrai JSON robustamente (caso venha com lixo ao redor).
    """
    text = (text or "").strip()
    # tenta carregar direto
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass

    # tenta achar o primeiro {...} grande
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    return {}


# ==========================
# Update mechanics
# ==========================

def _clip_int(x: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(x)))


def _clip_delta(d: int, max_abs: int) -> int:
    d = int(d)
    if d > max_abs:
        return max_abs
    if d < -max_abs:
        return -max_abs
    return d


def _apply_delta(cur: int, delta: int, cfg: EngineConfig) -> int:
    """
    Aplica delta com inércia e ruído mínimo para evitar previsibilidade.
    """
    delta = _clip_delta(delta, cfg.max_delta)
    # inércia (suaviza)
    effective = int(round(delta * cfg.inertia))
    # ruído leve controlado
    if cfg.noise > 0:
        effective += random.randint(-cfg.noise, cfg.noise)
    return _clip_int(cur + effective)


def update_relationship_state(
    rel: RelState,
    assessment: Assessment,
    cfg: EngineConfig,
    timeline: str,
) -> Tuple[RelState, Dict[str, Any]]:
    """
    Atualiza rel_state a partir do assessment e decide promoção/regressão.
    Retorna (novo_rel_state, meta) onde meta pode sugerir troca de timeline.
    """
    rel = dict(rel or {})
    timeline = (timeline or "").strip() or "cumplice"

    deltas = (assessment.get("deltas") or {}) if isinstance(assessment, dict) else {}
    signal = (assessment.get("signal") or "none") if isinstance(assessment, dict) else "none"
    intimacy_level = int(assessment.get("intimacy_level") or 0) if isinstance(assessment, dict) else 0
    stage_hint = (assessment.get("stage_hint") or "stay") if isinstance(assessment, dict) else "stay"
    conf = float(assessment.get("confidence") or 0.0) if isinstance(assessment, dict) else 0.0

    # Se confiança do avaliador for muito baixa, reduza impacto
    scale = 1.0
    if conf < 0.35:
        scale = 0.5

    for k in ["trust", "tension", "fear", "guilt", "attachment"]:
        cur = int(rel.get(k) or 0)
        d = int(deltas.get(k) or 0)
        d = int(round(d * scale))
        rel[k] = _apply_delta(cur, d, cfg)

    rel["last_signal"] = signal

    # boundaries pode ajustar conforme medo/culpa vs trust/tension
    rel["boundaries"] = _infer_boundaries(rel, timeline)

    # Atualiza notas curtas (opcional, ajuda o modelo)
    rel["notes"] = _infer_notes(rel, timeline)

    # Promoção/regressão de estágio (com streak)
    rel.setdefault("_promote_streak", 0)
    rel.setdefault("_regress_streak", 0)

    promote_ok = _promotion_condition(rel, timeline, intimacy_level)
    regress_ok = _regression_condition(rel, timeline)

    if stage_hint == "promote" and promote_ok:
        rel["_promote_streak"] += 1
        rel["_regress_streak"] = 0
    elif stage_hint == "regress" and regress_ok:
        rel["_regress_streak"] += 1
        rel["_promote_streak"] = 0
    else:
        # sem tendência clara: decaimento leve dos streaks
        rel["_promote_streak"] = max(0, int(rel["_promote_streak"]) - 1)
        rel["_regress_streak"] = max(0, int(rel["_regress_streak"]) - 1)

    stage_before = rel.get("stage") or ("conhecendo" if timeline == "universitaria" else "casados")
    stage_after = stage_before

    if rel["_promote_streak"] >= cfg.promote_streak_needed:
        stage_after = _bump_stage(stage_before, +1)
        rel["_promote_streak"] = 0

    if rel["_regress_streak"] >= cfg.regress_streak_needed:
        stage_after = _bump_stage(stage_after, -1)
        rel["_regress_streak"] = 0

    # trava regressão abaixo do mínimo na universitária
    if timeline == "universitaria":
        stage_after = _floor_stage(stage_after, MIN_STAGE_INDEX_UNIVERSITARIA)

    rel["stage"] = stage_after

    meta: Dict[str, Any] = {
        "stage_before": stage_before,
        "stage_after": stage_after,
        "suggested_timeline": None,
    }

    # Sugestão de troca de timeline:
    # Se universitária chegou em "casados", sugere timeline cúmplice
    if timeline == "universitaria" and stage_after == "casados":
        meta["suggested_timeline"] = "cumplice"

    return rel, meta


def _infer_boundaries(rel: RelState, timeline: str) -> str:
    """
    Boundaries = “freios” atuais.
    Quanto maior fear/guilt, maior boundary.
    Quanto maior trust/attachment, menor boundary.
    """
    fear = int(rel.get("fear") or 0)
    guilt = int(rel.get("guilt") or 0)
    trust = int(rel.get("trust") or 0)
    attach = int(rel.get("attachment") or 0)

    pressure = fear * 0.6 + guilt * 0.4
    safety = trust * 0.55 + attach * 0.45
    score = pressure - safety  # >0: mais freio

    if score >= 20:
        return "alta"
    if score >= -10:
        return "media"
    return "baixa"


def _infer_notes(rel: RelState, timeline: str) -> str:
    """
    Uma frase curta que ajuda a personagem a “sentir” coerente.
    """
    t = int(rel.get("tension") or 0)
    tr = int(rel.get("trust") or 0)
    f = int(rel.get("fear") or 0)
    g = int(rel.get("guilt") or 0)
    a = int(rel.get("attachment") or 0)

    if f > 65 or g > 65:
        return "Conflito interno alto: desejo existe, mas há medo/culpa puxando para trás."
    if t > 70 and tr < 45:
        return "Atração forte, mas confiança ainda instável; provoca e recua."
    if tr > 70 and a > 70 and f < 35 and g < 35:
        return "Entrega emocional sólida; carinho e intimidade fluem com naturalidade."
    if a > 70 and (f > 45 or g > 45):
        return "Amor forte, porém pressionado por receio moral/familiar; busca equilíbrio."
    return "Vínculo em evolução; sentimentos oscilam conforme o momento."


def _promotion_condition(rel: RelState, timeline: str, intimacy_level: int) -> bool:
    """
    Condição mínima para permitir promoção.
    """
    trust = int(rel.get("trust") or 0)
    attachment = int(rel.get("attachment") or 0)
    fear = int(rel.get("fear") or 0)
    guilt = int(rel.get("guilt") or 0)

    # Não promove se medo+culpa muito altos
    if fear > 70 or guilt > 70:
        return False

    # Para universitária: exige construção (trust+attachment) e algum sinal de intimidade
    if timeline == "universitaria":
        return (trust + attachment) >= 110 and intimacy_level >= 1

    # Para cúmplice: promoção é menos relevante, mas pode fortalecer (quase sempre ok)
    return (trust + attachment) >= 120


def _regression_condition(rel: RelState, timeline: str) -> bool:
    """
    Condição para permitir regressão (briga, quebra de confiança, culpa/medo dominando).
    """
    trust = int(rel.get("trust") or 0)
    fear = int(rel.get("fear") or 0)
    guilt = int(rel.get("guilt") or 0)

    # regressa se confiança baixa e pressão alta
    return trust < 35 and (fear + guilt) > 110


def _bump_stage(stage: str, step: int) -> str:
    stage = (stage or "").strip() or "conhecendo"
    try:
        idx = STAGE_ORDER.index(stage)
    except ValueError:
        idx = 0
    idx2 = max(0, min(len(STAGE_ORDER) - 1, idx + step))
    return STAGE_ORDER[idx2]


def _floor_stage(stage: str, min_index: int) -> str:
    try:
        idx = STAGE_ORDER.index(stage)
    except ValueError:
        idx = 0
    idx = max(min_index, idx)
    return STAGE_ORDER[idx]


# ==========================
# High-level helper
# ==========================

def evolve_relationship(
    rel: Optional[RelState],
    user_msg: str,
    mary_reply: str,
    timeline: str,
    llm_assessor: Callable[[str, str], str],
    cfg: Optional[EngineConfig] = None,
) -> Tuple[RelState, Assessment, Dict[str, Any]]:
    """
    Função principal para uso no service.py.

    - llm_assessor(system_prompt, user_prompt) -> raw_text
      (O service.py fornece a função que chama seu provider/modelo.)
    """
    cfg = cfg or EngineConfig()
    rel = rel or default_relationship_state(timeline)

    system_prompt = ASSESSMENT_SYSTEM
    user_prompt = build_assessment_prompt(user_msg, mary_reply)

    raw = llm_assessor(system_prompt, user_prompt)
    assessment = parse_assessment_json(raw)

    new_rel, meta = update_relationship_state(rel, assessment, cfg, timeline)
    return new_rel, assessment, meta
