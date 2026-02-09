from fastapi import APIRouter, UploadFile, File, HTTPException
# Gunakan relative import dengan titik (.) agar bisa dijalankan dari main app
from .helper import store_jobs_pipeline
from .vision import extract_job_from_image
from .storage import upload_image_to_supabase
import os
from dotenv import load_dotenv

load_dotenv()

# Ganti FastAPI() dengan APIRouter()
router = APIRouter(tags=["Store"])

@router.post("/store")
def store(payload: dict):
    return store_jobs_pipeline(
        payload,
        collection_name=os.getenv("COLLECTION_NAME"),
        qdrant_url=os.getenv("QDRANT_URL"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        embedding_model=os.getenv("EMBEDDING_MODEL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )

@router.post("/store/upload-image")
async def upload_image(file: UploadFile = File(...)):
    print(f"DEBUG: Received upload request. Filename: {file.filename}, Content-Type: {file.content_type}")
    if not file.content_type.startswith("image/"):
        print("DEBUG: Invalid content type")
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        # 1. Read content for Vision API
        print("DEBUG: Reading file content...")
        content = await file.read()
        print(f"DEBUG: Read {len(content)} bytes")
        await file.seek(0) # Reset cursor for Supabase upload
        
        # 2. Upload to Supabase to get real URL
        # Assumption: Bucket "job-posters" exists or env var SUPABASE_BUCKET is used
        bucket_name = os.getenv("SUPABASE_BUCKET", "images")
        print(f"DEBUG: Uploading to Supabase bucket: {bucket_name}")
        try:
            public_url = await upload_image_to_supabase(file, bucket_name)
            print(f"DEBUG: Upload success. URL: {public_url}")
        except Exception as e:
            print(f"DEBUG: Supabase upload failed: {e}")
            # For now let's raise error as user requested Supabase
            raise HTTPException(status_code=500, detail=f"Supabase upload failed: {str(e)}")

        # 3. Extract details using Vision
        print("DEBUG: Extracting job details with Vision...")
        job_data = extract_job_from_image(content)
        
        if not job_data:
            print("DEBUG: Vision extraction returned empty")
            raise HTTPException(status_code=500, detail="Failed to extract job details from image")
        
        print("DEBUG: Vision extraction success")
        # 4. Inject Real URL
        job_data["url"] = public_url
        
        # Wrap in expected list structure for pipeline
        payload = {"data": [job_data]}
        
        print("DEBUG: Storing to pipeline...")
        return store_jobs_pipeline(
            payload,
            collection_name=os.getenv("COLLECTION_NAME"),
            qdrant_url=os.getenv("QDRANT_URL"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY"),
            embedding_model=os.getenv("EMBEDDING_MODEL"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )
    except Exception as e:
        print(f"DEBUG: Exception in endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
