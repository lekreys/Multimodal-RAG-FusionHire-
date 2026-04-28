import sys
import os
from fastapi import APIRouter, HTTPException, Depends

from schema.generation import (
    GenerateRequest,
    GenerateResponse,
    HistoryResponse,
    MessageResponse,
    ConversationListResponse,
    ConversationListItem,
)
from .helper import generate_answer, generate_general_answer
from .intent import detect_intent
from database.database import SessionLocal
from database.models import Conversation
from auth.utils import get_current_user
from utils.logger import get_logger
from utils.errors import describe_error
from pydantic import BaseModel as _BaseModel

router = APIRouter(tags=["Generation"])
logger = get_logger(__name__)


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, current_user: dict = Depends(get_current_user)):
    try:
        answer = generate_answer(
            request.query,
            request.retrieved_jobs,
            request.conversation_id,
            user_id=current_user["user_id"],
        )
        return GenerateResponse(answer=answer)
    except Exception as e:
        detail = describe_error(e, "Generate")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)


@router.post("/generate/general")
async def generate_general(request: GenerateRequest, current_user: dict = Depends(get_current_user)):
    try:
        answer = generate_general_answer(
            request.query,
            request.conversation_id,
            user_id=current_user["user_id"],
        )
        return {"answer": answer}
    except Exception as e:
        detail = describe_error(e, "Generate/General")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)


@router.get("/history/{conversation_id}", response_model=HistoryResponse)
async def get_history(conversation_id: str, current_user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        messages = (
            db.query(Conversation)
            .filter(
                Conversation.conversation_id == conversation_id,
                Conversation.user_id == current_user["user_id"],
            )
            .order_by(Conversation.timestamp.asc())
            .all()
        )

        if not messages:
            raise HTTPException(status_code=404, detail="Conversation tidak ditemukan.")

        message_list = [
            MessageResponse(
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp.isoformat(),
                metadata=msg.extra_data,
            )
            for msg in messages
        ]

        return HistoryResponse(conversation_id=conversation_id, messages=message_list)
    except HTTPException:
        raise
    except Exception as e:
        detail = describe_error(e, "History")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)
    finally:
        db.close()


@router.get("/conversations", response_model=ConversationListResponse)
async def get_all_conversations(current_user: dict = Depends(get_current_user)):
    from sqlalchemy import func, desc

    db = SessionLocal()
    try:
        conversations_data = (
            db.query(
                Conversation.conversation_id,
                func.max(Conversation.timestamp).label("last_timestamp"),
                func.count(Conversation.id).label("message_count"),
            )
            .filter(Conversation.user_id == current_user["user_id"])
            .group_by(Conversation.conversation_id)
            .order_by(desc("last_timestamp"))
            .all()
        )

        conversation_list = []
        for conv_id, last_time, msg_count in conversations_data:
            last_msg = (
                db.query(Conversation)
                .filter(
                    Conversation.conversation_id == conv_id,
                    Conversation.user_id == current_user["user_id"],
                )
                .order_by(Conversation.timestamp.desc())
                .first()
            )

            preview = (
                last_msg.content[:100] + "..."
                if len(last_msg.content) > 100
                else last_msg.content
            )

            conversation_list.append(
                ConversationListItem(
                    conversation_id=conv_id,
                    last_message=preview,
                    last_timestamp=last_time.isoformat(),
                    message_count=msg_count,
                )
            )

        return ConversationListResponse(conversations=conversation_list)
    except Exception as e:
        detail = describe_error(e, "Conversations")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)
    finally:
        db.close()


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str, current_user: dict = Depends(get_current_user)
):
    db = SessionLocal()
    try:
        messages = (
            db.query(Conversation)
            .filter(
                Conversation.conversation_id == conversation_id,
                Conversation.user_id == current_user["user_id"],
            )
            .all()
        )

        if not messages:
            raise HTTPException(status_code=404, detail="Conversation tidak ditemukan.")

        db.query(Conversation).filter(
            Conversation.conversation_id == conversation_id,
            Conversation.user_id == current_user["user_id"],
        ).delete()

        db.commit()

        return {"message": "Conversation berhasil dihapus.", "conversation_id": conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        detail = describe_error(e, "Delete Conversation")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)
    finally:
        db.close()


class IntentRequest(_BaseModel):
    query: str


@router.post("/detect-intent")
async def detect_intent_endpoint(
    request: IntentRequest, _: dict = Depends(get_current_user)
):
    try:
        result = detect_intent(request.query)
        return result
    except Exception as e:
        detail = describe_error(e, "Intent Detection")
        logger.error(detail)
        raise HTTPException(status_code=500, detail=detail)
