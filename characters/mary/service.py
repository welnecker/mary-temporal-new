from __future__ import annotations

"""
MaryService (v3.7 – Timeline-Aware + Intro Canônico + Continuidade Espacial + Memórias Permanentes Compartilhadas + Resumo Automático)

- Timeline separa histórico (uid::mary::{timeline})
- Memórias permanentes são compartilhadas (uid::mary::shared) e NÃO dependem de timeline

COMANDOS (usuário):
1) Salvar texto direto (sem inventar):
   "Mary, salve na memória permanente ... Data 23/12/2025 ..."
   => grava exatamente o texto fornecido (ou, se vazio, grava recorte do histórico recente)

2) Salvar resumo automático (sem o usuário descrever tudo):
   "Mary, salve o resumo ... de X até Y ... em 24/12/2025"
   => Mary gera resumo factual SOMENTE a partir das falas da Mary no histórico real, e salva na memória compartilhada

3) Pergunta de memória:
   "Mary, você lembra do primeiro beijo?"
   => injeta memórias relevantes no system para a Mary responder com coerência (sem colar literal)
"""

import logging
import re
import hashlib
from typing import Any, Dict, List, Tuple, Optional

import streamlit as st

from core.common.base_service import BaseCharacter
from core.service_router import route_chat_strict
from core.repositories import (
    get_facts,
    get_fact,
    get_history_docs,
    save_interaction,
    set_fact,
    # memórias
    append_memory,
    list_memories,
)

from characters.registry import _SERVICE_CACHE
from .persona import get_persona

logger = logging.getLogger(__name__)
_SERVICE_CACHE.clear()


# ==========================================================
# 🔑 USER KEYS
# ==========================================================
def _current_user_id() -> str:
    uid = st.session_state.get("user_id") or st.session_state.get("usuario") or ""
    uid = str(uid).strip() or "anon"
    return uid


def _current_user_key() -> str:
    uid = _current_user_id()
    timeline = str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"
    return f"{uid}::mary::{timeline}"


def _shared_memory_key() -> str:
    uid = _current_user_id()
    return f"{uid}::mary::shared"


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
def _get_scene_state(facts: Dict[str, Any]) -> Tuple[str, str, str]:
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
# INTRO CANÔNICO (contexto 1x por sessão)
# ==========================================================
def _hash_text(text: str) -> str:
    t = (text or "").strip().encode("utf-8")
    return hashlib.sha256(t).hexdigest()


def _extract_intro_from_persona(timeline: str) -> Tuple[str, str]:
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
        intro_text = "Eu já estava ali quando você chegou. Eu te vejo e espero sua atitude."

    intro_id = _hash_text(intro_text)
    return intro_id, intro_text


def _sync_intro_fact(usuario_key: str, timeline: str) -> Tuple[str, str]:
    prefix = f"mary.intro.{(timeline or '').strip() or 'cumplice'}"
    id_key = f"{prefix}.id"
    text_key = f"{prefix}.text"
    hash_key = f"{prefix}.hash"

    current_id, current_text = _extract_intro_from_persona(timeline)
    current_hash = current_id

    try:
        stored_hash = str(get_fact(usuario_key, hash_key, default="") or "").strip()
        stored_text = str(get_fact(usuario_key, text_key, default="") or "").strip()

        if (not stored_hash) or (stored_hash != current_hash) or (not stored_text):
            set_fact(usuario_key, id_key, current_id, {"fonte": "persona_intro_sync"})
            set_fact(usuario_key, hash_key, current_hash, {"fonte": "persona_intro_sync"})
            set_fact(usuario_key, text_key, current_text, {"fonte": "persona_intro_sync"})
            clear_user_cache(usuario_key)

        return current_id, current_text
    except Exception:
        return current_id, current_text


def _inject_intro_as_context_once(usuario_key: str, timeline: str, messages: List[Dict[str, str]]) -> None:
    flag = f"intro_ctx_injected::{usuario_key}"
    if st.session_state.get(flag):
        return
    _, intro_text = _sync_intro_fact(usuario_key, timeline)
    intro_text = (intro_text or "").strip()
    if intro_text:
        messages.append({"role": "system", "content": f"[QUADRO ZERO — INTRO DA PERSONA]\n{intro_text}"})
    st.session_state[flag] = True


# ==========================================================
# MEMÓRIAS PERMANENTES (compartilhadas)
# ==========================================================
_SAVE_RE = re.compile(
    r"^\s*(?:mary\s*,?\s*)?(?:salve|salvar|guarde)\b",
    re.IGNORECASE,
)
_REMEMBER_RE = re.compile(
    r"^\s*(?:mary\s*,?\s*)?(?:você\s+)?(?:lembra|recorda)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})\b")
_SUMMARY_HINT_RE = re.compile(r"\b(resumo|resuma|resumir|resumindo)\b", re.IGNORECASE)


def _is_save_memory_command(user_text: str) -> bool:
    return bool(_SAVE_RE.search(user_text or ""))


def _is_memory_question(user_text: str) -> bool:
    return bool(_REMEMBER_RE.search(user_text or ""))


def _wants_auto_summary(user_text: str) -> bool:
    return bool(_SUMMARY_HINT_RE.search(user_text or ""))


def _extract_date_iso(text: str) -> Optional[str]:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    d, mo, y = m.group(1), m.group(2), m.group(3)
    try:
        dd = int(d)
        mm = int(mo)
        yy = int(y)
        if 1 <= dd <= 31 and 1 <= mm <= 12:
            return f"{yy:04d}-{mm:02d}-{dd:02d}"
    except Exception:
        return None
    return None


# ==========================================================
# ✅ SALVAMENTO DINÂMICO DE RESUMO (de X até Y) — apenas MARY
# ==========================================================
_RANGE_RE = re.compile(
    r"\bde\s+(?P<start>.+?)\s+at[ée]\s+(?P<end>.+?)(?:\s*,?\s*em\s+\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4})?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _extract_range_request(user_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrai o recorte do pedido do usuário:
    "Mary, salve o resumo ... de X até Y ... em 24/12/2025"
    Retorna (X, Y) ou (None, None) se não houver.
    """
    t = (user_text or "").strip()
    m = _RANGE_RE.search(t)
    if not m:
        return None, None
    start = (m.group("start") or "").strip(" \n\r\t\"'.,:;")
    end = (m.group("end") or "").strip(" \n\r\t\"'.,:;")
    if len(start) < 3 or len(end) < 3:
        return None, None
    return start, end


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _mary_only_turns(usuario_key: str, limit_turns: int = 80) -> List[str]:
    """
    Pega falas da MARY (resposta_mary) do histórico da timeline atual.
    Retorna lista de strings (cada item = uma resposta da Mary).
    """
    docs = get_history_docs(usuario_key, limit=400) or []
    docs = docs[-limit_turns:] if len(docs) > limit_turns else docs

    out: List[str] = []
    for d in docs:
        a = (d.get("resposta_mary") or "").strip()
        if a:
            out.append(a)
    return out


def _slice_mary_between_markers(
    mary_msgs: List[str],
    start_hint: str,
    end_hint: str,
) -> Tuple[List[str], str]:
    """
    Recorta a sequência de falas da Mary entre start_hint e end_hint (inclusive),
    usando busca aproximada (substring normalizada).
    Retorna (lista_recortada, debug_info).
    """
    if not mary_msgs:
        return [], "no_history"

    sh = _normalize(start_hint)
    eh = _normalize(end_hint)

    def find_idx(hint: str) -> Optional[int]:
        if not hint:
            return None
        for i, msg in enumerate(mary_msgs):
            if hint in _normalize(msg):
                return i
        return None

    i0 = find_idx(sh)
    i1 = find_idx(eh)

    if i0 is None and i1 is None:
        return [], "markers_not_found"

    if i0 is None and i1 is not None:
        i0 = max(0, i1 - 8)
        return mary_msgs[i0 : i1 + 1], "only_end_found"

    if i0 is not None and i1 is None:
        i1 = min(len(mary_msgs) - 1, i0 + 8)
        return mary_msgs[i0 : i1 + 1], "only_start_found"

    if i0 is not None and i1 is not None:
        if i1 < i0:
            i0, i1 = i1, i0
            return mary_msgs[i0 : i1 + 1], "markers_swapped"
        return mary_msgs[i0 : i1 + 1], "both_found"

    return [], "unexpected"


def _build_dynamic_mary_transcript(usuario_key: str, prompt: str) -> Tuple[str, Dict[str, Any]]:
    """
    Constrói a 'transcrição' (apenas falas da Mary) para o resumo dinâmico.
    Retorna (transcript, debug_meta).
    """
    start_hint, end_hint = _extract_range_request(prompt)
    mary_msgs = _mary_only_turns(usuario_key, limit_turns=120)

    if start_hint and end_hint:
        sliced, dbg = _slice_mary_between_markers(mary_msgs, start_hint, end_hint)
        if not sliced:
            sliced = mary_msgs[-10:]
            dbg = f"{dbg}__fallback_last10"

        transcript = "\n\n".join([f"[MARY #{i+1}]\n{m}" for i, m in enumerate(sliced)])
        meta = {
            "mode": "dynamic_range",
            "debug": dbg,
            "start_hint": start_hint,
            "end_hint": end_hint,
            "mary_msgs_used": len(sliced),
        }
        return transcript.strip(), meta

    sliced = mary_msgs[-10:]
    transcript = "\n\n".join([f"[MARY #{i+1}]\n{m}" for i, m in enumerate(sliced)])
    meta = {
        "mode": "fallback_last10",
        "debug": "no_range_in_prompt",
        "mary_msgs_used": len(sliced),
    }
    return transcript.strip(), meta


def _strip_save_prefix(full_text: str) -> str:
    t = (full_text or "").strip()
    m = _SAVE_RE.search(t)
    if not m:
        return t
    rest = t[m.end() :].strip()
    rest = re.sub(r"^\s*(na|no|em)\s+mem[oó]ria\s+permanente\b\s*:?\s*", "", rest, flags=re.IGNORECASE)
    rest = re.sub(r"^\s*(como|que)\s+", "", rest, flags=re.IGNORECASE)
    return rest.strip() or t


def _fallback_capture_recent_history(usuario_key: str, turns: int = 8) -> str:
    docs = cached_get_history(usuario_key)
    if not docs:
        return ""
    slice_docs = docs[-turns:]
    chunks: List[str] = []
    for d in slice_docs:
        u = (d.get("mensagem_usuario") or "").strip()
        a = (d.get("resposta_mary") or "").strip()
        if u:
            chunks.append(f"USUÁRIO:\n{u}")
        if a:
            chunks.append(f"MARY:\n{a}")
    return "\n\n".join(chunks).strip()


def _select_relevant_memories(mems: List[Dict[str, Any]], query: str, k: int = 3) -> List[Dict[str, Any]]:
    q = (query or "").lower()
    words = [w for w in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", q) if len(w) >= 4]
    date_iso = _extract_date_iso(query)

    scored = []
    for m in mems or []:
        txt = str(m.get("text") or "")
        low = txt.lower()
        score = 0
        for w in words[:10]:
            if w in low:
                score += 2
        meta = m.get("meta") or {}
        if date_iso and str(meta.get("date") or "") == date_iso:
            score += 5
        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [m for s, m in scored if s > 0][:k]
    if not picked:
        return (mems or [])[:k]
    return picked


def _inject_memories_context(shared_key: str, user_prompt: str, messages: List[Dict[str, str]]) -> None:
    try:
        mems = list_memories(shared_key, limit=200) or []
    except Exception:
        mems = []

    if not mems:
        return

    picked = _select_relevant_memories(mems, user_prompt, k=3)
    if not picked:
        return

    lines: List[str] = []
    for i, m in enumerate(picked, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        title = meta.get("title") or ""
        header = f"- MEMÓRIA {i}"
        if d:
            header += f" (data: {d})"
        if title:
            header += f" — {title}"
        lines.append(header)
        lines.append(str(m.get("text") or "").strip())
        lines.append("")

    mem_block = "\n".join(lines).strip()

    messages.append(
        {
            "role": "system",
            "content": (
                "[MEMÓRIAS PERMANENTES COMPARTILHADAS]\n"
                "Use estas memórias como fatos canônicos.\n"
                "Responda interpretando com coerência (não cole literal), citando detalhes concretos.\n\n"
                f"{mem_block}"
            ),
        }
    )


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
        shared_key = _shared_memory_key()
        timeline = str(st.session_state.get("mary_timeline") or "cumplice").strip() or "cumplice"

        # 1) Mudança explícita de local
        mudou, novo_local = _user_requested_location_change(prompt)
        if mudou and novo_local:
            _persist_scene_basics(usuario_key, novo_local, "agora", "transição")
            clear_user_cache(usuario_key)
            return f"_Eu te puxo comigo até {novo_local}…_"

        # 2) Comando: salvar memória (texto direto OU resumo automático)
        if _is_save_memory_command(prompt):
            raw_body = _strip_save_prefix(prompt)
            date_iso = _extract_date_iso(prompt) or _extract_date_iso(raw_body)

            # 2a) ✅ RESUMO dinâmico: gera e salva SOMENTE o resumo
            if _wants_auto_summary(prompt):
                transcript, dbg_meta = _build_dynamic_mary_transcript(usuario_key, prompt)
                if not transcript.strip():
                    return (
                        "⚠️ Não encontrei histórico suficiente da Mary para resumir. "
                        "Converse mais um pouco e peça novamente."
                    )

                summary_system = (
                    "Você é a personagem Mary, mas sua tarefa agora é gerar um RESUMO FACTUAL para memória.\n"
                    "REGRAS ABSOLUTAS:\n"
                    "- Use SOMENTE as informações presentes em [TRANSCRIÇÃO].\n"
                    "- NÃO invente, NÃO complete lacunas, NÃO crie fatos fora do texto.\n"
                    "- Texto corrido, sem bullets, sem listagem.\n"
                    "- Escreva com clareza e sequência temporal.\n"
                    "- Foque nos FATOS e no encadeamento (o que aconteceu e por quê), em 8 a 16 linhas.\n"
                    "- Se houver desejo do usuário por um recorte 'até X', respeite o recorte; não avance além.\n"
                )

                summary_user = (
                    "Gere um resumo factual para memória permanente.\n"
                    f"Data (se houver): {date_iso or '—'}\n"
                    "Recorte: definido pelo pedido do usuário (se presente).\n\n"
                    f"[TRANSCRIÇÃO — APENAS FALAS DA MARY]\n{transcript}"
                )

                try:
                    data, used_model, _ = self._chat(
                        model,
                        [
                            {"role": "system", "content": summary_system},
                            {"role": "user", "content": summary_user},
                        ],
                        temperature=0.2,
                        max_tokens=850,
                    )

                    try:
                        resumo = (
                            data.get("choices", [{}])[0].get("message", {}).get("content") or ""
                        ).strip()
                    except Exception:
                        resumo = ""

                    if not resumo:
                        return "⚠️ Não consegui gerar o resumo (modelo retornou vazio). Tente novamente."

                    meta = {
                        "kind": "dynamic_summary",
                        "date": date_iso or "",
                        "timeline_at_save": timeline,
                        "model_used": used_model or model,
                        **(dbg_meta or {}),
                    }

                    # ✅ salva SOMENTE o resumo (sem transcrição imensa)
                    append_memory(shared_key, resumo.strip(), meta=meta)

                    # ✅ mostra o mesmo resumo na tela do app
                    return (
                        "✅ **Resumo salvo na memória permanente** (compartilhado entre as duas Marys)\n\n"
                        f"📌 **Data:** `{date_iso or '—'}`\n"
                        f"🧭 **Recorte:** `{(dbg_meta or {}).get('mode','—')}`\n\n"
                        "---\n\n"
                        f"{resumo.strip()}"
                    )

                except Exception as e:
                    logger.exception("Falha ao gerar/salvar resumo dinâmico", exc_info=e)
                    return f"⚠️ Falha ao gerar/salvar resumo: {type(e).__name__}: {e}"

            # 2b) Salvamento normal: texto fornecido pelo usuário
            body = raw_body.strip()
            if not body:
                return "⚠️ Para salvar texto direto, cole o texto após o comando (ex: 'Mary, salve ...') e informe a data."

            meta = {
                "kind": "user_request",
                "date": date_iso or "",
                "timeline_at_save": timeline,
            }

            try:
                append_memory(shared_key, body, meta=meta)
            except Exception as e:
                logger.exception("Falha ao salvar memória (texto direto)", exc_info=e)
                return f"⚠️ Falha ao salvar memória: {type(e).__name__}: {e}"

            return "✅ Memória permanente salva (compartilhada entre as duas Marys)."

        # 3) Persona
        persona_text, _ = get_persona(timeline)

        facts = cached_get_facts(usuario_key)
        scene_loc, scene_time, scene_action = _get_scene_state(facts)
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

        # 4) Intro canônica 1x por sessão
        _inject_intro_as_context_once(usuario_key, timeline, messages)

        # 5) Se for pergunta de memória, injeta memórias compartilhadas
        if _is_memory_question(prompt):
            _inject_memories_context(shared_key, prompt, messages)

        # 6) Histórico (timeline atual)
        history = cached_get_history(usuario_key)
        for d in history[-30:]:
            u = (d.get("mensagem_usuario") or "").strip()
            a = (d.get("resposta_mary") or "").strip()
            if u:
                messages.append({"role": "user", "content": u})
            if a:
                messages.append({"role": "assistant", "content": a})

        messages.append({"role": "user", "content": prompt})

        # 7) Chat com retry/fallback
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
