"""
Centralized error classification and descriptive messaging.
Maps raw exceptions to human-readable descriptions explaining what failed and why.
"""
from __future__ import annotations
import re


def describe_error(e: Exception, context: str = "") -> str:
    """
    Convert an exception into a descriptive message that explains
    what went wrong and why, instead of a raw traceback string.

    Args:
        e: The caught exception.
        context: Short label for where the error occurred
                 (e.g. "OpenRouter", "Qdrant", "Embedding").

    Returns:
        A human-readable string suitable for API responses or chat messages.
    """
    msg = str(e).lower()
    prefix = f"[{context}] " if context else ""

    # ── API / Auth ────────────────────────────────────────────────────────
    if any(k in msg for k in ("401", "unauthorized", "api key", "authentication", "invalid_api_key")):
        return (
            f"{prefix}API key tidak valid atau tidak ditemukan. "
            "Pastikan OPENROUTER_API_KEY sudah di-set dengan benar di .env."
        )

    if any(k in msg for k in ("403", "forbidden", "permission")):
        return (
            f"{prefix}Akses ditolak oleh layanan eksternal. "
            "Periksa izin API key yang digunakan."
        )

    # ── Rate Limit ────────────────────────────────────────────────────────
    if any(k in msg for k in ("429", "rate limit", "too many requests", "quota", "ratelimit")):
        return (
            f"{prefix}Batas request API tercapai (rate limit). "
            "Tunggu beberapa saat lalu coba lagi."
        )

    # ── Network / Connection ──────────────────────────────────────────────
    if any(k in msg for k in ("connection", "connect", "network", "unreachable", "refused", "nodename")):
        target = context or "layanan eksternal"
        return (
            f"{prefix}Tidak bisa terhubung ke {target}. "
            "Periksa koneksi internet atau pastikan layanan sedang berjalan."
        )

    if any(k in msg for k in ("timeout", "timed out", "read timeout", "connect timeout")):
        target = context or "layanan eksternal"
        return (
            f"{prefix}Koneksi ke {target} timeout. "
            "Layanan mungkin sedang sibuk — coba lagi dalam beberapa detik."
        )

    if any(k in msg for k in ("ngrok", "tunnel", "502", "503", "504", "bad gateway", "service unavailable")):
        return (
            f"{prefix}Layanan lokal (Colab/ngrok) tidak bisa diakses. "
            "Pastikan tunnel ngrok dan runtime Colab masih aktif."
        )

    # ── Model / LLM ───────────────────────────────────────────────────────
    if any(k in msg for k in ("model", "not found", "does not exist", "no such model")):
        return (
            f"{prefix}Model LLM tidak ditemukan. "
            "Periksa nilai LLM_MODEL di .env — pastikan nama model sudah benar."
        )

    if any(k in msg for k in ("context length", "token", "max_tokens", "too long")):
        return (
            f"{prefix}Input terlalu panjang untuk model yang digunakan. "
            "Coba kurangi panjang pesan atau konteks."
        )

    # ── JSON / Parse ──────────────────────────────────────────────────────
    if any(k in msg for k in ("json", "parse", "decode", "invalid json", "could not extract")):
        return (
            f"{prefix}Response dari model tidak bisa dibaca (format JSON tidak valid). "
            "Model mungkin mengembalikan output yang tidak sesuai format."
        )

    # ── Qdrant / Vector DB ────────────────────────────────────────────────
    if any(k in msg for k in ("qdrant", "vector", "collection", "dimension", "upsert", "point")):
        return (
            f"{prefix}Pencarian vector (Qdrant) gagal: {str(e)}. "
            "Periksa QDRANT_URL, QDRANT_API_KEY, dan nama koleksi di .env."
        )

    # ── Database ──────────────────────────────────────────────────────────
    if any(k in msg for k in ("sqlalchemy", "psycopg", "database", "relation", "column", "table",
                               "integrity", "duplicate", "unique")):
        return (
            f"{prefix}Operasi database gagal: {str(e)}. "
            "Periksa koneksi DATABASE_URL atau jalankan migrasi terlebih dahulu."
        )

    # ── Supabase / Storage ────────────────────────────────────────────────
    if any(k in msg for k in ("supabase", "bucket", "storage", "upload")):
        return (
            f"{prefix}Upload ke Supabase Storage gagal: {str(e)}. "
            "Periksa SUPABASE_URL, SUPABASE_KEY, dan nama bucket di .env."
        )

    # ── Embedding ─────────────────────────────────────────────────────────
    if any(k in msg for k in ("embedding", "embed", "dimension 0", "got 0")):
        return (
            f"{prefix}Proses embedding gagal menghasilkan vector. "
            "Periksa EMBEDDING_MODEL dan OPENAI_API_KEY di .env."
        )

    # ── Generic fallback ─────────────────────────────────────────────────
    return f"{prefix}Terjadi kesalahan: {str(e)}"
