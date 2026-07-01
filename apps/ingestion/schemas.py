from uuid import UUID
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
from enum import Enum


class IngestionStatus(str, Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    INDEXING = "indexing"
    INDEXED = "indexed"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionResponse(BaseModel):
    id: UUID
    file_url: str
    json_url: str = ""
    status: IngestionStatus
    chunk_count: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    # validator to coerce None to empty string for json_url
    @field_validator("json_url", mode="before")
    @classmethod
    def coerce_none_to_empty(cls, v):
        return v if v is not None else ""

class IngestionStatusResponse(BaseModel):
    id: UUID
    status: IngestionStatus
    error_message: Optional[str] = None