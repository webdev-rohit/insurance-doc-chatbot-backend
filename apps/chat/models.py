from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from apps.core.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    title = Column(Text, server_default="New Chat", nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("conversations_user_id_idx", "user_id"),
    )


class Query(Base):
    __tablename__ = "queries"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    conv_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    query_type = Column(String(20), nullable=True)
    input_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("queries_conv_id_idx", "conv_id"),
    )
