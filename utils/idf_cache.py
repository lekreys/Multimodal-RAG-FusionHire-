import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BM25Stats:
    idf: Dict[str, float] = field(default_factory=dict)
    avgdl: float = 0.0


_cache: Optional[BM25Stats] = None
_cache_time: float = 0.0
_TTL_SECONDS = 3600


def get_bm25_stats(force_refresh: bool = False) -> BM25Stats:
    ## hitung parameter
    global _cache, _cache_time

    now = time.time()
    if not force_refresh and _cache is not None and (now - _cache_time) < _TTL_SECONDS:
        return _cache

    from database.database import SessionLocal
    from database.models import DataSkripsi
    from store.helper import document_splitting_multi  # lazy: avoid circular import
    from .sparse import compute_idf, compute_avgdl

    db = SessionLocal()
    try:
        jobs = db.query(DataSkripsi).all()
        if not jobs:
            _cache = BM25Stats()
            _cache_time = now
            return _cache

        job_dicts = [
            {
                "job_id": j.job_id, "url": j.url,
                "title": j.title, "company": j.company, "logo": j.logo,
                "salary": j.salary, "posted_at": j.posted_at,
                "work_type": j.work_type, "experience": j.experience,
                "education": j.education,
                "requirements_tags": j.requirements_tags,
                "skills": j.skills, "benefits": j.benefits,
                "description": j.description, "address": j.address,
                "source": j.source,
            }
            for j in jobs
        ]

        chunks = document_splitting_multi(job_dicts)
        chunk_texts = [c["text"] for c in chunks]

        if not chunk_texts:
            _cache = BM25Stats()
            _cache_time = now
            return _cache

        idf = compute_idf(chunk_texts)
        avgdl = compute_avgdl(chunk_texts)

        _cache = BM25Stats(idf=idf, avgdl=avgdl)
        _cache_time = now

        logger.info(
            "BM25 stats: %d jobs → %d chunks, %d unique tokens, avgdl=%.2f",
            len(jobs), len(chunks), len(idf), avgdl,
        )
        return _cache

    except Exception as e:
        logger.error("BM25 stats computation failed: %s — using empty stats", e)
        _cache = BM25Stats()
        _cache_time = now
        return _cache

    finally:
        db.close()


def invalidate_cache():
    """Force BM25 stats to recompute on next access (call after re-indexing)."""
    global _cache, _cache_time
    _cache = None
    _cache_time = 0.0
