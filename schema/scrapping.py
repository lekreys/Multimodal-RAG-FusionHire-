from pydantic import BaseModel, Field


class ScrapeRequest(BaseModel):
    query: str = Field(..., example="python developer")
    max_page: int = Field(1, ge=1, le=50)