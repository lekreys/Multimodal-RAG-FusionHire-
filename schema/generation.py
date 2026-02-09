from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class GenerateRequest(BaseModel):
    query: str
    retrieved_jobs: List[Dict[str, Any]]  # List of job dicts from retrieval
    conversation_id: Optional[str] = None  # For chat history

class GenerateResponse(BaseModel):
    answer: str

class MessageResponse(BaseModel):
    role: str
    content: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None  # Retrieved jobs for assistant

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
