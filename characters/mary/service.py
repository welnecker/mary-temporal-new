from __future__ import annotations

"""
MaryService (v3.4 – Intro Canônico da Persona + Timeline-Aware + Continuidade Espacial)

Objetivo:
- O app entende que a primeira interação SEMPRE começa a partir da INTRO da persona,
  independente do conteúdo (praça, cantina, etc).
- Se a persona mudar no futuro, o app acompanha automaticamente (hash/id).
- No restart do app, mesmo com histórico no BD, o modelo recebe de novo o "quadro zero"
  como CONTEXTO (system), evitando respostas fora de contexto na primeira fala do usuário.
"""

import logging
import re
import hashlib
from typing import Any, Dict, List, Tuple, Optional

import streamlit as st

from core.common.base_service import BaseCharacter
from core.repositories import (
    get_facts,
    get_fact,
    get_history_docs,
    save_interaction,
    set_fact,
)
from characters.registry import _SERVICE_CACHE
from core.service_router import route_chat_strict

from .persona import get_persona

logger = logging.getLogger(__name__)
_SERVICE_CACHE.clear()


# ==========================================================
# 🔑 USER KEY (COM TIMELINE)
# ==========================================================
def _current_user_key() -> str:
    uid = st.session_state.get("user_id") or st.session_state.get("usuario") or ""
    uid = str(uid).strip() or "anon"

    timeline = str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"
    return f"{uid}::mary::{timeline}"


# ==========================================================
# NSFW TOGGLE
# ==========================================================
SAFE_SENSUAL_STYLE = """
[NSFW_OFF]
Estilo: romance adulto, tensão, intimidade e sugestão.
Evite detalhes gráficos.
""".strip()

NSFW_TOGGLE_STYLE = """
[NSFW_ON]
ESTILO: SEXUALMENTE EXPLÍCITO, GRÁFICO, DIRETO E SEM CENSURA.
""".strip()


# ==========================================================
# CACHE
# ==========================================================
def cached_get_facts(usuario_key: str) -> Dict[str, Any]:
    ck = f"facts::{usuario_key}"
    if ck in st.session_state:
        return st.session_state[ck]
    try:
        f = get_facts(usuario_key) or {}
    except Exception:
        f = {}
    st.session_state[ck] = f
    return f


def cached_get_history(usuario_key: str) -> List[Dict[str, Any]]:
    hk = f"history::{usuario_key}"
    if hk in st.session_state:
        return st.session_state[hk]
    try:
        docs = get_history_docs(usuario_key) or []
    except Exception:
        docs = []
    st.session_state[hk] = docs
    return docs


def clear_user_cache(usuario_key: str) -> None:
    for k in (f"facts::{usuario_key}", f"history::{usuario_key}"):
        if k in st.session_state:
            del st.session_state[k]


# ==========================================================
# NSFW ENABLE
# ==========================================================
def nsfw_enabled(usuario_key: str) -> bool:
    if "mary_nsfw_on" in st.session_state:
        return bool(st.session_state["mary_nsfw_on"])

    facts = cached_get_facts(usuario_key) or {}
    v = facts.get("mary.nsfw")
    if isinstance(v, bool):
        return v
    return True


# ==========================================================
# CONTINUIDADE ESPACIAL
# ==========================================================
def _get_scene_state(usuario_key: str, facts: Dict[str, Any]) -> Tuple[str, str, str]:
    local = str(facts.get("cena.local") or facts.get("local_cena_atual") or "—")
    tempo = str(facts.get("cena.tempo") or "agora")
    acao = str(facts.get("cena.acao") or "em andamento")
    return local, tempo, acao


def _persist_scene_basics(usuario_key: str, local: str, tempo: str, acao: str) -> None:
    if local:
        set_fact(usuario_key, "cena.local", local, {"fonte": "scene"})
        set_fact(usuario_key, "local_cena_atual", local, {"fonte": "scene_compat"})
    if tempo:
        set_fact(usuario_key, "cena.tempo", tempo, {"fonte": "scene"})
    if acao:
        set_fact(usuario_key, "cena.acao", acao, {"fonte": "scene"})


def _build_spatial_context(local: str, tempo: str, acao: str) -> str:
    if not local or local == "—":
        return ""
    return f"""
[CONTEXTO ESPACIAL — OBRIGATÓRIO]
Local: {local}
Tempo: {tempo}
Ação: {acao}
""".strip()


def _user_requested_location_change(user_message: str) -> Tuple[bool, str]:
    patterns = [
        r"vamos (pro|pra|para o|para a)\s+([^\n\r,.!?]+)",
        r"me leva (pro|pra|para o|para a)\s+([^\n\r,.!?]+)",
        r"vamos para\s+([^\n\r,.!?]+)",
        r"ir para\s+([^\n\r,.!?]+)",
    ]
    msg = (user_message or "").lower().strip()
    for p in patterns:
        m = re.search(p, msg)
        if m:
            destino = (m.group(m.lastindex) or "").strip()
            return True, destino
    return False, ""


# ==========================================================
# INTRO CANÔNICO DA PERSONA (independente de conteúdo)
# ==========================================================
def _intro_fact_prefix(timeline: str) -> str:
    tl = (timeline or "").strip() or "cumplice"
    return f"mary.intro.{tl}"  # vira: mary.intro.universitaria.{text|hash|id}


def _hash_text(text: str) -> str:
    t = (text or "").strip().encode("utf-8")
    return hashlib.sha256(t).hexdigest()


def _extract_intro_from_persona(timeline: str) -> Tuple[str, str]:
    """
    Retorna (intro_id, intro_text) baseado na persona atual.
    intro_id: identificador estável que muda se o texto mudar (hash do texto).
    intro_text: o primeiro quadro da persona.
    """
    _, history_boot = get_persona(timeline)

    intro_text = ""
    if isinstance(history_boot, list):
        for msg in history_boot:
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("content"):
                if msg.get("timeline") and str(msg.get("timeline")) != str(timeline):
                    continue
                intro_text = str(msg["content"]).strip()
                break

    if not intro_text:
        # fallback mínimo (mas neutro; não “praça”)
        intro_text = "Eu já estava ali quando você chegou. Eu te vejo e espero sua atitude."

    intro_id = _hash_text(intro_text)  # id muda quando a persona muda
    return intro_id, intro_text


def _sync_intro_fact(usuario_key: str, timeline: str) -> Tuple[str, str]:
    """
    Garante que o BD tenha a intro atual da persona (por timeline).
    Se a persona mudar, atualiza text/hash/id no facts.
    Retorna (intro_id, intro_text).
    """
    prefix = _intro_fact_prefix(timeline)
    id_key = f"{prefix}.id"
    text_key = f"{prefix}.text"
    hash_key = f"{prefix}.hash"

    current_id, current_text = _extract_intro_from_persona(timeline)
    current_hash = current_id  # mesmo valor (sha256)

    try:
        stored_hash = str(get_fact(usuario_key, hash_key, default="") or "").strip()
        stored_text = str(get_fact(usuario_key, text_key, default="") or "").strip()

        # se não existe OU mudou (hash diferente) OU texto vazio, atualiza
        if (not stored_hash) or (stored_hash != current_hash) or (not stored_text):
            set_fact(usuario_key, id_key, current_id, {"fonte": "persona_intro_sync"})
            set_fact(usuario_key, hash_key, current_hash, {"fonte": "persona_intro_sync"})
            set_fact(usuario_key, text_key, current_text, {"fonte": "persona_intro_sync"})
            # cache do service pode estar com facts antigos
            clear_user_cache(usuario_key)

        return current_id, current_text
    except Exception:
        # sem travar o app
        return current_id, current_text


def _inject_intro_as_context_once(usuario_key: str, timeline: str, messages: List[Dict[str, str]]) -> None:
    """
    Injeta a intro como CONTEXTO (system) 1x por sessão Streamlit.
    Independentemente de existir histórico no BD.
    """
    flag = f"intro_ctx_injected::{usuario_key}"
    if st.session_state.get(flag):
        return

    _, intro_text = _sync_intro_fact(usuario_key, timeline)
    intro_text = (intro_text or "").strip()
    if intro_text:
        messages.append({"role": "system", "content": f"[QUADRO ZERO — INTRO DA PERSONA]\n{intro_text}"})

    st.session_state[flag] = True


# ==========================================================
# SERVICE
# ==========================================================
class MaryService(BaseCharacter):
    id = "mary"
    display_name = "Mary"

    def reply(self, user: str, model: str) -> str:
        prompt = (st.session_state.get("chat_input") or "").strip()
        if not prompt:
            return ""

        usuario_key = _current_user_key()
        timeline = str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"

        # 🔁 Mudança explícita de local
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou and novo_local:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            clear_user_cache(usuario_key)
            return f"_Eu te puxo comigo até {novo_local}…_"

        # 🔒 Fixar timeline canônica
        try:
            facts_now = cached_get_facts(usuario_key)
            if not facts_now.get("mary.timeline.fixed"):
                set_fact(usuario_key, "mary.timeline.fixed", timeline, {"fonte": "timeline_fixada"})
        except Exception:
            pass

        # 🎭 Persona
        persona_text, _ = get_persona(timeline)

        facts = cached_get_facts(usuario_key)
        scene_loc, scene_time, scene_action = _get_scene_state(usuario_key, facts)
        spatial_context = _build_spatial_context(scene_loc, scene_time, scene_action)

        nsfw_block = NSFW_TOGGLE_STYLE if nsfw_enabled(usuario_key) else SAFE_SENSUAL_STYLE

        system = f"""
{spatial_context}

VOCÊ É A PERSONAGEM MARY.

TIMELINE ATUAL: {timeline}

PERSONA:
{persona_text}

REGRAS ABSOLUTAS:
- NÃO misture timelines.
- Timeline universitária NÃO é casada e NÃO mora junto.
- Timeline cúmplice segue a persona de casamento.
- Nunca contradiga a timeline ativa.

{nsfw_block}
""".strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]

        # ✅ INTRO CANÔNICA DA PERSONA (independente do conteúdo) como CONTEXTO
        # Entra ANTES do histórico, e 1x por sessão Streamlit.
        _inject_intro_as_context_once(usuario_key, timeline, messages)

        # 📜 Histórico do backend
        history = cached_get_history(usuario_key)
        for d in history[-30:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": u})
            if a:
                messages.append({"role": "assistant", "content": a})

        # 👤 Mensagem atual
        messages.append({"role": "user", "content": prompt})

        # =========================
        # 🔁 Chamada com fallback
        # =========================
        def _extract_text(resp: dict) -> str:
            try:
                return (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            except Exception:
                return ""

        attempts = [
            {"model": model, "temperature": 0.7},
            {"model": model, "temperature": 0.4},
            {"model": "deepseek/deepseek-chat-v3-0324", "temperature": 0.6},
        ]

        last_err: Optional[Exception] = None
        for attempt in attempts:
            try:
                data, used_model, _ = self._chat(
                    attempt["model"],
                    messages,
                    temperature=attempt["temperature"],
                    max_tokens=1200,
                )
                texto = _extract_text(data)
                if texto:
                    save_interaction(usuario_key, prompt, texto, used_model or attempt["model"])
                    clear_user_cache(usuario_key)
                    return texto
            except Exception as e:
                last_err = e

        if last_err:
            logger.exception("Falha em todas tentativas de chat", exc_info=last_err)

        return "⚠️ O modelo retornou vazio. Troque o modelo no sidebar."

    def _chat(self, model: str, messages: List[Dict[str, str]], temperature: float, max_tokens: int):
        return route_chat_strict(
            model,
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "top_p": 0.95,
                "max_tokens": max_tokens,
            },
        )
