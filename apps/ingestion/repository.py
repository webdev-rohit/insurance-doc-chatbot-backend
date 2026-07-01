from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Ingestion, Chunk


class IngestionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **kwargs) -> Ingestion:
        record = Ingestion(**kwargs)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, ingestion_id: UUID) -> Ingestion | None:
        stmt = select(Ingestion).where(Ingestion.id == ingestion_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_latest_ingestion_by_user_id(self, user_id: UUID) -> Ingestion | None:
        stmt = select(Ingestion).where(Ingestion.user_id == user_id).order_by(Ingestion.created_at.desc()).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_all_ingestions_by_user_id(self, user_id: UUID) -> list[Ingestion]:
        stmt = select(Ingestion).where(Ingestion.user_id == user_id).order_by(Ingestion.created_at.desc())
        return self.db.execute(stmt).scalars().all()
    
    def get_all_chunks_by_ingestion_id(self, ingestion_id: UUID) -> list[Chunk]:
        stmt = select(Chunk).where(Chunk.ingestion_id == ingestion_id)
        return self.db.execute(stmt).scalars().all()

    def delete_chunks_by_ingestion_id(self, ingestion_id: UUID) -> None:
        self.db.execute(delete(Chunk).where(Chunk.ingestion_id == ingestion_id))
        self.db.commit()

    def update(self, record: Ingestion, **kwargs) -> Ingestion:
        for key, value in kwargs.items():
            setattr(record, key, value)
        record.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record
