"""
Intent Detection Module
Classifies user queries into intents:
  - "job_search":   user mencari lowongan/posisi tertentu  → RAG pipeline (retrieve + generate)
  - "work_related": pertanyaan/obrolan seputar dunia kerja → LLM langsung tanpa retrieval
  - "out_of_scope": pertanyaan di luar konteks kerja       → balas pesan refusal hardcoded
"""
import os
import json
from openai import OpenAI
from utils.logger import get_logger

logger = get_logger(__name__)

_client = None

VALID_INTENTS = ("job_search", "work_related", "out_of_scope")


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY env var is not set")
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    return _client


INTENT_PROMPT = """Kamu adalah classifier intent untuk asisten pencarian lowongan kerja.
Klasifikasikan query user ke SALAH SATU dari 3 kategori berikut:

1. "job_search" — User mencari lowongan kerja, posisi spesifik, atau rekomendasi pekerjaan.
   Contoh:
   - "lowongan python developer jakarta"
   - "cari kerja UI designer remote"
   - "ada gak posisi data scientist gaji 15 juta?"
   - "rekomendasi kerja untuk fresh graduate IT"

2. "work_related" — Pertanyaan / obrolan seputar dunia kerja yang BUKAN pencarian lowongan langsung.
   Termasuk:
   - Tips CV, surat lamaran, persiapan wawancara
   - Saran karir, skill / sertifikasi yang dibutuhkan profesi tertentu
   - Info umum tentang industri, profesi, atau perusahaan
   - Sapaan ringan & meta-question: "halo", "terima kasih", "siapa kamu", "apa yang bisa kamu lakukan"
   Contoh:
   - "tips bikin CV yang menarik"
   - "gimana cara persiapan wawancara?"
   - "skill apa yang dibutuhkan jadi data scientist?"
   - "halo", "makasih", "kamu siapa?"

3. "out_of_scope" — Pertanyaan DI LUAR konteks dunia kerja: resep, harga makanan, hitungan,
   info umum non-kerja, hiburan, gosip, curhat pribadi non-karir, dll.
   Contoh:
   - "harga soto berapa"
   - "resep nasi goreng"
   - "berapa 1+1"
   - "siapa presiden indonesia"
   - "ceritakan lelucon"
   - "rekomendasi film bagus"

ATURAN:
- Kalau ragu antara "work_related" dan "out_of_scope", pilih "out_of_scope".
- Sapaan & meta-question SELALU "work_related", BUKAN "out_of_scope".
- Kalau query menyebut posisi/profesi tapi bukan untuk cari lowongan (misal "apa itu data scientist?"), itu "work_related".

Respond HANYA dengan JSON valid: {"intent": "job_search"|"work_related"|"out_of_scope", "confidence": 0.0-1.0}
Tidak perlu penjelasan tambahan."""


def detect_intent(query: str) -> dict:
    """
    Detect user intent using LLM.
    Returns: {"intent": "job_search"|"work_related"|"out_of_scope", "confidence": float}
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

        if result.get("intent") not in VALID_INTENTS:
            result["intent"] = "out_of_scope"
        if not isinstance(result.get("confidence"), (int, float)):
            result["confidence"] = 0.5

        return result

    except Exception as e:
        logger.warning("Intent detection failed: %s — defaulting to out_of_scope", e)
        return {"intent": "out_of_scope", "confidence": 0.0}
