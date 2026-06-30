from uuid import UUID
from pydantic import BaseModel
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
    json_url: Optional[str] = None
    status: IngestionStatus
    chunk_count: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class IngestionStatusResponse(BaseModel):
    id: UUID
    status: IngestionStatus
    error_message: Optional[str] = None
