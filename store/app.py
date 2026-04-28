from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from auth.utils import require_admin
from .helper import store_jobs_pipeline
from .vision import extract_job_from_image, extract_job_from_image_debug, NotJobPostingError
from .storage import upload_image_to_supabase
from utils.logger import get_logger
from utils.errors import describe_error
import os
from dotenv import load_dotenv

load_dotenv()

logger = get_logger(__name__)
router = APIRouter(tags=["Store"])


@router.post("/store")
def store(payload: dict, _: dict = Depends(require_admin)):
    return store_jobs_pipeline(
        payload,
        collection_name=os.getenv("COLLECTION_NAME"),
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        embedding_model=os.getenv("EMBEDDING_MODEL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )


@router.post("/store/extract-image")
async def extract_image_only(file: UploadFile = File(...)):
    """Ekstrak data lowongan dari gambar TANPA menyimpan ke DB / Supabase. Untuk eksperimen."""
    ct = file.content_type or ""
    if not ct.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"File must be an image, got '{ct}'")
    try:
        content = await file.read()
        result = extract_job_from_image_debug(content)
        return {
            "status": "ok",
            "is_job_posting": result["is_job_posting"],
            "filename": file.filename,
            "api_used": result["api_used"],
            "raw_model_response": result["raw_model_response"],
            "parse_error": result.get("error", ""),
            "data": result["job_data"],
        }
    except Exception as e:
        detail = describe_error(e, "Extract Image")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)


@router.post("/store/upload-image")
async def upload_image(file: UploadFile = File(...), _: dict = Depends(require_admin)):
    logger.info("Upload request | filename=%s content_type=%s", file.filename, file.content_type)

    if not file.content_type.startswith("image/"):
        logger.warning("Rejected upload: invalid content type '%s'", file.content_type)
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        logger.debug("Reading file content...")
        content = await file.read()
        logger.info("Read %d bytes", len(content))
        await file.seek(0)

        bucket_name = os.getenv("SUPABASE_BUCKET", "images")
        logger.info("Uploading to Supabase bucket: %s", bucket_name)
        try:
            public_url = await upload_image_to_supabase(file, bucket_name)
            logger.info("Supabase upload success | url=%s", public_url)
        except Exception as e:
            logger.error("Supabase upload failed: %s", e)
            raise HTTPException(status_code=500, detail=f"Supabase upload failed: {str(e)}")

        logger.info("Extracting job details with Vision...")
        try:
            job_data = extract_job_from_image(content)
        except NotJobPostingError:
            raise HTTPException(status_code=400, detail="Ini bukan file lowongan kerja.")

        if not job_data:
            logger.error("Vision extraction returned empty result")
            raise HTTPException(status_code=500, detail="Gagal mengekstrak data dari gambar.")

        logger.info("Vision extraction success")
        job_data["url"] = public_url

        payload = {"data": [job_data]}

        logger.info("Storing to pipeline...")
        return store_jobs_pipeline(
            payload,
            collection_name=os.getenv("COLLECTION_NAME"),
            qdrant_url=os.getenv("QDRANT_URL"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY"),
            embedding_model=os.getenv("EMBEDDING_MODEL"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
    except HTTPException:
        raise
    except Exception as e:
        detail = describe_error(e, "Upload Image")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)
