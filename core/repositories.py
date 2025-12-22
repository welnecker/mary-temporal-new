# core/repositories.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime

from .database import get_col

# coleções
_state = lambda: get_col("state_data")
_hist = lambda: get_col("history")
_events = lambda: get_col("events")


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


def delete_fact(usuario: str, key: str) -> bool:
    doc = _state().find_one({"usuario": usuario})
    if not doc:
        return False

    facts = dict(doc.get("fatos", {}) or {})
    if not _delete_dotted(facts, key):
        return False

    _state().update_one({"usuario": usuario}, {"$set": {"fatos": facts}}, upsert=True)
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
        return int(r)
    if isinstance(r, dict):
        return int(r.get("deleted_count", 0) or 0)
    return int(getattr(r, "deleted_count", 0) or 0)


def delete_last_interaction(usuario: str) -> bool:
    last = _hist().find_one({"usuario": usuario}, sort=[("ts", -1), ("_id", -1)])
    if not last:
        last = _hist().find_one({"usuario": usuario}, sort=[("_id", -1)])
    if not last:
        return False

    r = _hist().delete_one({"_id": last["_id"]})
    if isinstance(r, dict):
        return int(r.get("deleted_count", 0) or 0) > 0
    return int(getattr(r, "deleted_count", 0) or 0) > 0

# ==========================================================
# ---------- Memórias permanentes (compartilhadas) ----------
# ==========================================================
def _mem_key() -> str:
    return "mary.memories"


def list_memories(usuario: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Retorna a lista de memórias permanentes (do state_data do 'usuario' informado).
    """
    memories = get_fact(usuario, _mem_key(), default=[]) or []
    if not isinstance(memories, list):
        return []
    if limit and len(memories) > limit:
        return memories[-limit:]
    return memories


def append_memory(usuario: str, entry: Dict[str, Any], max_keep: int = 200) -> Dict[str, Any]:
    """
    Adiciona uma memória permanente em 'mary.memories' como uma lista.
    Mantém no máximo 'max_keep' itens (corta os mais antigos).
    Retorna o entry final gravado (com id/ts).
    """
    entry = dict(entry or {})
    entry.setdefault("ts", datetime.utcnow())
    entry.setdefault("id", f"mem_{int(datetime.utcnow().timestamp())}")

    memories = list_memories(usuario, limit=max_keep)  # já retorna list
    memories.append(entry)

    if max_keep and len(memories) > max_keep:
        memories = memories[-max_keep:]

    set_fact(usuario, _mem_key(), memories, {"fonte": "permanent_memory"})
    return entry


def delete_last_memory(usuario: str) -> bool:
    """
    Remove a última memória da lista 'mary.memories'.
    """
    memories = list_memories(usuario, limit=1000)
    if not memories:
        return False
    memories.pop()
    set_fact(usuario, _mem_key(), memories, {"fonte": "permanent_memory_delete_last"})
    return True


def delete_all_memories(usuario: str) -> int:
    """
    Apaga todas as memórias permanentes.
    Retorna quantas existiam.
    """
    memories = list_memories(usuario, limit=5000)
    n = len(memories)
    set_fact(usuario, _mem_key(), [], {"fonte": "permanent_memory_delete_all"})
    return n



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


def _safe_create_index(col_obj, keys):
    try:
        if hasattr(col_obj, "create_index"):
            col_obj.create_index(keys)
            return True
    except Exception:
        pass

    try:
        inner = getattr(col_obj, "_col", None)
        if inner is not None and hasattr(inner, "create_index"):
            inner.create_index(keys)
            return True
    except Exception:
        pass

    return False


def ensure_indexes() -> None:
    try:
        from .database import get_backend
        if get_backend() != "mongo":
            return

        _safe_create_index(_hist(), [("usuario", 1), ("ts", 1), ("_id", 1)])
        _safe_create_index(_state(), [("usuario", 1)])
        _safe_create_index(_events(), [("usuario", 1), ("ts", -1), ("_id", -1)])
    except Exception:
        pass
