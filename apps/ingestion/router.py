from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .schemas import IngestionResponse, IngestionStatusResponse, IngestionStatus
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
    try:
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
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/status", response_model=IngestionStatusResponse)
async def get_ingestion_status(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
    ingestion_id: str|None = Query(None, description="The ID of the ingestion record to check the status of")
):
    try:
        if not ingestion_id:
            record = IngestionService(db).get_latest_ingestion_record(user_id)
        else:
            record = IngestionService(db).get_ingestion_record_by_id(ingestion_id, user_id)

        if not record:
            raise HTTPException(status_code=404, detail="No ingestion record found for the user")

        return IngestionStatusResponse(
            id=record.id,
            status=record.status,
            error_message=record.error_message,
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/show", response_model=list[IngestionResponse])
async def show_ingestion_record(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
    ingestion_id: str|None = Query(None, description="The ID of the ingestion record to check the status of")
):
    try:
        if not ingestion_id:
            records = IngestionService(db).fetch_all_ingestion_records(user_id)
            if not records:
                raise HTTPException(status_code=404, detail="No ingestion records found for the user")
            return [
                    IngestionResponse(
                        id=r.id,
                        file_url=r.file_url,
                        json_url=r.json_url,
                        status=r.status,
                        chunk_count=r.chunk_count,
                        created_at=r.created_at,
                    )
                    for r in records
                ]

        record = IngestionService(db).get_ingestion_record_by_id(ingestion_id, user_id)
        if not record:
            raise HTTPException(status_code=404, detail="No ingestion record found for the user")
        return [
                IngestionResponse(
                    id=record.id,
                    file_url=record.file_url,
                    json_url=record.json_url,
                    status=record.status,
                    chunk_count=record.chunk_count,
                    created_at=record.created_at,
                )
            ]
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/download")
async def download_ingestion(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
    ingestion_id: str|None = Query(None, description="The ID of the ingestion record to download")
):
    try:
        if not ingestion_id:
            record = IngestionService(db).get_latest_ingestion_record(user_id)
        else:
            record = IngestionService(db).get_ingestion_record_by_id(ingestion_id, user_id)

        if not record:
            raise HTTPException(status_code=404, detail="No ingestion record found for the user")

        if record.status != IngestionStatus.COMPLETED:
            raise HTTPException(
                status_code=400,
                detail=f"Ingestion is not completed (current status: {record.status})"
            )

        zip_buffer = IngestionService(db).download_ingestion_files(record.id)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="ingestion.zip"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/delete")
async def delete_ingestion(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user),
    ingestion_id: str|None = Query(None, description="The ID of the ingestion record to delete")
):
    try:
        if not ingestion_id:
            IngestionService(db).delete_all_ingestion_records(user_id)
            return {"message": "All ingestion records deleted successfully"}

        record = IngestionService(db).get_ingestion_record_by_id(ingestion_id, user_id)
        if not record:
            raise HTTPException(status_code=404, detail="No ingestion record found for the user")
        IngestionService(db).delete_ingestion_record_by_id(record.id)
        return {"message": f"Ingestion record {record.id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))