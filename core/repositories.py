# core/repositories.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
from threading import RLock
from uuid import uuid4

from .database import get_col

# Lock para operações thread-safe de memória
_MEMORY_LOCK = RLock()

# coleções
_state = lambda: get_col("state_data")
_hist = lambda: get_col("history")
_events = lambda: get_col("events")
_longmem = lambda: get_col("long_memory")  # ✅ NOVO: long memory (1 doc por memória)


# ---------- helpers internos ----------
def _delete_dotted(root: Dict[str, Any], dotted_key: str) -> bool:
    """
    Remove a chave `dotted_key` (ex.: "perfil.endereco.rua") de um dict aninhado,
    modificando `root` in-place. Faz prune de dicts vazios no caminho.
    Retorna True se removeu algo.
    """
    if not dotted_key:
        return False

    parts = [p for p in dotted_key.split(".") if p]
    if not parts:
        return False

    stack: List[tuple[Dict[str, Any], str]] = []
    cur: Any = root

    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return False
        stack.append((cur, p))
        cur = cur[p]

    leaf = parts[-1]
    if not isinstance(cur, dict) or leaf not in cur:
        return False

    del cur[leaf]

    while stack:
        parent, key = stack.pop()
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            del parent[key]
        else:
            break

    return True


# ---------- Fatos ----------
def get_facts(usuario: str) -> Dict[str, Any]:
    d = _state().find_one({"usuario": usuario})
    return d.get("fatos", {}) if d else {}


def get_fact(usuario: str, key: str, default: Any = None) -> Any:
    d = _state().find_one({"usuario": usuario})
    if not d:
        return default
    cur: Any = d.get("fatos", {})
    for part in (key or "").split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_fact(usuario: str, key: str, value: Any, meta: Optional[Dict[str, Any]] = None) -> None:
    meta = meta or {}
    _state().update_one(
        {"usuario": usuario},
        {"$set": {
            "usuario": usuario,
            f"fatos.{key}": value,
            f"meta.{key}": meta,
            "meta.updated_at": datetime.utcnow(),
        }},
        upsert=True,
    )
    _invalidate_cache_for_user(usuario)


def delete_fact(usuario: str, key: str) -> bool:
    doc = _state().find_one({"usuario": usuario})
    if not doc:
        return False

    facts = dict(doc.get("fatos", {}) or {})
    removed = _delete_dotted(facts, key)
    if not removed:
        return False

    # Atualiza fatos
    _state().update_one({"usuario": usuario}, {"$set": {"fatos": facts}}, upsert=True)

    # (Opcional, mas recomendado) remove também o meta associado, se existir
    try:
        _state().update_one({"usuario": usuario}, {"$unset": {f"meta.{key}": ""}})
    except Exception:
        pass

    _invalidate_cache_for_user(usuario)
    return True


# ---------- Histórico ----------
def save_interaction(usuario: str, mensagem_usuario: str, resposta_mary: str, model_tag: str) -> None:
    _hist().insert_one({
        "usuario": usuario,
        "mensagem_usuario": mensagem_usuario,
        "resposta_mary": resposta_mary,
        "model": model_tag,
        "ts": datetime.utcnow(),
    })
    _invalidate_cache_for_user(usuario)


def get_history_docs(usuario: str, limit: int = 400) -> List[Dict[str, Any]]:
    cur = _hist().find(
        {"usuario": usuario},
        sort=[("ts", 1), ("_id", 1)],
        limit=limit,
    )
    return list(cur)


def get_history_docs_multi(
    users_or_keys: List[str],
    limit: int = 400,
    limit_per_key: int = 400,
) -> List[Dict[str, Any]]:
    keys = [k for k in (users_or_keys or []) if k]
    if not keys:
        return []

    all_docs: List[Dict[str, Any]] = []
    for k in keys:
        cur = _hist().find(
            {"usuario": k},
            sort=[("ts", 1), ("_id", 1)],
            limit=limit_per_key,
        )
        all_docs.extend(list(cur))

    def _sort_key(d: Dict[str, Any]):
        ts = d.get("ts")
        if not isinstance(ts, datetime):
            ts = datetime.min
        return (ts, d.get("_id"))

    all_docs.sort(key=_sort_key)

    if limit and len(all_docs) > limit:
        return all_docs[-limit:]
    return all_docs


def delete_user_history(usuario: str) -> int:
    r = _hist().delete_many({"usuario": usuario})
    if isinstance(r, int):
        deleted = int(r)
    elif isinstance(r, dict):
        deleted = int(r.get("deleted_count", 0) or 0)
    else:
        deleted = int(getattr(r, "deleted_count", 0) or 0)

    _invalidate_cache_for_user(usuario)
    return deleted


def delete_last_interaction(usuario: str) -> bool:
    last = _hist().find_one({"usuario": usuario}, sort=[("ts", -1), ("_id", -1)])
    if not last:
        last = _hist().find_one({"usuario": usuario}, sort=[("_id", -1)])
    if not last:
        return False

    r = _hist().delete_one({"_id": last["_id"]})
    if isinstance(r, dict):
        ok = int(r.get("deleted_count", 0) or 0) > 0
    else:
        ok = int(getattr(r, "deleted_count", 0) or 0) > 0

    _invalidate_cache_for_user(usuario)
    return ok


# ==========================================================
# ---------- Memórias permanentes (compartilhadas) ----------
# ==========================================================
def _mem_key() -> str:
    # fica dentro de fatos.mary.memories (nested), graças ao set_fact/get_fact
    return "mary.memories"


def list_memories(usuario: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Retorna a lista de memórias permanentes (guardadas em state_data/fatos).
    Obs: o `usuario` aqui pode ser "Janio Donisete::mary::shared" (recomendado),
    então isso fica compartilhado entre timelines.
    """
    memories = get_fact(usuario, _mem_key(), default=[]) or []
    if not isinstance(memories, list):
        return []
    if limit and len(memories) > limit:
        return memories[-limit:]
    return memories


def append_memory(
    usuario: str,
    text_or_entry: Any,
    meta: Optional[Dict[str, Any]] = None,
    max_keep: int = 200,
) -> Dict[str, Any]:
    """
    Adiciona uma memória permanente na lista fatos.mary.memories.
    Thread-safe: usa lock para evitar race conditions.

    Aceita:
    - append_memory(usuario, "texto", meta={...})
    - append_memory(usuario, {"text": "...", "meta": {...}, ...})  # compat

    Retorna o entry final gravado (com id/ts).
    """
    with _MEMORY_LOCK:
        meta = meta or {}

        # --- compat: se vier dict, respeita ---
        if isinstance(text_or_entry, dict):
            entry = dict(text_or_entry)
            if meta:
                entry_meta = entry.get("meta")
                if isinstance(entry_meta, dict):
                    entry["meta"] = {**entry_meta, **meta}
                else:
                    entry["meta"] = dict(meta)
        else:
            entry = {
                "text": str(text_or_entry or "").strip(),
                "meta": dict(meta),
            }

        # validação mínima
        if not str(entry.get("text") or "").strip():
            return {
                "text": "",
                "meta": dict(entry.get("meta") or {}),
                "ts": datetime.utcnow(),
                "id": f"mem_{uuid4().hex}",
            }

        # ids/ts (sem colisão)
        entry.setdefault("ts", datetime.utcnow())
        entry.setdefault("id", f"mem_{uuid4().hex}")

        # lista atual (read-modify-write atômico sob lock)
        memories = list_memories(usuario, limit=5000)
        memories.append(entry)

        if max_keep and len(memories) > max_keep:
            memories = memories[-max_keep:]

        set_fact(usuario, _mem_key(), memories, {"fonte": "permanent_memory"})
        _invalidate_cache_for_user(usuario)
        return entry


def delete_last_memory(usuario: str) -> bool:
    """
    Remove a última memória da lista fatos.mary.memories.
    """
    with _MEMORY_LOCK:
        memories = list_memories(usuario, limit=5000)
        if not memories:
            return False
        memories.pop()
        set_fact(usuario, _mem_key(), memories, {"fonte": "permanent_memory_delete_last"})
        _invalidate_cache_for_user(usuario)
        return True


def delete_all_memories(usuario: str) -> int:
    """
    Apaga todas as memórias permanentes.
    Retorna quantas existiam.
    """
    with _MEMORY_LOCK:
        memories = list_memories(usuario, limit=5000)
        n = len(memories)
        set_fact(usuario, _mem_key(), [], {"fonte": "permanent_memory_delete_all"})
        _invalidate_cache_for_user(usuario)
        return n


# ==========================================================
# ✅ LONG MEMORY (1 doc por memória + Text Search no Mongo)
# ==========================================================
def append_long_memory(
    usuario: str,
    text: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Insere 1 memória como 1 documento em long_memory.
    Retorna o doc gravado (com id e ts).
    """
    meta = meta or {}
    doc: Dict[str, Any] = {
        "usuario": usuario,
        "text": str(text or "").strip(),
        "meta": dict(meta),
        "ts": datetime.utcnow(),
        "id": f"lm_{uuid4().hex}",
    }

    # validação mínima
    if not doc["text"]:
        return doc

    _longmem().insert_one(doc)
    _invalidate_cache_for_user(usuario)
    return doc


def list_long_memory(usuario: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Lista memórias longas (mais recentes primeiro).
    """
    cur = _longmem().find(
        {"usuario": usuario},
        sort=[("ts", -1), ("_id", -1)],
        limit=limit,
    )
    return list(cur)


def search_long_memory_text(usuario: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Busca lexical em long_memory.
    - Mongo: usa $text (precisa de índice text em 'text' e/ou 'meta.title')
    - Fallback: contains simples.
    """
    q = str(query or "").strip()
    if not q:
        return []

    # tenta Mongo $text primeiro
    try:
        from .database import get_backend
        if get_backend() == "mongo":
            # projection com textScore pode não existir no wrapper -> fazemos simples
            cur = _longmem().find(
                {"usuario": usuario, "$text": {"$search": q}},
                limit=limit,
            )
            return list(cur)
    except Exception:
        pass

    # fallback lexical simples (caso backend mude)
    rows = list_long_memory(usuario, limit=2000)
    qq = q.lower()
    out: List[Dict[str, Any]] = []
    for d in rows:
        t = str(d.get("text") or "").lower()
        m = d.get("meta") or {}
        title = str(m.get("title") or "").lower() if isinstance(m, dict) else ""
        hay = f"{title} {t}".strip()
        if qq in hay:
            out.append(d)
        if len(out) >= limit:
            break
    return out


# ---------- Eventos ----------
def register_event(
    usuario: str,
    tipo: str,
    descricao: str,
    local: Optional[str],
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    _events().insert_one({
        "usuario": usuario,
        "tipo": tipo,
        "descricao": descricao,
        "local": local,
        "extra": extra or {},
        "ts": datetime.utcnow(),
    })


def list_events(usuario: str, limit: int = 5) -> List[Dict[str, Any]]:
    cur = _events().find(
        {"usuario": usuario},
        sort=[("ts", -1), ("_id", -1)],
        limit=limit,
    )
    return list(cur)


def last_event(usuario: str, tipo: str) -> Optional[Dict[str, Any]]:
    return _events().find_one(
        {"usuario": usuario, "tipo": tipo},
        sort=[("ts", -1), ("_id", -1)],
    )


def _safe_create_index(col_obj, keys, **kwargs) -> bool:
    """
    Cria índice tanto no wrapper quanto no pymongo interno (._col), se existir.
    Aceita kwargs para índices text, nomes, etc.
    """
    try:
        if hasattr(col_obj, "create_index"):
            col_obj.create_index(keys, **kwargs)
            return True
    except Exception:
        pass

    try:
        inner = getattr(col_obj, "_col", None)
        if inner is not None and hasattr(inner, "create_index"):
            inner.create_index(keys, **kwargs)
            return True
    except Exception:
        pass

    return False


def ensure_long_memory_indexes() -> None:
    """
    Índices específicos da long_memory:
    - text index em "text" (e opcionalmente em meta.title)
    - índice (usuario, ts) para listagem rápida
    """
    try:
        from .database import get_backend
        if get_backend() != "mongo":
            return

        # índice por usuário + tempo
        _safe_create_index(_longmem(), [("usuario", 1), ("ts", -1), ("_id", -1)], name="lm_user_ts_idx")

        # índice text (Mongo aceita "text" como tipo)
        # OBS: alguns wrappers não aceitam isso; o fallback via ._col resolve.
        _safe_create_index(_longmem(), [("text", "text")], name="lm_text_idx")
    except Exception:
        pass


def ensure_indexes() -> None:
    try:
        from .database import get_backend
        if get_backend() != "mongo":
            return

        _safe_create_index(_hist(), [("usuario", 1), ("ts", 1), ("_id", 1)], name="hist_user_ts_idx")
        _safe_create_index(_state(), [("usuario", 1)], name="state_user_idx")
        _safe_create_index(_events(), [("usuario", 1), ("ts", -1), ("_id", -1)], name="events_user_ts_idx")

        # ✅ NOVO: long_memory
        ensure_long_memory_indexes()
    except Exception:
        pass


# ---------- Cache invalidation (Streamlit) ----------
def _invalidate_cache_for_user(usuario: str) -> None:
    """
    Invalida cache do Streamlit para um usuário específico.
    Corrigido para casar com as chaves usadas no service:
      - facts::{usuario}
      - history::{usuario}::{limit}
      - mem::{usuario}::{limit}
    Seguro: não quebra se streamlit não estiver disponível.
    """
    try:
        import streamlit as st

        # facts direto
        fk = f"facts::{usuario}"
        if fk in st.session_state:
            del st.session_state[fk]

        # history e mem são prefixos (porque têm ::{limit})
        history_prefix = f"history::{usuario}::"
        mem_prefix = f"mem::{usuario}::"

        for k in list(st.session_state.keys()):
            if not isinstance(k, str):
                continue
            if k.startswith(history_prefix) or k.startswith(mem_prefix):
                del st.session_state[k]

        # compat: se existir alguma versão antiga sem ::limit
        hk = f"history::{usuario}"
        if hk in st.session_state:
            del st.session_state[hk]

        mk = f"mem::{usuario}"
        if mk in st.session_state:
            del st.session_state[mk]

        # (opcional) se você cachear longmem no futuro:
        # lm_prefix = f"longmem::{usuario}::"
        # for k in list(st.session_state.keys()):
        #     if isinstance(k, str) and k.startswith(lm_prefix):
        #         del st.session_state[k]

    except (ImportError, AttributeError, RuntimeError):
        pass
