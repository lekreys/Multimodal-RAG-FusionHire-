import os
import httpx
from openai import OpenAI
from utils.logger import get_logger

logger = get_logger(__name__)


def _local_base_url() -> str:
    return os.getenv("LOCAL_API_URL", "").strip().rstrip("/")


def is_local() -> bool:
    return bool(_local_base_url())


def api_source() -> str:
    return "local (Colab/ngrok)" if is_local() else "openrouter"


def call_local_generate(query: str, context: str = "", system_prompt: str = "",
                        temperature: float = 0.7, max_new_tokens: int = 1024) -> str:
    base_url = _local_base_url()
    url = f"{base_url}/generate"

    body = {
        "query": query,
        "context": context,
        "system_prompt": system_prompt,
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
    }

    logger.info("POST %s", url)
    resp = httpx.post(url, json=body, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    return (
        data.get("response")
        or data.get("answer")
        or data.get("generated_text")
        or data.get("text")
        or data.get("output")
        or str(data)
    )


def get_llm_model() -> str:
    if is_local():
        return os.getenv("LOCAL_LLM_MODEL") or "local-model"
    return os.getenv("LLM_MODEL", "qwen/qwen3-vl-30b-a3b-instruct")


def call_local_embed(texts) -> list:
    base_url = _local_base_url()
    url = f"{base_url}/embed"

    if isinstance(texts, str):
        texts = [texts]

    logger.info("POST %s | texts=%d", url, len(texts))
    resp = httpx.post(url, json={"texts": texts}, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    embeddings = (
        data.get("embeddings")
        or data.get("vectors")
        or data.get("data")
        or data
    )

    return embeddings


def get_embedding_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("API Key tidak ditemukan. Set OPENROUTER_API_KEY di .env")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def get_embedding_model() -> str:
    return os.getenv("LOCAL_EMBEDDING_MODEL") or os.getenv("EMBEDDING_MODEL", "qwen/qwen3-embedding-8b")


def get_openrouter_client() -> OpenAI:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("API Key tidak ditemukan. Set OPENROUTER_API_KEY di .env")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
