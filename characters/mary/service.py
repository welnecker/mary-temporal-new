from __future__ import annotations

"""
MaryService (refatorado v3 - Continuidade Espacial + Timelines + Intro Canônica Fixa)

O que este service garante:
- user_key por timeline: uid::mary::{timeline}
- intro canônica fixada por timeline (fact: mary.intro.fixed)
- continuidade espacial (cena.local / cena.tempo / cena.acao)
- cache de facts/history com invalidation após salvar
- NSFW toggle: mantido como chave
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

from .persona import get_persona

logger = logging.getLogger(__name__)


# ==========================================================
# 🔑 USER KEY (COM TIMELINE)
# ==========================================================
def _current_user_key() -> str:
    uid = st.session_state.get("user_id") or st.session_state.get("usuario") or ""
    uid = str(uid).strip() or "anon"

    timeline = str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"
    return f"{uid}::mary::{timeline}"



# ==========================================================
# NSFW TOGGLE (INALTERADO)
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
    # 1) UI state
    if "mary_nsfw_on" in st.session_state:
        return bool(st.session_state["mary_nsfw_on"])

    # 2) fact fallback
    facts = cached_get_facts(usuario_key) or {}
    v = facts.get("mary.nsfw")
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "sim", "on", "yes", "y"):
            return True
        if s in ("0", "false", "nao", "não", "off", "no", "n"):
            return False

    # 3) default
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
    try:
        if local:
            set_fact(usuario_key, "cena.local", local, {"fonte": "scene"})
            set_fact(usuario_key, "local_cena_atual", local, {"fonte": "scene_compat"})
        if tempo:
            set_fact(usuario_key, "cena.tempo", tempo, {"fonte": "scene"})
        if acao:
            set_fact(usuario_key, "cena.acao", acao, {"fonte": "scene"})
    except Exception as e:
        try:
            logger.warning("persist_scene_basics failed: %s", e)
        except Exception:
            pass


def _build_spatial_context(local: str, tempo: str, acao: str) -> str:
    if not local or local == "—":
        return ""
    return f"""
[CONTEXTO ESPACIAL — OBRIGATÓRIO]
Local: {local}
Tempo: {tempo}
Ação: {acao}

Regra: mantenha o local até o usuário pedir explicitamente uma mudança.
""".strip()


def _user_requested_location_change(user_message: str) -> Tuple[bool, str]:
    patterns = [
        r"vamos (pro|pra|para o|para a) (\w+)",
        r"me leva (pro|pra|para o|para a) (\w+)",
    ]
    msg = (user_message or "").lower()
    for p in patterns:
        m = re.search(p, msg)
        if m:
            return True, m.group(2)
    return False, ""


# ==========================================================
# INTRO CANÔNICA FIXA (POR TIMELINE)
# ==========================================================
def _ensure_fixed_intro(usuario_key: str, facts: Dict[str, Any], history_boot: List[Dict[str, str]]) -> str:
    """
    Garante que existe UMA introdução canônica fixa por timeline.
    Armazena em fact: mary.intro.fixed
    Retorna a intro fixa (string) ou "" se não houver.
    """
    intro_key = "mary.intro.fixed"
    intro_fixed = facts.get(intro_key)

    if isinstance(intro_fixed, str) and intro_fixed.strip():
        return intro_fixed.strip()

    # Se não existe, fixa a primeira disponível do history_boot
    if history_boot:
        first = history_boot[0] or {}
        content = (first.get("content") or "").strip()
        if content:
            try:
                set_fact(usuario_key, intro_key, content, {"fonte": "persona"})
            except Exception:
                pass
            return content

    return ""


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

        # 1) mudança de local (antes de tudo)
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou and novo_local:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            clear_user_cache(usuario_key)
            return f"_Eu te puxo comigo até o {novo_local}…_"

        # 2) persona por timeline
        persona_text, history_boot = get_persona()

        # 3) facts + intro fixa
        facts = cached_get_facts(usuario_key) or {}
        intro_fixed = _ensure_fixed_intro(usuario_key, facts, history_boot)

        # 4) cena atual + contexto espacial
        scene_loc, scene_time, scene_action = _get_scene_state(usuario_key, facts)
        spatial_context = _build_spatial_context(scene_loc, scene_time, scene_action)

        # 5) nsfw (toggle)
        nsfw_block = NSFW_TOGGLE_STYLE if nsfw_enabled(usuario_key) else SAFE_SENSUAL_STYLE

        # 6) system prompt (inclui intro fixa como “âncora” do início)
        intro_section = f"\n\n[INTRO_CANÔNICA_FIXA]\n{intro_fixed}\n" if intro_fixed else ""

        system = f"""
{spatial_context}

Você é Mary Massariol.

PERSONA:
{persona_text}
{intro_section}

CENA:
Local: {scene_loc}
Tempo: {scene_time}
Ação: {scene_action}

REGRAS:
- Primeira pessoa absoluta.
- Continuidade: não reinicie, não “teleporte”, não troque de lugar sem pedido explícito.
- Não termine resposta com pergunta.

{nsfw_block}
""".strip()

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]

        # 7) histórico recente por timeline
        for d in cached_get_history(usuario_key)[-30:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": u})
            if a:
                messages.append({"role": "assistant", "content": a})

        # 8) user message atual
        messages.append({"role": "user", "content": prompt})

        # 9) call
        try:
            data, used_model, _prov = route_chat_strict(
                model,
                {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "max_tokens": 1200,
                },
            )
        except Exception as e:
            try:
                logger.exception("route_chat_strict failed: %s", e)
            except Exception:
                pass
            return "⚠️ Falha ao chamar o modelo. Verifique logs/modelo."

        texto = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not texto:
            return "⚠️ O modelo retornou vazio."

        # 10) persist
        try:
            save_interaction(usuario_key, prompt, texto, used_model or model)
        except Exception as e:
            try:
                logger.warning("save_interaction failed: %s", e)
            except Exception:
                pass

        clear_user_cache(usuario_key)
        return texto
