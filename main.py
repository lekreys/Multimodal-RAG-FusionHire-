from fastapi import FastAPI
from dotenv import load_dotenv
import os

load_dotenv()

from utils.logger import setup_root_logger
setup_root_logger()

from scrapping.app import router as scrapping_router
from store.app import router as store_router
from retrieval.app import router as retrieval_router
from generation.app import router as generation_router
from auth.app import router as auth_router

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Job Search RAG API",
    description="Unified API for Job Scrapping, Storage, Retrieval, and Generation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(scrapping_router)
app.include_router(store_router)
app.include_router(retrieval_router)
app.include_router(generation_router)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Job Search RAG API",
        "docs": "/docs"
    }
