import os
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from database.models import DataSkripsi


# Feature flag — when "true", hide jobs whose source listing has been confirmed
# closed by scrapping/verifier.py (DataSkripsi.is_active=False). Default off so
# nothing changes for thesis evaluation runs.
def _filter_inactive_enabled() -> bool:
    return os.getenv("FILTER_INACTIVE_JOBS", "false").strip().lower() in {"1", "true", "yes", "on"}


def qdrant_result_to_full_docs(db: Session, qdrant_result: Any) -> List[Dict[str, Any]]:

    points = getattr(qdrant_result, "points", None) or []

    ordered_job_ids: List[str] = []
    seen = set()
    job_score_map: Dict[str, float] = {}

    for p in points:
        payload = getattr(p, "payload", None) or {}
        job_id = payload.get("job_id")
        if not job_id:
            continue

        score = float(getattr(p, "score", 0.0) or 0.0)

        if job_id not in job_score_map or score > job_score_map[job_id]:
            job_score_map[job_id] = score

        if job_id not in seen:
            seen.add(job_id)
            ordered_job_ids.append(job_id)

    if not ordered_job_ids:
        return []

    query = db.query(DataSkripsi).filter(DataSkripsi.job_id.in_(ordered_job_ids))
    if _filter_inactive_enabled():
        query = query.filter(DataSkripsi.is_active.is_(True))
    jobs: List[DataSkripsi] = query.all()

    def job_to_dict(job: DataSkripsi) -> Dict[str, Any]:
        return {
            "job_id": job.job_id,
            "score": job_score_map.get(job.job_id, 0.0),

            "url": job.url,
            "title": job.title,
            "company": job.company,
            "logo": job.logo,
            "salary": job.salary,
            "posted_at": job.posted_at,
            "work_type": job.work_type,
            "experience": job.experience,
            "education": job.education,
            "requirements_tags": job.requirements_tags or [],
            "skills": job.skills or [],
            "benefits": job.benefits or [],
            "description": job.description,
            "address": job.address,
            "source": job.source,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }

    job_map = {j.job_id: job_to_dict(j) for j in jobs}

    return [job_map[jid] for jid in ordered_job_ids if jid in job_map]
