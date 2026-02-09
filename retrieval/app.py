import sys
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient, models

# Import relative jika dijalankan sebagai package
from .hybrid import embed_openai, sparse_query_manual
from .db_helpers import qdrant_result_to_full_docs

# Import dari parent package (asumsi run dari production root)
from database.database import SessionLocal  
from schema.retrieval import RetrieveRequest, RetrieveResponse

router = APIRouter(tags=["Retrieval"])

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("COLLECTION_NAME", "jobsaaa")

PREFETCH_LIMIT = int(os.getenv("PREFETCH_LIMIT", "10"))

if not QDRANT_URL or not QDRANT_API_KEY:
    # Bisa di-warning saja atau raise error saat startup, 
    # di sini kita biarkan, tapi akan error kalau dipanggil jika env belum set
    pass

# Client inisialisasi sebaiknya lazy atau di global
# Kita pasang di global scope modul ini
qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest):
    try:
        # 1) build vectors
        dense_vec = embed_openai(req.query)          # List[float]
        sparse_vec = sparse_query_manual(req.query)  # SparseVector

        # Jika QDRANT belum terinisialisasi dengan benar (misal env kosong)
        if not qdrant_client:
             raise HTTPException(status_code=500, detail="Qdrant client not initialized")

        # 2) hybrid query with RRF fusion (fixed prefetch limit)
        qdrant_res = qdrant_client.query_points(
            collection_name=QDRANT_COLLECTION,
            prefetch=[
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vec.indices,
                        values=sparse_vec.values,
                    ),
                    using="sparse",
                    limit=PREFETCH_LIMIT,
                ),
                models.Prefetch(
                    query=dense_vec,
                    using="dense",
                    limit=PREFETCH_LIMIT,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
        )

        # 3) fetch full docs from Postgres based on job_id
        db = SessionLocal()
        try:
            docs = qdrant_result_to_full_docs(db, qdrant_res)
        finally:
            db.close()

        return RetrieveResponse(
            query=req.query,
            collection=QDRANT_COLLECTION,
            results=docs,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
