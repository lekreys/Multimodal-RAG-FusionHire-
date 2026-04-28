
import re
import math
import hashlib
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from qdrant_client.models import SparseVector


SPARSE_DIM = 262_144
TOKEN_RE = re.compile(r"[a-zA-Z0-9_+#\.-]+")


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
        unique_tokens = set(tokenize(doc))
        for tok in unique_tokens:
            df[tok] += 1

    idf: Dict[str, float] = {}
    for tok, count in df.items():
        idf[tok] = math.log((N + 1) / (count + 1)) + 1.0

    return idf


def text_to_sparse_vector(
    text: str,
    *,
    dim: int = SPARSE_DIM,
    tf_weight: str = "log",
    l2_normalize: bool = True,
    idf_weights: Optional[Dict[str, float]] = None,
) -> SparseVector:

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

        if idf_weights is not None:
            w *= idf_weights.get(tok, 1.0)

        bucket[idx] += w

    indices = list(bucket.keys())
    values = [bucket[i] for i in indices]

    if l2_normalize and values:
        norm = math.sqrt(sum(v * v for v in values))
        if norm > 0:
            values = [v / norm for v in values]

    return SparseVector(indices=indices, values=values)
