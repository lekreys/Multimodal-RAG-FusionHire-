import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from .prompt import SYSTEM_PROMPT
from .general_prompt import GENERAL_SYSTEM_PROMPT
from utils.client import (
    is_local, api_source, get_llm_model,
    call_local_generate,
    get_openrouter_client,
)
from utils.logger import get_logger
from utils.errors import describe_error

load_dotenv()

logger = get_logger(__name__)


def format_jobs_context(jobs: List[Dict[str, Any]]) -> str:
    if not jobs:
        return ""

    context_parts = []
    for idx, job in enumerate(jobs, 1):
        title = job.get("title", "N/A")
        company = job.get("company", "N/A")
        location = job.get("address", "N/A")
        salary = job.get("salary", "N/A")
        skills = job.get("skills", [])
        if isinstance(skills, list):
            skills_str = ", ".join(skills)
        else:
            skills_str = str(skills)

        desc = (job.get("description") or "")[:500] + "..."
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


def generate_answer(
    query: str,
    retrieved_jobs: List[Dict[str, Any]],
    conversation_id: str = None,
    user_id: Optional[int] = None,
) -> str:
    from database.database import SessionLocal
    from database.models import Conversation

    context_str = format_jobs_context(retrieved_jobs)
    logger.info("generate_answer | source=%s model=%s", api_source(), get_llm_model())

    # ── Local Colab API (dengan fallback ke OpenRouter jika gagal) ──────────
    if is_local():
        try:
            answer = call_local_generate(
                query=query,
                context=context_str,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.7,
                max_new_tokens=1024,
            )
            if conversation_id:
                _save_conversation(conversation_id, query, answer, retrieved_jobs, user_id)
            return answer
        except Exception as e:
            err_msg = describe_error(e, "Local API")
            logger.warning("%s — fallback ke OpenRouter...", err_msg)

    # ── OpenRouter ────────────────────────────────────────────
    client = get_openrouter_client()
    model = os.getenv("LLM_MODEL", "qwen/qwen3-vl-30b-a3b-instruct")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if conversation_id:
        db = SessionLocal()
        try:
            q = db.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            )
            if user_id is not None:
                q = q.filter(Conversation.user_id == user_id)
            history = q.order_by(Conversation.timestamp.asc()).all()
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
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            extra_headers={
                "HTTP-Referer": "http://localhost:8501",
                "X-Title": "Job Search RAG",
            },
            temperature=0.7,
        )
        assistant_message = response.choices[0].message.content

        if conversation_id:
            _save_conversation(conversation_id, query, assistant_message, retrieved_jobs, user_id)

        return assistant_message
    except Exception as e:
        err_msg = describe_error(e, "OpenRouter")
        logger.error(err_msg)
        raise RuntimeError(err_msg) from e


def generate_general_answer(
    query: str,
    conversation_id: str = None,
    user_id: Optional[int] = None,
) -> str:
    from database.database import SessionLocal
    from database.models import Conversation

    logger.info("generate_general_answer | source=%s model=%s", api_source(), get_llm_model())

    # ── Local Colab API (dengan fallback ke OpenRouter jika gagal) ──────────
    if is_local():
        try:
            answer = call_local_generate(
                query=query,
                context="",
                system_prompt=GENERAL_SYSTEM_PROMPT,
                temperature=0.7,
                max_new_tokens=1024,
            )
            if conversation_id:
                _save_conversation(conversation_id, query, answer, None, user_id)
            return answer
        except Exception as e:
            err_msg = describe_error(e, "Local API")
            logger.warning("%s — fallback ke OpenRouter...", err_msg)

    # ── OpenRouter ────────────────────────────────────────────
    client = get_openrouter_client()
    model = os.getenv("LLM_MODEL", "qwen/qwen3-vl-30b-a3b-instruct")

    llm_messages = [{"role": "system", "content": GENERAL_SYSTEM_PROMPT}]

    if conversation_id:
        db = SessionLocal()
        try:
            q = db.query(Conversation).filter(
                Conversation.conversation_id == conversation_id
            )
            if user_id is not None:
                q = q.filter(Conversation.user_id == user_id)
            history = q.order_by(Conversation.timestamp.asc()).limit(20).all()
            for msg in history:
                llm_messages.append({"role": msg.role, "content": msg.content})
        finally:
            db.close()

    llm_messages.append({"role": "user", "content": query})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=llm_messages,
            extra_headers={
                "HTTP-Referer": "http://localhost:8501",
                "X-Title": "Job Search RAG",
            },
            temperature=0.7,
        )
        assistant_message = response.choices[0].message.content

        if conversation_id:
            _save_conversation(conversation_id, query, assistant_message, None, user_id)

        return assistant_message
    except Exception as e:
        err_msg = describe_error(e, "OpenRouter")
        logger.error(err_msg)
        raise RuntimeError(err_msg) from e


def _save_conversation(
    conversation_id: str,
    query: str,
    answer: str,
    retrieved_jobs: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[int] = None,
):
    from database.database import SessionLocal
    from database.models import Conversation

    db = SessionLocal()
    try:
        db.add(Conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=query,
        ))
        extra = {"retrieved_jobs": retrieved_jobs} if retrieved_jobs else {}
        db.add(Conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=answer,
            extra_data=extra if extra else None,
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to save conversation %s: %s", conversation_id,
                     describe_error(e, "Database"))
    finally:
        db.close()
