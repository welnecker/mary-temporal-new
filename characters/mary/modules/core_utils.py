from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Iterable, List


def _safe(value: Any, default: str = "") -> str:
    """
    Converte qualquer valor em string segura.
    """
    try:
        if value is None:
            return default
        return str(value)
    except Exception:
        return default


def _clamp01(x: float) -> float:
    """
    Limita um número ao intervalo [0.0, 1.0].
    """
    try:
        x = float(x)
    except Exception:
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _norm_any(value: Any) -> str:
    """
    Normalização genérica e leve para comparações textuais.
    """
    text = _safe(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _norm_token(value: Any) -> str:
    """
    Normaliza token para comparação mais rígida.
    Remove espaços excedentes e caracteres estranhos nas bordas.
    """
    text = _norm_any(value)
    text = re.sub(r"^[\W_]+|[\W_]+$", "", text)
    return text


def _hash_text(text: Any) -> str:
    """
    Gera hash estável de texto.
    """
    raw = _safe(text)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _tok(text: Any) -> List[str]:
    """
    Tokenização simples para busca/ranking local.
    """
    raw = _norm_any(text)
    if not raw:
        return []
    return re.findall(r"\b[\wÀ-ÿ']+\b", raw, flags=re.UNICODE)


def _idf(doc_freq: int, total_docs: int) -> float:
    """
    IDF simples e seguro.
    """
    try:
        doc_freq = int(doc_freq)
        total_docs = int(total_docs)
        if doc_freq < 0:
            doc_freq = 0
        if total_docs <= 0:
            return 0.0
        return math.log((1 + total_docs) / (1 + doc_freq)) + 1.0
    except Exception:
        return 0.0


def _bm25_topk(
    query: str,
    docs: Iterable[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
    top_k: int = 5,
) -> List[int]:
    """
    BM25 simplificado.
    Retorna os índices dos documentos mais relevantes.
    """
    docs = list(docs or [])
    if not docs:
        return []

    q_tokens = _tok(query)
    if not q_tokens:
        return []

    tokenized_docs = [_tok(doc) for doc in docs]
    doc_lens = [len(toks) for toks in tokenized_docs]
    avgdl = sum(doc_lens) / max(len(doc_lens), 1)

    df = {}
    for qt in set(q_tokens):
        df[qt] = sum(1 for toks in tokenized_docs if qt in toks)

    scores = []
    for idx, toks in enumerate(tokenized_docs):
        score = 0.0
        dl = len(toks)

        for qt in q_tokens:
            tf = toks.count(qt)
            if tf == 0:
                continue

            idf = _idf(df.get(qt, 0), len(tokenized_docs))
            denom = tf + k1 * (1 - b + b * (dl / avgdl if avgdl > 0 else 0.0))
            score += idf * ((tf * (k1 + 1)) / denom)

        scores.append((idx, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, score in scores[:top_k] if score > 0]
