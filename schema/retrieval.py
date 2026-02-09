from pydantic import BaseModel, Field
from typing import Optional, List





class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User query")


class JobDocOut(BaseModel):
    job_id: str
    score: float

    url: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    logo: Optional[str] = None

    salary: Optional[str] = None
    posted_at: Optional[str] = None
    work_type: Optional[str] = None
    experience: Optional[str] = None
    education: Optional[str] = None

    requirements_tags: List[str] = []
    skills: List[str] = []
    benefits: List[str] = []

    description: Optional[str] = None
    address: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None


class RetrieveResponse(BaseModel):
    query: str
    collection: str
    results: List[JobDocOut]
