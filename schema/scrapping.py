from typing import Optional

from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    query: str = Field(..., example="python developer")
    max_page: int = Field(1, ge=1, le=50)
    # When set, stop after collecting this many job URLs (faster — useful for demos).
    # Leave empty/null to scrape all jobs found across max_page pages.
    max_jobs: Optional[int] = Field(None, ge=1, le=500, example=3)
