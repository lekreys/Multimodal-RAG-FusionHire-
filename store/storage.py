import os
import uuid
from supabase import create_client, Client
from fastapi import UploadFile
from utils.logger import get_logger

logger = get_logger(__name__)

def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)

async def upload_image_to_supabase(file: UploadFile, bucket_name: str = "job-posters") -> str:
    """
    Uploads a file to Supabase Storage and returns the public URL.
    """
    supabase = get_supabase_client()
    
    file_ext = file.filename.split(".")[-1]
    file_name = f"{uuid.uuid4()}.{file_ext}"
    
    content = await file.read()
    
    await file.seek(0)
    
    try:
        supabase.storage.from_(bucket_name).upload(
            path=file_name,
            file=content,
            file_options={"content-type": file.content_type}
        )
        
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
        return public_url
        
    except Exception as e:
        logger.error("Supabase upload error: %s", e)
        raise e
