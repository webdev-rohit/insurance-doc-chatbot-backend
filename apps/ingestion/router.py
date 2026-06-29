from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .schemas import IngestionResponse
from .services import IngestionService, run_ingestion_pipeline
from apps.core.database import get_db
from apps.core.global_utils import get_current_user


router = APIRouter(prefix="/ingestion", tags=["Ingestion Process"])


@router.post("", response_model=IngestionResponse, status_code=202)
async def ingest_data(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Read bytes before the response is sent — the request body is gone after that
    file_bytes = await file.read()

    record, user_email = IngestionService(db).create_ingestion_record(file.filename, user_id)

    background_tasks.add_task(
        run_ingestion_pipeline,
        file_bytes=file_bytes,
        filename=file.filename,
        user_id=user_id,
        user_email=user_email,
        ingestion_id=record.id,
    )

    return IngestionResponse(
        id=record.id,
        file_url=record.file_url,
        json_url=record.json_url,
        status=record.status,
        chunk_count=record.chunk_count,
        created_at=record.created_at,
    )
