from fastapi import APIRouter
import sys
import os

from .helper import scrape_loker_jobs
from .glints_helper import scrape_glints_jobs
from .jobstreet_helper import scrape_jobstreet_jobs
from schema.scrapping import ScrapeRequest

router = APIRouter(tags=["Scrapping"])

@router.get("/scrapping")
def read_root():
    return {"message": "Welcome to the scrapping API"}

@router.post("/scrapping/loker-id")
async def scrapping_loker(request : ScrapeRequest):
    data = scrape_loker_jobs(request.query, request.max_page)
    data_json = {
        "query" : request.query,
        "max_page" : request.max_page,
        "data" : data
    }
    return data_json

@router.post("/scrapping/glints")
async def scrapping_glints(request : ScrapeRequest):
    data = scrape_glints_jobs(keyword=request.query, end_page=request.max_page)
    data_json = {
        "query" : request.query,
        "max_page" : request.max_page,
        "data" : data
    }
    return data_json

@router.post("/scrapping/jobstreet")
async def scrapping_jobstreet(request : ScrapeRequest):
    data = scrape_jobstreet_jobs(request.query, request.max_page)
    data_json = {
        "query" : request.query,
        "max_page" : request.max_page,
        "data" : data
    }
    return data_json