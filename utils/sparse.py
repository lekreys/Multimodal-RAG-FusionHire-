
import re
import math
import hashlib
from collections import Counter, defaultdict
from typing import Dict, List

from qdrant_client.models import SparseVector


SPARSE_DIM = 262_144
TOKEN_RE = re.compile(r"[a-zA-Z0-9_+#\.-]+")

# BM25 default parameters (Lucene / Elasticsearch defaults)
BM25_K1 = 1.5
BM25_B = 0.75


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return TOKEN_RE.findall(text.lower())


def stable_hash(token: str) -> int:
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(h, 16)


def compute_idf(documents: List[str]) -> Dict[str, float]:

    N = len(documents)
    if N == 0:
        return {}

    df: Dict[str, int] = defaultdict(int)
    for doc in documents:
        for tok in set(tokenize(doc)):
            df[tok] += 1

    return {
        tok: math.log((N - count + 0.5) / (count + 0.5) + 1.0)
        for tok, count in df.items()
    }


def compute_avgdl(documents: List[str]) -> float:
    """Average document length in tokens — denominator for BM25 length norm."""
    if not documents:
        return 0.0
    total = sum(len(tokenize(doc)) for doc in documents)
    return total / len(documents)


def bm25_document_vector(
    text: str,
    *,
    idf_weights: Dict[str, float],
    avgdl: float,
    k1: float = BM25_K1,
    b: float = BM25_B,
    dim: int = SPARSE_DIM,
) -> SparseVector:
    
    # convert dokument per chunk
  
    toks = tokenize(text)
    if not toks:
        return SparseVector(indices=[], values=[])

    dl = len(toks)
    avgdl_safe = avgdl if avgdl > 0 else 1.0
    norm = 1.0 - b + b * (dl / avgdl_safe)

    tf = Counter(toks)
    bucket: Dict[int, float] = defaultdict(float)

    for tok, freq in tf.items():
        idf = idf_weights.get(tok, 0.0)
        if idf == 0.0:
            continue
        weight = idf * (freq * (k1 + 1.0)) / (freq + k1 * norm)
        idx = stable_hash(tok) % dim
        bucket[idx] += weight

    indices = list(bucket.keys())
    values = [bucket[i] for i in indices]
    return SparseVector(indices=indices, values=values)


def bm25_query_vector(text: str, *, dim: int = SPARSE_DIM) -> SparseVector:
    """
    BM25 query side: 1.0 indicator per unique query token.

    Dot product against `bm25_document_vector` yields the standard BM25 score
    (sum of per-term BM25 weights for terms present in the query).
    """
    toks = tokenize(text)
    if not toks:
        return SparseVector(indices=[], values=[])

    bucket: Dict[int, float] = {}
    for tok in set(toks):
        idx = stable_hash(tok) % dim
        bucket[idx] = 1.0

    return SparseVector(indices=list(bucket.keys()), values=list(bucket.values()))
