"""
Shared sparse vector utilities for hybrid search.
Used by both store (indexing) and retrieval (querying).
"""
import re
import math
import hashlib
from collections import Counter, defaultdict
from typing import List

from qdrant_client.models import SparseVector


# Sparse vector configuration
SPARSE_DIM = 262_144  # 2^18 - large enough to minimize collisions
TOKEN_RE = re.compile(r"[a-zA-Z0-9_+#\.-]+")


def tokenize(text: str) -> List[str]:
    """
    Simple tokenization that handles Indo/EN + skill tokens like:
    fastapi, c++, node.js, react-native, etc.
    """
    if not text:
        return []
    return TOKEN_RE.findall(text.lower())


def stable_hash(token: str) -> int:
    """
    Deterministic hash across sessions (python's hash() is random per session).
    """
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(h, 16)


def text_to_sparse_vector(
    text: str,
    *,
    dim: int = SPARSE_DIM,
    tf_weight: str = "log",  # "raw" or "log"
    l2_normalize: bool = True,
) -> SparseVector:
    """
    Create sparse vector using lexical hashing:
    - index = md5(token) % dim
    - value = tf (raw or 1+log(tf))
    
    This is not exact BM25, but works well for hybrid dense+sparse search:
    - Dense: semantic understanding
    - Sparse: keyword matching (exact token presence)
    """
    toks = tokenize(text)
    if not toks:
        return SparseVector(indices=[], values=[])

    tf = Counter(toks)

    bucket = defaultdict(float)
    for tok, freq in tf.items():
        idx = stable_hash(tok) % dim
        if tf_weight == "log":
            w = 1.0 + math.log(freq)
        else:
            w = float(freq)
        bucket[idx] += w  # accumulate on collision

    indices = list(bucket.keys())
    values = [bucket[i] for i in indices]

    if l2_normalize and values:
        norm = math.sqrt(sum(v * v for v in values))
        if norm > 0:
            values = [v / norm for v in values]

    return SparseVector(indices=indices, values=values)


# Alias for backward compatibility
sparse_query_manual = text_to_sparse_vector
text_to_sparse_hash_vector = text_to_sparse_vector
