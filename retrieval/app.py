import os
from fastapi import APIRouter, HTTPException, Depends
from qdrant_client import QdrantClient, models

from .hybrid import embed_openai, sparse_query_manual
from .db_helpers import qdrant_result_to_full_docs

from database.database import SessionLocal
from schema.retrieval import RetrieveRequest, RetrieveResponse
from auth.utils import get_current_user
from utils.logger import get_logger
from utils.errors import describe_error

router = APIRouter(tags=["Retrieval"])
logger = get_logger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("COLLECTION_NAME", "final_skripsi_collection_bm25")

# How many chunks each retriever (sparse, dense) returns BEFORE fusion.
# Tuned for chunk-level indexing + job-level dedup: ~50 chunks ≈ 8-12 unique jobs.
PREFETCH_LIMIT = int(os.getenv("PREFETCH_LIMIT", "50"))

# How many chunks the fused query returns (before dedup-by-job in db_helpers).
# 50 chunks ≈ 8-12 unique jobs after dedup → cukup headroom untuk MAX_UNIQUE_JOBS=10.
RETRIEVE_LIMIT = int(os.getenv("RETRIEVE_LIMIT", "50"))

# Cap on unique jobs returned to client (post-dedup). LLM re-ranks these to top 5.
MAX_UNIQUE_JOBS = int(os.getenv("MAX_UNIQUE_JOBS", "10"))

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest, _: dict = Depends(get_current_user)):
    try:
        # Sparse first — fast, local. If empty (e.g. punctuation-only query),
        # we'll fall back to dense-only retrieval.
        sparse_vec = sparse_query_manual(req.query)
        has_sparse = bool(sparse_vec.indices)

        dense_vec = embed_openai(req.query)
        if not dense_vec:
            raise ValueError(
                "Embedding menghasilkan vector kosong. "
                "Periksa EMBEDDING_MODEL dan OPENAI_API_KEY di .env."
            )

        prefetch = []
        if has_sparse:
            prefetch.append(
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vec.indices,
                        values=sparse_vec.values,
                    ),
                    using="sparse",
                    limit=PREFETCH_LIMIT,
                )
            )
        else:
            logger.warning(
                "Sparse query kosong (query=%r). Fallback ke dense-only retrieval.",
                req.query,
            )
        prefetch.append(
            models.Prefetch(
                query=dense_vec,
                using="dense",
                limit=PREFETCH_LIMIT,
            )
        )

        qdrant_res = qdrant_client.query_points(
            collection_name=QDRANT_COLLECTION,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=RETRIEVE_LIMIT,
        )

        db = SessionLocal()
        try:
            docs = qdrant_result_to_full_docs(db, qdrant_res)
        finally:
            db.close()

        docs = docs[:MAX_UNIQUE_JOBS]

        return RetrieveResponse(
            query=req.query,
            collection=QDRANT_COLLECTION,
            results=docs,
        )

    except HTTPException:
        raise
    except Exception as e:
        detail = describe_error(e, "Retrieval")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)
