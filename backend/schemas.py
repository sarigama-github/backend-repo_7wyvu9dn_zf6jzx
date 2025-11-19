from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime

# Collections: activity, finance, file

class Activity(BaseModel):
    date: date = Field(...)
    name: str = Field(..., max_length=200)
    category: str = Field(..., regex=r"^(administration|academics|finance|social|community service|documentation)$")
    duration_hours: float = Field(..., ge=0)
    output: Optional[str] = None
    notes: Optional[str] = None
    file_ids: Optional[List[str]] = None  # references to File documents

class Finance(BaseModel):
    date: date = Field(...)
    category: str = Field(..., max_length=100)
    income: float = Field(0, ge=0)
    expense: float = Field(0, ge=0)
    notes: Optional[str] = None

class File(BaseModel):
    filename: str
    content_type: str
    url: str  # stored public/static URL
    size: int

# Response models (with id and timestamps)
class DocumentMeta(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime

class ActivityOut(Activity, DocumentMeta):
    pass

class FinanceOut(Finance, DocumentMeta):
    pass

class FileOut(File, DocumentMeta):
    pass
