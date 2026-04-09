from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import core.service_router as service_router


def _safe_json_extract(text: str) -> Dict[str, Any]:
    """
    Tenta extrair um objeto JSON puro da resposta do modelo.
    Se o modelo devolver texto extra, tenta recortar o primeiro bloco {...}.
    """
    t = (text or "").strip()
    if not t:
        return {}

    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        chunk = t[start : end + 1]
        try:
            data = json.loads(chunk)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    return {}


def _extract_text(resp: Any) -> str:
    """
    Extrai texto de:
    - tuple(data, used_model, provider)
    - dict OpenAI-like
    - str
    """
    if resp is None:
        return ""

    if isinstance(resp, tuple) and resp:
        return _extract_text(resp[0])

    if isinstance(resp, str):
        return resp.strip()

    if isinstance(resp, dict):
        try:
            choices = resp.get("choices") or []
            if isinstance(choices, list) and choices:
                c0 = choices[0] or {}
                msg = c0.get("message") or {}

                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()

                if isinstance(content, list):
                    parts: List[str] = []
                    for item in content:
                        if isinstance(item, str) and item.strip():
                            parts.append(item.strip())
                        elif isinstance(item, dict):
                            txt = item.get("text") or item.get("content")
                            if isinstance(txt, str) and txt.strip():
                                parts.append(txt.strip())
                    if parts:
                        return "\n".join(parts).strip()

                reasoning = msg.get("reasoning")
                if isinstance(reasoning, str) and reasoning.strip():
                    return reasoning.strip()

                txt2 = c0.get("text")
                if isinstance(txt2, str) and txt2.strip():
                    return txt2.strip()

            for k in ("output_text", "text", "content", "result"):
                v = resp.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        except Exception:
            return ""

    return ""


def _compact_facts_for_reasoning(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduz facts para o essencial do turno.
    Evita mandar facts gigantes para o modelo auxiliar.
    """
    f = facts if isinstance(facts, dict) else {}

    mary_obj = f.get("mary") if isinstance(f.get("mary"), dict) else {}
    rel_obj = f.get("rel") if isinstance(f.get("rel"), dict) else {}
    scene_obj = f.get("cena") if isinstance(f.get("cena"), dict) else {}
    state_obj = f.get("state") if isinstance(f.get("state"), dict) else {}

    compact = {
        "cena.local": scene_obj.get("local") or f.get("cena.local") or f.get("local_cena_atual"),
        "cena.tempo": scene_obj.get("tempo") or f.get("cena.tempo"),
        "cena.acao": scene_obj.get("acao") or f.get("cena.acao"),
        "cena.locked": scene_obj.get("locked") if "locked" in scene_obj else f.get("cena.locked"),
        "state.local": state_obj.get("local") or f.get("state.local"),
        "state.assunto": state_obj.get("assunto") or f.get("state.assunto"),
        "intimacy.phase": f.get("intimacy.phase"),
        "rel.jealousy_level": f.get("rel.jealousy_level"),
        "rel.jealousy_mode": f.get("rel.jealousy_mode"),
        "mary.nsfw": mary_obj.get("nsfw") if isinstance(mary_obj, dict) else f.get("mary.nsfw"),
        "mary.virginity": mary_obj.get("virginity") if isinstance(mary_obj, dict) else None,
    }

    return {k: v for k, v in compact.items() if v is not None and v != ""}


def _compact_scene_state(scene_state: Dict[str, Any]) -> Dict[str, Any]:
    s = scene_state if isinstance(scene_state, dict) else {}
    compact = {
        "local": s.get("local"),
        "tempo": s.get("tempo"),
        "acao": s.get("acao"),
        "locked": s.get("locked"),
    }
    return {k: v for k, v in compact.items() if v is not None and v != ""}


def _compact_recent_turns(recent_turns: Optional[List[Dict[str, str]]], max_turns: int = 5) -> List[Dict[str, str]]:
    turns = recent_turns if isinstance(recent_turns, list) else []
    out: List[Dict[str, str]] = []

    for t in turns[-max_turns:]:
        if not isinstance(t, dict):
            continue

        user_msg = str(t.get("user") or "").strip()
        mary_msg = str(t.get("mary") or "").strip()

        if user_msg or mary_msg:
            out.append({
                "user": user_msg[:500],
                "mary": mary_msg[:700],
            })

    return out


def _normalize_llm_reasoning(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza campos esperados para evitar surpresas no merge.
    """
    if not isinstance(data, dict):
        return {}

    out: Dict[str, Any] = {}

    fields = {
        "intent_refined": "",
        "tone": "",
        "emotional_focus": "",
        "memory_hint": "",
        "advance_bias": "",
        "delivery_bias": "",
        "continuity_hint": "",
        "object_focus": "",
        "interlocutor_hint": "",
    }

    for k in fields:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()

    # compat: aceita aliases
    if not out.get("intent_refined"):
        v = data.get("intent")
        if isinstance(v, str) and v.strip():
            out["intent_refined"] = v.strip()

    if not out.get("delivery_bias"):
        v = data.get("delivery_mode")
        if isinstance(v, str) and v.strip():
            out["delivery_bias"] = v.strip()

    if not out.get("advance_bias"):
        v = data.get("advance_limit")
        if isinstance(v, str) and v.strip():
            out["advance_bias"] = v.strip()

    return out


def build_llm_reasoning(
    *,
    model: str,
    user_text: str,
    facts: Dict[str, Any],
    memories: List[str],
    scene_state: Dict[str, Any],
    recent_turns: Optional[List[Dict[str, str]]] = None,
    base_reasoning: Dict[str, Any],
    max_memory_items: int = 5,
) -> Dict[str, Any]:
    """
    Usa um LLM auxiliar para refinar a direção narrativa do turno.

    IMPORTANTE:
    - Não escreve a resposta final da Mary
    - Não faz roleplay
    - Não inventa fatos
    - Não substitui a continuidade decidida pelo reasoning base
    - Só devolve um JSON curto de refinamento
    """
    model = str(model or "").strip()
    if not model:
        raise RuntimeError("build_llm_reasoning: model vazio")

    mems = memories if isinstance(memories, list) else []
    mems = [str(m).strip() for m in mems if str(m).strip()]
    mems = mems[-max_memory_items:]

    facts_compact = _compact_facts_for_reasoning(facts)
    scene_compact = _compact_scene_state(scene_state)
    recent_turns_compact = _compact_recent_turns(recent_turns, max_turns=5)
    base_reasoning = base_reasoning if isinstance(base_reasoning, dict) else {}

    system = (
        "Você é um motor auxiliar de preparação narrativa.\n"
        "Sua função é refinar a direção interna de um turno.\n"
        "Você NÃO escreve a resposta final da personagem.\n"
        "Você NÃO faz roleplay.\n"
        "Você NÃO inventa fatos.\n"
        "Você NÃO altera interlocutor, local, objeto ativo ou continuidade já decididos no reasoning base.\n"
        "Você apenas refina tom, foco emocional, entrega e avanço.\n"
        "Responda APENAS com JSON válido."
    )

    user = f"""
Refine a direção do próximo turno de Mary.

MENSAGEM DO USUÁRIO:
{user_text}

FACTS ESSENCIAIS:
{json.dumps(facts_compact, ensure_ascii=False)}

SCENE STATE:
{json.dumps(scene_compact, ensure_ascii=False)}

ÚLTIMAS 5 INTERAÇÕES:
{json.dumps(recent_turns_compact, ensure_ascii=False)}

MEMÓRIAS RELEVANTES:
{json.dumps(mems, ensure_ascii=False)}

REASONING BASE:
{json.dumps(base_reasoning, ensure_ascii=False)}

Retorne APENAS JSON válido com estas chaves:
- intent_refined
- tone
- emotional_focus
- memory_hint
- advance_bias
- delivery_bias
- continuity_hint
- object_focus
- interlocutor_hint

Regras obrigatórias:
- respeite o reasoning base
- respeite cena travada
- não invente fatos
- não troque interlocutor
- não substitua objeto ativo
- não mude o local da cena
- não contradiga a continuidade_imediata
- se houver conflito emocional, prefira contenção à aceleração
- se houver risco alto, reduza avanço
- seja curto e operacional
""".strip()

    raw = service_router.chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=260,
        temperature=0.2,
        top_p=0.9,
    )

    text = _extract_text(raw)
    data = _safe_json_extract(text)
    return _normalize_llm_reasoning(data)


def merge_reasoning(
    base: Dict[str, Any],
    llm: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Faz merge do reasoning determinístico com o refinement do LLM.

    Regras:
    - base continua soberano nas regras duras
    - llm só refina intenção/entrega/tom/foco
    - não derruba campos importantes se vier vazio
    - continuidade estrutural permanece no base
    """
    merged = dict(base or {})
    llm = llm if isinstance(llm, dict) else {}

    if not isinstance(merged.get("rules"), list):
        merged["rules"] = []

    # Refino leve da intenção
    intent_refined = str(llm.get("intent_refined") or "").strip()
    if intent_refined:
        merged["intent"] = intent_refined

    # Refino do modo de entrega
    delivery_bias = str(llm.get("delivery_bias") or "").strip().lower()
    if delivery_bias in {
        "fala_direta",
        "fala_com_subtexto",
        "micro_acao",
        "confissao_curta",
        "provocacao_controlada",
    }:
        merged["delivery_mode"] = delivery_bias

    # Refino do limite de avanço
    advance_bias = str(llm.get("advance_bias") or "").strip().lower()
    if advance_bias in {"minimo", "leve", "medio", "alto", "baixo"}:
        if advance_bias == "baixo":
            merged["advance_limit"] = "minimo"
        else:
            merged["advance_limit"] = advance_bias

    # Guarda refinamentos sem substituir continuidade estrutural
    merged["llm_reasoning"] = {
        "tone": str(llm.get("tone") or "").strip(),
        "emotional_focus": str(llm.get("emotional_focus") or "").strip(),
        "memory_hint_refined": str(llm.get("memory_hint") or "").strip(),
        "continuity_hint": str(llm.get("continuity_hint") or "").strip(),
        "object_focus": str(llm.get("object_focus") or "").strip(),
        "interlocutor_hint": str(llm.get("interlocutor_hint") or "").strip(),
    }

    return merged
