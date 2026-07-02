from sqlalchemy import Column, String, Text, Integer, Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from apps.core.base import Base


class QueryContext(Base):
    __tablename__ = "query_context"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    query_id = Column(UUID(as_uuid=True), ForeignKey("queries.id"), nullable=True)
    ingestion_id = Column(UUID(as_uuid=True), ForeignKey("ingestions.id"), nullable=True)
    chunk_id = Column(Text, nullable=True)
    chunk_text = Column(Text, nullable=True)
    score = Column(Float, nullable=True)

    __table_args__ = (
        Index("query_context_query_id_idx", "query_id"),
    )


class QueryUsage(Base):
    __tablename__ = "query_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    query_id = Column(UUID(as_uuid=True), ForeignKey("queries.id"), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    model = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("query_usage_query_id_idx", "query_id"),
    )
