from sqlalchemy import Column, String, Text, JSON, DateTime, Integer
from sqlalchemy.sql import func
from database.database import Base

class Job(Base):
    __tablename__ = "jobs_docs"

    job_id = Column(String, primary_key=True, index=True)

    url = Column(Text, unique=True, index=True, nullable=False)

    title = Column(Text)
    company = Column(Text)
    logo = Column(Text)

    salary = Column(Text)
    posted_at = Column(Text)       # "3 hari yang lalu" masih string
    work_type = Column(Text)
    experience = Column(Text)
    education = Column(Text)

    requirements_tags = Column(JSON)   # list string
    skills = Column(JSON)              # list string
    benefits = Column(JSON)            # list string

    description = Column(Text)
    address = Column(Text)

    source = Column(String, index=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(255), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    extra_data = Column(JSON, nullable=True)  # Store retrieved_jobs (renamed from metadata)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)
