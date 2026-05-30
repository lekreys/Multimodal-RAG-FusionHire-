from typing import List, Union

from utils.sparse import bm25_query_vector
from utils.client import (
    is_local,
    call_local_embed,
    get_embedding_client, get_embedding_model,
)
from utils.logger import get_logger

logger = get_logger(__name__)


def sparse_query_manual(text: str):
    """BM25 query vector (presence indicator per token)."""
    return bm25_query_vector(text)


def embed_openai(
    texts: Union[str, List[str]],
) -> Union[List[float], List[List[float]]]:

    is_single = isinstance(texts, str)
    texts_list = [texts] if is_single else texts

    # ── Local Colab API (dengan fallback ke OpenRouter jika gagal) ──────────
    if is_local():
        try:
            result = call_local_embed(texts_list)
            return result[0] if is_single else result
        except Exception as e:
            logger.warning("Local embed gagal (%s), fallback ke OpenRouter...", e)

    # ── OpenRouter / OpenAI embedding ────────────────────────────────────────
    client = get_embedding_client()
    embedding_model = get_embedding_model()

    resp = client.embeddings.create(
        model=embedding_model,
        input=texts_list,
    )

    if is_single:
        return resp.data[0].embedding

    return [item.embedding for item in resp.data]
