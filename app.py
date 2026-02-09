from fastapi import FastAPI
from dotenv import load_dotenv
import uvicorn
import os

# Import router dari module masing-masing
from scrapping.app import router as scrapping_router
from store.app import router as store_router
from retrieval.app import router as retrieval_router
from generation.app import router as generation_router

from fastapi.middleware.cors import CORSMiddleware

# Load env variables
load_dotenv()

app = FastAPI(
    title="Job Search RAG API",
    description="Unified API for Job Scrapping, Storage, Retrieval, and Generation",
    version="1.0.0"
)

# Add CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
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

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
