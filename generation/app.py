import sys
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from schema.generation import (
    GenerateRequest, 
    GenerateResponse, 
    HistoryResponse, 
    MessageResponse,
    ConversationListResponse,
    ConversationListItem
)
from .helper import generate_answer, generate_answer_stream
from database.database import SessionLocal
from database.models import Conversation

router = APIRouter(tags=["Generation"])

@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    try:
        answer = generate_answer(request.query, request.retrieved_jobs)
        return GenerateResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate/stream")
async def generate_stream(request: GenerateRequest):
    """
    Stream LLM response chunks in real-time using Server-Sent Events (SSE).
    Supports chat history via conversation_id.
    """
    try:
        def event_generator():
            for chunk in generate_answer_stream(
                request.query, 
                request.retrieved_jobs,
                request.conversation_id  # Pass conversation_id for history
            ):
                # Send chunk in SSE format
                yield f"data: {chunk}\n\n"
            # Send completion signal
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{conversation_id}", response_model=HistoryResponse)
async def get_history(conversation_id: str):
    """
    Get conversation history by conversation_id.
    Returns all messages in chronological order.
    """
    db = SessionLocal()
    try:
        messages = db.query(Conversation)\
            .filter(Conversation.conversation_id == conversation_id)\
            .order_by(Conversation.timestamp.asc())\
            .all()
        
        if not messages:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        message_list = [
            MessageResponse(
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp.isoformat(),
                metadata=msg.extra_data  # Return extra_data as metadata in API
            )
            for msg in messages
        ]
        
        return HistoryResponse(
            conversation_id=conversation_id,
            messages=message_list
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@router.get("/conversations", response_model=ConversationListResponse)
async def get_all_conversations():
    """
    Get list of all conversations with preview.
    Returns conversations sorted by most recent first.
    """
    from sqlalchemy import func, desc
    
    db = SessionLocal()
    try:
        conversations_data = db.query(
            Conversation.conversation_id,
            func.max(Conversation.timestamp).label('last_timestamp'),
            func.count(Conversation.id).label('message_count')
        ).group_by(Conversation.conversation_id)\
         .order_by(desc('last_timestamp'))\
         .all()
        
        conversation_list = []
        for conv_id, last_time, msg_count in conversations_data:
            # Get the last message for preview
            last_msg = db.query(Conversation)\
                .filter(Conversation.conversation_id == conv_id)\
                .order_by(Conversation.timestamp.desc())\
                .first()
            
            # Truncate message for preview (first 100 chars)
            preview = last_msg.content[:100] + "..." if len(last_msg.content) > 100 else last_msg.content
            
            conversation_list.append(
                ConversationListItem(
                    conversation_id=conv_id,
                    last_message=preview,
                    last_timestamp=last_time.isoformat(),
                    message_count=msg_count
                )
            )
        
        return ConversationListResponse(conversations=conversation_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """
    Delete a conversation and all its messages.
    """
    db = SessionLocal()
    try:
        # Check if conversation exists
        messages = db.query(Conversation)\
            .filter(Conversation.conversation_id == conversation_id)\
            .all()
        
        if not messages:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Delete all messages in the conversation
        db.query(Conversation)\
            .filter(Conversation.conversation_id == conversation_id)\
            .delete()
        
        db.commit()
        
        return {"message": "Conversation deleted successfully", "conversation_id": conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
