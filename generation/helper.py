import os
from typing import List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv
from .prompt import SYSTEM_PROMPT

load_dotenv()

def format_jobs_context(jobs: List[Dict[str, Any]]) -> str:
    """
    Format list of job dicts into a string for LLM context.
    """
    if not jobs:
        return ""

    context_parts = []
    for idx, job in enumerate(jobs, 1):
        # Ambil field penting
        title = job.get("title", "N/A")
        company = job.get("company", "N/A")
        location = job.get("address", "N/A")
        salary = job.get("salary", "N/A")
        skills = job.get("skills", [])
        if isinstance(skills, list):
            skills_str = ", ".join(skills)
        else:
            skills_str = str(skills)
        
        desc = job.get("description", "")[:500] + "..." # Truncate description agar tidak terlalu panjang
        url = job.get("url", "#")
        job_id = job.get("job_id", "")

        part = (
            f"Lowongan #{idx}\n"
            f"ID: {job_id}\n"
            f"Posisi: {title}\n"
            f"Perusahaan: {company}\n"
            f"Lokasi: {location}\n"
            f"Gaji: {salary}\n"
            f"Skills: {skills_str}\n"
            f"URL: {url}\n"
            f"Ringkasan Deskripsi: {desc}\n"
        )
        context_parts.append(part)

    return "\n---\n".join(context_parts)

def generate_answer(query: str, retrieved_jobs: List[Dict[str, Any]]) -> str:
    """
    Generate answer using OpenAI based on query and retrieved jobs.
    """
    # Prioritize OPENROUTER_API_KEY, fallback to OPENAI_API_KEY
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("API Key not found (OPENROUTER_API_KEY or OPENAI_API_KEY)")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    
    # Use User's preferred model or default to Qwen 2.5 72B
    model = os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")

    context_str = format_jobs_context(retrieved_jobs)
    
    # Construct user message with context
    user_content = (
        f"Query User: {query}\n\n"
        f"Daftar Lowongan (Context):\n"
        f"{context_str}\n"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            extra_headers={
                "HTTP-Referer": "http://localhost:8501", 
                "X-Title": "Job Search RAG",
            },
            temperature=0.7, # Higher temp for better format adherence
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error generating answer: {str(e)}"

def generate_answer_stream(query: str, retrieved_jobs: List[Dict[str, Any]], conversation_id: str = None):

    from database.database import SessionLocal
    from database.models import Conversation
    
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("API Key not found (OPENROUTER_API_KEY or OPENAI_API_KEY)")

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    
    model = os.getenv("LLM_MODEL", "qwen/qwen-2.5-72b-instruct")

    context_str = format_jobs_context(retrieved_jobs)
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if conversation_id:
        db = SessionLocal()
        try:
            history = db.query(Conversation)\
                .filter(Conversation.conversation_id == conversation_id)\
                .order_by(Conversation.timestamp.asc())\
                .all()
            
            for msg in history:
                messages.append({"role": msg.role, "content": msg.content})
        finally:
            db.close()
    
    user_content = (
        f"Query User: {query}\n\n"
        f"Daftar Lowongan (Context):\n"
        f"{context_str}\n"
    )
    
    messages.append({"role": "user", "content": user_content})

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            extra_headers={
                "HTTP-Referer": "http://localhost:8501", 
                "X-Title": "Job Search RAG",
            },
            temperature=0.7,  # Higher temp for better format adherence
            stream=True,
        )
        
        assistant_message = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                assistant_message += content
                yield content
        
        if conversation_id:
            db = SessionLocal()
            try:
                # Save CLEAN user query, not the full context
                user_msg = Conversation(
                    conversation_id=conversation_id,
                    role="user",
                    content=query  # Save original query only, not user_content with context
                )
                db.add(user_msg)
                
                # Save assistant message with retrieved_jobs in extra_data
                assistant_msg = Conversation(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_message,
                    extra_data={"retrieved_jobs": retrieved_jobs}  # Use extra_data
                )
                db.add(assistant_msg)
                
                db.commit()
            finally:
                db.close()
                
    except Exception as e:
        yield f"Error generating answer: {str(e)}"
