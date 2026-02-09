import os
from typing import List, Union

from openai import OpenAI

# Use shared sparse vector utilities
from utils.sparse import text_to_sparse_vector as sparse_query_manual


def embed_openai(
    texts: Union[str, List[str]],
    model: str = "text-embedding-3-small",
) -> Union[List[float], List[List[float]]]:
    """
    Uses OpenRouter for Embeddings. 
    Ensure valid model ID in .env (EMBEDDING_MODEL).
    """
    
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    embedding_model = os.getenv("EMBEDDING_MODEL", "qwen/qwen-embedding")
    
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY env var is not set")
    
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

    try:
        resp = client.embeddings.create(
            model=embedding_model,
            input=texts,
        )
    except Exception as e:
        print(f"OpenRouter Embedding Error: {e}")
        return [] if isinstance(texts, list) else []

    if isinstance(texts, str):
        return resp.data[0].embedding

    # batch
    return [item.embedding for item in resp.data]
