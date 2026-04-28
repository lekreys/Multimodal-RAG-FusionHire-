from sqlalchemy import Column, String, Text, JSON, DateTime, Integer, Boolean, ForeignKey
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
    posted_at = Column(Text)
    work_type = Column(Text)
    experience = Column(Text)
    education = Column(Text)

    requirements_tags = Column(JSON)
    skills = Column(JSON)
    benefits = Column(JSON)

    description = Column(Text)
    address = Column(Text)

    source = Column(String, index=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class ITJob(Base):
    __tablename__ = "it_jobs"

    job_id = Column(String, primary_key=True, index=True)

    url = Column(Text, unique=True, index=True, nullable=False)

    title = Column(Text)
    company = Column(Text)
    logo = Column(Text)

    salary = Column(Text)
    posted_at = Column(Text)
    work_type = Column(Text)
    experience = Column(Text)
    education = Column(Text)

    requirements_tags = Column(JSON)
    skills = Column(JSON)
    benefits = Column(JSON)

    description = Column(Text)
    address = Column(Text)

    source = Column(String, index=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(255), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    extra_data = Column(JSON, nullable=True)
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)


class DataSkripsi(Base):
    __tablename__ = "data_skripsi"

    job_id = Column(String, primary_key=True, index=True)

    url = Column(Text, unique=True, index=True, nullable=False)

    title = Column(Text)
    company = Column(Text)
    logo = Column(Text)

    salary = Column(Text)
    posted_at = Column(Text)
    work_type = Column(Text)
    experience = Column(Text)
    education = Column(Text)

    requirements_tags = Column(JSON)
    skills = Column(JSON)
    benefits = Column(JSON)

    description = Column(Text)
    address = Column(Text)

    source = Column(String, index=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
