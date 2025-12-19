from __future__ import annotations

"""
MaryService (refatorado v3.1 - Timeline-Aware Persona + Continuidade Espacial)
"""

import logging
import re
from typing import Any, Dict, List, Tuple

import streamlit as st

from core.common.base_service import BaseCharacter
from core.repositories import (
    get_facts,
    get_history_docs,
    save_interaction,
    set_fact,
)
from core.service_router import route_chat_strict
from characters.registry import _SERVICE_CACHE

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
# NSFW TOGGLE (mantido)
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
    # prioridade para toggle da UI
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
        r"vamos (pro|pra|para o|para a) (\w+)",
        r"me leva (pro|pra|para o|para a) (\w+)",
    ]
    msg = user_message.lower()
    for p in patterns:
        m = re.search(p, msg)
        if m:
            return True, m.group(2)
    return False, ""


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

        # mudança de local
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            clear_user_cache(usuario_key)
            return f"_Eu te puxo comigo até o {novo_local}…_"

        # ✅ persona DEPENDE da timeline
        persona_text, _ = get_persona(timeline)

        facts = cached_get_facts(usuario_key)
        scene_loc, scene_time, scene_action = _get_scene_state(usuario_key, facts)
        spatial_context = _build_spatial_context(scene_loc, scene_time, scene_action)

        nsfw_block = NSFW_TOGGLE_STYLE if nsfw_enabled(usuario_key) else SAFE_SENSUAL_STYLE

        # ✅ Não force “esposa” aqui: isso vem do persona_text.
        # ✅ Não force “Massariol”: se quiser manter, ok, mas não contradiga a timeline.
        system = f"""
{spatial_context}

VOCÊ É A PERSONAGEM MARY, E DEVE SEGUIR A PERSONA ABAIXO SEM CONTRADIÇÕES.

TIMELINE ATUAL: {timeline}

PERSONA:
{persona_text}

CENA:
Local: {scene_loc}
Tempo: {scene_time}
Ação: {scene_action}

REGRAS:
- Não misture timelines.
- Se TIMELINE=universitaria: não trate como casada, não trate como morando junto.
- Se TIMELINE=cumplice: siga a persona de casada.

{nsfw_block}
""".strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]

        # histórico do backend (já separado por usuario_key com timeline)
        for d in cached_get_history(usuario_key)[-30:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": u})
            if a:
                messages.append({"role": "assistant", "content": a})

        messages.append({"role": "user", "content": prompt})

        data, used_model, _ = route_chat_strict(
            model,
            {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "top_p": 0.95,
                "max_tokens": 1200,
            },
        )

        texto = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not texto:
            return "⚠️ O modelo retornou vazio."

        save_interaction(usuario_key, prompt, texto, used_model or model)
        clear_user_cache(usuario_key)
        return texto
