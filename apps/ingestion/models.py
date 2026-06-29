from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from apps.core.base import Base


class Ingestion(Base):
    __tablename__ = "ingestions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    status = Column(String(50), server_default="uploaded", nullable=True)
    file_name = Column(Text, nullable=False)
    file_url = Column(Text, nullable=False)
    json_url = Column(Text, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    failed_at_stage = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("ingestions_user_id_idx", "user_id"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    ingestion_id = Column(UUID(as_uuid=True), ForeignKey("ingestions.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    chunk_index = Column(Integer, nullable=False)
    block_type = Column(String(20), nullable=True)
    page = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=True)

    # "metadata" shadows SQLAlchemy's Base.metadata, so use attribute name "meta"
    meta = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
