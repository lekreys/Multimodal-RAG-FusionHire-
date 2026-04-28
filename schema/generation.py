from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class GenerateRequest(BaseModel):
    query: str
    retrieved_jobs: List[Dict[str, Any]]
    conversation_id: Optional[str] = None

class GenerateResponse(BaseModel):
    answer: str

class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None

class HistoryResponse(BaseModel):
    conversation_id: str
    messages: List[MessageResponse]

class ConversationListItem(BaseModel):
    conversation_id: str
    last_message: str
    last_timestamp: str
    message_count: int

class ConversationListResponse(BaseModel):
    conversations: List[ConversationListItem]

class FeedbackRequest(BaseModel):
    conversation_id: str
    message_index: Optional[int] = None
    rating: str
    comment: Optional[str] = None

class FeedbackResponse(BaseModel):
    message: str
    feedback_id: Optional[str] = None
