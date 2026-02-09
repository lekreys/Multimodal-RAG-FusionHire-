import base64
import os
import json
import uuid
from openai import OpenAI
from typing import Dict, Any

def extract_job_from_image(image_bytes: bytes) -> Dict[str, Any]:
    # Prioritize OPENROUTER_API_KEY, fallback to OPENAI_API_KEY (if user reused it)
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY or OPENAI_API_KEY is not set")
    
    # Configure for OpenRouter
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )
    base64_image = base64.b64encode(image_bytes).decode('utf-8')

    prompt = """
    Analyze this job poster image and extract the following details in JSON format:
    - title (Job Title)
    - company (Company Name)
    - location (Location/Address)
    - salary (Salary string, e.g. "Rp 10.000.000 - Rp 15.000.000")
    - work_type (Full-time, Contract, Remote, etc.)
    - experience (Experience level string)
    - education (Education level string)
    - skills (List of strings)
    - description (Summary of the job description, convert image text to summary)
    - requirements_tags (List of strings for requirements)
    - benefits (List of strings)

    If a field is not found, use null or empty string/list as appropriate.
    Response must be a valid JSON object.
    """

    try:
        # Use Qwen-VL-Plus (or Max) via OpenRouter
        response = client.chat.completions.create(
            model="qwen/qwen-vl-plus", 
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            response_format={ "type": "json_object" },
            extra_headers={
                "HTTP-Referer": "http://localhost:8501", 
                "X-Title": "Job Search RAG",
            }
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        
        # Normalize to internal schema
        return {
            "job_id": f"img-{uuid.uuid4().hex[:8]}", 
            "url": f"https://image-upload.local/{uuid.uuid4().hex[:12]}", # Will be overwritten by app.py
            "title": data.get("title") or "Unknown Position",
            "company": data.get("company") or "Unknown Company",
            "logo": "",
            "salary": data.get("salary") or "",
            "posted_at": "Just now",
            "work_type": data.get("work_type") or "",
            "experience": data.get("experience") or "",
            "education": data.get("education") or "",
            "requirements_tags": data.get("requirements_tags") or [],
            "skills": data.get("skills") or [],
            "benefits": data.get("benefits") or [],
            "description": data.get("description") or "No description extracted from image.",
            "address": data.get("location") or "",
            "source": "Image Upload"
        }
    except Exception as e:
        print(f"Error parsing vision response: {e}")
        return {}
