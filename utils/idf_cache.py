"""
Cached IDF weights for TF-IDF sparse vectors.

Loads IDF from PostgreSQL (all job docs), caches in memory with 1-hour TTL.
Both store (indexing) and retrieval (querying) use this to get consistent IDF weights.
"""
import time
from typing import Dict, Optional
from utils.logger import get_logger

logger = get_logger(__name__)

_idf_cache: Optional[Dict[str, float]] = None
_idf_cache_time: float = 0
_IDF_TTL_SECONDS = 3600


def get_idf_weights(force_refresh: bool = False) -> Dict[str, float]:
    global _idf_cache, _idf_cache_time

    now = time.time()
    if not force_refresh and _idf_cache is not None and (now - _idf_cache_time) < _IDF_TTL_SECONDS:
        return _idf_cache

    from database.database import SessionLocal
    from database.models import DataSkripsi
    from .sparse import compute_idf

    db = SessionLocal()
    try:
        jobs = db.query(DataSkripsi.title, DataSkripsi.description, DataSkripsi.skills, DataSkripsi.address).all()

        if not jobs:
            _idf_cache = {}
            _idf_cache_time = now
            return _idf_cache

        documents = []
        for job in jobs:
            parts = []
            if job.title:
                parts.append(str(job.title))
            if job.description:
                parts.append(str(job.description))
            if job.skills:
                if isinstance(job.skills, list):
                    parts.append(" ".join(str(s) for s in job.skills))
                else:
                    parts.append(str(job.skills))
            if job.address:
                parts.append(str(job.address))
            documents.append(" ".join(parts))

        _idf_cache = compute_idf(documents)
        _idf_cache_time = now

        logger.info("Computed IDF from %d jobs, %d unique tokens", len(documents), len(_idf_cache))

        return _idf_cache

    except Exception as e:
        logger.error("Error computing IDF: %s — using empty weights", e)
        _idf_cache = {}
        _idf_cache_time = now
        return _idf_cache

    finally:
        db.close()


def invalidate_cache():
    """Force IDF cache to refresh on next access (call after re-indexing)."""
    global _idf_cache, _idf_cache_time
    _idf_cache = None
    _idf_cache_time = 0
