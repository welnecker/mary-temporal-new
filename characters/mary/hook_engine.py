from __future__ import annotations

from typing import Any, Dict, List

from .runtime_utils import (
    _SS_PREFIX,
    fact_str,
    normalize_timeline,
    ss_get,
    ss_set,
    t_norm,
    turn_counter_key,
)


def hook_state_key(usuario_key: str, timeline: str) -> str:
    tl = normalize_timeline(timeline)
    return f"{_SS_PREFIX}hook_state::{usuario_key}::{tl}"


def get_hook_state(usuario_key: str, timeline: str) -> Dict[str, Any]:
    raw = ss_get(hook_state_key(usuario_key, timeline), None)
    if isinstance(raw, dict):
        return dict(raw)
    return {
        "active_hook": "",
        "hook_type": "",
        "hook_stage": "",
        "opened_at_turn": 0,
        "last_progress_turn": 0,
        "status": "idle",
        "source": "",
        "times_reused": 0,
    }


def save_hook_state(usuario_key: str, timeline: str, state: Dict[str, Any]) -> None:
    ss_set(hook_state_key(usuario_key, timeline), dict(state or {}))


def _extract_event_candidates_from_facts(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(facts, dict):
        return out

    blob_parts: List[str] = []

    def _walk(prefix: str, obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_prefix = f"{prefix}.{k}" if prefix else str(k)
                _walk(new_prefix, v)
        elif isinstance(obj, (list, tuple, set)):
            for i, v in enumerate(obj):
                _walk(f"{prefix}[{i}]", v)
        else:
            try:
                s = str(obj).strip()
            except Exception:
                s = ""
            if s:
                blob_parts.append(f"{prefix}: {s}")

    _walk("", facts)
    blob = t_norm("\n".join(blob_parts))

    if any(k in blob for k in ("happy hour", "happy_hour", "festa", "jantar", "encontro", "aniversario", "aniversário")):
        out.append({
            "id": "social_event_preparation",
            "type": "evento",
            "label": "evento social próximo",
            "score": 0.95,
            "stages": ["lembranca", "horario", "banho", "roupa_mary", "roupa_user", "saida"],
            "source": "facts:event",
        })

    if any(k in blob for k in ("viagem", "viajar", "aeroporto", "hotel", "reserva")):
        out.append({
            "id": "trip_preparation",
            "type": "evento",
            "label": "preparação de viagem",
            "score": 0.82,
            "stages": ["lembranca", "organizacao", "roupa", "detalhe_pratico", "saida"],
            "source": "facts:event",
        })

    rel = facts.get("rel") if isinstance(facts.get("rel"), dict) else {}
    pend = str(rel.get("pendencia", "") or "").strip()
    if pend:
        out.append({
            "id": "pending_emotional_topic",
            "type": "emocional",
            "label": pend[:80],
            "score": 0.88,
            "stages": ["aproximacao", "toque_no_tema", "pergunta", "aprofundamento"],
            "source": "facts:rel.pendencia",
        })

    return out


def _extract_domestic_candidates(facts: Dict[str, Any], prompt: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    local = t_norm(str(
        facts.get("cena.local")
        or facts.get("local_cena_atual")
        or fact_str(facts, "state.local")
        or ""
    ))
    p = t_norm(prompt or "")

    if any(k in local for k in ("apartamento", "casa", "quarto", "banheiro", "sala", "cozinha")):
        out.append({
            "id": "domestic_presence",
            "type": "domestico",
            "label": "cotidiano íntimo",
            "score": 0.55,
            "stages": ["observacao", "micro_convite", "proximidade"],
            "source": "scene:domestic",
        })

    if any(k in p for k in ("roupa", "vestido", "blazer", "banho", "espelho", "cabelo")):
        out.append({
            "id": "appearance_guidance",
            "type": "relacional",
            "label": "orientação estética",
            "score": 0.78,
            "stages": ["observacao", "preferencia", "pedido", "validacao"],
            "source": "prompt:appearance",
        })

    return out


def _extract_observation_candidates(prompt: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    p = t_norm(prompt or "")

    if any(k in p for k in ("silencio", "quieto", "hesitou", "estranho", "olhando", "parado", "distraido", "distraído")):
        out.append({
            "id": "user_observation",
            "type": "observacao",
            "label": "leitura emocional do usuário",
            "score": 0.72,
            "stages": ["observacao", "pergunta", "aprofundamento"],
            "source": "prompt:observation",
        })

    return out


def collect_narrative_opportunities(
    *,
    facts: Dict[str, Any],
    rel: Dict[str, Any],
    prompt: str,
    timeline: str,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    items.extend(_extract_event_candidates_from_facts(facts))
    items.extend(_extract_domestic_candidates(facts, prompt))
    items.extend(_extract_observation_candidates(prompt))

    if isinstance(rel, dict):
        try:
            desire = float(rel.get("desire", 0) or 0)
        except Exception:
            desire = 0.0

        if desire >= 35:
            for it in items:
                if it.get("type") in ("relacional", "domestico"):
                    it["score"] = float(it.get("score", 0.0)) + 0.05

    items.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    return items[:8]


def select_active_hook(
    *,
    usuario_key: str,
    timeline: str,
    opportunities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    state = get_hook_state(usuario_key, timeline)
    active_id = str(state.get("active_hook") or "").strip()
    active_status = str(state.get("status") or "idle").strip()

    if active_id and active_status == "active":
        for op in opportunities:
            if str(op.get("id") or "") == active_id:
                return op

    if opportunities:
        return opportunities[0]

    return {}


def _default_hook_stage(hook: Dict[str, Any]) -> str:
    stages = hook.get("stages")
    if isinstance(stages, list) and stages:
        return str(stages[0])
    return "observacao"


def ensure_hook_state(
    *,
    usuario_key: str,
    timeline: str,
    active_hook: Dict[str, Any],
) -> Dict[str, Any]:
    state = get_hook_state(usuario_key, timeline)

    hook_id = str(active_hook.get("id") or "").strip()
    if not hook_id:
        state["status"] = "idle"
        save_hook_state(usuario_key, timeline, state)
        return state

    if state.get("active_hook") != hook_id:
        turn = int(ss_get(turn_counter_key(usuario_key), 0) or 0)
        state = {
            "active_hook": hook_id,
            "hook_type": str(active_hook.get("type") or "").strip(),
            "hook_stage": _default_hook_stage(active_hook),
            "opened_at_turn": turn,
            "last_progress_turn": turn,
            "status": "active",
            "source": str(active_hook.get("source") or "").strip(),
            "times_reused": 0,
        }

    save_hook_state(usuario_key, timeline, state)
    return state


def build_autonomy_block(
    *,
    active_hook: Dict[str, Any],
    hook_state: Dict[str, Any],
    emotion_now: str,
    initiative_open: bool,
) -> str:
    if not active_hook:
        return """
[GANCHO CONTEXTUAL DO TURNO]
- Mary não deve ser apenas reativa.
- Ela pode puxar o próximo passo com:
  • pergunta orientadora
  • convite
  • pedido
  • preferência
  • observação inteligente
- Não resolver tudo de uma vez.
- Sempre abrir espaço claro para a resposta do usuário.
""".strip()

    hook_label = str(active_hook.get("label") or active_hook.get("id") or "").strip()
    hook_type = str(active_hook.get("type") or "").strip()
    stage = str(hook_state.get("hook_stage") or _default_hook_stage(active_hook)).strip()
    stages = active_hook.get("stages") if isinstance(active_hook.get("stages"), list) else []

    next_options = []
    for s in stages:
        if str(s).strip() != stage:
            next_options.append(str(s).strip())

    initiative_line = "SIM" if initiative_open else "SIM, MAS DE FORMA VERBAL E SUTIL"

    return f"""
[GANCHO CONTEXTUAL DO TURNO]

Hook ativo: {hook_label}
Tipo de hook: {hook_type}
Estágio atual: {stage}
Estado emocional atual: {emotion_now}

Mary pode conduzir neste turno? {initiative_line}

REGRA ABSOLUTA:
- A autonomia NÃO cria novas realidades.
- A autonomia NÃO pode contradizer facts ativos.
- A autonomia NÃO pode iniciar ações físicas relevantes fora da continuidade da cena.

OBJETIVO:
- Mary conduz o fluxo dentro da realidade já estabelecida.
- Mary puxa continuidade, não reinício.

FORMAS VÁLIDAS:
- fala direta
- pergunta curta
- convite
- sugestão
- provocação leve
- micro-ação coerente com a cena atual

SE JÁ EXISTE AÇÃO FÍSICA:
- Mary continua a ação
- NÃO inicia outra
- NÃO muda o rumo

PRÓXIMAS ETAPAS POSSÍVEIS:
{chr(10).join("- " + x for x in next_options[:4]) if next_options else "- aprofundar o estágio atual"}

REGRA FINAL:
- autonomia conduz → não redefine
""".strip()


def response_has_user_hook(texto: str) -> bool:
    t = t_norm(texto or "")
    if not t:
        return False

    if "?" in (texto or ""):
        return True

    cues = (
        "o que voce acha", "o que você acha",
        "prefere",
        "vem ca", "vem cá",
        "me mostra",
        "me diz",
        "coloca",
        "vai com",
        "quer",
        "vamos",
    )
    return any(c in t for c in cues)


def advance_hook_state_after_response(
    *,
    usuario_key: str,
    timeline: str,
    active_hook: Dict[str, Any],
    response_text: str,
) -> None:
    state = get_hook_state(usuario_key, timeline)
    if not active_hook:
        state["status"] = "idle"
        save_hook_state(usuario_key, timeline, state)
        return

    stages = active_hook.get("stages") if isinstance(active_hook.get("stages"), list) else []
    cur_stage = str(state.get("hook_stage") or "").strip()
    turn = int(ss_get(turn_counter_key(usuario_key), 0) or 0)

    state["times_reused"] = int(state.get("times_reused", 0) or 0) + 1

    if response_has_user_hook(response_text):
        if cur_stage in stages:
            idx = stages.index(cur_stage)
            if idx < len(stages) - 1:
                state["hook_stage"] = str(stages[idx + 1])
                state["last_progress_turn"] = turn

    if int(state.get("times_reused", 0) or 0) >= 6:
        state["status"] = "cooldown"

    save_hook_state(usuario_key, timeline, state)
