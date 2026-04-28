import base64
import os
import json
import re
import uuid
import httpx
from openai import OpenAI
from typing import Dict, Any
from utils.logger import get_logger
from utils.errors import describe_error

logger = get_logger(__name__)


def _detect_mime(image_bytes: bytes) -> str:
    """Deteksi MIME type dari magic bytes — tanpa dependency tambahan."""
    if image_bytes[:2] == b'\xff\xd8':
        return "image/jpeg"
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    if image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    if image_bytes[:4] in (b'\x00\x00\x00\x0c', b'\x00\x00\x00\x18', b'\x00\x00\x00\x1c') or image_bytes[4:8] == b'ftyp':
        return "image/avif"
    return "image/jpeg"  # fallback


class NotJobPostingError(ValueError):
    """Raised when the uploaded image is not a job posting."""
    def __init__(self):
        super().__init__("Ini bukan file lowongan kerja.")


def _extract_json(text: str) -> dict:
    text = text.strip()

    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        candidate = match.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            last_brace = candidate.rfind("}")
            if last_brace != -1:
                try:
                    return json.loads(candidate[: last_brace + 1])
                except json.JSONDecodeError:
                    pass

    logger.warning("Tidak bisa ekstrak JSON. Raw response (500 char pertama): %s", text[:500])
    raise ValueError(
        "Model mengembalikan response yang tidak bisa dibaca sebagai JSON. "
        f"Panjang response: {len(text)} karakter."
    )


VISION_PROMPT = """
You are a job poster analyzer. Your task has TWO steps:

STEP 1 — VALIDATION
Determine whether this image is a job posting / job vacancy / lowongan kerja.
A valid job posting typically contains at least one of: job title, company name, job requirements, or application instructions.
Examples of INVALID images: food menus, product catalogs, event flyers, personal photos, memes, invoices, receipts, random documents.

STEP 2 — EXTRACTION (only if valid)
If and only if the image IS a job posting, extract the following fields:
- title (Job Title)
- company (Company Name)
- location (Location/Address)
- salary (Salary string, e.g. "Rp 10.000.000 - Rp 15.000.000")
- work_type (Full-time, Contract, Remote, etc.)
- experience (Experience level string)
- education (Education level string)
- skills (List of strings)
- description (Summary of the job description, max 300 words)
- requirements_tags (List of strings for requirements)
- benefits (List of strings)

OUTPUT RULES:
- If NOT a job posting → respond ONLY with: {"valid": false}
- If IS a job posting → respond ONLY with: {"valid": true, "title": ..., "company": ..., ...all fields...}
- Response must be a single valid JSON object, no extra text or markdown.
- For missing fields use null or empty string/list as appropriate.
"""


def _validate_and_build(data: dict) -> dict:
    """Check the 'valid' flag from model response, then build the job result."""
    if not data.get("valid", True):
        logger.warning("Model menyatakan gambar bukan poster lowongan kerja.")
        raise NotJobPostingError()

    return {
        "job_id": f"img-{uuid.uuid4().hex[:8]}",
        "url": f"https://image-upload.local/{uuid.uuid4().hex[:12]}",
        "title": data.get("title") or "Unknown Position",
        "company": data.get("company") or "Unknown Company",
        "logo": "",
        "salary": data.get("salary") or "",
        "posted_at": "Just now",
        "work_type": data.get("work_type") or "",
        "experience": data.get("experience") or "",
        "education": data.get("education") or "",
        "requirements_tags": data.get("requirements_tags") or [],
        "skills": data.get("skills") or [],
        "benefits": data.get("benefits") or [],
        "description": data.get("description") or "No description extracted from image.",
        "address": data.get("location") or "",
        "source": "Image Upload"
    }


def _extract_via_openrouter(base64_image: str, mime: str = "image/jpeg") -> Dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "API key tidak ditemukan. Set OPENROUTER_API_KEY di .env untuk menggunakan fitur ini."
        )

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    logger.info("Using OpenRouter for vision extraction")
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "qwen/qwen-vl-plus"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{base64_image}"},
                    },
                ],
            }
        ],
        max_tokens=2000,
        extra_headers={
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "Job Search RAG",
        },
    )

    content = response.choices[0].message.content
    logger.info("OpenRouter vision response: %d chars", len(content))
    data = _extract_json(content)
    return _validate_and_build(data)


def extract_job_from_image_debug(image_bytes: bytes) -> Dict[str, Any]:
    """
    Sama seperti extract_job_from_image tapi juga return raw model response dan api_used.
    Return: {"job_data": dict|None, "raw_model_response": str, "is_job_posting": bool, "api_used": str}
    """
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    local_url = os.getenv("LOCAL_API_URL", "").strip().rstrip("/")
    raw_text = ""
    api_used = ""

    if local_url:
        url = f"{local_url}/vision"
        api_used = f"local ({local_url})"
        try:
            resp = httpx.post(
                url,
                json={"image_base64": base64_image, "prompt": VISION_PROMPT, "max_new_tokens": 2000},
                timeout=180,
            )
            resp.raise_for_status()
            raw = resp.json()
            raw_text = raw.get("response") or raw.get("answer") or raw.get("text") or str(raw)
        except Exception as e:
            logger.warning("Local vision failed: %s — fallback ke OpenRouter", e)
            raw_text = ""

    mime = _detect_mime(image_bytes)

    if not raw_text:
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("API key tidak ditemukan.")
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        model = os.getenv("LLM_MODEL", "qwen/qwen-vl-plus")
        api_used = f"openrouter ({model})"
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64_image}"}},
            ]}],
            max_tokens=2000,
            extra_headers={"HTTP-Referer": "http://localhost:8501", "X-Title": "Job Search RAG"},
        )
        raw_text = response.choices[0].message.content

    try:
        data = _extract_json(raw_text)
    except ValueError:
        return {"job_data": None, "raw_model_response": raw_text, "is_job_posting": None, "api_used": api_used, "error": "JSON parse failed"}

    is_job = bool(data.get("valid", True))
    if not is_job:
        return {"job_data": None, "raw_model_response": raw_text, "is_job_posting": False, "api_used": api_used, "error": ""}

    job_data = _validate_and_build(data)
    return {"job_data": job_data, "raw_model_response": raw_text, "is_job_posting": True, "api_used": api_used, "error": ""}


def extract_job_from_image(image_bytes: bytes) -> Dict[str, Any]:
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    mime = _detect_mime(image_bytes)

    local_url = os.getenv("LOCAL_API_URL", "").strip().rstrip("/")

    # ── Local Colab /vision ───────────────────────────────────────────
    if local_url:
        url = f"{local_url}/vision"
        logger.info("Using local Colab: POST %s", url)
        try:
            resp = httpx.post(
                url,
                json={
                    "image_base64": base64_image,
                    "prompt": VISION_PROMPT,
                    "max_new_tokens": 2000,
                },
                timeout=180,
            )
            resp.raise_for_status()
            raw = resp.json()

            content = (
                raw.get("response")
                or raw.get("answer")
                or raw.get("text")
                or str(raw)
            )
            logger.info("Local vision response: %d chars", len(content))
            data = _extract_json(content)
            return _validate_and_build(data)

        except NotJobPostingError:
            raise  # jangan fallback, langsung tolak
        except Exception as e:
            err_msg = describe_error(e, "Local Vision")
            logger.warning("%s — fallback ke OpenRouter", err_msg)

    # ── OpenRouter (primary or fallback) ─────────────────────────────
    try:
        return _extract_via_openrouter(base64_image, mime=mime)
    except Exception as e:
        err_msg = describe_error(e, "Vision/OpenRouter")
        logger.error(err_msg)
        raise RuntimeError(err_msg) from e
