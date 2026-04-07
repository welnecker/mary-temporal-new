from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Dict, List, Optional


def _memory_timeline_ok(
    meta: Dict[str, Any],
    timeline: str,
    *,
    normalize_timeline_fn: Callable[[str], str],
) -> bool:
    tl = normalize_timeline_fn(timeline)

    raw = (meta.get("timeline_at_save") or meta.get("timeline") or "")
    raw_s = str(raw).strip()
    raw_l = raw_s.lower()

    if raw_l in ("[all]", "all", "*"):
        return True

    tms = normalize_timeline_fn(raw_s) if raw_s else ""

    # legado: canon antigo sem timeline -> vale só para cúmplice
    if not tms:
        return tl == "cumplice"

    return tms == tl


def _has_canon_memories(
    shared_key: str,
    timeline: str,
    *,
    cached_list_memories_page_fn: Callable[..., List[Dict[str, Any]]],
    normalize_timeline_fn: Callable[[str], str],
) -> bool:
    PAGE = 120
    HARD_CAP = 480

    scanned = 0
    offset = 0

    while scanned < HARD_CAP:
        batch = cached_list_memories_page_fn(shared_key, offset=offset, limit=PAGE)
        if not batch:
            return False

        for m in batch:
            meta = m.get("meta") or {}
            if str(meta.get("kind") or "").strip().lower() != "canon":
                continue
            if _memory_timeline_ok(
                meta,
                timeline,
                normalize_timeline_fn=normalize_timeline_fn,
            ):
                return True

        scanned += len(batch)
        offset += PAGE

    return False


def _inject_canon_memories_always(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    max_items: int = 30,
    *,
    dedupe_bucket: Optional[set] = None,
    cached_list_memories_page_fn: Callable[..., List[Dict[str, Any]]],
    normalize_timeline_fn: Callable[[str], str],
    ss_set_fn: Optional[Callable[[str, Any], None]] = None,
    ss_prefix: str = "",
) -> None:
    """
    FIX: antes injetava repetidamente dentro do loop.
    Agora: monta bloco uma vez e injeta uma vez.
    """
    canon: List[Dict[str, Any]] = []

    PAGE = 120
    HARD_CAP = 480

    scanned = 0
    offset = 0
    want = int(max_items or 30)

    while scanned < HARD_CAP and len(canon) < want:
        batch = cached_list_memories_page_fn(shared_key, offset=offset, limit=PAGE)
        if not batch:
            break

        for m in batch:
            meta = m.get("meta") or {}
            if str(meta.get("kind") or "").strip().lower() != "canon":
                continue
            if not _memory_timeline_ok(
                meta,
                timeline,
                normalize_timeline_fn=normalize_timeline_fn,
            ):
                continue

            canon.append(m)
            if len(canon) >= want:
                break

        scanned += len(batch)
        offset += PAGE

    if not canon:
        return

    selected = canon[-want:] if len(canon) > want else canon

    if callable(ss_set_fn) and ss_prefix:
        try:
            ss_set_fn(f"{ss_prefix}debug_canon_injected_count", len(selected))
        except Exception:
            pass

    lines: List[str] = []
    lines.append("[FATOS CANÔNICOS]")
    lines.append("Use como verdade do universo.")
    lines.append("")

    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        d = meta.get("date") or meta.get("ts") or ""
        title = meta.get("title") or meta.get("key") or ""

        header = f"- CANON {i}"
        if d:
            header += f" (data: {d})"
        if title:
            header += f" - {title}"
        lines.append(header)

        txt = str(m.get("text") or "").strip()
        if txt:
            lines.append(txt)
        lines.append("")

        if dedupe_bucket is not None and txt:
            dedupe_bucket.add(hashlib.sha1(txt.encode("utf-8")).hexdigest())

    block = "\n".join(lines).strip()

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = (str(messages[0].get("content") or "").rstrip() + "\n\n" + block).strip()
    else:
        messages.append({"role": "system", "content": block})


def _inject_active_state_memories_always(
    shared_key: str,
    timeline: str,
    messages: List[Dict[str, str]],
    max_items: int = 12,
    *,
    dedupe_bucket: Optional[set] = None,
    cached_list_memories_page_fn: Callable[..., List[Dict[str, Any]]],
    normalize_timeline_fn: Callable[[str], str],
    ss_set_fn: Optional[Callable[[str, Any], None]] = None,
    ss_prefix: str = "",
) -> None:
    """
    Injeta memórias shared com kind='estado_ativo'.
    """
    active_state: List[Dict[str, Any]] = []

    PAGE = 120
    HARD_CAP = 480

    scanned = 0
    offset = 0
    want = int(max_items or 12)

    while scanned < HARD_CAP and len(active_state) < want:
        batch = cached_list_memories_page_fn(shared_key, offset=offset, limit=PAGE)
        if not batch:
            break

        for m in batch:
            meta = m.get("meta") or {}
            kind = str(meta.get("kind") or "").strip().lower()

            if kind != "estado_ativo":
                continue

            if not _memory_timeline_ok(
                meta,
                timeline,
                normalize_timeline_fn=normalize_timeline_fn,
            ):
                continue

            txt = str(m.get("text") or "").strip()
            if not txt:
                continue

            txt = re.sub(r"(?im)^\s*\[TAGS:\s*[^\]]+\]\s*", "", txt).strip()
            if not txt:
                continue

            m2 = dict(m)
            m2["text"] = txt
            active_state.append(m2)

            if len(active_state) >= want:
                break

        scanned += len(batch)
        offset += PAGE

    if not active_state:
        return

    selected = active_state[-want:] if len(active_state) > want else active_state

    if callable(ss_set_fn) and ss_prefix:
        try:
            ss_set_fn(f"{ss_prefix}debug_active_state_injected_count", len(selected))
        except Exception:
            pass

    lines: List[str] = []
    lines.append("[ESTADO ATIVO COMPARTILHADO]")
    lines.append("Use como identidade contínua, rotina e contexto estável da vida de Mary e Janio.")
    lines.append("Não citar literalmente; incorporar de forma natural.")
    lines.append("")

    for i, m in enumerate(selected, 1):
        meta = m.get("meta") or {}
        title = meta.get("title") or meta.get("key") or ""
        d = meta.get("date") or meta.get("ts") or ""

        header = f"- ESTADO {i}"
        if d:
            header += f" (data: {d})"
        if title:
            header += f" - {title}"
        lines.append(header)

        txt = str(m.get("text") or "").strip()
        if txt:
            lines.append(txt)
        lines.append("")

        if dedupe_bucket is not None and txt:
            dedupe_bucket.add(hashlib.sha1(txt.encode("utf-8")).hexdigest())

    block = "\n".join(lines).strip()

    if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
        messages[0]["content"] = (
            str(messages[0].get("content") or "").rstrip() + "\n\n" + block
        ).strip()
    else:
        messages.append({"role": "system", "content": block})


def _choose_intro_text(
    usuario_key: str,
    timeline: str,
    *,
    get_fact_fn: Callable[..., Any],
    sync_intro_fact_fn: Callable[[str, str], tuple[str, str]],
) -> str:
    """
    Prioridade correta:
    - 1. intro da timeline sincronizado da persona
    - 2. intro FIXO somente se o flag mary.intro.use_fixed estiver True
    """
    use_fixed = bool(get_fact_fn(usuario_key, "mary.intro.use_fixed", default=False))
    fixed_intro = str(get_fact_fn(usuario_key, "mary.intro.fixed", default="") or "").strip()

    if use_fixed and fixed_intro:
        return fixed_intro

    _, intro_text = sync_intro_fact_fn(usuario_key, timeline)
    return str(intro_text or "").strip()
