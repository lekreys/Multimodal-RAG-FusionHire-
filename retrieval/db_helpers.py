from typing import Any, Dict, List
from sqlalchemy.orm import Session

# Pastikan sys.path sudah dikonfigurasi di entry point (app.py)
# sehingga 'database' package (parent) bisa ditemukan.
from database.models import Job


def qdrant_result_to_full_docs(db: Session, qdrant_result: Any) -> List[Dict[str, Any]]:
    """
    Input:
        - db: SQLAlchemy Session
        - qdrant_result: hasil retrieve Qdrant (punya .points)

    Output:
        - list dict full document dari PostgreSQL table jobs_docs
        - SETIAP ITEM ada field 'score' (diambil dari Qdrant)
        - urutan mengikuti ranking Qdrant
    """

    # 1) Extract job_ids + ambil score tertinggi per job_id
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

        # simpan score tertinggi untuk job_id ini
        if job_id not in job_score_map or score > job_score_map[job_id]:
            job_score_map[job_id] = score

        # preserve order (ranking Qdrant)
        if job_id not in seen:
            seen.add(job_id)
            ordered_job_ids.append(job_id)

    if not ordered_job_ids:
        return []

    # 2) Fetch all matching rows in ONE query (Postgres)
    jobs: List[Job] = db.query(Job).filter(Job.job_id.in_(ordered_job_ids)).all()

    # 3) Convert ke dict + attach score
    def job_to_dict(job: Job) -> Dict[str, Any]:
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

    # 4) Return sesuai ranking Qdrant (skip yang tidak ada di DB)
    return [job_map[jid] for jid in ordered_job_ids if jid in job_map]
