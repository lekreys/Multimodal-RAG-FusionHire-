"""
Intent Detection Module
Classifies user queries into intents:
  - "job_search": queries about finding jobs → use RAG pipeline
  - "general": general questions → answer directly without retrieval
"""
import os
import json
from openai import OpenAI
from utils.logger import get_logger

logger = get_logger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY env var is not set")
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    return _client


INTENT_PROMPT = """Kamu adalah classifier intent. Klasifikasikan query user ke salah satu intent berikut:

1. "job_search" — User mencari lowongan kerja, rekomendasi pekerjaan, atau info spesifik tentang posisi/perusahaan tertentu.
   Contoh: "lowongan python developer jakarta", "cari kerja UI designer", "ada gak posisi data scientist gaji 15 juta?"

2. "general" — Pertanyaan umum, obrolan biasa, atau topik yang TIDAK terkait pencarian lowongan kerja.
   Contoh: "apa itu machine learning?", "jelaskan perbedaan SQL dan NoSQL", "halo", "terima kasih"

Respond HANYA dengan JSON: {"intent": "job_search" atau "general", "confidence": 0.0-1.0}
Tidak perlu penjelasan tambahan."""


def detect_intent(query: str) -> dict:
    """
    Detect user intent using LLM.
    Returns: {"intent": "job_search"|"general", "confidence": float}
    """
    client = _get_client()
    model = os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": query},
            ],
            extra_headers={
                "HTTP-Referer": "http://localhost:8501",
                "X-Title": "Job Search RAG",
            },
            temperature=0.1,
            max_tokens=50,
        )

        content = resp.choices[0].message.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        result = json.loads(content)

        if result.get("intent") not in ("job_search", "general"):
            result["intent"] = "job_search"
        if not isinstance(result.get("confidence"), (int, float)):
            result["confidence"] = 0.5

        return result

    except Exception as e:
        logger.warning("Intent detection failed: %s — defaulting to job_search", e)
        return {"intent": "job_search", "confidence": 0.5}
