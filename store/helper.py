from __future__ import annotations

from typing import Any, Dict, List, Union, Tuple, Optional
import os
import uuid

from sqlalchemy.exc import IntegrityError

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseVector,
    PointStruct,
)

from openai import OpenAI

from database.database import SessionLocal
from database.models import Job

# Use shared sparse vector utilities
from utils.sparse import text_to_sparse_vector as text_to_sparse_hash_vector




# Sparse vector function imported from utils.sparse


# =========================
# 1) SAVE TO SQL DB
# =========================
def save_documents_database(
    payload: Union[Dict[str, Any], List[Dict[str, Any]]]
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Return:
      inserted_jobs: list job dict yang BERHASIL masuk DB (ini yang di-embed)
      inserted: jumlah inserted
      skipped: jumlah skipped
    """
    data = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        raise ValueError("payload['data'] harus list")

    db = SessionLocal()

    inserted_jobs: List[Dict[str, Any]] = []
    inserted = 0
    skipped = 0
    seen_urls = set()

    try:
        for item in data:
            if not isinstance(item, dict):
                skipped += 1
                continue

            url = (item.get("url") or "").strip()
            job_id = (item.get("job_id") or "").strip()
            if not url or not job_id:
                skipped += 1
                continue

            # 1) skip duplikat url dalam batch
            if url in seen_urls:
                skipped += 1
                continue
            seen_urls.add(url)

            # 2) skip kalau url sudah ada di DB
            exists = db.query(Job).filter(Job.url == url).first()
            if exists:
                skipped += 1
                continue

            db.add(Job(
                job_id=job_id,
                url=url,
                title=item.get("title"),
                company=item.get("company"),
                logo=item.get("logo"),
                salary=item.get("salary"),
                posted_at=item.get("posted_at"),
                work_type=item.get("work_type"),
                experience=item.get("experience"),
                education=item.get("education"),
                requirements_tags=item.get("requirements_tags"),
                skills=item.get("skills"),
                benefits=item.get("benefits"),
                description=item.get("description"),
                address=item.get("address"),
                source=item.get("source"),
            ))

            inserted_jobs.append(item)
            inserted += 1

        db.commit()
        return inserted_jobs, inserted, skipped

    except IntegrityError:
        db.rollback()
        return inserted_jobs, inserted, skipped

    finally:
        db.close()


# =========================
# 2) SPLITTING / CHUNKING
# =========================
def chunk_text(text: str, max_chars: int = 900) -> List[str]:
    if not text:
        return []
    t = str(text).strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]

    chunks = []
    start = 0
    while start < len(t):
        end = min(start + max_chars, len(t))
        chunks.append(t[start:end])
        start = end
    return chunks


def document_splitting_multi(scrapping_json: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    data = scrapping_json
    out_docs: List[Dict[str, Any]] = []

    for job in data:
        job_id = job.get("job_id")
        if not job_id:
            continue

        url = job.get("url", "")
        title = job.get("title", "") or ""
        company = job.get("company", "") or ""
        logo = job.get("logo", "")
        salary = job.get("salary", "") or ""
        posted_at = job.get("posted_at", "") or ""
        work_type = job.get("work_type", "") or ""
        experience = job.get("experience", "") or ""
        education = job.get("education", "") or ""
        requirements_tags = job.get("requirements_tags", []) or []
        skills = job.get("skills", []) or []
        benefits = job.get("benefits", []) or []
        description = job.get("description", "") or ""
        address = job.get("address", "") or ""
        source = job.get("source", "") or ""

        if isinstance(skills, str):
            skills = [skills]
        if isinstance(requirements_tags, str):
            requirements_tags = [requirements_tags]
        if isinstance(benefits, str):
            benefits = [benefits]

        base_payload = {
            "job_id": job_id,
            "url": url,
            "title": title,
            "company": company,
            "logo": logo,
            "salary": salary,
            "posted_at": posted_at,
            "work_type": work_type,
            "experience": experience,
            "education": education,
            "address": address,
            "source": source,
        }

        # 1) TITLE + COMPANY
        title_company_text = " | ".join([x for x in [title.strip(), company.strip()] if x])
        if title_company_text:
            out_docs.append({
                "point_id": f"{job_id}:title_company:0",
                "job_id": job_id,
                "field": "title_company",
                "text": f"Posisi: {title}. Perusahaan: {company}.",
                "payload": {**base_payload, "field": "title_company", "chunk_idx": 0}
            })

        # 2) SKILLS + REQUIREMENTS
        skills_text = ", ".join([s.strip() for s in skills if str(s).strip()])
        req_text = ", ".join([r.strip() for r in requirements_tags if str(r).strip()])

        parts = []
        if skills_text:
            parts.append(f"Keterampilan teknis yang dibutuhkan meliputi: {skills_text}.")
        if req_text:
            parts.append(f"Persyaratan tambahan yang diperlukan meliputi: {req_text}.")
        document_skills_req = " ".join(parts).strip()

        if document_skills_req:
            out_docs.append({
                "point_id": f"{job_id}:skills_requirements:0",
                "job_id": job_id,
                "field": "skills_requirements",
                "text": document_skills_req,
                "payload": {**base_payload, "field": "skills_requirements", "chunk_idx": 0}
            })

        # 3) DESCRIPTION (chunking)
        desc_chunks = chunk_text(description, max_chars=900)
        for i, ch in enumerate(desc_chunks):
            ch = ch.strip()
            if ch:
                out_docs.append({
                    "point_id": f"{job_id}:description:{i}",
                    "job_id": job_id,
                    "field": "description",
                    "text": f"Deskripsi pekerjaan: {ch}",
                    "payload": {**base_payload, "field": "description", "chunk_idx": i}
                })

        # 4) META
        meta_parts = []
        if address:
            meta_parts.append(f"Lokasi: {address}")
        if work_type:
            meta_parts.append(f"Tipe kerja: {work_type}")
        if experience:
            meta_parts.append(f"Pengalaman: {experience}")
        if salary:
            meta_parts.append(f"Gaji: {salary}")
        if posted_at:
            meta_parts.append(f"Diunggah: {posted_at}")

        meta_text = ". ".join(meta_parts).strip()
        if meta_text:
            out_docs.append({
                "point_id": f"{job_id}:meta:0",
                "job_id": job_id,
                "field": "meta",
                "text": meta_text + ".",
                "payload": {**base_payload, "field": "meta", "chunk_idx": 0}
            })

        # 5) EDUCATION
        if education.strip():
            out_docs.append({
                "point_id": f"{job_id}:education:0",
                "job_id": job_id,
                "field": "education",
                "text": f"Pendidikan yang dibutuhkan: {education.strip()}.",
                "payload": {**base_payload, "field": "education", "chunk_idx": 0}
            })

        # 6) BENEFITS
        benefits_text = ", ".join([b.strip() for b in benefits if str(b).strip()])
        if benefits_text:
            out_docs.append({
                "point_id": f"{job_id}:benefits:0",
                "job_id": job_id,
                "field": "benefits",
                "text": f"Benefit yang ditawarkan meliputi: {benefits_text}.",
                "payload": {**base_payload, "field": "benefits", "chunk_idx": 0}
            })

    return out_docs


# =========================
# 3) EMBEDDING DENSE (OpenAI)
# =========================
def embed_texts_openai(
    texts: List[str],
    *,
    api_key: Optional[str] = None,
    model: str = "text-embedding-3-small",
) -> List[List[float]]:
    if not texts:
        return []

    # Use OpenRouter for Embeddings as requested
    # Note: User must ensure the model ID in .env (EMBEDDING_MODEL) is valid on OpenRouter
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    embedding_model = os.getenv("EMBEDDING_MODEL", "qwen/qwen-embedding") 
    
    if not api_key:
         # Fallback or error
         raise ValueError("OPENROUTER_API_KEY for embedding is missing")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )
    
    # OpenRouter embedding interface usually matches OpenAI
    try:
        resp = client.embeddings.create(model=embedding_model, input=texts)
        return [d.embedding for d in resp.data]
    except Exception as e:
        print(f"OpenRouter Embedding Error: {e}")
        return []


# =========================
# 4) SPARSE MANUAL (NO fastembed)
# =========================
def embed_texts_sparse_manual(texts: List[str]) -> List[SparseVector]:
    """
    Buat sparse vector manual untuk semua text.
    """
    return [text_to_sparse_hash_vector(t) for t in texts]


# =========================
# 5) ENSURE HYBRID COLLECTION (dense + sparse)
# =========================
def ensure_hybrid_collection(
    client: QdrantClient,
    *,
    collection_name: str,
    dense_size: int,
    distance: Distance = Distance.COSINE,
    recreate: bool = False,
) -> None:
    existing = {c.name for c in client.get_collections().collections}

    if collection_name in existing:
        if recreate:
            client.recreate_collection(
                collection_name=collection_name,
                vectors_config={"dense": VectorParams(size=dense_size, distance=distance)},
                sparse_vectors_config={"sparse": SparseVectorParams()},
            )
        return

    client.create_collection(
        collection_name=collection_name,
        vectors_config={"dense": VectorParams(size=dense_size, distance=distance)},
        sparse_vectors_config={"sparse": SparseVectorParams()},
    )


# =========================
# 6) UPSERT QDRANT (HYBRID)
# =========================
def upsert_embeddings_to_qdrant(
    data: Union[Dict[str, Any], List[Dict[str, Any]]],
    *,
    collection_name: str,
    qdrant_url: str,
    api_key: Optional[str] = None,
    dense_size: Optional[int] = None,
    distance: Distance = Distance.COSINE,
    batch_size: int = 128,
    recreate_collection: bool = False,
) -> Dict[str, int]:

    items = [data] if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ValueError("data harus dict atau list[dict] dan tidak boleh kosong")

    # Determine dense size if not provided
    if dense_size is None:
        first_vec = items[0].get("dense_vector")
        if not isinstance(first_vec, list) or len(first_vec) == 0:
            raise ValueError("dense_size tidak bisa ditentukan: item pertama tidak punya dense_vector yang valid")
        dense_size = len(first_vec)

    client = QdrantClient(url=qdrant_url, api_key=api_key)

    ensure_hybrid_collection(
        client,
        collection_name=collection_name,
        dense_size=dense_size,
        distance=distance,
        recreate=recreate_collection,
    )

    inserted = 0
    skipped = 0
    batch: List[PointStruct] = []

    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue

        point_id = item.get("point_id")
        dense_vector = item.get("dense_vector")
        sparse_vector = item.get("sparse_vector")
        payload = item.get("payload") or {}
        text = item.get("text")

        if not point_id or not isinstance(point_id, str):
            skipped += 1
            continue

        if not isinstance(dense_vector, list) or len(dense_vector) != dense_size:
            skipped += 1
            continue

        if not isinstance(sparse_vector, SparseVector):
            skipped += 1
            continue

        if not isinstance(payload, dict):
            skipped += 1
            continue

        qdrant_id = str(uuid.uuid5(uuid.NAMESPACE_URL, point_id))

        final_payload = dict(payload)
        final_payload["point_id"] = point_id
        if text is not None:
            final_payload["text"] = text

        batch.append(
            PointStruct(
                id=qdrant_id,
                vector={
                    "dense": dense_vector,
                    "sparse": sparse_vector,
                },
                payload=final_payload,
            )
        )

        if len(batch) >= batch_size:
            client.upsert(collection_name=collection_name, points=batch)
            inserted += len(batch)
            batch = []

    if batch:
        client.upsert(collection_name=collection_name, points=batch)
        inserted += len(batch)

    return {"inserted": inserted, "skipped": skipped}


# =========================
# 7) PIPELINE UTAMA: DB -> Split -> Dense+Sparse -> Qdrant
# =========================
def store_jobs_pipeline(
    payload: Union[Dict[str, Any], List[Dict[str, Any]]],
    *,
    collection_name: str,
    qdrant_url: str,
    qdrant_api_key: Optional[str] = None,
    embedding_model: str = "text-embedding-3-small",
    openai_api_key: Optional[str] = None,
    recreate_collection: bool = False,
) -> Dict[str, Any]:

    inserted_jobs, db_inserted, db_skipped = save_documents_database(payload)

    if not inserted_jobs:
        return {
            "db": {"inserted": db_inserted, "skipped": db_skipped},
            "docs": {"generated": 0},
            "qdrant": {"inserted": 0, "skipped": 0},
        }

    docs = document_splitting_multi(inserted_jobs)
    texts = [d["text"] for d in docs]

    # Dense (OpenAI)
    dense_vectors = embed_texts_openai(
        texts,
        api_key=openai_api_key,
        model=embedding_model,
    )

    # Sparse (manual)
    sparse_vectors = embed_texts_sparse_manual(texts)

    embedded_docs: List[Dict[str, Any]] = []
    for d, dv, sv in zip(docs, dense_vectors, sparse_vectors):
        embedded_docs.append({
            "point_id": d["point_id"],
            "job_id": d["job_id"],
            "payload": d["payload"],
            "dense_vector": dv,
            "sparse_vector": sv,
            "text": d["text"],
        })

    qdrant_res = upsert_embeddings_to_qdrant(
        data=embedded_docs,
        collection_name=collection_name,
        qdrant_url=qdrant_url,
        api_key=qdrant_api_key,
        dense_size=len(dense_vectors[0]) if dense_vectors else None,
        recreate_collection=recreate_collection,
    )

    return {
        "db": {"inserted": db_inserted, "skipped": db_skipped},
        "docs": {"generated": len(docs)},
        "qdrant": qdrant_res,
    }
