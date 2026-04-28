import sys
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
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
QDRANT_COLLECTION = os.getenv("COLLECTION_NAME", "jobsaaa")
PREFETCH_LIMIT = int(os.getenv("PREFETCH_LIMIT", "10"))

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(req: RetrieveRequest, _: dict = Depends(get_current_user)):
    try:
        dense_vec = embed_openai(req.query)
        if not dense_vec:
            raise ValueError(
                "Embedding menghasilkan vector kosong. "
                "Periksa EMBEDDING_MODEL dan OPENAI_API_KEY di .env."
            )

        sparse_vec = sparse_query_manual(req.query)

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

    except HTTPException:
        raise
    except Exception as e:
        detail = describe_error(e, "Retrieval")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)
